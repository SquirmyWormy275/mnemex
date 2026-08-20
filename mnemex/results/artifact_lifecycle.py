from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from mnemex.partners.models import PartnerOrganization
from mnemex.results.artifacts import (
    ArtifactCollisionError,
    PrivateArtifactStore,
    artifact_reference_for,
)
from mnemex.results.models import ArtifactObject, ArtifactObjectWrite, SourceArtifact

DEFAULT_WRITE_LEASE = timedelta(minutes=15)
DEFAULT_CLEANUP_GRACE = timedelta(minutes=5)
MAX_UNRESOLVED_WRITES_PER_OBJECT = 1000
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class _ReconciliationResult(str, Enum):
    CLEANED = "cleaned"
    PRESERVED = "preserved"
    BLOCKED = "blocked"
    SKIPPED_ACTIVE = "skipped_active"


@dataclass(frozen=True)
class ArtifactReconciliationOutcome:
    examined: int = 0
    cleaned: int = 0
    preserved: int = 0
    blocked: int = 0
    skipped_active: int = 0


def _now(value: datetime | None) -> datetime:
    return value or timezone.now()


def _positive_duration(value: timedelta, *, label: str, allow_zero: bool = False) -> None:
    minimum = timedelta(0)
    if value < minimum or (not allow_zero and value == minimum):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValidationError(f"{label} must be {qualifier}")


def _safe_error_code(value: str) -> str:
    if not _ERROR_CODE.fullmatch(value):
        raise ValidationError("artifact lifecycle error code is invalid")
    return value


@transaction.atomic
def begin_artifact_write(
    *,
    organization: PartnerOrganization,
    content: bytes,
    filename: str,
    now: datetime | None = None,
    write_lease: timedelta = DEFAULT_WRITE_LEASE,
) -> ArtifactObjectWrite:
    """Register a write lease before bytes enter the shared object namespace."""

    _positive_duration(write_lease, label="artifact write lease")
    current_time = _now(now)
    reference = artifact_reference_for(content=content, filename=filename)
    digest = hashlib.sha256(content).hexdigest()
    artifact_object, created = ArtifactObject.objects.select_for_update().get_or_create(
        object_reference=reference,
        defaults={"digest": digest, "byte_size": len(content)},
    )
    if not created and (
        not hmac.compare_digest(artifact_object.digest, digest)
        or artifact_object.byte_size != len(content)
    ):
        raise ValidationError("artifact object registry does not match the upload bytes")
    return ArtifactObjectWrite.objects.create(
        organization=organization,
        artifact_object=artifact_object,
        reconcile_after=current_time + write_lease,
    )


def install_registered_artifact(
    *,
    store: PrivateArtifactStore,
    organization: PartnerOrganization,
    content: bytes,
    filename: str,
    now: datetime | None = None,
    write_lease: timedelta = DEFAULT_WRITE_LEASE,
) -> ArtifactObjectWrite:
    """Register request ownership, then install bytes in the shared namespace."""

    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename=filename,
        now=now,
        write_lease=write_lease,
    )
    try:
        with transaction.atomic():
            current = _locked_attempt(attempt)
            current_time = _now(now)
            if current.status != ArtifactObjectWrite.Status.ACTIVE:
                raise ValidationError("artifact write is no longer active")
            if current.reconcile_after <= current_time:
                raise ValidationError("artifact write lease expired before object installation")
            object_reference = store.put(content=content, filename=filename)
            if object_reference != current.artifact_object.object_reference:
                raise ValidationError("artifact store returned an unexpected object reference")
            current.reconcile_after = current_time + write_lease
            current.save(
                update_fields=("reconcile_after", "updated_at"),
                _lifecycle_transition=True,
            )
            attempt = current
    except Exception:
        abandon_artifact_write(
            attempt=attempt,
            error_code="object_install_failed",
            now=now,
        )
        raise
    return attempt


def _locked_attempt(attempt: ArtifactObjectWrite) -> ArtifactObjectWrite:
    ArtifactObject.objects.select_for_update().get(pk=attempt.artifact_object_id)
    return (
        ArtifactObjectWrite.objects.select_for_update()
        .select_related("artifact_object")
        .get(pk=attempt.pk)
    )


def lock_artifact_write(attempt: ArtifactObjectWrite) -> ArtifactObjectWrite:
    """Fence provenance creation behind the registry row in the caller transaction."""

    if not connection.in_atomic_block:
        raise ValidationError("artifact write locking requires an active transaction")
    return _locked_attempt(attempt)


@transaction.atomic
def complete_artifact_write(
    *,
    attempt: ArtifactObjectWrite,
    artifact: SourceArtifact,
    now: datetime | None = None,
) -> ArtifactObjectWrite:
    """Atomically bind one active write attempt to immutable database provenance."""

    current_time = _now(now)
    current = _locked_attempt(attempt)
    if current.status == ArtifactObjectWrite.Status.LINKED:
        if current.source_artifact_id != artifact.pk:
            raise ValidationError("artifact write is already linked to different provenance")
        return current
    if current.status != ArtifactObjectWrite.Status.ACTIVE:
        raise ValidationError("artifact write is no longer active")
    if current.reconcile_after <= current_time:
        raise ValidationError("artifact write lease expired before provenance commit")
    if artifact.organization_id != current.organization_id:
        raise ValidationError("artifact write organization does not match source artifact")
    artifact_object = current.artifact_object
    if (
        not hmac.compare_digest(artifact.digest, artifact_object.digest)
        or artifact.object_reference != artifact_object.object_reference
        or artifact.byte_size != artifact_object.byte_size
    ):
        raise ValidationError("source artifact does not match the registered object")
    current.status = ArtifactObjectWrite.Status.LINKED
    current.source_artifact = artifact
    current.error_code = ""
    current.reconcile_after = current_time
    current.resolved_at = current_time
    current.save(
        update_fields=(
            "status",
            "source_artifact",
            "error_code",
            "reconcile_after",
            "resolved_at",
            "updated_at",
        ),
        _lifecycle_transition=True,
    )
    return current


@transaction.atomic
def abandon_artifact_write(
    *,
    attempt: ArtifactObjectWrite,
    error_code: str,
    now: datetime | None = None,
    cleanup_grace: timedelta = DEFAULT_CLEANUP_GRACE,
) -> ArtifactObjectWrite:
    """End request ownership without deleting a potentially shared object."""

    _positive_duration(cleanup_grace, label="artifact cleanup grace", allow_zero=True)
    current_time = _now(now)
    current = _locked_attempt(attempt)
    if current.status != ArtifactObjectWrite.Status.ACTIVE:
        return current
    current.status = ArtifactObjectWrite.Status.ABANDONED
    current.error_code = _safe_error_code(error_code)
    current.reconcile_after = current_time + cleanup_grace
    current.resolved_at = current_time
    current.save(
        update_fields=(
            "status",
            "error_code",
            "reconcile_after",
            "resolved_at",
            "updated_at",
        ),
        _lifecycle_transition=True,
    )
    return current


def _resolve_attempts(
    attempts: list[ArtifactObjectWrite],
    *,
    status: ArtifactObjectWrite.Status,
    error_code: str,
    now: datetime,
    source_artifact: SourceArtifact | None = None,
) -> None:
    if status == ArtifactObjectWrite.Status.LINKED:
        if source_artifact is None:
            raise ValidationError("linked artifact attempts require source provenance")
    elif source_artifact is not None:
        raise ValidationError("only linked artifact attempts may receive source provenance")
    for attempt in attempts:
        attempt.status = status
        attempt.source_artifact = source_artifact
        if status != ArtifactObjectWrite.Status.CLEANED or not attempt.error_code:
            attempt.error_code = error_code
        attempt.reconcile_after = now
        attempt.resolved_at = now
        attempt.save(
            update_fields=(
                "status",
                "source_artifact",
                "error_code",
                "reconcile_after",
                "resolved_at",
                "updated_at",
            ),
            _lifecycle_transition=True,
        )


def _reconcile_one(
    *,
    object_id: UUID,
    store: PrivateArtifactStore,
    now: datetime,
) -> _ReconciliationResult:
    with transaction.atomic():
        artifact_object = ArtifactObject.objects.select_for_update().get(pk=object_id)
        attempts = list(
            ArtifactObjectWrite.objects.select_for_update()
            .filter(
                artifact_object=artifact_object,
                status__in=(
                    ArtifactObjectWrite.Status.ACTIVE,
                    ArtifactObjectWrite.Status.ABANDONED,
                ),
            )
            .order_by("created_at", "write_id")[: MAX_UNRESOLVED_WRITES_PER_OBJECT + 1]
        )
        if not attempts:
            return _ReconciliationResult.PRESERVED
        if any(
            attempt.status == ArtifactObjectWrite.Status.ACTIVE and attempt.reconcile_after > now
            for attempt in attempts
        ):
            return _ReconciliationResult.SKIPPED_ACTIVE
        if len(attempts) > MAX_UNRESOLVED_WRITES_PER_OBJECT:
            _resolve_attempts(
                attempts[:MAX_UNRESOLVED_WRITES_PER_OBJECT],
                status=ArtifactObjectWrite.Status.BLOCKED,
                error_code="unresolved_write_limit_exceeded",
                now=now,
            )
            return _ReconciliationResult.BLOCKED
        for attempt in attempts:
            if attempt.status == ArtifactObjectWrite.Status.ACTIVE:
                attempt.error_code = "write_lease_expired"

        source_artifacts = SourceArtifact.objects.filter(
            organization_id__in={attempt.organization_id for attempt in attempts},
            digest=artifact_object.digest,
            object_reference=artifact_object.object_reference,
            byte_size=artifact_object.byte_size,
        ).order_by("organization_id", "received_at", "artifact_id")
        source_by_organization: dict[UUID, SourceArtifact] = {}
        for source_artifact in source_artifacts:
            source_by_organization.setdefault(
                source_artifact.organization_id,
                source_artifact,
            )
        source_artifact_exists = bool(source_by_organization)
        try:
            content = store.read(reference=artifact_object.object_reference)
        except FileNotFoundError:
            if source_artifact_exists:
                _resolve_attempts(
                    attempts,
                    status=ArtifactObjectWrite.Status.BLOCKED,
                    error_code="referenced_object_missing",
                    now=now,
                )
                return _ReconciliationResult.BLOCKED
            _resolve_attempts(
                attempts,
                status=ArtifactObjectWrite.Status.CLEANED,
                error_code="object_absent",
                now=now,
            )
            return _ReconciliationResult.CLEANED
        except ArtifactCollisionError:
            _resolve_attempts(
                attempts,
                status=ArtifactObjectWrite.Status.BLOCKED,
                error_code="object_digest_mismatch",
                now=now,
            )
            return _ReconciliationResult.BLOCKED
        except OSError:
            _resolve_attempts(
                attempts,
                status=ArtifactObjectWrite.Status.BLOCKED,
                error_code="object_read_failed",
                now=now,
            )
            return _ReconciliationResult.BLOCKED

        actual_digest = hashlib.sha256(content).hexdigest()
        if (
            not hmac.compare_digest(actual_digest, artifact_object.digest)
            or len(content) != artifact_object.byte_size
        ):
            _resolve_attempts(
                attempts,
                status=ArtifactObjectWrite.Status.BLOCKED,
                error_code="object_digest_mismatch",
                now=now,
            )
            return _ReconciliationResult.BLOCKED
        if source_artifact_exists:
            for attempt in attempts:
                tenant_source_artifact = source_by_organization.get(attempt.organization_id)
                if tenant_source_artifact is not None:
                    _resolve_attempts(
                        [attempt],
                        status=ArtifactObjectWrite.Status.LINKED,
                        error_code="",
                        now=now,
                        source_artifact=tenant_source_artifact,
                    )
                else:
                    _resolve_attempts(
                        [attempt],
                        status=ArtifactObjectWrite.Status.PRESERVED,
                        error_code="shared_object_is_referenced",
                        now=now,
                    )
            return _ReconciliationResult.PRESERVED
        if not store.remove_if_exact(
            reference=artifact_object.object_reference,
            content=content,
        ):
            _resolve_attempts(
                attempts,
                status=ArtifactObjectWrite.Status.BLOCKED,
                error_code="object_changed_during_cleanup",
                now=now,
            )
            return _ReconciliationResult.BLOCKED
        _resolve_attempts(
            attempts,
            status=ArtifactObjectWrite.Status.CLEANED,
            error_code="orphan_object_removed",
            now=now,
        )
        return _ReconciliationResult.CLEANED


def reconcile_artifact_objects(
    *,
    store: PrivateArtifactStore,
    now: datetime | None = None,
    limit: int = 100,
) -> ArtifactReconciliationOutcome:
    """Reconcile expired writes in bounded registry-locked batches."""

    if limit < 1 or limit > 1000:
        raise ValidationError("artifact reconciliation limit must be from 1 to 1000")
    current_time = _now(now)
    object_ids = list(
        ArtifactObjectWrite.objects.filter(
            status__in=(
                ArtifactObjectWrite.Status.ACTIVE,
                ArtifactObjectWrite.Status.ABANDONED,
            ),
            reconcile_after__lte=current_time,
        )
        .order_by("artifact_object_id")
        .values_list("artifact_object_id", flat=True)
        .distinct()[:limit]
    )
    counts: Counter[_ReconciliationResult] = Counter()
    for object_id in object_ids:
        result = _reconcile_one(object_id=object_id, store=store, now=current_time)
        counts[result] += 1
    return ArtifactReconciliationOutcome(
        examined=len(object_ids),
        cleaned=counts[_ReconciliationResult.CLEANED],
        preserved=counts[_ReconciliationResult.PRESERVED],
        blocked=counts[_ReconciliationResult.BLOCKED],
        skipped_active=counts[_ReconciliationResult.SKIPPED_ACTIVE],
    )
