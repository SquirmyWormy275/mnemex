from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models

from mnemex.legacy_migration.jobs import (
    authorize_apply_job_source_read,
    claim_next_apply_job,
    execute_apply_job,
    settle_apply_job_failure,
)
from mnemex.legacy_migration.models import LegacyMigrationJob
from mnemex.legacy_migration.private_workbooks import read_private_workbook
from mnemex.legacy_migration.services import ApplyClaimLost

MAX_JOBS_PER_RUN = 25


@dataclass(frozen=True)
class MigrationWorkerBatchOutcome:
    claimed: int = 0
    completed: int = 0
    retry_scheduled: int = 0
    terminal_failed: int = 0
    cancelled: int = 0
    claim_lost: int = 0
    unresolved_failed: int = 0


def _validate_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_JOBS_PER_RUN:
        raise ValidationError(f"job limit must be between 1 and {MAX_JOBS_PER_RUN}")
    return limit


def _count_unresolved_failed_apply_jobs() -> int:
    later_replacement = LegacyMigrationJob.objects.filter(
        run_id=models.OuterRef("run_id"),
        job_kind=LegacyMigrationJob.Kind.APPLY,
        requested_manifest_digest=models.OuterRef("requested_manifest_digest"),
        chunk_size=models.OuterRef("chunk_size"),
        job_sequence__gt=models.OuterRef("job_sequence"),
    )
    return (
        LegacyMigrationJob.objects.filter(
            job_kind=LegacyMigrationJob.Kind.APPLY,
            status=LegacyMigrationJob.Status.FAILED,
        )
        .annotate(has_replacement=models.Exists(later_replacement))
        .filter(has_replacement=False)
        .count()
    )


def run_apply_jobs_once(
    *,
    artifact_root: str | Path | None,
    owner: str,
    limit: int = 1,
    should_stop: Callable[[], bool] | None = None,
) -> MigrationWorkerBatchOutcome:
    """Claim and execute one bounded batch of durable APPLY jobs."""

    checked_limit = _validate_limit(limit)
    stop_requested = should_stop or (lambda: False)
    claimed = completed = retry_scheduled = terminal_failed = cancelled = claim_lost = 0
    for _ in range(checked_limit):
        if stop_requested():
            break
        claim = claim_next_apply_job(owner=owner)
        if claim is None:
            break
        claimed += 1
        try:
            try:
                content = authorize_apply_job_source_read(
                    claim,
                    read_source=lambda run: read_private_workbook(
                        run,
                        artifact_root=artifact_root,
                    ),
                )
            except ApplyClaimLost:
                raise
            except Exception as error:
                outcome = settle_apply_job_failure(claim, error)
            else:
                outcome = execute_apply_job(
                    claim,
                    workbook_content=content,
                    should_stop=stop_requested,
                )
        except ApplyClaimLost:
            claim_lost += 1
            current_status = (
                LegacyMigrationJob.objects.filter(pk=claim.job_id)
                .values_list("status", flat=True)
                .first()
            )
            if current_status == LegacyMigrationJob.Status.CANCELLED:
                cancelled += 1
            continue
        if outcome.status == LegacyMigrationJob.Status.COMPLETED:
            completed += 1
        elif outcome.status == LegacyMigrationJob.Status.RETRY_WAIT:
            retry_scheduled += 1
        elif outcome.status == LegacyMigrationJob.Status.FAILED:
            terminal_failed += 1
        elif outcome.status == LegacyMigrationJob.Status.CANCELLED:
            cancelled += 1
    unresolved_failed = _count_unresolved_failed_apply_jobs()
    return MigrationWorkerBatchOutcome(
        claimed=claimed,
        completed=completed,
        retry_scheduled=retry_scheduled,
        terminal_failed=terminal_failed,
        cancelled=cancelled,
        claim_lost=claim_lost,
        unresolved_failed=unresolved_failed,
    )
