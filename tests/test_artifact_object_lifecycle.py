from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import override_settings
from django.utils import timezone

from mnemex.accounts.models import Account
from mnemex.partners.models import PartnerOrganization
from mnemex.results import artifact_lifecycle
from mnemex.results.artifact_lifecycle import (
    ArtifactReconciliationOutcome,
    abandon_artifact_write,
    begin_artifact_write,
    complete_artifact_write,
    install_registered_artifact,
    lock_artifact_write,
    reconcile_artifact_objects,
)
from mnemex.results.artifacts import LocalPrivateArtifactStore
from mnemex.results.models import ArtifactObject, ArtifactObjectWrite, SourceArtifact
from mnemex.worker import main as worker_main

pytestmark = pytest.mark.django_db


def _actor(label: str = "artifact-lifecycle") -> Account:
    return Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password=None,
    )


def _artifact(
    *,
    organization: PartnerOrganization,
    actor: Account,
    attempt: ArtifactObjectWrite,
) -> SourceArtifact:
    artifact_object = attempt.artifact_object
    return SourceArtifact.objects.create(
        organization=organization,
        kind=SourceArtifact.Kind.SPREADSHEET,
        digest=artifact_object.digest,
        original_name="synthetic.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=artifact_object.byte_size,
        object_reference=artifact_object.object_reference,
        uploaded_by=actor,
    )


def test_failed_business_transaction_leaves_a_tracked_collectable_object(
    tmp_path: Path,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Rollback Show")
    content = b"synthetic workbook bytes"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="synthetic.xlsx",
        now=now,
    )
    store.put(content=content, filename="synthetic.xlsx")

    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with transaction.atomic():
            raise RuntimeError("synthetic rollback")
    abandon_artifact_write(
        attempt=attempt,
        error_code="business_transaction_rolled_back",
        now=now,
        cleanup_grace=timedelta(0),
    )

    attempt.refresh_from_db()
    assert attempt.status == ArtifactObjectWrite.Status.ABANDONED
    assert (tmp_path / attempt.artifact_object.object_reference).read_bytes() == content

    outcome = reconcile_artifact_objects(store=store, now=now, limit=10)

    attempt.refresh_from_db()
    assert outcome.cleaned == 1
    assert attempt.status == ArtifactObjectWrite.Status.CLEANED
    assert not (tmp_path / attempt.artifact_object.object_reference).exists()


def test_registered_install_failure_is_durably_abandoned(tmp_path: Path) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Failed Install Show")

    class FailingStore(LocalPrivateArtifactStore):
        def put(self, *, content: bytes, filename: str) -> str:
            raise OSError("synthetic object installation failure")

    with pytest.raises(OSError, match="synthetic object installation failure"):
        install_registered_artifact(
            store=FailingStore(tmp_path),
            organization=organization,
            content=b"synthetic failed install",
            filename="failed.xlsx",
            now=timezone.now(),
        )

    attempt = ArtifactObjectWrite.objects.get()
    assert attempt.status == ArtifactObjectWrite.Status.ABANDONED
    assert attempt.error_code == "object_install_failed"


def test_reconciliation_bounds_unresolved_attempts_per_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Attempt Limit Show")
    content = b"synthetic repeatedly failed object"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    monkeypatch.setattr(artifact_lifecycle, "MAX_UNRESOLVED_WRITES_PER_OBJECT", 2)
    for sequence in range(3):
        begin_artifact_write(
            organization=organization,
            content=content,
            filename="repeated.xlsx",
            now=now - timedelta(seconds=sequence + 1),
            write_lease=timedelta(seconds=1),
        )
    store.put(content=content, filename="repeated.xlsx")

    first = reconcile_artifact_objects(store=store, now=now, limit=10)

    assert first.blocked == 1
    assert (
        ArtifactObjectWrite.objects.filter(
            status=ArtifactObjectWrite.Status.BLOCKED,
            error_code="unresolved_write_limit_exceeded",
        ).count()
        == 2
    )
    assert ArtifactObjectWrite.objects.filter(status=ArtifactObjectWrite.Status.ACTIVE).count() == 1

    second = reconcile_artifact_objects(store=store, now=now, limit=10)
    assert second.cleaned == 1
    assert not (tmp_path / ArtifactObject.objects.get().object_reference).exists()


def test_collector_does_not_delete_an_object_owned_by_an_active_concurrent_write(
    tmp_path: Path,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Concurrent Show")
    content = b"shared synthetic workbook"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    abandoned = begin_artifact_write(
        organization=organization,
        content=content,
        filename="shared.xlsx",
        now=now,
    )
    store.put(content=content, filename="shared.xlsx")
    abandon_artifact_write(
        attempt=abandoned,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )
    active = begin_artifact_write(
        organization=organization,
        content=content,
        filename="shared.xlsx",
        now=now,
        write_lease=timedelta(minutes=5),
    )

    outcome = reconcile_artifact_objects(store=store, now=now, limit=10)

    abandoned.refresh_from_db()
    active.refresh_from_db()
    assert outcome.skipped_active == 1
    assert abandoned.status == ArtifactObjectWrite.Status.ABANDONED
    assert active.status == ArtifactObjectWrite.Status.ACTIVE
    assert (tmp_path / active.artifact_object.object_reference).read_bytes() == content


def test_link_and_source_artifact_commit_are_atomic_and_preserve_shared_bytes(
    tmp_path: Path,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Linked Show")
    content = b"linked synthetic workbook"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="linked.xlsx",
        now=now,
    )
    store.put(content=content, filename="linked.xlsx")

    with transaction.atomic():
        artifact = _artifact(organization=organization, actor=actor, attempt=attempt)
        complete_artifact_write(attempt=attempt, artifact=artifact, now=now)

    attempt.refresh_from_db()
    assert attempt.status == ArtifactObjectWrite.Status.LINKED
    assert attempt.source_artifact == artifact
    assert reconcile_artifact_objects(store=store, now=now, limit=10).cleaned == 0
    assert (tmp_path / artifact.object_reference).read_bytes() == content


def test_expired_crashed_write_is_reclaimed_without_a_request_cleanup(
    tmp_path: Path,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Crashed Write Show")
    content = b"crashed synthetic workbook"
    started = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="crashed.xlsx",
        now=started,
        write_lease=timedelta(seconds=1),
    )
    store.put(content=content, filename="crashed.xlsx")

    outcome = reconcile_artifact_objects(
        store=store,
        now=started + timedelta(seconds=2),
        limit=10,
    )

    attempt.refresh_from_db()
    assert outcome.cleaned == 1
    assert attempt.status == ArtifactObjectWrite.Status.CLEANED
    assert attempt.error_code == "write_lease_expired"


def test_reconciliation_never_deletes_unexpected_bytes_at_a_digest_address(
    tmp_path: Path,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Tamper Show")
    content = b"expected synthetic workbook"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="tamper.xlsx",
        now=now,
    )
    reference = store.put(content=content, filename="tamper.xlsx")
    (tmp_path / reference).write_bytes(b"unexpected bytes")
    abandon_artifact_write(
        attempt=attempt,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )

    outcome = reconcile_artifact_objects(store=store, now=now, limit=10)

    attempt.refresh_from_db()
    assert outcome.blocked == 1
    assert attempt.status == ArtifactObjectWrite.Status.BLOCKED
    assert attempt.error_code == "object_digest_mismatch"
    assert (tmp_path / reference).read_bytes() == b"unexpected bytes"


def test_artifact_registry_provenance_is_immutable_and_linking_is_tenant_bound() -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Owner Show")
    other = PartnerOrganization.objects.create(name="Synthetic Other Show")
    attempt = begin_artifact_write(
        organization=organization,
        content=b"tenant-bound synthetic workbook",
        filename="tenant.xlsx",
        now=timezone.now(),
    )
    wrong_artifact = _artifact(organization=other, actor=actor, attempt=attempt)

    with pytest.raises(ValidationError, match="organization"):
        complete_artifact_write(
            attempt=attempt,
            artifact=wrong_artifact,
            now=timezone.now(),
        )
    with pytest.raises(PermissionDenied, match="immutable"):
        ArtifactObject.objects.filter(pk=attempt.artifact_object_id).update(byte_size=1)


def test_artifact_write_terminal_state_cannot_be_created_reopened_or_bulk_inserted(
    tmp_path: Path,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Immutable Write Show")
    now = timezone.now()
    attempt = begin_artifact_write(
        organization=organization,
        content=b"synthetic immutable write",
        filename="immutable.xlsx",
        now=now,
    )

    with pytest.raises(PermissionDenied, match="begin in the active state"):
        ArtifactObjectWrite.objects.create(
            organization=organization,
            artifact_object=attempt.artifact_object,
            status=ArtifactObjectWrite.Status.BLOCKED,
            reconcile_after=now,
            error_code="synthetic_direct_terminal",
            resolved_at=now,
        )
    with pytest.raises(PermissionDenied, match="lifecycle service"):
        ArtifactObjectWrite.objects.bulk_create(
            [
                ArtifactObjectWrite(
                    organization=organization,
                    artifact_object=attempt.artifact_object,
                    reconcile_after=now + timedelta(minutes=1),
                )
            ]
        )

    abandon_artifact_write(
        attempt=attempt,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )
    attempt.refresh_from_db()
    attempt.status = ArtifactObjectWrite.Status.BLOCKED
    attempt.error_code = "synthetic_rewrite"
    with pytest.raises(PermissionDenied, match="lifecycle service"):
        attempt.save()

    reconcile_artifact_objects(store=LocalPrivateArtifactStore(tmp_path), now=now, limit=10)
    attempt.refresh_from_db()
    assert attempt.status == ArtifactObjectWrite.Status.CLEANED
    attempt.status = ArtifactObjectWrite.Status.ACTIVE
    attempt.error_code = ""
    attempt.resolved_at = None
    with pytest.raises(PermissionDenied, match="terminal"):
        attempt.save(_lifecycle_transition=True)


def test_worker_can_reconcile_one_bounded_batch_of_expired_artifact_writes(
    tmp_path: Path,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Worker Reconcile Show")
    content = b"worker-reconciled synthetic workbook"
    started = timezone.now() - timedelta(minutes=1)
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="worker.xlsx",
        now=started,
        write_lease=timedelta(seconds=1),
    )
    store.put(content=content, filename="worker.xlsx")

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        assert worker_main(["--reconcile-artifacts-once", "--limit", "10"]) == 0

    attempt.refresh_from_db()
    assert attempt.status == ArtifactObjectWrite.Status.CLEANED
    assert not (tmp_path / attempt.artifact_object.object_reference).exists()


def test_worker_keeps_signaling_persisted_blocked_recovery_evidence(tmp_path: Path) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Blocked Worker Show")
    content = b"synthetic expected worker bytes"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="blocked-worker.xlsx",
        now=now,
    )
    reference = store.put(content=content, filename="blocked-worker.xlsx")
    (tmp_path / reference).write_bytes(b"synthetic unexpected worker bytes")
    abandon_artifact_write(
        attempt=attempt,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        assert worker_main(["--reconcile-artifacts-once", "--limit", "10"]) == 1
        assert worker_main(["--reconcile-artifacts-once", "--limit", "10"]) == 1

    attempt.refresh_from_db()
    assert attempt.status == ArtifactObjectWrite.Status.BLOCKED


@pytest.mark.django_db(transaction=True)
def test_postgresql_registry_lock_serializes_cleanup_against_a_new_shared_write(
    tmp_path: Path,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row-lock behavior")

    organization = PartnerOrganization.objects.create(name="Synthetic Registry Lock Show")
    content = b"registry-locked synthetic workbook"
    now = timezone.now()
    ordinary_store = LocalPrivateArtifactStore(tmp_path)
    abandoned = begin_artifact_write(
        organization=organization,
        content=content,
        filename="locked.xlsx",
        now=now,
    )
    ordinary_store.put(content=content, filename="locked.xlsx")
    abandon_artifact_write(
        attempt=abandoned,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )

    read_entered = Event()
    allow_cleanup = Event()
    upload_started = Event()

    class BlockingReadStore(LocalPrivateArtifactStore):
        def read(self, *, reference: str) -> bytes:
            read_entered.set()
            if not allow_cleanup.wait(timeout=5):
                raise RuntimeError("synthetic cleanup barrier timed out")
            return super().read(reference=reference)

    def collect() -> ArtifactReconciliationOutcome:
        close_old_connections()
        try:
            return reconcile_artifact_objects(
                store=BlockingReadStore(tmp_path),
                now=now,
                limit=10,
            )
        finally:
            connection.close()

    def upload_again() -> object:
        close_old_connections()
        try:
            upload_started.set()
            current_organization = PartnerOrganization.objects.get(pk=organization.pk)
            attempt = begin_artifact_write(
                organization=current_organization,
                content=content,
                filename="locked.xlsx",
                now=now,
            )
            ordinary_store.put(content=content, filename="locked.xlsx")
            return attempt.pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        collector = pool.submit(collect)
        assert read_entered.wait(timeout=5)
        uploader = pool.submit(upload_again)
        assert upload_started.wait(timeout=5)
        with pytest.raises(FutureTimeoutError):
            uploader.result(timeout=0.2)
        allow_cleanup.set()
        outcome = collector.result(timeout=10)
        new_write_id = uploader.result(timeout=10)

    assert outcome.cleaned == 1
    new_write = ArtifactObjectWrite.objects.get(pk=new_write_id)
    assert new_write.status == ArtifactObjectWrite.Status.ACTIVE
    assert (tmp_path / new_write.artifact_object.object_reference).read_bytes() == content


@pytest.mark.django_db(transaction=True)
def test_postgresql_install_lock_prevents_cleanup_before_bytes_are_registered(
    tmp_path: Path,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row-lock behavior")

    organization = PartnerOrganization.objects.create(name="Synthetic Install Lock Show")
    content = b"synthetic install-locked workbook"
    started = timezone.now()
    installed = Event()
    allow_install_to_finish = Event()

    class InstalledThenBlockingStore(LocalPrivateArtifactStore):
        def put(self, *, content: bytes, filename: str) -> str:
            reference = super().put(content=content, filename=filename)
            installed.set()
            if not allow_install_to_finish.wait(timeout=5):
                raise RuntimeError("synthetic install barrier timed out")
            return reference

    def upload() -> object:
        close_old_connections()
        try:
            current_organization = PartnerOrganization.objects.get(pk=organization.pk)
            attempt = install_registered_artifact(
                store=InstalledThenBlockingStore(tmp_path),
                organization=current_organization,
                content=content,
                filename="install-locked.xlsx",
                now=started,
                write_lease=timedelta(minutes=5),
            )
            return attempt.pk
        finally:
            connection.close()

    def collect() -> ArtifactReconciliationOutcome:
        close_old_connections()
        try:
            return reconcile_artifact_objects(
                store=LocalPrivateArtifactStore(tmp_path),
                now=started + timedelta(hours=1),
                limit=10,
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        uploader = pool.submit(upload)
        assert installed.wait(timeout=5)
        collector = pool.submit(collect)
        with pytest.raises(FutureTimeoutError):
            collector.result(timeout=0.2)
        visible_attempt = ArtifactObjectWrite.objects.get()
        assert visible_attempt.status == ArtifactObjectWrite.Status.ACTIVE
        assert (tmp_path / visible_attempt.artifact_object.object_reference).read_bytes() == content
        allow_install_to_finish.set()
        write_id = uploader.result(timeout=10)
        outcome = collector.result(timeout=10)

    write = ArtifactObjectWrite.objects.get(pk=write_id)
    assert outcome.cleaned == 1
    assert write.status == ArtifactObjectWrite.Status.CLEANED
    assert not (tmp_path / write.artifact_object.object_reference).exists()


@pytest.mark.django_db(transaction=True)
def test_postgresql_provenance_transaction_locks_registry_before_insert(
    tmp_path: Path,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row-lock behavior")

    organization = PartnerOrganization.objects.create(name="Synthetic Provenance Lock Show")
    actor = _actor("provenance-lock")
    content = b"synthetic provenance-locked workbook"
    started = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    attempt = install_registered_artifact(
        store=store,
        organization=organization,
        content=content,
        filename="provenance-locked.xlsx",
        now=started,
        write_lease=timedelta(minutes=5),
    )
    provenance_inserted = Event()
    allow_commit = Event()

    def publish() -> object:
        close_old_connections()
        try:
            with transaction.atomic():
                current = lock_artifact_write(ArtifactObjectWrite.objects.get(pk=attempt.pk))
                artifact = _artifact(
                    organization=PartnerOrganization.objects.get(pk=organization.pk),
                    actor=Account.objects.get(pk=actor.pk),
                    attempt=current,
                )
                provenance_inserted.set()
                if not allow_commit.wait(timeout=5):
                    raise RuntimeError("synthetic provenance barrier timed out")
                complete_artifact_write(attempt=current, artifact=artifact, now=started)
                return artifact.pk
        finally:
            connection.close()

    def collect() -> ArtifactReconciliationOutcome:
        close_old_connections()
        try:
            return reconcile_artifact_objects(
                store=LocalPrivateArtifactStore(tmp_path),
                now=started + timedelta(hours=1),
                limit=10,
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        publisher = pool.submit(publish)
        assert provenance_inserted.wait(timeout=5)
        collector = pool.submit(collect)
        with pytest.raises(FutureTimeoutError):
            collector.result(timeout=0.2)
        allow_commit.set()
        artifact_id = publisher.result(timeout=10)
        outcome = collector.result(timeout=10)

    write = ArtifactObjectWrite.objects.get(pk=attempt.pk)
    assert SourceArtifact.objects.filter(pk=artifact_id).exists()
    assert write.status == ArtifactObjectWrite.Status.LINKED
    assert outcome.preserved == 1
    assert (tmp_path / write.artifact_object.object_reference).read_bytes() == content


def test_reconciliation_links_each_shared_object_attempt_to_its_tenant_provenance(
    tmp_path: Path,
) -> None:
    first_organization = PartnerOrganization.objects.create(name="Synthetic Shared First")
    second_organization = PartnerOrganization.objects.create(name="Synthetic Shared Second")
    actor = _actor("shared-tenant-provenance")
    content = b"same workbook shared across two tenants"
    now = timezone.now()
    store = LocalPrivateArtifactStore(tmp_path)
    first_attempt = begin_artifact_write(
        organization=first_organization,
        content=content,
        filename="shared.xlsx",
        now=now,
    )
    second_attempt = begin_artifact_write(
        organization=second_organization,
        content=content,
        filename="shared.xlsx",
        now=now,
    )
    store.put(content=content, filename="shared.xlsx")
    first_artifact = _artifact(
        organization=first_organization,
        actor=actor,
        attempt=first_attempt,
    )
    second_artifact = _artifact(
        organization=second_organization,
        actor=actor,
        attempt=second_attempt,
    )
    abandon_artifact_write(
        attempt=first_attempt,
        error_code="synthetic_interruption",
        now=now,
        cleanup_grace=timedelta(0),
    )
    abandon_artifact_write(
        attempt=second_attempt,
        error_code="synthetic_interruption",
        now=now,
        cleanup_grace=timedelta(0),
    )

    outcome = reconcile_artifact_objects(store=store, now=now, limit=10)

    first_attempt.refresh_from_db()
    second_attempt.refresh_from_db()
    assert outcome.preserved == 1
    assert first_attempt.status == ArtifactObjectWrite.Status.LINKED
    assert first_attempt.source_artifact_id == first_artifact.pk
    assert second_attempt.status == ArtifactObjectWrite.Status.LINKED
    assert second_attempt.source_artifact_id == second_artifact.pk
