from __future__ import annotations

import argparse
import os
import secrets
import signal
import threading
from collections.abc import Sequence
from types import FrameType
from typing import Any


def _bounded_job_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("job limit must be an integer") from error
    if not 1 <= limit <= 25:
        raise argparse.ArgumentTypeError("job limit must be between 1 and 25")
    return limit


def _worker_identity() -> str:
    return f"mnemex-{os.getpid()}-{secrets.token_hex(8)}"


def main(
    argv: Sequence[str] | None = None,
    *,
    worker_owner: str | None = None,
    supervisor_max_cycles: int | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="MNEMEX worker process entry point")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--check",
        action="store_true",
        help="run Django system checks and exit",
    )
    actions.add_argument(
        "--reconcile-artifacts-once",
        action="store_true",
        help="reconcile one bounded batch of expired private-object writes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="maximum artifact objects to reconcile in one run (1-1000)",
    )
    actions.add_argument(
        "--run-migration-jobs-once",
        action="store_true",
        help="claim and execute one bounded batch of durable migration jobs",
    )
    actions.add_argument(
        "--supervise",
        action="store_true",
        help="run fair bounded queue cycles until graceful shutdown",
    )
    parser.add_argument(
        "--job-limit",
        type=_bounded_job_limit,
        default=1,
        help="maximum migration jobs to claim in one run (1-25)",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mnemex.web.settings.production")
    import django
    from django.conf import settings
    from django.core.management import call_command

    django.setup()
    if args.check:
        call_command("check", verbosity=0)
    if args.reconcile_artifacts_once:
        from mnemex.results.artifact_lifecycle import reconcile_artifact_objects
        from mnemex.results.artifacts import private_artifact_store_from_settings

        artifact_outcome = reconcile_artifact_objects(
            store=private_artifact_store_from_settings(),
            limit=args.limit,
        )
        from mnemex.results.models import ArtifactObjectWrite

        unresolved_blocked = ArtifactObjectWrite.objects.filter(
            status=ArtifactObjectWrite.Status.BLOCKED
        ).count()
        print(
            "artifact reconciliation: "
            f"examined={artifact_outcome.examined} cleaned={artifact_outcome.cleaned} "
            f"preserved={artifact_outcome.preserved} blocked={artifact_outcome.blocked} "
            f"skipped_active={artifact_outcome.skipped_active} "
            f"unresolved_blocked={unresolved_blocked}"
        )
        return 1 if unresolved_blocked else 0
    if args.run_migration_jobs_once:
        from mnemex.legacy_migration.worker_jobs import run_apply_jobs_once

        stop_event = threading.Event()

        def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
            stop_event.set()

        migration_handlers: dict[signal.Signals, Any] = {}
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                migration_handlers[signal_name] = signal.signal(signal_name, request_stop)
            except (ValueError, OSError):
                continue
        try:
            migration_outcome = run_apply_jobs_once(
                artifact_root=getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_ROOT", None),
                owner=worker_owner or _worker_identity(),
                limit=args.job_limit,
                should_stop=stop_event.is_set,
            )
        finally:
            for signal_name, previous_handler in migration_handlers.items():
                signal.signal(signal_name, previous_handler)
        print(
            "migration jobs: "
            f"claimed={migration_outcome.claimed} completed={migration_outcome.completed} "
            f"retry_scheduled={migration_outcome.retry_scheduled} "
            f"terminal_failed={migration_outcome.terminal_failed} "
            f"cancelled={migration_outcome.cancelled} "
            f"claim_lost={migration_outcome.claim_lost} "
            f"unresolved_failed={migration_outcome.unresolved_failed}"
        )
        return 1 if migration_outcome.terminal_failed or migration_outcome.unresolved_failed else 0
    if args.supervise:
        from django.db import models
        from django.utils import timezone

        from mnemex.accounts.key_rotation import (
            KeyRotationClaimLost,
            assert_configured_key_versions_available,
            claim_next_key_rotation,
            release_key_rotation_claim,
            run_mfa_key_rotation_batch,
            settle_key_rotation_failure,
        )
        from mnemex.accounts.models import EncryptionKeyRotationJob
        from mnemex.accounts.notifications import (
            notification_queue_metrics,
            run_security_notifications_once,
        )
        from mnemex.legacy_migration.models import LegacyMigrationJob, LegacyMigrationRun
        from mnemex.legacy_migration.worker_jobs import run_apply_jobs_once
        from mnemex.results.artifact_lifecycle import reconcile_artifact_objects
        from mnemex.results.artifacts import private_artifact_store_from_settings
        from mnemex.results.models import ArtifactObjectWrite
        from mnemex.supervisor import QueueTask, run_supervisor

        stop_event = threading.Event()
        owner = worker_owner or _worker_identity()
        assert_configured_key_versions_available(purpose="mfa")
        assert_configured_key_versions_available(purpose="notification")

        def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
            stop_event.set()

        def reconcile_artifacts() -> None:
            outcome = reconcile_artifact_objects(
                store=private_artifact_store_from_settings(),
                limit=1,
            )
            unresolved = ArtifactObjectWrite.objects.filter(
                status=ArtifactObjectWrite.Status.BLOCKED
            ).count()
            measured_at = timezone.now()
            ready_writes = ArtifactObjectWrite.objects.filter(
                status__in=(
                    ArtifactObjectWrite.Status.ACTIVE,
                    ArtifactObjectWrite.Status.ABANDONED,
                ),
                reconcile_after__lte=measured_at,
            )
            ready_depth = ready_writes.order_by().values("artifact_object_id").distinct().count()
            oldest = (
                ready_writes.order_by("reconcile_after")
                .values_list("reconcile_after", flat=True)
                .first()
            )
            oldest_age = (
                None if oldest is None else max(0, int((measured_at - oldest).total_seconds()))
            )
            print(
                "worker task=artifact_reconciliation "
                f"examined={outcome.examined} blocked={outcome.blocked} "
                f"ready={ready_depth} oldest_ready_age_seconds={oldest_age} "
                f"unresolved={unresolved}"
            )
            if unresolved:
                raise RuntimeError("artifact_reconciliation_unhealthy")

        def apply_migrations() -> None:
            outcome = run_apply_jobs_once(
                artifact_root=getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_ROOT", None),
                owner=owner,
                limit=1,
                should_stop=stop_event.is_set,
            )
            measured_at = timezone.now()
            ready_jobs = (
                LegacyMigrationJob.objects.filter(
                    models.Q(
                        status__in=(
                            LegacyMigrationJob.Status.PENDING,
                            LegacyMigrationJob.Status.RETRY_WAIT,
                        ),
                        available_at__lte=measured_at,
                    )
                    | models.Q(
                        status=LegacyMigrationJob.Status.RUNNING,
                        lease_expires_at__lte=measured_at,
                    ),
                    job_kind=LegacyMigrationJob.Kind.APPLY,
                    failure_count__lt=models.F("max_attempts"),
                )
                .exclude(run__state=LegacyMigrationRun.State.WITHDRAWN)
                .annotate(
                    claim_ready_at=models.Case(
                        models.When(
                            status=LegacyMigrationJob.Status.RUNNING,
                            then=models.F("lease_expires_at"),
                        ),
                        default=models.F("available_at"),
                        output_field=models.DateTimeField(),
                    )
                )
            )
            oldest = (
                ready_jobs.order_by("claim_ready_at")
                .values_list("claim_ready_at", flat=True)
                .first()
            )
            oldest_age = (
                None if oldest is None else max(0, int((measured_at - oldest).total_seconds()))
            )
            print(
                "worker task=migration_apply "
                f"claimed={outcome.claimed} completed={outcome.completed} "
                f"retry_scheduled={outcome.retry_scheduled} "
                f"ready={ready_jobs.count()} oldest_ready_age_seconds={oldest_age} "
                f"unresolved_failed={outcome.unresolved_failed}"
            )
            if outcome.terminal_failed or outcome.unresolved_failed:
                raise RuntimeError("migration_apply_unhealthy")

        def deliver_security_notifications() -> None:
            outcome = run_security_notifications_once(
                owner=owner,
                limit=5,
                should_stop=stop_event.is_set,
            )
            metrics = notification_queue_metrics()
            print(
                "worker task=security_notifications "
                f"claimed={outcome.claimed} delivered={outcome.delivered} "
                f"retry_scheduled={outcome.retry_scheduled} ready={metrics.ready_depth} "
                f"oldest_ready_age_seconds={metrics.oldest_ready_age_seconds} "
                f"failed_review={metrics.failed_review_depth} "
                f"delivery_uncertain={metrics.delivery_uncertain_depth}"
            )

        def rotate_mfa_keys() -> None:
            claim = claim_next_key_rotation(owner=owner)
            claimed = int(claim is not None)
            scanned = 0
            rotated = 0
            completed = 0
            retry_scheduled = 0
            claim_lost = 0
            failed_review = 0
            if claim is not None:
                try:
                    if stop_event.is_set():
                        release_key_rotation_claim(claim)
                    else:
                        outcome = run_mfa_key_rotation_batch(claim, limit=100)
                        scanned = outcome.batch_scanned_count
                        rotated = outcome.batch_rotated_count
                        if outcome.status == EncryptionKeyRotationJob.Status.COMPLETED:
                            completed = 1
                        else:
                            release_key_rotation_claim(claim)
                except KeyRotationClaimLost:
                    claim_lost = 1
                except Exception:
                    try:
                        settled = settle_key_rotation_failure(
                            claim,
                            error_code="rotation_batch_failed",
                        )
                    except KeyRotationClaimLost:
                        claim_lost = 1
                    else:
                        if settled.status == EncryptionKeyRotationJob.Status.FAILED_REVIEW:
                            failed_review = 1
                        else:
                            retry_scheduled = 1
            unresolved = EncryptionKeyRotationJob.objects.filter(
                status=EncryptionKeyRotationJob.Status.FAILED_REVIEW
            ).count()
            measured_at = timezone.now()
            ready_rotations = EncryptionKeyRotationJob.objects.filter(
                models.Q(
                    status__in=(
                        EncryptionKeyRotationJob.Status.PENDING,
                        EncryptionKeyRotationJob.Status.RETRY_WAIT,
                    ),
                    available_at__lte=measured_at,
                )
                | models.Q(
                    status=EncryptionKeyRotationJob.Status.RUNNING,
                    lease_expires_at__lte=measured_at,
                )
            ).annotate(
                claim_ready_at=models.Case(
                    models.When(
                        status=EncryptionKeyRotationJob.Status.RUNNING,
                        then=models.F("lease_expires_at"),
                    ),
                    default=models.F("available_at"),
                    output_field=models.DateTimeField(),
                )
            )
            oldest = (
                ready_rotations.order_by("claim_ready_at")
                .values_list("claim_ready_at", flat=True)
                .first()
            )
            oldest_age = (
                None if oldest is None else max(0, int((measured_at - oldest).total_seconds()))
            )
            print(
                "worker task=mfa_key_rotation "
                f"claimed={claimed} scanned={scanned} rotated={rotated} "
                f"completed={completed} retry_scheduled={retry_scheduled} "
                f"claim_lost={claim_lost} failed_review={failed_review} "
                f"ready={ready_rotations.count()} oldest_ready_age_seconds={oldest_age} "
                f"unresolved_failed={unresolved}"
            )
            if failed_review or unresolved:
                raise RuntimeError("mfa_key_rotation_unhealthy")

        def observe(event: str, task: str, code: str) -> None:
            print(f"supervisor event={event} task={task} code={code}")

        installed_handlers: dict[signal.Signals, Any] = {}
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                installed_handlers[signal_name] = signal.signal(signal_name, request_stop)
            except (ValueError, OSError):
                continue
        try:
            supervisor_outcome = run_supervisor(
                tasks=(
                    QueueTask(name="artifact_reconciliation", run=reconcile_artifacts),
                    QueueTask(name="migration_apply", run=apply_migrations),
                    QueueTask(
                        name="security_notifications",
                        run=deliver_security_notifications,
                    ),
                    QueueTask(name="mfa_key_rotation", run=rotate_mfa_keys),
                ),
                should_stop=stop_event.is_set,
                observe=observe,
                max_cycles=supervisor_max_cycles,
            )
        finally:
            for signal_name, previous_handler in installed_handlers.items():
                signal.signal(signal_name, previous_handler)
        print(
            "supervisor "
            f"cycles={supervisor_outcome.cycles} task_runs={supervisor_outcome.task_runs} "
            f"failures={supervisor_outcome.failure_count} stopped={int(supervisor_outcome.stopped)} "
            f"unhealthy={int(supervisor_outcome.unhealthy)}"
        )
        return 1 if supervisor_outcome.unhealthy else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
