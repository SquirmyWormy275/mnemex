from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from allauth.mfa.models import Authenticator
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import connection, models, transaction
from django.utils import timezone

from mnemex.accounts.keyring import KeyRingError, VersionedKeyRing, mfa_key_ring
from mnemex.accounts.models import Account, EncryptionKeyRotationJob, SecurityNotification
from mnemex.foundation.services import record_audit_event

DEFAULT_ROTATION_LEASE = timedelta(minutes=5)
MAX_ROTATION_BATCH_SIZE = 500
MAX_ROTATIONS_PER_RUN = 10
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ACTIVE_STATUSES = (
    EncryptionKeyRotationJob.Status.PENDING,
    EncryptionKeyRotationJob.Status.RUNNING,
    EncryptionKeyRotationJob.Status.RETRY_WAIT,
)


class KeyRotationClaimLost(RuntimeError):
    """A stale or mismatched worker attempted to mutate a rotation job."""


class KeyRetirementBlocked(RuntimeError):
    """A configured key version is still required by durable state."""


@dataclass(frozen=True)
class ClaimedKeyRotation:
    job_id: UUID
    token: str
    generation: int
    owner: str


@dataclass(frozen=True)
class KeyRotationOutcome:
    job_id: UUID
    status: str
    scanned_count: int
    processed_count: int
    cursor_authenticator_id: int | None


@dataclass(frozen=True)
class KeyRotationBatchOutcome(KeyRotationOutcome):
    batch_scanned_count: int
    batch_rotated_count: int

    @property
    def rotated_count(self) -> int:
        return self.batch_rotated_count


@dataclass(frozen=True)
class KeyRetirementBlocker:
    code: str
    count: int


def _checked_version(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError({field: "key version must be a positive integer"})
    return value


def _checked_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValidationError("rotation worker time must be timezone-aware")
    return value


def _checked_owner(owner: str) -> str:
    if not isinstance(owner, str):
        raise ValidationError("rotation claim owner is invalid")
    normalized = owner.strip()
    if not normalized or len(normalized) > 120 or any(ord(char) < 32 for char in normalized):
        raise ValidationError("rotation claim owner is invalid")
    return normalized


def _checked_lease(lease_duration: timedelta) -> timedelta:
    if not isinstance(lease_duration, timedelta) or not (
        timedelta(seconds=1) <= lease_duration <= timedelta(hours=1)
    ):
        raise ValidationError("rotation lease must be between 1 second and 1 hour")
    return lease_duration


def _checked_limit(limit: int, *, maximum: int, field: str) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValidationError(f"{field} must be between 1 and {maximum}")
    return limit


def _clear_claim(job: EncryptionKeyRotationJob) -> None:
    job.claim_token = ""
    job.claim_owner = ""
    job.heartbeat_at = None
    job.lease_expires_at = None


def _outcome(job: EncryptionKeyRotationJob) -> KeyRotationOutcome:
    return KeyRotationOutcome(
        job_id=job.pk,
        status=job.status,
        scanned_count=job.scanned_count,
        processed_count=job.processed_count,
        cursor_authenticator_id=job.cursor_authenticator_id,
    )


def _audit_rotation(
    *,
    action: str,
    job: EncryptionKeyRotationJob,
    metadata: dict[str, str | int],
) -> None:
    payload_digest = hashlib.sha256(
        (
            f"{action}:{job.pk}:{job.purpose}:{job.source_key_version}:{job.target_key_version}"
        ).encode("utf-8")
    ).hexdigest()
    record_audit_event(
        action=action,
        target_type="encryption_key_rotation",
        target_id=str(job.pk),
        payload_digest=payload_digest,
        metadata=metadata,
        actor_id=job.requested_by_id,
        correlation_id=job.pk,
    )


@transaction.atomic
def enqueue_mfa_key_rotation(
    *,
    requested_by: Account,
    source_version: int,
    target_version: int,
    now: datetime | None = None,
) -> EncryptionKeyRotationJob:
    queued_at = _checked_now(now)
    source = _checked_version(source_version, field="source_version")
    target = _checked_version(target_version, field="target_version")
    if source == target:
        raise ValidationError("rotation source and target versions must differ")
    ring = mfa_key_ring(required_versions=(source, target))
    if ring.active_version != target:
        raise ValidationError("rotation target must be the active MFA key version")
    existing = (
        EncryptionKeyRotationJob.objects.select_for_update()
        .filter(
            purpose=EncryptionKeyRotationJob.Purpose.MFA,
            source_key_version=source,
            target_key_version=target,
            status__in=_ACTIVE_STATUSES,
        )
        .first()
    )
    if existing is not None:
        return existing
    job = EncryptionKeyRotationJob.objects.create(
        purpose=EncryptionKeyRotationJob.Purpose.MFA,
        source_key_version=source,
        target_key_version=target,
        available_at=queued_at,
        requested_by=requested_by,
    )
    _audit_rotation(
        action="account.mfa_key_rotation.queued",
        job=job,
        metadata={"source_version": source, "target_version": target},
    )
    return job


def _claimable(now: datetime) -> models.QuerySet[EncryptionKeyRotationJob]:
    due = models.Q(
        status__in=(
            EncryptionKeyRotationJob.Status.PENDING,
            EncryptionKeyRotationJob.Status.RETRY_WAIT,
        ),
        available_at__lte=now,
    )
    expired = models.Q(
        status=EncryptionKeyRotationJob.Status.RUNNING,
        lease_expires_at__lte=now,
    )
    return (
        EncryptionKeyRotationJob.objects.filter(due | expired)
        .annotate(
            claim_ready_at=models.Case(
                models.When(
                    status=EncryptionKeyRotationJob.Status.RUNNING,
                    then=models.F("lease_expires_at"),
                ),
                default=models.F("available_at"),
                output_field=models.DateTimeField(),
            )
        )
        .order_by("claim_ready_at", "created_at", "rotation_id")
    )


@transaction.atomic
def claim_next_key_rotation(
    *,
    owner: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_ROTATION_LEASE,
) -> ClaimedKeyRotation | None:
    claimed_at = _checked_now(now)
    checked_owner = _checked_owner(owner)
    checked_lease = _checked_lease(lease_duration)
    while True:
        job = (
            _claimable(claimed_at)
            .select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
            .first()
        )
        if job is None:
            return None
        if job.status == EncryptionKeyRotationJob.Status.RUNNING:
            job.failure_count += 1
            if job.failure_count >= job.max_attempts:
                job.status = EncryptionKeyRotationJob.Status.FAILED_REVIEW
                job.completed_at = claimed_at
                job.last_error_code = "lease_attempts_exhausted"
                _clear_claim(job)
                job.save(
                    update_fields=[
                        "status",
                        "failure_count",
                        "completed_at",
                        "last_error_code",
                        "claim_token",
                        "claim_owner",
                        "heartbeat_at",
                        "lease_expires_at",
                        "updated_at",
                    ]
                )
                _audit_rotation(
                    action="account.mfa_key_rotation.failed_review",
                    job=job,
                    metadata={"error_code": job.last_error_code},
                )
                continue
        token = secrets.token_hex(32)
        job.status = EncryptionKeyRotationJob.Status.RUNNING
        job.attempt_count += 1
        job.claim_generation += 1
        job.claim_token = token
        job.claim_owner = checked_owner
        job.heartbeat_at = claimed_at
        job.lease_expires_at = claimed_at + checked_lease
        job.started_at = job.started_at or claimed_at
        job.completed_at = None
        job.last_error_code = ""
        job.save(
            update_fields=[
                "status",
                "attempt_count",
                "failure_count",
                "claim_generation",
                "claim_token",
                "claim_owner",
                "heartbeat_at",
                "lease_expires_at",
                "started_at",
                "completed_at",
                "last_error_code",
                "updated_at",
            ]
        )
        return ClaimedKeyRotation(
            job_id=job.pk,
            token=token,
            generation=job.claim_generation,
            owner=checked_owner,
        )


def _locked_job(job_id: UUID) -> EncryptionKeyRotationJob:
    job = EncryptionKeyRotationJob.objects.select_for_update().filter(pk=job_id).first()
    if job is None:
        raise KeyRotationClaimLost("rotation claim no longer exists")
    return job


def _assert_claim(
    job: EncryptionKeyRotationJob,
    claim: ClaimedKeyRotation,
    *,
    now: datetime,
) -> None:
    if (
        job.status != EncryptionKeyRotationJob.Status.RUNNING
        or job.claim_token != claim.token
        or job.claim_owner != claim.owner
        or job.claim_generation != claim.generation
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise KeyRotationClaimLost("rotation claim is stale or invalid")


def _authenticator_secret(authenticator: Authenticator) -> tuple[str, str]:
    field = {
        Authenticator.Type.TOTP: "secret",
        Authenticator.Type.RECOVERY_CODES: "seed",
    }.get(authenticator.type)
    data = authenticator.data
    ciphertext = data.get(field) if field is not None and isinstance(data, dict) else None
    if field is None or not isinstance(ciphertext, str):
        raise ValueError("authenticator ciphertext is invalid")
    return field, ciphertext


def _reencrypt_and_verify(
    *,
    ring: VersionedKeyRing,
    ciphertext: str,
    source_version: int,
    target_version: int,
) -> str | None:
    current_version = ring.ciphertext_version(ciphertext)
    if current_version != source_version:
        return None
    decrypted = ring.decrypt_text(ciphertext)
    replacement = ring.encrypt_text(decrypted.plaintext)
    try:
        verified = ring.decrypt_text(replacement)
    except KeyRingError as error:
        raise ValueError("authenticator re-encryption verification failed") from error
    if verified.key_version != target_version or not hmac.compare_digest(
        verified.plaintext,
        decrypted.plaintext,
    ):
        raise ValueError("authenticator re-encryption verification failed")
    return replacement


@transaction.atomic
def run_mfa_key_rotation_batch(
    claim: ClaimedKeyRotation,
    *,
    limit: int = 100,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_ROTATION_LEASE,
) -> KeyRotationBatchOutcome:
    processed_at = _checked_now(now)
    checked_limit = _checked_limit(
        limit,
        maximum=MAX_ROTATION_BATCH_SIZE,
        field="rotation batch limit",
    )
    checked_lease = _checked_lease(lease_duration)
    job = _locked_job(claim.job_id)
    _assert_claim(job, claim, now=processed_at)
    ring = mfa_key_ring(required_versions=(job.source_key_version, job.target_key_version))
    if ring.active_version != job.target_key_version:
        raise ValueError("rotation target is no longer the active MFA key version")
    authenticators = Authenticator.objects.filter(
        type__in=(Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES)
    ).order_by("pk")
    if job.cursor_authenticator_id is not None:
        authenticators = authenticators.filter(pk__gt=job.cursor_authenticator_id)
    # Cursor advancement must never jump over a temporarily locked authenticator.
    # The fenced job claim already guarantees one rotation worker for this request.
    authenticators = authenticators.select_for_update()
    batch = list(authenticators[:checked_limit])
    rotated = 0
    for authenticator in batch:
        field, ciphertext = _authenticator_secret(authenticator)
        replacement = _reencrypt_and_verify(
            ring=ring,
            ciphertext=ciphertext,
            source_version=job.source_key_version,
            target_version=job.target_key_version,
        )
        if replacement is not None:
            data = dict(authenticator.data)
            data[field] = replacement
            authenticator.data = data
            authenticator.save(update_fields=["data"])
            rotated += 1
        job.cursor_authenticator_id = authenticator.pk
    job.scanned_count += len(batch)
    job.processed_count += rotated
    job.heartbeat_at = processed_at
    job.lease_expires_at = processed_at + checked_lease
    if len(batch) < checked_limit:
        job.status = EncryptionKeyRotationJob.Status.COMPLETED
        job.completed_at = processed_at
        _clear_claim(job)
    job.save(
        update_fields=[
            "cursor_authenticator_id",
            "scanned_count",
            "processed_count",
            "heartbeat_at",
            "lease_expires_at",
            "status",
            "completed_at",
            "claim_token",
            "claim_owner",
            "updated_at",
        ]
    )
    _audit_rotation(
        action=(
            "account.mfa_key_rotation.completed"
            if job.status == EncryptionKeyRotationJob.Status.COMPLETED
            else "account.mfa_key_rotation.batch_committed"
        ),
        job=job,
        metadata={
            "batch_scanned": len(batch),
            "batch_rotated": rotated,
            "scanned_count": job.scanned_count,
            "processed_count": job.processed_count,
        },
    )
    return KeyRotationBatchOutcome(
        **_outcome(job).__dict__,
        batch_scanned_count=len(batch),
        batch_rotated_count=rotated,
    )


@transaction.atomic
def release_key_rotation_claim(
    claim: ClaimedKeyRotation,
    *,
    now: datetime | None = None,
) -> KeyRotationOutcome:
    released_at = _checked_now(now)
    job = _locked_job(claim.job_id)
    _assert_claim(job, claim, now=released_at)
    job.status = EncryptionKeyRotationJob.Status.PENDING
    job.available_at = released_at
    job.last_error_code = "graceful_shutdown"
    _clear_claim(job)
    job.save(
        update_fields=[
            "status",
            "available_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return _outcome(job)


@transaction.atomic
def settle_key_rotation_failure(
    claim: ClaimedKeyRotation,
    *,
    error_code: str,
    now: datetime | None = None,
) -> KeyRotationOutcome:
    settled_at = _checked_now(now)
    if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
        raise ValidationError("rotation error code is invalid")
    job = _locked_job(claim.job_id)
    _assert_claim(job, claim, now=settled_at)
    job.failure_count += 1
    job.last_error_code = error_code
    if job.failure_count >= job.max_attempts:
        job.status = EncryptionKeyRotationJob.Status.FAILED_REVIEW
        job.completed_at = settled_at
    else:
        job.status = EncryptionKeyRotationJob.Status.RETRY_WAIT
        job.available_at = settled_at + timedelta(
            seconds=min(30 * (2 ** (job.failure_count - 1)), 15 * 60)
        )
    _clear_claim(job)
    job.save(
        update_fields=[
            "status",
            "failure_count",
            "last_error_code",
            "completed_at",
            "available_at",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit_rotation(
        action=(
            "account.mfa_key_rotation.failed_review"
            if job.status == EncryptionKeyRotationJob.Status.FAILED_REVIEW
            else "account.mfa_key_rotation.retry_scheduled"
        ),
        job=job,
        metadata={"error_code": error_code, "failure_count": job.failure_count},
    )
    return _outcome(job)


def _ciphertext_version(ciphertext: object) -> int | None:
    if not isinstance(ciphertext, str) or not ciphertext.startswith("v"):
        return None
    prefix, separator, _payload = ciphertext.partition(".")
    if not separator or not prefix[1:].isdigit() or prefix[1:].startswith("0"):
        return None
    return int(prefix[1:])


def _authenticator_dependency_count(key_version: int) -> int:
    count = 0
    rows = Authenticator.objects.filter(
        type__in=(Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES)
    ).values_list("type", "data")
    for authenticator_type, data in rows.iterator():
        field = "secret" if authenticator_type == Authenticator.Type.TOTP else "seed"
        if isinstance(data, dict) and _ciphertext_version(data.get(field)) == key_version:
            count += 1
    return count


def _backup_required_versions(purpose: str) -> frozenset[int]:
    if not apps.is_installed("mnemex.recovery"):
        return frozenset()
    manifest_model = apps.get_model("recovery", "RecoveryManifest")
    field = (
        "required_mfa_key_versions" if purpose == "mfa" else "required_notification_key_versions"
    )
    required: set[int] = set()
    for versions in manifest_model.objects.values_list(field, flat=True).iterator():
        if isinstance(versions, list):
            required.update(version for version in versions if isinstance(version, int))
    return frozenset(required)


def required_key_versions(*, purpose: str) -> frozenset[int]:
    if purpose not in {"mfa", "notification"}:
        raise ValidationError("key purpose is invalid")
    required = set(_backup_required_versions(purpose))
    active_setting = (
        "MNEMEX_MFA_ACTIVE_KEY_VERSION"
        if purpose == "mfa"
        else "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION"
    )
    active_version = getattr(settings, active_setting, None)
    if isinstance(active_version, int) and not isinstance(active_version, bool):
        required.add(active_version)
    if purpose == "mfa":
        rows = Authenticator.objects.filter(
            type__in=(Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES)
        ).values_list("type", "data")
        for authenticator_type, data in rows.iterator():
            field = "secret" if authenticator_type == Authenticator.Type.TOTP else "seed"
            version = _ciphertext_version(data.get(field) if isinstance(data, dict) else None)
            if version is None:
                raise ImproperlyConfigured("MFA authenticator ciphertext version is invalid")
            required.add(version)
        for source, target in EncryptionKeyRotationJob.objects.filter(
            status__in=_ACTIVE_STATUSES
        ).values_list("source_key_version", "target_key_version"):
            required.update((source, target))
    else:
        required.update(
            SecurityNotification.objects.exclude(recipient_ciphertext="").values_list(
                "encryption_key_version",
                flat=True,
            )
        )
    return frozenset(required)


def assert_configured_key_versions_available(*, purpose: str) -> None:
    keys_setting = (
        "MNEMEX_MFA_ENCRYPTION_KEYS" if purpose == "mfa" else "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS"
    )
    label = "MFA" if purpose == "mfa" else "notification"
    keys = getattr(settings, keys_setting, {})
    if not isinstance(keys, Mapping):
        raise ImproperlyConfigured(f"{label} encryption is not configured")
    available = {
        version
        for version in keys
        if isinstance(version, int) and not isinstance(version, bool) and version >= 1
    }
    if not required_key_versions(purpose=purpose).issubset(available):
        raise ImproperlyConfigured(f"required {label} encryption key is unavailable")


def key_retirement_blockers(*, purpose: str, key_version: int) -> tuple[KeyRetirementBlocker, ...]:
    version = _checked_version(key_version, field="key_version")
    if purpose not in {"mfa", "notification"}:
        raise ValidationError("key purpose is invalid")
    blockers: list[KeyRetirementBlocker] = []
    active_setting = (
        "MNEMEX_MFA_ACTIVE_KEY_VERSION"
        if purpose == "mfa"
        else "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION"
    )
    if getattr(settings, active_setting, None) == version:
        blockers.append(KeyRetirementBlocker(code="active_key_version", count=1))
    if purpose == "mfa":
        authenticator_count = _authenticator_dependency_count(version)
        if authenticator_count:
            blockers.append(
                KeyRetirementBlocker(
                    code="authenticator_ciphertext",
                    count=authenticator_count,
                )
            )
        active_jobs = EncryptionKeyRotationJob.objects.filter(
            status__in=_ACTIVE_STATUSES,
        ).filter(models.Q(source_key_version=version) | models.Q(target_key_version=version))
        active_job_count = active_jobs.count()
        if active_job_count:
            blockers.append(
                KeyRetirementBlocker(code="active_rotation_job", count=active_job_count)
            )
    else:
        notification_count = (
            SecurityNotification.objects.filter(
                encryption_key_version=version,
            )
            .exclude(recipient_ciphertext="")
            .count()
        )
        if notification_count:
            blockers.append(
                KeyRetirementBlocker(
                    code="notification_ciphertext",
                    count=notification_count,
                )
            )
    if version in _backup_required_versions(purpose):
        blockers.append(KeyRetirementBlocker(code="backup_evidence", count=1))
    return tuple(sorted(blockers, key=lambda blocker: blocker.code))


def assert_key_version_retirable(*, purpose: str, key_version: int) -> None:
    blockers = key_retirement_blockers(purpose=purpose, key_version=key_version)
    if blockers:
        codes = ",".join(blocker.code for blocker in blockers)
        raise KeyRetirementBlocked(f"encryption key cannot be retired: {codes}")
