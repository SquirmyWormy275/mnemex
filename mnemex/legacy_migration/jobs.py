from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, connection, models, transaction
from django.utils import timezone

from mnemex.accounts.models import Account
from mnemex.legacy_migration import services as migration_services
from mnemex.legacy_migration.models import LegacyMigrationJob, LegacyMigrationRun
from mnemex.partners.models import PartnerOrganization

DEFAULT_APPLY_LEASE = timedelta(minutes=5)
INITIAL_RETRY_DELAY_SECONDS = 30
MAX_RETRY_DELAY_SECONDS = 15 * 60
MAX_APPLY_ATTEMPTS = 5


@dataclass(frozen=True)
class ClaimedApplyJob:
    job_id: UUID
    token: str
    generation: int
    owner: str


@dataclass(frozen=True)
class ApplyJobOutcome:
    job_id: UUID
    status: str
    attempt_count: int
    error_code: str
    message: str
    available_at: datetime


class _GracefulStop(Exception):
    pass


def _checked_now(now: datetime | None) -> datetime:
    value = now if now is not None else timezone.now()
    if timezone.is_naive(value):
        raise ValidationError("worker time must be timezone-aware")
    return value


def _checked_owner(owner: str) -> str:
    normalized = migration_services._plain_string(owner, field="claim owner", maximum=120)
    if any(ord(character) < 32 for character in normalized):
        raise ValidationError("claim owner contains invalid characters")
    return normalized


def _checked_lease(lease_duration: timedelta) -> timedelta:
    if not isinstance(lease_duration, timedelta) or not (
        timedelta(seconds=1) <= lease_duration <= timedelta(hours=1)
    ):
        raise ValidationError("claim lease must be between 1 second and 1 hour")
    return lease_duration


def _checked_rationale(request_rationale: str) -> str:
    normalized = migration_services._plain_string(
        request_rationale,
        field="request rationale",
        maximum=500,
    )
    if any(ord(character) < 32 and character not in "\r\n\t" for character in normalized):
        raise ValidationError("request rationale contains invalid characters")
    return normalized


def _outcome(job: LegacyMigrationJob) -> ApplyJobOutcome:
    return ApplyJobOutcome(
        job_id=job.pk,
        status=job.status,
        attempt_count=job.attempt_count,
        error_code=job.last_error_code,
        message=job.last_error_message,
        available_at=job.available_at,
    )


def _clear_claim(job: LegacyMigrationJob) -> None:
    job.claim_token = ""
    job.claim_owner = ""
    job.heartbeat_at = None
    job.lease_expires_at = None


def _job_coordinates(job_id: UUID) -> tuple[UUID, UUID]:
    coordinates = (
        LegacyMigrationJob.objects.filter(pk=job_id)
        .values_list("organization_id", "run_id")
        .first()
    )
    if coordinates is None:
        raise migration_services.ApplyClaimLost("legacy migration APPLY claim no longer exists")
    return coordinates


def _lock_job(job_id: UUID) -> tuple[LegacyMigrationRun, LegacyMigrationJob]:
    organization_id, run_id = _job_coordinates(job_id)
    organization = (
        PartnerOrganization.objects.select_for_update().filter(pk=organization_id).first()
    )
    if organization is None:
        raise migration_services.ApplyClaimLost("legacy migration APPLY claim no longer exists")
    run = (
        LegacyMigrationRun.objects.select_for_update()
        .select_related("organization", "inventory__artifact", "created_by")
        .filter(pk=run_id, organization=organization)
        .first()
    )
    job = (
        LegacyMigrationJob.objects.select_for_update()
        .select_related("created_by")
        .filter(pk=job_id, run=run, organization=organization)
        .first()
    )
    if run is None or job is None:
        raise migration_services.ApplyClaimLost("legacy migration APPLY claim no longer exists")
    return run, job


def _assert_claim(job: LegacyMigrationJob, claim: ClaimedApplyJob, *, now: datetime) -> None:
    if job.job_kind != LegacyMigrationJob.Kind.APPLY:
        raise migration_services.ApplyClaimLost("legacy migration claim is not an APPLY job")
    migration_services._assert_active_apply_claim(
        job,
        claim_token=claim.token,
        claim_generation=claim.generation,
        claim_owner=claim.owner,
        now=now,
    )


@transaction.atomic
def enqueue_apply_job(
    *,
    actor: Account,
    run: LegacyMigrationRun,
    approved_manifest_digest: str,
    chunk_size: int,
    request_rationale: str,
    max_attempts: int = MAX_APPLY_ATTEMPTS,
    now: datetime | None = None,
) -> LegacyMigrationJob:
    queued_at = _checked_now(now)
    if not isinstance(approved_manifest_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", approved_manifest_digest
    ):
        raise ValidationError("approved manifest digest must be a lowercase SHA-256 digest")
    if (
        isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or not (1 <= chunk_size <= migration_services.MAX_APPLY_CHUNK_ROWS)
    ):
        raise ValidationError(
            f"chunk size must be between 1 and {migration_services.MAX_APPLY_CHUNK_ROWS}"
        )
    if max_attempts != MAX_APPLY_ATTEMPTS:
        raise ValidationError(f"max attempts must be exactly {MAX_APPLY_ATTEMPTS}")
    rationale = _checked_rationale(request_rationale)

    migration_services._lock_organization(run)
    current = migration_services._current_run(run)
    migration_services._authorize(actor, current)
    if current.state == LegacyMigrationRun.State.WITHDRAWN:
        raise ValidationError("withdrawn legacy migrations cannot be applied")
    migration_services._verified_approval(current, approved_manifest_digest)
    if current.state not in {
        LegacyMigrationRun.State.APPROVED,
        LegacyMigrationRun.State.APPLYING,
        LegacyMigrationRun.State.FAILED,
        LegacyMigrationRun.State.COMPLETED,
    }:
        raise ValidationError("legacy migration must be approved before apply")
    matching = current.jobs.select_for_update().filter(
        job_kind=LegacyMigrationJob.Kind.APPLY,
        requested_manifest_digest=approved_manifest_digest,
        chunk_size=chunk_size,
    )
    existing = (
        matching.filter(
            status__in=(
                LegacyMigrationJob.Status.PENDING,
                LegacyMigrationJob.Status.RUNNING,
                LegacyMigrationJob.Status.RETRY_WAIT,
            )
        )
        .order_by("-job_sequence")
        .first()
    )
    if existing is not None:
        return existing
    completed = (
        matching.filter(status=LegacyMigrationJob.Status.COMPLETED)
        .order_by("-job_sequence")
        .first()
    )
    if completed is not None:
        return completed
    different_request = (
        current.jobs.select_for_update()
        .filter(
            job_kind=LegacyMigrationJob.Kind.APPLY,
        )
        .exclude(
            requested_manifest_digest=approved_manifest_digest,
            chunk_size=chunk_size,
        )
        .exists()
    )
    if different_request:
        raise ValidationError("migration run already has a different immutable APPLY request")
    if current.state == LegacyMigrationRun.State.COMPLETED:
        raise ValidationError("completed migration has no matching APPLY request")
    last_sequence = (
        current.jobs.filter(job_kind=LegacyMigrationJob.Kind.APPLY)
        .order_by("-job_sequence")
        .values_list("job_sequence", flat=True)
        .first()
    )
    return LegacyMigrationJob.objects.create(
        organization=current.organization,
        run=current,
        job_kind=LegacyMigrationJob.Kind.APPLY,
        job_sequence=(last_sequence or 0) + 1,
        requested_manifest_digest=approved_manifest_digest,
        request_rationale=rationale,
        chunk_size=chunk_size,
        max_attempts=max_attempts,
        available_at=queued_at,
        created_by=actor,
    )


def _claimable(now: datetime) -> models.QuerySet[LegacyMigrationJob]:
    due = models.Q(
        status__in=(
            LegacyMigrationJob.Status.PENDING,
            LegacyMigrationJob.Status.RETRY_WAIT,
        ),
        available_at__lte=now,
    )
    expired = models.Q(
        status=LegacyMigrationJob.Status.RUNNING,
        lease_expires_at__lte=now,
    )
    return (
        LegacyMigrationJob.objects.filter(
            models.Q(due | expired),
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
        .order_by("claim_ready_at", "created_at", "job_id")
    )


def _expired_exhausted(now: datetime) -> models.QuerySet[LegacyMigrationJob]:
    return LegacyMigrationJob.objects.filter(
        job_kind=LegacyMigrationJob.Kind.APPLY,
        status=LegacyMigrationJob.Status.RUNNING,
        lease_expires_at__lte=now,
        failure_count__gte=models.F("max_attempts"),
    ).order_by("lease_expires_at", "created_at", "job_id")


def _candidate_organization_ids(
    queryset: models.QuerySet[LegacyMigrationJob], *, ordering_field: str
) -> list[UUID]:
    return list(
        queryset.order_by()
        .values("organization_id")
        .annotate(
            earliest=models.Min(ordering_field),
            earliest_created=models.Min("created_at"),
        )
        .order_by("earliest", "earliest_created", "organization_id")
        .values_list("organization_id", flat=True)[:100]
    )


def _terminalize_job(
    *,
    run: LegacyMigrationRun,
    job: LegacyMigrationJob,
    now: datetime,
    error_code: str,
    message: str,
    record_failure: bool,
) -> None:
    if record_failure and job.failure_count < job.max_attempts:
        job.failure_count += 1
    job.status = LegacyMigrationJob.Status.FAILED
    job.completed_at = now
    job.last_error_code = error_code
    job.last_error_message = message
    _clear_claim(job)
    job.save(
        update_fields=[
            "status",
            "failure_count",
            "completed_at",
            "last_error_code",
            "last_error_message",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    if run.state not in {
        LegacyMigrationRun.State.COMPLETED,
        LegacyMigrationRun.State.WITHDRAWN,
    }:
        run.state = LegacyMigrationRun.State.FAILED
        run.save(update_fields=["state", "updated_at"])


def _terminalize_one_expired_exhausted(now: datetime) -> bool:
    organization_ids = _candidate_organization_ids(
        _expired_exhausted(now), ordering_field="lease_expires_at"
    )
    for organization_id in organization_ids:
        organization = (
            PartnerOrganization.objects.select_for_update(
                skip_locked=connection.features.has_select_for_update_skip_locked
            )
            .filter(pk=organization_id)
            .first()
        )
        if organization is None:
            continue
        coordinates = (
            _expired_exhausted(now)
            .filter(organization=organization)
            .values_list("run_id", "job_id")
            .first()
        )
        if coordinates is None:
            continue
        run_id, job_id = coordinates
        run = (
            LegacyMigrationRun.objects.select_for_update()
            .filter(pk=run_id, organization=organization)
            .first()
        )
        if run is None:
            continue
        job = (
            _expired_exhausted(now)
            .select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
            .filter(pk=job_id, run=run)
            .first()
        )
        if job is None:
            continue
        _terminalize_job(
            run=run,
            job=job,
            now=now,
            error_code="attempts_exhausted",
            message="worker failures exhausted; operator review is required",
            record_failure=False,
        )
        return True
    return False


def _claim_locked_job(
    *,
    run: LegacyMigrationRun,
    job: LegacyMigrationJob,
    owner: str,
    now: datetime,
    lease_duration: timedelta,
    allow_early_retry: bool,
) -> ClaimedApplyJob | None:
    is_due = job.status == LegacyMigrationJob.Status.PENDING and job.available_at <= now
    is_due = is_due or (
        job.status == LegacyMigrationJob.Status.RETRY_WAIT
        and (allow_early_retry or job.available_at <= now)
    )
    is_due = is_due or (
        job.status == LegacyMigrationJob.Status.RUNNING
        and job.lease_expires_at is not None
        and job.lease_expires_at <= now
    )
    if not is_due or job.failure_count >= job.max_attempts:
        return None
    if run.state == LegacyMigrationRun.State.WITHDRAWN:
        return None
    if run.organization.status != PartnerOrganization.Status.ACTIVE:
        _terminalize_job(
            run=run,
            job=job,
            now=now,
            error_code="organization_inactive",
            message="job organization is no longer active",
            record_failure=True,
        )
        return None
    try:
        migration_services._authorize(job.created_by, run)
    except PermissionDenied:
        _terminalize_job(
            run=run,
            job=job,
            now=now,
            error_code="authorization_denied",
            message="job creator authorization is no longer valid",
            record_failure=True,
        )
        return None
    expired_takeover = (
        job.status == LegacyMigrationJob.Status.RUNNING
        and job.lease_expires_at is not None
        and job.lease_expires_at <= now
    )
    if expired_takeover:
        job.failure_count += 1
        if job.failure_count >= job.max_attempts:
            _terminalize_job(
                run=run,
                job=job,
                now=now,
                error_code="attempts_exhausted",
                message="expired worker leases exhausted; operator review is required",
                record_failure=False,
            )
            return None
    migration_services._verified_approval(run, job.requested_manifest_digest)
    token = secrets.token_hex(32)
    job.status = LegacyMigrationJob.Status.RUNNING
    job.attempt_count += 1
    job.claim_generation += 1
    job.claim_token = token
    job.claim_owner = owner
    job.heartbeat_at = now
    job.lease_expires_at = now + lease_duration
    job.started_at = job.started_at or now
    job.completed_at = None
    job.last_error_code = ""
    job.last_error_message = ""
    job.save(
        update_fields=[
            "status",
            "attempt_count",
            "claim_generation",
            "failure_count",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "started_at",
            "completed_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    if run.state != LegacyMigrationRun.State.APPLYING:
        run.state = LegacyMigrationRun.State.APPLYING
        run.save(update_fields=["state", "updated_at"])
    return ClaimedApplyJob(
        job_id=job.pk,
        token=token,
        generation=job.claim_generation,
        owner=owner,
    )


@transaction.atomic
def claim_next_apply_job(
    *,
    owner: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_APPLY_LEASE,
) -> ClaimedApplyJob | None:
    claimed_at = _checked_now(now)
    checked_owner = _checked_owner(owner)
    checked_lease = _checked_lease(lease_duration)
    _terminalize_one_expired_exhausted(claimed_at)
    organization_ids = _candidate_organization_ids(
        _claimable(claimed_at), ordering_field="claim_ready_at"
    )
    for organization_id in organization_ids:
        organization_queryset = PartnerOrganization.objects.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
        organization = organization_queryset.filter(pk=organization_id).first()
        if organization is None:
            continue
        coordinates = (
            _claimable(claimed_at)
            .filter(organization=organization)
            .values_list("run_id", "job_id")
            .first()
        )
        if coordinates is None:
            continue
        run_id, job_id = coordinates
        run = (
            LegacyMigrationRun.objects.select_for_update()
            .select_related("organization")
            .filter(pk=run_id, organization=organization)
            .first()
        )
        if run is None:
            continue
        job_queryset = _claimable(claimed_at).filter(pk=job_id, run=run)
        job_queryset = job_queryset.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
        job = job_queryset.first()
        if job is None:
            continue
        claim = _claim_locked_job(
            run=run,
            job=job,
            owner=checked_owner,
            now=claimed_at,
            lease_duration=checked_lease,
            allow_early_retry=False,
        )
        if claim is not None:
            return claim
    return None


@transaction.atomic
def _claim_specific_apply_job(
    *,
    job_id: UUID,
    owner: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_APPLY_LEASE,
    allow_early_retry: bool = False,
) -> ClaimedApplyJob | None:
    claimed_at = _checked_now(now)
    checked_owner = _checked_owner(owner)
    checked_lease = _checked_lease(lease_duration)
    run, job = _lock_job(job_id)
    if job.job_kind != LegacyMigrationJob.Kind.APPLY:
        return None
    return _claim_locked_job(
        run=run,
        job=job,
        owner=checked_owner,
        now=claimed_at,
        lease_duration=checked_lease,
        allow_early_retry=allow_early_retry,
    )


@transaction.atomic
def heartbeat_apply_job(
    claim: ClaimedApplyJob,
    *,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_APPLY_LEASE,
) -> ApplyJobOutcome:
    heartbeat_at = _checked_now(now)
    checked_lease = _checked_lease(lease_duration)
    _, job = _lock_job(claim.job_id)
    _assert_claim(job, claim, now=heartbeat_at)
    assert job.lease_expires_at is not None
    assert job.heartbeat_at is not None
    job.heartbeat_at = max(job.heartbeat_at, heartbeat_at)
    job.lease_expires_at = max(job.lease_expires_at, heartbeat_at + checked_lease)
    job.save(update_fields=["heartbeat_at", "lease_expires_at", "updated_at"])
    return _outcome(job)


def authorize_apply_job_source_read(
    claim: ClaimedApplyJob,
    *,
    read_source: Callable[[LegacyMigrationRun], bytes],
    now: datetime | None = None,
) -> bytes:
    """Read a private workbook while the reauthorized claim remains locked."""

    checked_at = _checked_now(now)
    denial_message = ""
    content: bytes | None = None
    with transaction.atomic():
        run, job = _lock_job(claim.job_id)
        _assert_claim(job, claim, now=checked_at)
        if run.organization.status != PartnerOrganization.Status.ACTIVE:
            _terminalize_job(
                run=run,
                job=job,
                now=checked_at,
                error_code="organization_inactive",
                message="job organization is no longer active",
                record_failure=True,
            )
            denial_message = "legacy migration organization is inactive"
        else:
            try:
                migration_services._authorize(job.created_by, run)
            except PermissionDenied:
                _terminalize_job(
                    run=run,
                    job=job,
                    now=checked_at,
                    error_code="authorization_denied",
                    message="job creator authorization is no longer valid",
                    record_failure=True,
                )
                denial_message = "legacy migration creator authorization is no longer valid"
            else:
                content = read_source(run)
    if denial_message:
        raise migration_services.ApplyClaimLost(denial_message)
    if content is None:
        raise migration_services.ApplyClaimLost("legacy migration source read did not complete")
    return content


def _failure_details(error: Exception) -> tuple[str, str, bool]:
    if isinstance(error, PermissionDenied):
        return "authorization_denied", "job authorization is no longer valid", True
    if isinstance(error, ValidationError):
        return "provenance_validation_failed", "job provenance validation failed", True
    if isinstance(error, OperationalError):
        return (
            "database_unavailable",
            "temporary worker failure; retry is scheduled",
            False,
        )
    if isinstance(error, OSError):
        return (
            "storage_unavailable",
            "temporary worker failure; retry is scheduled",
            False,
        )
    return "worker_error", "temporary worker failure; retry is scheduled", False


@transaction.atomic
def settle_apply_job_failure(
    claim: ClaimedApplyJob,
    error: Exception,
    *,
    now: datetime | None = None,
    immediate_retry: bool = False,
) -> ApplyJobOutcome:
    settled_at = _checked_now(now)
    run, job = _lock_job(claim.job_id)
    _assert_claim(job, claim, now=settled_at)
    error_code, message, terminal = _failure_details(error)
    graceful = isinstance(error, _GracefulStop)
    if graceful:
        error_code = "graceful_shutdown"
        message = "worker stopped safely between chunks; retry is ready"
        immediate_retry = True
    else:
        job.failure_count += 1
    exhausted = job.failure_count >= job.max_attempts
    if terminal or exhausted:
        job.status = LegacyMigrationJob.Status.FAILED
        job.completed_at = settled_at
        if run.state not in {
            LegacyMigrationRun.State.COMPLETED,
            LegacyMigrationRun.State.WITHDRAWN,
        }:
            run.state = LegacyMigrationRun.State.FAILED
            run.save(update_fields=["state", "updated_at"])
    else:
        delay = (
            0
            if immediate_retry
            else min(
                INITIAL_RETRY_DELAY_SECONDS * (2 ** max(job.failure_count - 1, 0)),
                MAX_RETRY_DELAY_SECONDS,
            )
        )
        job.status = LegacyMigrationJob.Status.RETRY_WAIT
        job.available_at = settled_at + timedelta(seconds=delay)
        job.completed_at = None
    job.last_error_code = error_code
    job.last_error_message = message
    _clear_claim(job)
    job.save(
        update_fields=[
            "status",
            "failure_count",
            "available_at",
            "completed_at",
            "last_error_code",
            "last_error_message",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return _outcome(job)


@transaction.atomic
def cancel_apply_job(
    *, actor: Account, job_id: UUID, now: datetime | None = None
) -> ApplyJobOutcome:
    cancelled_at = _checked_now(now)
    run, job = _lock_job(job_id)
    migration_services._authorize(actor, run)
    if job.status in {
        LegacyMigrationJob.Status.COMPLETED,
        LegacyMigrationJob.Status.FAILED,
        LegacyMigrationJob.Status.CANCELLED,
    }:
        return _outcome(job)
    job.status = LegacyMigrationJob.Status.CANCELLED
    job.completed_at = cancelled_at
    job.last_error_code = "operator_cancelled"
    job.last_error_message = "job was cancelled by an authorized operator"
    _clear_claim(job)
    job.save(
        update_fields=[
            "status",
            "completed_at",
            "last_error_code",
            "last_error_message",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return _outcome(job)


def execute_apply_job(
    claim: ClaimedApplyJob,
    *,
    workbook_content: bytes,
    should_stop: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] = timezone.now,
    fail_after_committed_chunks: int | None = None,
    _raise_error: bool = False,
) -> ApplyJobOutcome:
    execution_time = _checked_now(clock())
    if fail_after_committed_chunks is not None:
        fail_after_committed_chunks = migration_services._positive_integer(
            fail_after_committed_chunks,
            field="failure injection count",
        )
    with transaction.atomic():
        run, job = _lock_job(claim.job_id)
        _assert_claim(job, claim, now=execution_time)
        actor = job.created_by
    try:
        migration_services._authorize(actor, run)
        inspection = migration_services._verify_source(run, workbook_content)
        migration_services._verify_persisted_plan(run, inspection)
        current, mapping, chunks, next_sequence = migration_services._prepare_claimed_apply(
            actor=actor,
            run=run,
            job=job,
            approved_manifest_digest=job.requested_manifest_digest,
            claim_token=claim.token,
            claim_generation=claim.generation,
            claim_owner=claim.owner,
        )
        committed_this_attempt = 0
        for chunk in chunks[next_sequence - 1 :]:
            if should_stop is not None and should_stop():
                return settle_apply_job_failure(
                    claim,
                    _GracefulStop(),
                    now=_checked_now(clock()),
                    immediate_retry=True,
                )
            heartbeat_apply_job(claim, now=_checked_now(clock()))
            _, committed = migration_services._commit_apply_chunk(
                actor=actor,
                run=current,
                job=job,
                mapping=mapping,
                chunk=chunk,
                approved_manifest_digest=job.requested_manifest_digest,
                claim_token=claim.token,
                claim_generation=claim.generation,
                claim_owner=claim.owner,
            )
            if committed:
                committed_this_attempt += 1
                if committed_this_attempt == fail_after_committed_chunks:
                    raise RuntimeError("synthetic injected failure after committed chunk")
        migration_services._complete_apply(
            actor=actor,
            run=current,
            job=job,
            chunks=chunks,
            approved_manifest_digest=job.requested_manifest_digest,
            claim_token=claim.token,
            claim_generation=claim.generation,
            claim_owner=claim.owner,
        )
        return _outcome(LegacyMigrationJob.objects.get(pk=job.pk))
    except migration_services.ApplyClaimLost:
        raise
    except Exception as error:
        outcome = settle_apply_job_failure(claim, error, now=_checked_now(clock()))
        if _raise_error:
            raise error
        return outcome
