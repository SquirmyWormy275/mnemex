from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from mnemex.recovery.services import (
    DatabaseRecoveryInventory,
    LeaseInventoryEntry,
    ObjectInventoryEntry,
    RecoveryManifestPayload,
    RecoveryTarget,
    UnsafeRecoveryTargetError,
    run_recovery_rehearsal,
)

_MAX_FIXTURE_BYTES = 5 * 1024 * 1024


def _option_text(options: dict[str, object], name: str) -> str:
    value = options.get(name)
    if not isinstance(value, str):
        # The target validator remains responsible for the fail-closed public error.
        return ""
    return value


def _read_json(path_value: object, *, label: str) -> object:
    if not isinstance(path_value, str) or not path_value.strip():
        raise CommandError(f"{label} JSON path is required")
    path = Path(path_value).resolve()
    try:
        size = path.stat().st_size
    except OSError as error:
        raise CommandError(f"{label} JSON is unavailable") from error
    if size > _MAX_FIXTURE_BYTES:
        raise CommandError(f"{label} JSON exceeds the bounded input size")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CommandError(f"{label} JSON is invalid") from error


def _observed_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise CommandError("observed-at must be an ISO-8601 timestamp")
    parsed = parse_datetime(value)
    if parsed is None or timezone.is_naive(parsed):
        raise CommandError("observed-at must be a timezone-aware ISO-8601 timestamp")
    return parsed


def _objects(value: object) -> tuple[ObjectInventoryEntry, ...]:
    if not isinstance(value, list):
        raise CommandError("object inventory must be a JSON array")
    if any(not isinstance(entry, dict) for entry in value):
        raise CommandError("object inventory contains an invalid entry")
    try:
        return tuple(
            ObjectInventoryEntry(
                reference=entry["reference"],
                digest=entry["digest"],
                byte_size=entry["byte_size"],
            )
            for entry in value
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise CommandError("object inventory contains an invalid entry") from error


def _versions(value: object, *, field: str) -> frozenset[int]:
    if not isinstance(value, list):
        raise CommandError(f"{field} must be a JSON array")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
        raise CommandError(f"{field} contains an invalid key version")
    return frozenset(value)


def _leases(value: object) -> tuple[LeaseInventoryEntry, ...]:
    if not isinstance(value, list):
        raise CommandError("lease inventory must be a JSON array")
    entries: list[LeaseInventoryEntry] = []
    try:
        for raw in value:
            if not isinstance(raw, dict):
                raise TypeError
            raw_expiry = raw.get("lease_expires_at")
            expiry = parse_datetime(raw_expiry) if isinstance(raw_expiry, str) else None
            if raw_expiry is not None and expiry is None:
                raise ValueError
            entries.append(
                LeaseInventoryEntry(
                    queue=raw["queue"],
                    lease_id=raw["lease_id"],
                    status=raw["status"],
                    lease_expires_at=expiry,
                    terminal=raw["terminal"],
                )
            )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise CommandError("lease inventory contains an invalid entry") from error
    return tuple(entries)


@dataclass
class SyntheticRecoveryBackend:
    """Credential-free backend for the checked-in disposable rehearsal contract.

    Provider-specific PostgreSQL and Storage restoration happens outside this command.
    This backend is intentionally synthetic; its result cannot satisfy a hosted gate.
    """

    database: DatabaseRecoveryInventory
    observed_objects: tuple[ObjectInventoryEntry, ...]
    mfa_key_versions: frozenset[int]
    notification_key_versions: frozenset[int]
    leases: tuple[LeaseInventoryEntry, ...]
    application_issue_codes: tuple[str, ...]
    pristine: bool = True
    _restored: bool = False
    _cleaned: bool = False
    _normalized: set[tuple[str, str]] = field(default_factory=set)

    def inspect_pristine(self, *, target: RecoveryTarget) -> bool:
        return self.pristine and not self._restored and not self._cleaned

    def restore_database(
        self, *, target: RecoveryTarget, snapshot_identity: str
    ) -> tuple[str, ...]:
        self._restored = True
        return (f"database:{target.database_name}",)

    def restore_objects(
        self,
        *,
        target: RecoveryTarget,
        objects: Sequence[ObjectInventoryEntry],
    ) -> tuple[str, ...]:
        if not self._restored:
            raise RuntimeError("database restore must precede object restore")
        return (f"objects:{target.object_namespace}",)

    def database_inventory(self, *, target: RecoveryTarget) -> DatabaseRecoveryInventory:
        return self.database

    def object_inventory(self, *, target: RecoveryTarget) -> tuple[ObjectInventoryEntry, ...]:
        return self.observed_objects

    def available_mfa_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]:
        return self.mfa_key_versions

    def available_notification_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]:
        return self.notification_key_versions

    def lease_inventory(self, *, target: RecoveryTarget) -> tuple[LeaseInventoryEntry, ...]:
        return self.leases

    def normalize_expired_leases(
        self,
        *,
        target: RecoveryTarget,
        leases: Sequence[LeaseInventoryEntry],
        observed_at: datetime,
    ) -> int:
        for lease in leases:
            if not lease.is_expired_running(observed_at=observed_at):
                raise RuntimeError("only expired running leases may be normalized")
            self._normalized.add((lease.queue, lease.lease_id))
        return len(leases)

    def reconcile_application(self, *, target: RecoveryTarget) -> tuple[str, ...]:
        return self.application_issue_codes

    def cleanup(
        self,
        *,
        target: RecoveryTarget,
        created_resources: Sequence[str],
    ) -> None:
        expected = (
            f"database:{target.database_name}",
            f"objects:{target.object_namespace}",
        )
        if tuple(created_resources) != expected:
            raise UnsafeRecoveryTargetError("cleanup inventory escaped the disposable target")
        self._cleaned = True


@dataclass(frozen=True)
class RecoveryCommandBundle:
    manifest: RecoveryManifestPayload
    objects: tuple[ObjectInventoryEntry, ...]
    backend: SyntheticRecoveryBackend


def build_backend(**options: object) -> RecoveryCommandBundle:
    manifest_value = _read_json(options.get("manifest"), label="manifest")
    object_value = _read_json(options.get("object_inventory"), label="object inventory")
    restored_value = _read_json(options.get("restored_state"), label="restored state")
    if not isinstance(restored_value, dict):
        raise CommandError("restored state must be a JSON object")
    try:
        manifest = RecoveryManifestPayload.from_dict(manifest_value)
        objects = _objects(object_value)
        raw_database = restored_value["database"]
        if not isinstance(raw_database, dict):
            raise TypeError
        database = DatabaseRecoveryInventory(
            snapshot_identity=raw_database["snapshot_identity"],
            application_schema_version=raw_database["application_schema_version"],
            environment_fingerprint=raw_database["environment_fingerprint"],
        )
        raw_issue_codes = restored_value.get("application_issue_codes", [])
        if not isinstance(raw_issue_codes, list) or any(
            not isinstance(code, str) for code in raw_issue_codes
        ):
            raise TypeError
        backend = SyntheticRecoveryBackend(
            database=database,
            observed_objects=_objects(restored_value["objects"]),
            mfa_key_versions=_versions(
                restored_value["mfa_key_versions"],
                field="mfa_key_versions",
            ),
            notification_key_versions=_versions(
                restored_value["notification_key_versions"],
                field="notification_key_versions",
            ),
            leases=_leases(restored_value.get("leases", [])),
            application_issue_codes=tuple(raw_issue_codes),
            pristine=restored_value.get("pristine", True) is True,
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise CommandError("recovery fixture bundle is invalid") from error
    return RecoveryCommandBundle(manifest=manifest, objects=objects, backend=backend)


class Command(BaseCommand):
    help = "Run a credential-free recovery rehearsal against one exact disposable target."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--target-id", required=True)
        parser.add_argument("--environment-kind", required=True)
        parser.add_argument("--database-name", required=True)
        parser.add_argument("--object-namespace", required=True)
        parser.add_argument("--environment-fingerprint", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--object-inventory", required=True)
        parser.add_argument("--restored-state", required=True)
        parser.add_argument("--observed-at", required=True)

    def handle(self, *args: object, **options: object) -> str:
        target = RecoveryTarget(
            target_id=_option_text(options, "target_id"),
            environment_kind=_option_text(options, "environment_kind"),
            database_name=_option_text(options, "database_name"),
            object_namespace=_option_text(options, "object_namespace"),
            environment_fingerprint=_option_text(options, "environment_fingerprint"),
        )
        # This check is deliberately before file reads, backend construction, any
        # database connection, or any mutable recovery operation.
        target.validate()
        observed_at = _observed_at(options.get("observed_at"))
        bundle = build_backend(**options)
        evidence = run_recovery_rehearsal(
            target=target,
            manifest=bundle.manifest,
            objects=bundle.objects,
            backend=bundle.backend,
            observed_at=observed_at,
            cleanup=not bool(options.get("no_cleanup", False)),
        )
        output = evidence.to_redacted_json()
        if evidence.result != "pass":
            self.stderr.write(output)
            raise CommandError("recovery rehearsal reconciliation failed")
        return output
