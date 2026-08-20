from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from mnemex.accounts.models import PrivilegedRoleAssignment
from mnemex.legacy_migration.jobs import (
    claim_next_apply_job,
    enqueue_apply_job,
    execute_apply_job,
    settle_apply_job_failure,
)
from mnemex.legacy_migration.models import LegacyMigrationJob, LegacyMigrationRun
from mnemex.legacy_migration.private_workbooks import read_private_workbook
from mnemex.legacy_migration.services import (
    ApplyClaimLost,
    approve_migration,
    withdraw_migration,
)
from mnemex.legacy_migration.worker_jobs import (
    MigrationWorkerBatchOutcome,
    run_apply_jobs_once,
)
from mnemex.partners.models import PartnerOrganization
from mnemex.results.artifacts import ArtifactCollisionError
from mnemex.results.models import PublishedSourceResult
from mnemex.worker import main as worker_main
from tests.mfa_helpers import force_login_with_fresh_mfa
from tests.test_legacy_migration_portal import (
    _account,
    _configuration,
    _xlsx,
)

pytestmark = pytest.mark.django_db


def _approved_private_run(
    artifact_root: Path, *, label: str
) -> tuple[LegacyMigrationRun, Client, bytes]:
    organization = PartnerOrganization.objects.create(name=f"{label} Show")
    manager = _account(
        organization,
        label=f"{label}-manager",
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    )
    reviewer = _account(
        organization,
        label=f"{label}-reviewer",
        role=PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    )
    client = Client()
    force_login_with_fresh_mfa(client, manager)
    content = _xlsx()
    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=artifact_root):
        uploaded = client.post(
            reverse("legacy_migration:upload"),
            {
                "organization": str(organization.pk),
                "source_key": f"{label}-synthetic-source",
                "data_rights_reference": "synthetic-test-authorization",
                "spreadsheet": SimpleUploadedFile(
                    f"{label}-synthetic.xlsx",
                    content,
                    content_type=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                ),
            },
        )
        assert uploaded.status_code == 302
        run = LegacyMigrationRun.objects.get(organization=organization)
        configured = client.post(
            reverse("legacy_migration:configure", args=[run.pk]),
            {"configuration": _configuration()},
        )
        previewed = client.post(reverse("legacy_migration:dry-run", args=[run.pk]))
    assert configured.status_code == 302
    assert previewed.status_code == 302
    run.refresh_from_db()
    approve_migration(
        actor=reviewer,
        run=run,
        manifest_digest=run.dry_run_manifest_digest,
        rationale="Synthetic worker approval.",
    )
    run.refresh_from_db()
    return run, client, content


def _enqueue(run: LegacyMigrationRun) -> LegacyMigrationJob:
    return enqueue_apply_job(
        actor=run.created_by,
        run=run,
        approved_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=2,
        request_rationale="Synthetic manager request.",
    )


def test_apply_portal_only_enqueues_idempotently_without_reading_storage(
    tmp_path: Path,
) -> None:
    run, client, _ = _approved_private_run(tmp_path, label="enqueue")
    payload = {
        "manifest_digest": run.dry_run_manifest_digest,
        "rationale": "Synthetic manager request.",
    }

    with patch(
        "mnemex.legacy_migration.views.read_private_workbook",
        side_effect=AssertionError("apply view must not read private storage"),
    ):
        first = client.post(reverse("legacy_migration:apply", args=[run.pk]), payload)
        second = client.post(reverse("legacy_migration:apply", args=[run.pk]), payload)

    assert first.status_code == second.status_code == 302
    run.refresh_from_db()
    job = run.jobs.get(job_kind=LegacyMigrationJob.Kind.APPLY)
    assert run.state == LegacyMigrationRun.State.APPROVED
    assert job.status == LegacyMigrationJob.Status.PENDING
    assert job.requested_manifest_digest == run.dry_run_manifest_digest
    assert run.jobs.filter(job_kind=LegacyMigrationJob.Kind.APPLY).count() == 1
    assert PublishedSourceResult.objects.filter(organization=run.organization).count() == 0


def test_private_workbook_reader_verifies_reference_digest_and_size(
    tmp_path: Path,
) -> None:
    run, _, content = _approved_private_run(tmp_path, label="reader")

    assert read_private_workbook(run, artifact_root=tmp_path) == content

    target = tmp_path.joinpath(*run.inventory.artifact.object_reference.split("/"))
    target.write_bytes(b"tampered synthetic bytes")
    with pytest.raises(ValidationError, match="immutable artifact manifest"):
        read_private_workbook(run, artifact_root=tmp_path)


def test_private_workbook_reader_rejects_uncontained_reference(tmp_path: Path) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="containment")
    artifact = run.inventory.artifact
    artifact.object_reference = "../outside.xlsx"

    with pytest.raises(ValidationError, match="reference is invalid"):
        read_private_workbook(run, artifact_root=tmp_path)


def test_private_workbook_reader_treats_hosted_digest_tamper_as_terminal_integrity_failure(
    tmp_path: Path,
) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="hosted-reader-tamper")

    class TamperedHostedStore:
        def read(self, *, reference: str) -> bytes:
            raise ArtifactCollisionError("provider response contained different bytes")

    with (
        override_settings(MNEMEX_PRIVATE_ARTIFACT_BACKEND="supabase"),
        patch(
            "mnemex.legacy_migration.private_workbooks.private_artifact_store_from_settings",
            return_value=TamperedHostedStore(),
        ),
        pytest.raises(ValidationError, match="immutable artifact manifest"),
    ):
        read_private_workbook(run)


def test_one_shot_worker_is_idle_and_claim_bound(tmp_path: Path) -> None:
    idle = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-idle-worker",
        limit=1,
    )
    assert idle.claimed == idle.completed == idle.retry_scheduled == 0

    first, _, _ = _approved_private_run(tmp_path / "first", label="bound-first")
    second, _, _ = _approved_private_run(tmp_path / "second", label="bound-second")
    _enqueue(first)
    _enqueue(second)

    outcome = run_apply_jobs_once(
        artifact_root=tmp_path / "first",
        owner="synthetic-bounded-worker",
        limit=1,
    )

    assert outcome.claimed == 1
    assert LegacyMigrationJob.objects.filter(status=LegacyMigrationJob.Status.PENDING).count() == 1


def test_one_shot_worker_executes_verified_private_artifact(tmp_path: Path) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="success")
    job = _enqueue(run)

    outcome = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-success-worker",
        limit=1,
    )

    job.refresh_from_db()
    run.refresh_from_db()
    assert outcome == replace(outcome, claimed=1, completed=1)
    assert outcome.retry_scheduled == outcome.terminal_failed == 0
    assert job.status == LegacyMigrationJob.Status.COMPLETED
    assert run.state == LegacyMigrationRun.State.COMPLETED
    assert PublishedSourceResult.objects.filter(organization=run.organization).count() == 1


def test_storage_failure_schedules_retry_without_leaking_detail(tmp_path: Path) -> None:
    run, _, _ = _approved_private_run(tmp_path / "stored", label="storage")
    job = _enqueue(run)

    outcome = run_apply_jobs_once(
        artifact_root=tmp_path / "missing",
        owner="synthetic-storage-worker",
        limit=1,
    )

    job.refresh_from_db()
    assert outcome.claimed == outcome.retry_scheduled == 1
    assert outcome.terminal_failed == 0
    assert job.status == LegacyMigrationJob.Status.RETRY_WAIT
    assert job.last_error_code == "storage_unavailable"
    assert "missing" not in job.last_error_message.lower()


def test_worker_catches_claim_loss_during_storage_failure_settlement(tmp_path: Path) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="settle-claim-lost")
    job = _enqueue(run)

    with (
        patch(
            "mnemex.legacy_migration.worker_jobs.read_private_workbook",
            side_effect=OSError("private path"),
        ),
        patch(
            "mnemex.legacy_migration.worker_jobs.settle_apply_job_failure",
            side_effect=ApplyClaimLost("superseded"),
        ),
    ):
        outcome = run_apply_jobs_once(
            artifact_root=tmp_path,
            owner="synthetic-settle-claim-lost",
            limit=1,
        )

    job.refresh_from_db()
    assert outcome.claimed == outcome.claim_lost == 1
    assert outcome.completed == outcome.retry_scheduled == outcome.terminal_failed == 0
    assert job.status == LegacyMigrationJob.Status.RUNNING


def test_worker_counts_cancelled_when_withdrawn_between_read_and_execute(tmp_path: Path) -> None:
    run, _, content = _approved_private_run(tmp_path, label="withdraw-claim-lost")
    job = _enqueue(run)
    reviewer = run.decision_revisions.get(sequence=1).actor

    def withdraw_then_return(*_args: object, **_kwargs: object) -> bytes:
        withdraw_migration(
            actor=reviewer,
            run=run,
            manifest_digest=run.dry_run_manifest_digest,
            rationale="Synthetic withdrawal during worker read.",
        )
        return content

    with patch(
        "mnemex.legacy_migration.worker_jobs.read_private_workbook",
        side_effect=withdraw_then_return,
    ):
        outcome = run_apply_jobs_once(
            artifact_root=tmp_path,
            owner="synthetic-withdraw-worker",
            limit=1,
        )

    job.refresh_from_db()
    assert outcome.claimed == outcome.claim_lost == outcome.cancelled == 1
    assert job.status == LegacyMigrationJob.Status.CANCELLED


def test_integrity_failure_is_terminal_and_sticky_for_exit_status(
    tmp_path: Path,
) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="integrity")
    job = _enqueue(run)
    target = tmp_path.joinpath(*run.inventory.artifact.object_reference.split("/"))
    target.write_bytes(b"private competitor and contact details")

    outcome = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-integrity-worker",
        limit=1,
    )
    idle_after_failure = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-followup-worker",
        limit=1,
    )

    job.refresh_from_db()
    assert outcome.terminal_failed == 1
    assert outcome.unresolved_failed == 1
    assert idle_after_failure.claimed == 0
    assert idle_after_failure.unresolved_failed == 1
    assert job.status == LegacyMigrationJob.Status.FAILED
    assert "competitor" not in job.last_error_message.lower()


def test_successful_replacement_clears_historical_failure_signal(tmp_path: Path) -> None:
    run, _, content = _approved_private_run(tmp_path, label="resolved-failure")
    first = _enqueue(run)
    claim = claim_next_apply_job(owner="synthetic-first-failure")
    assert claim is not None
    settle_apply_job_failure(claim, ValidationError("synthetic terminal failure"))
    replacement = enqueue_apply_job(
        actor=run.created_by,
        run=run,
        approved_manifest_digest=run.dry_run_manifest_digest,
        chunk_size=2,
        request_rationale="Operator reviewed the failure and requested a replacement.",
    )

    replacement_claim = claim_next_apply_job(owner="synthetic-replacement-worker")
    assert replacement_claim is not None
    outcome = execute_apply_job(
        replacement_claim,
        workbook_content=content,
        _raise_error=True,
    )
    idle = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-post-recovery-worker",
        limit=1,
    )

    first.refresh_from_db()
    replacement.refresh_from_db()
    assert first.status == LegacyMigrationJob.Status.FAILED
    assert replacement.status == LegacyMigrationJob.Status.COMPLETED
    assert outcome.status == LegacyMigrationJob.Status.COMPLETED
    assert idle.claimed == idle.unresolved_failed == 0


def test_worker_stop_seam_stops_before_claim_and_between_chunks(tmp_path: Path) -> None:
    run, _, _ = _approved_private_run(tmp_path, label="stop")
    job = _enqueue(run)

    stopped = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-stop-worker",
        limit=1,
        should_stop=lambda: True,
    )
    job.refresh_from_db()
    assert stopped.claimed == 0
    assert job.status == LegacyMigrationJob.Status.PENDING

    calls = 0

    def stop_between_chunks() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    interrupted = run_apply_jobs_once(
        artifact_root=tmp_path,
        owner="synthetic-stop-worker",
        limit=1,
        should_stop=stop_between_chunks,
    )
    job.refresh_from_db()
    assert interrupted.claimed == interrupted.retry_scheduled == 1
    assert job.status == LegacyMigrationJob.Status.RETRY_WAIT
    assert job.last_error_code == "graceful_shutdown"


def test_worker_cli_uses_safe_bounded_output_and_sticky_failure_exit(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    safe_outcome = MigrationWorkerBatchOutcome(
        claimed=1,
        completed=0,
        retry_scheduled=1,
        terminal_failed=0,
        cancelled=0,
        unresolved_failed=0,
    )
    with (
        override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path),
        patch(
            "mnemex.legacy_migration.worker_jobs.run_apply_jobs_once",
            return_value=safe_outcome,
        ) as run_once,
    ):
        assert worker_main(["--run-migration-jobs-once", "--job-limit", "3"]) == 0
    run_once.assert_called_once()
    output = capsys.readouterr().out
    assert "claimed=1" in output
    assert "retry_scheduled=1" in output
    assert "claim_token" not in output
    assert "object_reference" not in output
    assert "competitor" not in output

    failed_outcome = replace(safe_outcome, retry_scheduled=0, unresolved_failed=1)
    with (
        override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path),
        patch(
            "mnemex.legacy_migration.worker_jobs.run_apply_jobs_once",
            return_value=failed_outcome,
        ),
    ):
        assert worker_main(["--run-migration-jobs-once"]) == 1


@pytest.mark.parametrize("limit", ["0", "26", "not-a-number"])
def test_worker_cli_rejects_invalid_job_limit(limit: str) -> None:
    with pytest.raises(SystemExit) as error:
        worker_main(["--run-migration-jobs-once", "--job-limit", limit])
    assert error.value.code == 2


def test_job_rendering_is_tenant_scoped_and_privacy_safe(tmp_path: Path) -> None:
    run, client, _ = _approved_private_run(tmp_path, label="render")
    job = _enqueue(run)
    claim = claim_next_apply_job(owner="private-worker-identity")
    assert claim is not None
    settle_apply_job_failure(
        claim,
        OSError("raw private path and Synthetic Person One"),
    )

    response = client.get(reverse("legacy_migration:run-detail", args=[run.pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Retry scheduled" in body
    assert "Failures 1 of 5" in body
    assert "Claims 1" in body
    assert "Next checkpoint" in body
    assert "private-worker-identity" not in body
    assert "raw private path" not in body
    assert run.inventory.artifact.object_reference not in body
    assert "Synthetic Person One" not in body
    assert claim.token not in body

    dashboard = client.get(reverse("legacy_migration:dashboard"))
    dashboard_body = dashboard.content.decode()
    assert dashboard.status_code == 200
    assert "Retry scheduled" in dashboard_body
    assert "Failures 1 of 5" in dashboard_body
    assert "Claims 1" in dashboard_body
    assert "Next checkpoint" in dashboard_body
    assert "private-worker-identity" not in dashboard_body
    assert "raw private path" not in dashboard_body
    assert run.inventory.artifact.object_reference not in dashboard_body
    assert "Synthetic Person One" not in dashboard_body
    assert claim.token not in dashboard_body

    other = PartnerOrganization.objects.create(name="Other tenant")
    other_manager = _account(
        other,
        label="other-render-manager",
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    )
    other_client = Client()
    force_login_with_fresh_mfa(other_client, other_manager)
    assert (
        other_client.get(reverse("legacy_migration:run-detail", args=[run.pk])).status_code == 404
    )
