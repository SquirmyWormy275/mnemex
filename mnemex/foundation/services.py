from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from mnemex.foundation.models import AuditEvent, IdempotencyRecord

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_AUDIT_KEYS = {
    "date_of_birth",
    "email",
    "legal_name",
    "password",
    "secret",
    "token",
}


class IdempotencyConflict(ValueError):
    """The same idempotency key was reused for a different payload."""


def _validate_digest(value: str) -> None:
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError("payload digest must be 64 lowercase hexadecimal characters")


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _SENSITIVE_AUDIT_KEYS:
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def record_audit_event(
    *,
    action: str,
    target_type: str,
    target_id: str,
    payload_digest: str,
    metadata: dict[str, Any] | None = None,
    actor_id: UUID | None = None,
    correlation_id: UUID | None = None,
) -> AuditEvent:
    safe_metadata = metadata or {}
    _validate_digest(payload_digest)
    if _contains_sensitive_key(safe_metadata):
        raise ValueError("sensitive audit metadata is not permitted")
    values: dict[str, Any] = {
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "payload_digest": payload_digest,
        "metadata": safe_metadata,
    }
    if correlation_id is not None:
        values["correlation_id"] = correlation_id
    return AuditEvent.objects.create(**values)


@transaction.atomic
def claim_idempotency(
    *, scope: str, key: str, request_digest: str
) -> tuple[IdempotencyRecord, bool]:
    _validate_digest(request_digest)
    try:
        record = IdempotencyRecord.objects.select_for_update().get(scope=scope, key=key)
        created = False
    except IdempotencyRecord.DoesNotExist:
        try:
            # The savepoint keeps a uniqueness race from poisoning the outer
            # service transaction before the winning row can be read.
            with transaction.atomic():
                record = IdempotencyRecord.objects.create(
                    scope=scope, key=key, request_digest=request_digest
                )
            created = True
        except IntegrityError:
            record = IdempotencyRecord.objects.select_for_update().get(scope=scope, key=key)
            created = False

    if record.request_digest != request_digest:
        raise IdempotencyConflict("idempotency key was already claimed for a different payload")
    return record, created
