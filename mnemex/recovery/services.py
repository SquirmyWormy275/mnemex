from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from django.core.exceptions import ValidationError
from django.utils import timezone

RECOVERY_CONTRACT_VERSION = "mnemex.recovery-rehearsal.v1"
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_TARGET_ID = re.compile(r"^mnemex-rehearsal-(?P<suffix>[a-z0-9][a-z0-9-]{7,63})$")
_OBJECT_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
_ISSUE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class UnsafeRecoveryTargetError(RuntimeError):
    """The requested target is not provably disposable and isolated."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _checked_digest(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _HEX_DIGEST.fullmatch(value):
        raise ValidationError({field: "Expected a lowercase SHA-256 digest"})
    return value


def _checked_safe_id(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValidationError({field: "Expected a non-secret stable identifier"})
    return value


def _checked_versions(values: Sequence[int], *, field: str) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise ValidationError({field: "Expected positive integer key versions"})
    normalized: set[int] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError({field: "Expected positive integer key versions"})
        normalized.add(value)
    if not normalized:
        raise ValidationError({field: "At least one required key version is needed"})
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class ObjectInventoryEntry:
    """One opaque object identity without tenant or original-filename data."""

    reference: str
    digest: str
    byte_size: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reference, str)
            or not _OBJECT_REFERENCE.fullmatch(self.reference)
            or self.reference.startswith("/")
            or ".." in self.reference.split("/")
            or "//" in self.reference
        ):
            raise ValidationError({"reference": "Object reference must be opaque and relative"})
        _checked_digest(self.digest, field="digest")
        if isinstance(self.byte_size, bool) or not isinstance(self.byte_size, int):
            raise ValidationError({"byte_size": "Object byte size must be a non-negative integer"})
        if self.byte_size < 0:
            raise ValidationError({"byte_size": "Object byte size must be a non-negative integer"})

    def canonical_record(self) -> dict[str, object]:
        return {
            "byte_size": self.byte_size,
            "digest": self.digest,
            "reference": self.reference,
        }


def canonical_object_inventory_digest(objects: Sequence[ObjectInventoryEntry]) -> str:
    entries = sorted(objects, key=lambda entry: entry.reference)
    references = [entry.reference for entry in entries]
    if len(references) != len(set(references)):
        raise ValidationError("duplicate object reference in recovery inventory")
    return _sha256([entry.canonical_record() for entry in entries])


@dataclass(frozen=True)
class RecoveryManifestPayload:
    database_snapshot_identity: str
    object_inventory_digest: str
    object_count: int
    required_mfa_key_versions: tuple[int, ...]
    required_notification_key_versions: tuple[int, ...]
    application_schema_version: str
    environment_fingerprint: str
    payload_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "database_snapshot_identity",
            _checked_safe_id(
                self.database_snapshot_identity,
                field="database_snapshot_identity",
            ),
        )
        _checked_digest(self.object_inventory_digest, field="object_inventory_digest")
        if (
            isinstance(self.object_count, bool)
            or not isinstance(self.object_count, int)
            or self.object_count < 0
        ):
            raise ValidationError({"object_count": "Object count must be non-negative"})
        object.__setattr__(
            self,
            "required_mfa_key_versions",
            _checked_versions(
                self.required_mfa_key_versions,
                field="required_mfa_key_versions",
            ),
        )
        object.__setattr__(
            self,
            "required_notification_key_versions",
            _checked_versions(
                self.required_notification_key_versions,
                field="required_notification_key_versions",
            ),
        )
        object.__setattr__(
            self,
            "application_schema_version",
            _checked_safe_id(
                self.application_schema_version,
                field="application_schema_version",
            ),
        )
        _checked_digest(self.environment_fingerprint, field="environment_fingerprint")
        if self.payload_digest:
            _checked_digest(self.payload_digest, field="payload_digest")

    @classmethod
    def build(
        cls,
        *,
        database_snapshot_identity: str,
        objects: Sequence[ObjectInventoryEntry],
        required_mfa_key_versions: Sequence[int],
        required_notification_key_versions: Sequence[int],
        application_schema_version: str,
        environment_fingerprint: str,
    ) -> RecoveryManifestPayload:
        payload = cls(
            database_snapshot_identity=database_snapshot_identity,
            object_inventory_digest=canonical_object_inventory_digest(objects),
            object_count=len(objects),
            required_mfa_key_versions=tuple(required_mfa_key_versions),
            required_notification_key_versions=tuple(required_notification_key_versions),
            application_schema_version=application_schema_version,
            environment_fingerprint=environment_fingerprint,
        )
        return cls(
            database_snapshot_identity=payload.database_snapshot_identity,
            object_inventory_digest=payload.object_inventory_digest,
            object_count=payload.object_count,
            required_mfa_key_versions=payload.required_mfa_key_versions,
            required_notification_key_versions=payload.required_notification_key_versions,
            application_schema_version=payload.application_schema_version,
            environment_fingerprint=payload.environment_fingerprint,
            payload_digest=manifest_payload_digest(payload),
        )

    @classmethod
    def from_dict(cls, value: object) -> RecoveryManifestPayload:
        if not isinstance(value, dict):
            raise ValidationError("Recovery manifest must be a JSON object")
        expected = {
            "database_snapshot_identity",
            "object_inventory_digest",
            "object_count",
            "required_mfa_key_versions",
            "required_notification_key_versions",
            "application_schema_version",
            "environment_fingerprint",
            "payload_digest",
        }
        if set(value) != expected:
            raise ValidationError("Recovery manifest fields do not match the v1 contract")
        try:
            required_mfa_key_versions = tuple(value["required_mfa_key_versions"])
            required_notification_key_versions = tuple(value["required_notification_key_versions"])
        except TypeError as error:
            raise ValidationError("Recovery manifest key versions must be arrays") from error
        payload = cls(
            database_snapshot_identity=value["database_snapshot_identity"],
            object_inventory_digest=value["object_inventory_digest"],
            object_count=value["object_count"],
            required_mfa_key_versions=required_mfa_key_versions,
            required_notification_key_versions=required_notification_key_versions,
            application_schema_version=value["application_schema_version"],
            environment_fingerprint=value["environment_fingerprint"],
            payload_digest=value["payload_digest"],
        )
        payload.verify()
        return payload

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "application_schema_version": self.application_schema_version,
            "database_snapshot_identity": self.database_snapshot_identity,
            "environment_fingerprint": self.environment_fingerprint,
            "object_count": self.object_count,
            "object_inventory_digest": self.object_inventory_digest,
            "required_mfa_key_versions": list(self.required_mfa_key_versions),
            "required_notification_key_versions": list(self.required_notification_key_versions),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "payload_digest": self.payload_digest}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def verify(self) -> None:
        if not self.payload_digest or not hmac.compare_digest(
            self.payload_digest,
            manifest_payload_digest(self),
        ):
            raise ValidationError({"payload_digest": "Recovery manifest payload digest differs"})


def manifest_payload_digest(manifest: RecoveryManifestPayload) -> str:
    return _sha256(manifest.unsigned_dict())


@dataclass(frozen=True)
class RecoveryTarget:
    target_id: str
    environment_kind: str
    database_name: str
    object_namespace: str
    environment_fingerprint: str

    def validate(self, *, expected_environment_fingerprint: str | None = None) -> None:
        match = _TARGET_ID.fullmatch(self.target_id) if isinstance(self.target_id, str) else None
        if match is None or self.environment_kind != "disposable":
            raise UnsafeRecoveryTargetError("recovery target is not explicitly disposable")
        suffix = match.group("suffix")
        expected_database = f"mnemex_rehearsal_{suffix.replace('-', '_')}"
        expected_namespace = f"mnemex-rehearsal/{suffix}"
        if self.database_name != expected_database:
            raise UnsafeRecoveryTargetError("recovery database is outside the disposable target")
        if self.object_namespace != expected_namespace:
            raise UnsafeRecoveryTargetError("recovery objects are outside the disposable target")
        try:
            _checked_digest(self.environment_fingerprint, field="environment_fingerprint")
        except ValidationError as error:
            raise UnsafeRecoveryTargetError(
                "recovery environment fingerprint is invalid"
            ) from error
        if expected_environment_fingerprint is not None and not hmac.compare_digest(
            self.environment_fingerprint,
            expected_environment_fingerprint,
        ):
            raise UnsafeRecoveryTargetError("recovery target environment does not match manifest")


@dataclass(frozen=True)
class DatabaseRecoveryInventory:
    snapshot_identity: str
    application_schema_version: str
    environment_fingerprint: str

    def __post_init__(self) -> None:
        _checked_safe_id(self.snapshot_identity, field="snapshot_identity")
        _checked_safe_id(
            self.application_schema_version,
            field="application_schema_version",
        )
        _checked_digest(self.environment_fingerprint, field="environment_fingerprint")


@dataclass(frozen=True)
class LeaseInventoryEntry:
    queue: str
    lease_id: str
    status: str
    lease_expires_at: datetime | None
    terminal: bool

    def __post_init__(self) -> None:
        _checked_safe_id(self.queue, field="queue")
        _checked_safe_id(self.lease_id, field="lease_id")
        _checked_safe_id(self.status, field="status")
        if self.lease_expires_at is not None and timezone.is_naive(self.lease_expires_at):
            raise ValidationError({"lease_expires_at": "Lease time must be timezone-aware"})
        if not isinstance(self.terminal, bool):
            raise ValidationError({"terminal": "Lease terminal marker must be boolean"})
        if self.status == "running" and self.terminal:
            raise ValidationError({"terminal": "A running lease cannot be terminal"})

    def is_expired_running(self, *, observed_at: datetime) -> bool:
        return (
            self.status == "running"
            and not self.terminal
            and self.lease_expires_at is not None
            and self.lease_expires_at <= observed_at
        )


class RecoveryBackend(Protocol):
    """Provider boundary; implementations are always bound to one exact target."""

    def inspect_pristine(self, *, target: RecoveryTarget) -> bool: ...

    def restore_database(
        self, *, target: RecoveryTarget, snapshot_identity: str
    ) -> Sequence[str]: ...

    def restore_objects(
        self,
        *,
        target: RecoveryTarget,
        objects: Sequence[ObjectInventoryEntry],
    ) -> Sequence[str]: ...

    def database_inventory(self, *, target: RecoveryTarget) -> DatabaseRecoveryInventory: ...

    def object_inventory(self, *, target: RecoveryTarget) -> Sequence[ObjectInventoryEntry]: ...

    def available_mfa_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]: ...

    def available_notification_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]: ...

    def lease_inventory(self, *, target: RecoveryTarget) -> Sequence[LeaseInventoryEntry]: ...

    def normalize_expired_leases(
        self,
        *,
        target: RecoveryTarget,
        leases: Sequence[LeaseInventoryEntry],
        observed_at: datetime,
    ) -> int: ...

    def reconcile_application(self, *, target: RecoveryTarget) -> Sequence[str]: ...

    def cleanup(
        self,
        *,
        target: RecoveryTarget,
        created_resources: Sequence[str],
    ) -> None: ...


@dataclass(frozen=True)
class RecoveryRehearsalEvidence:
    result: str
    manifest_digest: str
    environment_fingerprint: str
    object_count: int
    normalized_lease_count: int
    issue_codes: tuple[str, ...]
    evidence_digest: str

    def to_redacted_dict(self) -> dict[str, object]:
        return {
            "contract_version": RECOVERY_CONTRACT_VERSION,
            "environment_fingerprint": self.environment_fingerprint,
            "evidence_digest": self.evidence_digest,
            "issue_codes": list(self.issue_codes),
            "manifest_digest": self.manifest_digest,
            "normalized_lease_count": self.normalized_lease_count,
            "object_count": self.object_count,
            "result": self.result,
        }

    def to_redacted_json(self) -> str:
        return _canonical_json(self.to_redacted_dict())


def _checked_issue_codes(codes: Sequence[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for code in codes:
        if not isinstance(code, str) or not _ISSUE_CODE.fullmatch(code):
            raise ValidationError("Application reconciliation returned an unsafe issue code")
        normalized.add(code)
    return tuple(sorted(normalized))


def recovery_rehearsal_evidence_digest(
    *,
    result: str,
    manifest_digest: str,
    environment_fingerprint: str,
    object_count: int,
    normalized_lease_count: int,
    issue_codes: Sequence[str],
) -> str:
    checked_codes = _checked_issue_codes(issue_codes)
    expected_result = "pass" if not checked_codes else "fail"
    if result != expected_result:
        raise ValidationError("Recovery result differs from its issue codes")
    _checked_digest(manifest_digest, field="manifest_digest")
    _checked_digest(environment_fingerprint, field="environment_fingerprint")
    for field, value in (
        ("object_count", object_count),
        ("normalized_lease_count", normalized_lease_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError({field: "Recovery evidence counts must be non-negative"})
    return _sha256(
        {
            "contract_version": RECOVERY_CONTRACT_VERSION,
            "environment_fingerprint": environment_fingerprint,
            "issue_codes": list(checked_codes),
            "manifest_digest": manifest_digest,
            "normalized_lease_count": normalized_lease_count,
            "object_count": object_count,
            "result": result,
        }
    )


def _evidence(
    *,
    manifest: RecoveryManifestPayload,
    issue_codes: Sequence[str],
    normalized_lease_count: int,
) -> RecoveryRehearsalEvidence:
    checked_codes = _checked_issue_codes(issue_codes)
    result = "pass" if not checked_codes else "fail"
    return RecoveryRehearsalEvidence(
        result=result,
        manifest_digest=manifest.payload_digest,
        environment_fingerprint=manifest.environment_fingerprint,
        object_count=manifest.object_count,
        normalized_lease_count=normalized_lease_count,
        issue_codes=checked_codes,
        evidence_digest=recovery_rehearsal_evidence_digest(
            result=result,
            manifest_digest=manifest.payload_digest,
            environment_fingerprint=manifest.environment_fingerprint,
            object_count=manifest.object_count,
            normalized_lease_count=normalized_lease_count,
            issue_codes=checked_codes,
        ),
    )


def run_recovery_rehearsal(
    *,
    target: RecoveryTarget,
    manifest: RecoveryManifestPayload,
    objects: Sequence[ObjectInventoryEntry],
    backend: RecoveryBackend,
    observed_at: datetime | None = None,
    cleanup: bool = True,
) -> RecoveryRehearsalEvidence:
    """Restore and reconcile one new disposable target, then remove only that target."""

    target.validate(expected_environment_fingerprint=manifest.environment_fingerprint)
    manifest.verify()
    if observed_at is not None and timezone.is_naive(observed_at):
        raise ValidationError("Recovery observation time must be timezone-aware")
    checked_at = observed_at or timezone.now()
    expected_object_digest = canonical_object_inventory_digest(objects)
    if len(objects) != manifest.object_count or not hmac.compare_digest(
        expected_object_digest, manifest.object_inventory_digest
    ):
        raise ValidationError("manifest object inventory does not match supplied backup inventory")
    if not cleanup:
        raise UnsafeRecoveryTargetError("recovery rehearsal cleanup cannot be disabled")
    if not backend.inspect_pristine(target=target):
        raise UnsafeRecoveryTargetError("recovery target must be new and empty")

    database_resource = f"database:{target.database_name}"
    object_resource = f"objects:{target.object_namespace}"
    created_resources = (database_resource, object_resource)
    normalized_lease_count = 0
    issues: list[str] = []
    try:
        restored_database = tuple(
            backend.restore_database(
                target=target,
                snapshot_identity=manifest.database_snapshot_identity,
            )
        )
        if restored_database != (database_resource,):
            raise UnsafeRecoveryTargetError("database restore escaped its exact disposable target")
        restored_objects = tuple(backend.restore_objects(target=target, objects=objects))
        if restored_objects != (object_resource,):
            raise UnsafeRecoveryTargetError("object restore escaped its exact disposable target")

        database = backend.database_inventory(target=target)
        if database.snapshot_identity != manifest.database_snapshot_identity:
            issues.append("database_snapshot_mismatch")
        if database.application_schema_version != manifest.application_schema_version:
            issues.append("application_schema_mismatch")
        if not hmac.compare_digest(
            database.environment_fingerprint,
            manifest.environment_fingerprint,
        ):
            issues.append("environment_fingerprint_mismatch")

        restored_inventory = tuple(backend.object_inventory(target=target))
        if len(restored_inventory) != manifest.object_count or not hmac.compare_digest(
            canonical_object_inventory_digest(restored_inventory),
            manifest.object_inventory_digest,
        ):
            issues.append("object_inventory_mismatch")

        available_mfa = backend.available_mfa_key_versions(target=target)
        if not set(manifest.required_mfa_key_versions).issubset(available_mfa):
            issues.append("mfa_key_versions_missing")
        available_notification = backend.available_notification_key_versions(target=target)
        if not set(manifest.required_notification_key_versions).issubset(available_notification):
            issues.append("notification_key_versions_missing")

        expired = tuple(
            lease
            for lease in backend.lease_inventory(target=target)
            if lease.is_expired_running(observed_at=checked_at)
        )
        normalized_lease_count = backend.normalize_expired_leases(
            target=target,
            leases=expired,
            observed_at=checked_at,
        )
        if normalized_lease_count != len(expired):
            issues.append("lease_normalization_incomplete")
        issues.extend(backend.reconcile_application(target=target))
        return _evidence(
            manifest=manifest,
            issue_codes=issues,
            normalized_lease_count=normalized_lease_count,
        )
    finally:
        backend.cleanup(target=target, created_resources=created_resources)
