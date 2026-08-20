from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections, transaction
from django.utils import timezone

from mnemex.accounts.models import PrivilegedRoleAssignment
from mnemex.legacy_migration.jobs import (
    _GracefulStop,
    authorize_apply_job_source_read,
    claim_next_apply_job,
    enqueue_apply_job,
    execute_apply_job,
    heartbeat_apply_job,
    settle_apply_job_failure,
)
from mnemex.legacy_migration.models import (
    LegacyMigrationCheckpoint,
    LegacyMigrationJob,
    LegacyMigrationRun,
)
from mnemex.legacy_migration.services import (
    ApplyClaimLost,
    approve_migration,
    withdraw_migration,
)
from mnemex.results.models import IngestionRun, PublishedSourceResult
from tests.test_legacy_migration_apply import _roles

pytestmark = pytest.mark.django_db


def _approved_run() -> tuple[LegacyMigrationRun, bytes]:
    _, _, reviewer, run, content = _roles()
    approve_migration(
        actor=reviewer,
        run=run,
        manifest_digest=run.dry_run_manifest_digest,
        rationale="Synthetic worker approval.",
    )
    run.refresh_from_db()
    return run, content


def _enqueue(run: LegacyMigrationRun, *, chunk_size: int = 2) -> LegacyMigrationJob:
    return enqueue_apply_job(
        actor=run.created_by,
        run=run,
        approved_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=chunk_size,
        request_rationale="Synthetic manager request.",
    )


def test_enqueue_is_idempotent_and_freezes_requested_execution_manifest() -> None:
    run, _ = _approved_run()

    first = _enqueue(run)
    second = _enqueue(run)

    run.refresh_from_db()
    assert first.pk == second.pk
    assert run.state == LegacyMigrationRun.State.APPROVED
    assert first.status == LegacyMigrationJob.Status.PENDING
    assert first.requested_manifest_digest == run.dry_run_manifest_digest
    assert first.chunk_size == 2
    assert first.max_attempts == 5
    assert first.attempt_count == first.claim_generation == 0
    assert first.claim_token == first.claim_owner == ""
    first.requested_manifest_digest = "f" * 64
    with pytest.raises(PermissionDenied, match="provenance is immutable"):
        first.save(update_fields=["requested_manifest_digest", "updated_at"])
    with pytest.raises(PermissionDenied, match="transitions are service-owned"):
        LegacyMigrationJob.objects.filter(pk=first.pk).update(status="running")


def test_job_shape_and_transition_validation_rejects_invalid_direct_claim_state() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    job.status = LegacyMigrationJob.Status.RUNNING

    with pytest.raises(ValidationError, match="running job"):
        job.save(update_fields=["status", "updated_at"])


def test_database_constraint_rejects_running_job_without_complete_claim_shape() -> None:
    run, _ = _approved_run()
    invalid = LegacyMigrationJob(
        organization=run.organization,
        run=run,
        job_kind=LegacyMigrationJob.Kind.APPLY,
        job_sequence=1,
        requested_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=2,
        status=LegacyMigrationJob.Status.RUNNING,
        attempt_count=1,
        claim_generation=1,
        created_by=run.created_by,
    )

    with pytest.raises(PermissionDenied, match="service-owned"):
        LegacyMigrationJob.objects.bulk_create([invalid])


def test_claim_heartbeat_and_expired_takeover_are_token_and_generation_fenced() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()

    first = claim_next_apply_job(owner="worker-a", now=now, lease_duration=timedelta(minutes=5))
    assert first is not None
    job.refresh_from_db()
    run.refresh_from_db()
    assert first.job_id == job.pk
    assert job.status == LegacyMigrationJob.Status.RUNNING
    assert (job.attempt_count, job.claim_generation) == (1, 1)
    assert run.state == LegacyMigrationRun.State.APPLYING
    original_expiry = job.lease_expires_at

    heartbeat_apply_job(
        first,
        now=now + timedelta(minutes=1),
        lease_duration=timedelta(seconds=30),
    )
    job.refresh_from_db()
    assert job.lease_expires_at == original_expiry
    with pytest.raises(PermissionDenied, match="claim"):
        heartbeat_apply_job(replace(first, token="0" * 64), now=now + timedelta(minutes=2))
    with pytest.raises(PermissionDenied, match="expired"):
        heartbeat_apply_job(first, now=original_expiry)

    second = claim_next_apply_job(owner="worker-b", now=original_expiry)
    assert second is not None
    job.refresh_from_db()
    assert second.job_id == first.job_id
    assert second.token != first.token
    assert second.generation == first.generation + 1
    assert (job.attempt_count, job.claim_generation) == (2, 2)


def test_wrong_token_is_rejected_before_source_or_checkpoint_writes() -> None:
    run, content = _approved_run()
    _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None

    with pytest.raises(PermissionDenied, match="claim"):
        execute_apply_job(replace(claim, token="f" * 64), workbook_content=content)

    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()
    assert not IngestionRun.objects.filter(legacy_migration_checkpoint__run=run).exists()


def test_execution_uses_fresh_clock_and_cannot_settle_after_expiry() -> None:
    run, content = _approved_run()
    _enqueue(run)
    started_at = timezone.now()
    claim = claim_next_apply_job(
        owner="worker-a",
        now=started_at,
        lease_duration=timedelta(seconds=1),
    )
    assert claim is not None
    moments = iter((started_at, started_at + timedelta(seconds=1)))

    with pytest.raises(PermissionDenied, match="expired"):
        execute_apply_job(
            claim,
            workbook_content=content,
            should_stop=lambda: True,
            clock=lambda: next(moments),
        )

    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()


def test_transient_backoff_is_due_bounded_and_exhausts_at_max_attempts() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()
    expected_delays = (30, 60, 120, 240)

    for attempt, expected_delay in enumerate(expected_delays, start=1):
        claim = claim_next_apply_job(owner=f"worker-{attempt}", now=now)
        assert claim is not None
        outcome = settle_apply_job_failure(claim, OSError("private detail"), now=now)
        assert outcome.status == LegacyMigrationJob.Status.RETRY_WAIT
        job.refresh_from_db()
        assert job.last_error_code == "storage_unavailable"
        assert job.last_error_message == "temporary worker failure; retry is scheduled"
        assert job.available_at == now + timedelta(seconds=expected_delay)
        assert (
            claim_next_apply_job(
                owner="too-early", now=job.available_at - timedelta(microseconds=1)
            )
            is None
        )
        now = job.available_at

    final_claim = claim_next_apply_job(owner="worker-5", now=now)
    assert final_claim is not None
    final = settle_apply_job_failure(final_claim, OSError("still private"), now=now)
    job.refresh_from_db()
    assert final.status == LegacyMigrationJob.Status.FAILED
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert job.attempt_count == job.max_attempts == 5
    assert job.claim_token == job.claim_owner == ""


def test_expired_final_crash_is_terminalized_instead_of_left_running_forever() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()

    for attempt in range(1, 6):
        claim = claim_next_apply_job(
            owner=f"worker-{attempt}",
            now=now,
            lease_duration=timedelta(seconds=1),
        )
        assert claim is not None
        job.refresh_from_db()
        assert job.lease_expires_at is not None
        now = job.lease_expires_at

    assert claim_next_apply_job(owner="worker-6", now=now) is None
    job.refresh_from_db()
    run.refresh_from_db()
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "attempts_exhausted"
    assert run.state == LegacyMigrationRun.State.FAILED


def test_graceful_stop_is_observed_between_chunks_and_retries_immediately() -> None:
    run, content = _approved_run()
    job = _enqueue(run)
    now = timezone.now()
    claim = claim_next_apply_job(owner="worker-a", now=now)
    assert claim is not None

    outcome = execute_apply_job(
        claim,
        workbook_content=content,
        should_stop=lambda: True,
        clock=lambda: now,
    )

    job.refresh_from_db()
    assert outcome.status == LegacyMigrationJob.Status.RETRY_WAIT
    assert job.last_error_code == "graceful_shutdown"
    assert job.available_at == now
    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()


def test_resume_repairs_stale_cursor_from_verified_committed_checkpoints() -> None:
    run, content = _approved_run()
    job = _enqueue(run)
    now = timezone.now()
    first = claim_next_apply_job(owner="worker-a", now=now)
    assert first is not None

    first_outcome = execute_apply_job(
        first,
        workbook_content=content,
        clock=lambda: now,
        fail_after_committed_chunks=1,
    )
    assert first_outcome.status == LegacyMigrationJob.Status.RETRY_WAIT
    assert LegacyMigrationCheckpoint.objects.filter(run=run, status="committed").count() == 1
    assert PublishedSourceResult.objects.filter(organization=run.organization).count() == 2

    job.refresh_from_db()
    job.next_checkpoint_sequence = 99
    job.save(update_fields=["next_checkpoint_sequence", "updated_at"])
    second = claim_next_apply_job(owner="worker-b", now=job.available_at)
    assert second is not None
    completed = execute_apply_job(
        second,
        workbook_content=content,
        clock=lambda: job.available_at,
    )

    job.refresh_from_db()
    run.refresh_from_db()
    assert completed.status == LegacyMigrationJob.Status.COMPLETED
    assert job.next_checkpoint_sequence == 4
    assert run.state == LegacyMigrationRun.State.COMPLETED
    assert LegacyMigrationCheckpoint.objects.filter(run=run).count() == 3
    assert PublishedSourceResult.objects.filter(organization=run.organization).count() == 5


def test_execution_rechecks_creator_authority_and_terminally_fails_without_writes() -> None:
    run, content = _approved_run()
    job = _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None
    PrivilegedRoleAssignment.objects.filter(
        account=run.created_by,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    ).delete()

    outcome = execute_apply_job(claim, workbook_content=content)

    job.refresh_from_db()
    assert outcome.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "authorization_denied"
    assert job.last_error_message == "job authorization is no longer valid"
    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()


def test_execution_rechecks_exact_source_and_terminally_fails_provenance_drift() -> None:
    run, content = _approved_run()
    job = _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None

    outcome = execute_apply_job(claim, workbook_content=content + b"synthetic-tamper")

    job.refresh_from_db()
    assert outcome.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "provenance_validation_failed"
    assert job.last_error_message == "job provenance validation failed"
    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()


def test_withdrawal_clears_active_claim_and_old_owner_cannot_write() -> None:
    run, content = _approved_run()
    reviewer = run.decision_revisions.get(sequence=1).actor
    job = _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None

    withdraw_migration(
        actor=reviewer,
        run=run,
        manifest_digest=run.dry_run_manifest_digest,
        rationale="Synthetic authorization withdrawn.",
    )

    job.refresh_from_db()
    assert job.status == LegacyMigrationJob.Status.CANCELLED
    assert job.claim_token == job.claim_owner == ""
    assert job.heartbeat_at is None
    assert job.lease_expires_at is None
    with pytest.raises(PermissionDenied, match="claim"):
        execute_apply_job(claim, workbook_content=content)
    assert not LegacyMigrationCheckpoint.objects.filter(run=run).exists()


@pytest.mark.django_db(transaction=True)
def test_postgresql_competing_claimers_claim_a_job_once() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock coverage")
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()

    def claim(owner: str):
        connections.close_all()
        return claim_next_apply_job(owner=owner, now=now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].job_id == job.pk


@pytest.mark.django_db(transaction=True)
def test_postgresql_claim_scan_does_not_starve_a_later_tenant() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL SKIP LOCKED fairness coverage")
    busy_run, _ = _approved_run()
    busy_run.organization.name = "Synthetic U3 Organization busy"
    busy_run.organization.save(update_fields=["name"])
    ready_run, _ = _approved_run()
    available_at = timezone.now()
    for sequence in range(1, 102):
        LegacyMigrationJob.objects.create(
            organization=busy_run.organization,
            run=busy_run,
            job_kind=LegacyMigrationJob.Kind.APPLY,
            job_sequence=sequence,
            requested_manifest_digest=f"{sequence:064x}",
            request_rationale="Synthetic busy-tenant fairness request.",
            chunk_size=2,
            available_at=available_at - timedelta(minutes=1),
            created_by=busy_run.created_by,
        )
    ready_job = _enqueue(ready_run)
    now = timezone.now()
    locked = Event()
    release = Event()

    def hold_busy_organization_lock() -> None:
        connections.close_all()
        with transaction.atomic():
            busy_run.organization.__class__.objects.select_for_update().get(
                pk=busy_run.organization_id
            )
            locked.set()
            release.wait(timeout=10)
        connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_busy_organization_lock)
        assert locked.wait(timeout=10)
        try:
            claim = claim_next_apply_job(owner="fair-worker", now=now)
        finally:
            release.set()
            future.result(timeout=10)

    assert claim is not None
    assert claim.job_id == ready_job.pk


@pytest.mark.django_db(transaction=True)
def test_postgresql_claim_ready_time_prefers_older_pending_tenant() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL claim-ready fairness coverage")
    now = timezone.now()
    pending_run, _ = _approved_run()
    pending_run.organization.name = "Synthetic oldest-pending tenant"
    pending_run.organization.save(update_fields=["name"])
    pending_job = _enqueue(pending_run)
    LegacyMigrationJob._base_manager.filter(pk=pending_job.pk).update(
        available_at=now - timedelta(hours=2)
    )

    for sequence in range(101):
        expired_run, _ = _approved_run()
        expired_run.organization.name = f"Synthetic recent-expiry tenant {sequence}"
        expired_run.organization.save(update_fields=["name"])
        expired_job = _enqueue(expired_run)
        expired_job.status = LegacyMigrationJob.Status.RUNNING
        expired_job.attempt_count = expired_job.claim_generation = 1
        expired_job.claim_token = f"{sequence + 1:064x}"
        expired_job.claim_owner = f"expired-owner-{sequence}"
        expired_job.heartbeat_at = now - timedelta(minutes=10)
        expired_job.lease_expires_at = now - timedelta(minutes=1)
        expired_job.started_at = now - timedelta(minutes=10)
        expired_job.save(
            update_fields=[
                "status",
                "attempt_count",
                "claim_generation",
                "claim_token",
                "claim_owner",
                "heartbeat_at",
                "lease_expires_at",
                "started_at",
                "updated_at",
            ]
        )

    selected = claim_next_apply_job(owner="oldest-ready-worker", now=now)

    assert selected is not None
    assert selected.job_id == pending_job.pk


def test_job_rejects_invalid_chunk_and_manifest_shape_before_enqueue() -> None:
    run, _ = _approved_run()
    with pytest.raises(ValidationError, match="chunk size"):
        enqueue_apply_job(
            actor=run.created_by,
            run=run,
            approved_manifest_digest=run.dry_run_manifest_digest,
            chunk_size=0,
            request_rationale="Synthetic manager request.",
        )
    with pytest.raises(ValidationError, match="manifest"):
        enqueue_apply_job(
            actor=run.created_by,
            run=run,
            approved_manifest_digest="not-a-digest",
            chunk_size=2,
            request_rationale="Synthetic manager request.",
        )
    with pytest.raises(ValidationError, match="max attempts"):
        enqueue_apply_job(
            actor=run.created_by,
            run=run,
            approved_manifest_digest=run.dry_run_manifest_digest,
            chunk_size=2,
            max_attempts=6,
            request_rationale="Synthetic manager request.",
        )


def test_graceful_reclaims_do_not_consume_failure_budget() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()

    for sequence in range(7):
        claim = claim_next_apply_job(owner=f"worker-{sequence}", now=now)
        assert claim is not None
        outcome = settle_apply_job_failure(claim, _GracefulStop(), now=now)
        assert outcome.status == LegacyMigrationJob.Status.RETRY_WAIT

    job.refresh_from_db()
    assert job.attempt_count == job.claim_generation == 7
    assert job.failure_count == 0
    assert job.status == LegacyMigrationJob.Status.RETRY_WAIT


def test_transient_failures_use_failure_budget_after_clean_reclaims() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    now = timezone.now()
    for sequence in range(6):
        claim = claim_next_apply_job(owner=f"clean-{sequence}", now=now)
        assert claim is not None
        settle_apply_job_failure(claim, _GracefulStop(), now=now)

    for failure in range(1, 6):
        claim = claim_next_apply_job(owner=f"failure-{failure}", now=now)
        assert claim is not None
        outcome = settle_apply_job_failure(claim, OSError("private detail"), now=now)
        job.refresh_from_db()
        assert job.failure_count == failure
        if failure < 5:
            assert outcome.status == LegacyMigrationJob.Status.RETRY_WAIT
            now = job.available_at
        else:
            assert outcome.status == LegacyMigrationJob.Status.FAILED

    assert job.attempt_count == job.claim_generation == 11


def test_terminal_request_recovery_appends_audited_replacement() -> None:
    run, _ = _approved_run()
    first = _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None
    settle_apply_job_failure(claim, ValidationError("synthetic terminal failure"))

    replacement = enqueue_apply_job(
        actor=run.created_by,
        run=run,
        approved_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=2,
        request_rationale="Operator reviewed the terminal failure and requested recovery.",
    )

    first.refresh_from_db()
    assert first.status == LegacyMigrationJob.Status.FAILED
    assert replacement.pk != first.pk
    assert replacement.job_sequence == first.job_sequence + 1
    assert replacement.status == LegacyMigrationJob.Status.PENDING
    assert replacement.request_rationale.startswith("Operator reviewed")
    assert run.jobs.filter(job_kind=LegacyMigrationJob.Kind.APPLY).count() == 2


def test_terminal_replacement_resumes_predecessor_checkpoint_chain() -> None:
    run, content = _approved_run()
    first = _enqueue(run)
    first_claim = claim_next_apply_job(owner="worker-first")
    assert first_claim is not None
    interrupted = execute_apply_job(
        first_claim,
        workbook_content=content,
        fail_after_committed_chunks=1,
    )
    assert interrupted.status == LegacyMigrationJob.Status.RETRY_WAIT
    first.refresh_from_db()
    retry_claim = claim_next_apply_job(owner="worker-terminal", now=first.available_at)
    assert retry_claim is not None
    settle_apply_job_failure(
        retry_claim,
        ValidationError("synthetic terminal review failure"),
        now=first.available_at,
    )
    replacement = enqueue_apply_job(
        actor=run.created_by,
        run=run,
        approved_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=2,
        request_rationale="Operator reviewed the partial failure and requested recovery.",
    )
    replacement_claim = claim_next_apply_job(owner="worker-replacement", now=first.available_at)
    assert replacement_claim is not None

    completed = execute_apply_job(
        replacement_claim,
        workbook_content=content,
        _raise_error=True,
    )

    checkpoints = list(run.checkpoints.order_by("sequence"))
    assert completed.status == LegacyMigrationJob.Status.COMPLETED
    assert checkpoints[0].job_id == first.pk
    assert {checkpoint.job_id for checkpoint in checkpoints[1:]} == {replacement.pk}
    assert PublishedSourceResult.objects.filter(organization=run.organization).count() == 5


def test_claim_reauthorizes_creator_before_private_source_read() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    PrivilegedRoleAssignment.objects.filter(
        account=run.created_by,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    ).delete()

    assert claim_next_apply_job(owner="worker-a") is None
    job.refresh_from_db()
    run.refresh_from_db()
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "authorization_denied"
    assert run.state == LegacyMigrationRun.State.FAILED


def test_source_read_reauthorization_commits_denial_before_raising() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    claim = claim_next_apply_job(owner="worker-a")
    assert claim is not None
    PrivilegedRoleAssignment.objects.filter(
        account=run.created_by,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    ).delete()
    read_called = False

    def read_source(_run: LegacyMigrationRun) -> bytes:
        nonlocal read_called
        read_called = True
        return b"must not be read"

    with pytest.raises(ApplyClaimLost, match="authorization"):
        authorize_apply_job_source_read(claim, read_source=read_source)

    job.refresh_from_db()
    run.refresh_from_db()
    assert read_called is False
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "authorization_denied"
    assert job.claim_token == job.claim_owner == ""
    assert run.state == LegacyMigrationRun.State.FAILED


def test_claim_rejects_inactive_organization_before_returning_token() -> None:
    run, _ = _approved_run()
    job = _enqueue(run)
    run.organization.status = "suspended"
    run.organization.save(update_fields=["status"])

    assert claim_next_apply_job(owner="worker-a") is None
    job.refresh_from_db()
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert job.last_error_code == "organization_inactive"


def test_operational_querysets_reject_bulk_grafts() -> None:
    run, content = _approved_run()
    job = _enqueue(run)
    original_run_id = job.run_id
    original_organization_id = run.organization_id
    other_organization = run.organization.__class__.objects.create(name="Synthetic graft target")
    job.organization = other_organization
    run.organization = other_organization

    with pytest.raises(PermissionDenied, match="service-owned"):
        LegacyMigrationJob.objects.bulk_update([job], ["organization"])
    with pytest.raises(PermissionDenied, match="service-owned"):
        LegacyMigrationJob.objects.bulk_create([job])
    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationRun.objects.bulk_update([run], ["organization"])

    claimed = claim_next_apply_job(owner="checkpoint-worker")
    assert claimed is not None
    execute_apply_job(claimed, workbook_content=content)
    checkpoint = LegacyMigrationCheckpoint.objects.first()
    assert checkpoint is not None
    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationCheckpoint.objects.bulk_update([checkpoint], ["organization"])
    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationCheckpoint.objects.bulk_create([checkpoint])

    job.refresh_from_db()
    run.refresh_from_db()
    assert job.run_id == original_run_id
    assert run.organization_id == original_organization_id
