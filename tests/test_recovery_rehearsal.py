from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

import pytest
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError, OutputWrapper

from mnemex.recovery.management.commands.rehearse_restore import Command
from mnemex.recovery.services import (
    DatabaseRecoveryInventory,
    LeaseInventoryEntry,
    ObjectInventoryEntry,
    RecoveryManifestPayload,
    RecoveryTarget,
    UnsafeRecoveryTargetError,
    run_recovery_rehearsal,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def _object(reference: str, content: bytes) -> ObjectInventoryEntry:
    import hashlib

    return ObjectInventoryEntry(
        reference=reference,
        digest=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


OBJECTS = (
    _object("sha256/aa/aa/" + "a" * 64 + ".xlsx", b"first"),
    _object("sha256/bb/bb/" + "b" * 64 + ".csv", b"second"),
)


def _manifest() -> RecoveryManifestPayload:
    return RecoveryManifestPayload.build(
        database_snapshot_identity="snapshot-synthetic-20260818",
        objects=OBJECTS,
        required_mfa_key_versions=(1, 3),
        required_notification_key_versions=(1, 2),
        application_schema_version="mnemex-schema-2026-08-18",
        environment_fingerprint="f" * 64,
    )


def _target(suffix: str = "run-00000001") -> RecoveryTarget:
    return RecoveryTarget(
        target_id=f"mnemex-rehearsal-{suffix}",
        environment_kind="disposable",
        database_name=f"mnemex_rehearsal_{suffix.replace('-', '_')}",
        object_namespace=f"mnemex-rehearsal/{suffix}",
        environment_fingerprint="f" * 64,
    )


@dataclass
class FakeRecoveryBackend:
    pristine: bool = True
    database_snapshot_identity: str = "snapshot-synthetic-20260818"
    application_schema_version: str = "mnemex-schema-2026-08-18"
    environment_fingerprint: str = "f" * 64
    objects: Sequence[ObjectInventoryEntry] = OBJECTS
    mfa_keys: frozenset[int] = frozenset({1, 3})
    notification_keys: frozenset[int] = frozenset({1, 2})
    reconciliation_codes: tuple[str, ...] = ()
    leases: tuple[LeaseInventoryEntry, ...] = (
        LeaseInventoryEntry(
            queue="security_notification",
            lease_id="expired-notification",
            status="running",
            lease_expires_at=NOW - timedelta(seconds=1),
            terminal=False,
        ),
        LeaseInventoryEntry(
            queue="legacy_migration",
            lease_id="active-job",
            status="running",
            lease_expires_at=NOW + timedelta(minutes=1),
            terminal=False,
        ),
        LeaseInventoryEntry(
            queue="legacy_migration",
            lease_id="completed-job",
            status="completed",
            lease_expires_at=NOW - timedelta(minutes=1),
            terminal=True,
        ),
    )
    calls: list[object] = field(default_factory=list)

    def inspect_pristine(self, *, target: RecoveryTarget) -> bool:
        self.calls.append(("inspect_pristine", target.target_id))
        return self.pristine

    def restore_database(
        self, *, target: RecoveryTarget, snapshot_identity: str
    ) -> tuple[str, ...]:
        self.calls.append(("restore_database", target.target_id, snapshot_identity))
        return (f"database:{target.database_name}",)

    def restore_objects(
        self, *, target: RecoveryTarget, objects: Sequence[ObjectInventoryEntry]
    ) -> tuple[str, ...]:
        self.calls.append(("restore_objects", target.target_id, len(objects)))
        return (f"objects:{target.object_namespace}",)

    def database_inventory(self, *, target: RecoveryTarget) -> DatabaseRecoveryInventory:
        self.calls.append(("database_inventory", target.target_id))
        return DatabaseRecoveryInventory(
            snapshot_identity=self.database_snapshot_identity,
            application_schema_version=self.application_schema_version,
            environment_fingerprint=self.environment_fingerprint,
        )

    def object_inventory(self, *, target: RecoveryTarget) -> Sequence[ObjectInventoryEntry]:
        self.calls.append(("object_inventory", target.target_id))
        return self.objects

    def available_mfa_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]:
        self.calls.append(("mfa_keys", target.target_id))
        return self.mfa_keys

    def available_notification_key_versions(self, *, target: RecoveryTarget) -> frozenset[int]:
        self.calls.append(("notification_keys", target.target_id))
        return self.notification_keys

    def lease_inventory(self, *, target: RecoveryTarget) -> Sequence[LeaseInventoryEntry]:
        self.calls.append(("lease_inventory", target.target_id))
        return self.leases

    def normalize_expired_leases(
        self,
        *,
        target: RecoveryTarget,
        leases: Sequence[LeaseInventoryEntry],
        observed_at: datetime,
    ) -> int:
        self.calls.append(
            (
                "normalize_expired_leases",
                target.target_id,
                tuple((lease.queue, lease.lease_id) for lease in leases),
                observed_at,
            )
        )
        return len(leases)

    def reconcile_application(self, *, target: RecoveryTarget) -> tuple[str, ...]:
        self.calls.append(("reconcile_application", target.target_id))
        return self.reconciliation_codes

    def cleanup(self, *, target: RecoveryTarget, created_resources: Sequence[str]) -> None:
        self.calls.append(("cleanup", target.target_id, tuple(created_resources)))


@pytest.mark.parametrize(
    "target",
    [
        RecoveryTarget(
            target_id="production",
            environment_kind="production",
            database_name="mnemex",
            object_namespace="artifacts",
            environment_fingerprint="f" * 64,
        ),
        RecoveryTarget(
            target_id="mnemex-rehearsal-run-00000001",
            environment_kind="disposable",
            database_name="mnemex",
            object_namespace="mnemex-rehearsal/run-00000001",
            environment_fingerprint="f" * 64,
        ),
        RecoveryTarget(
            target_id="mnemex-rehearsal-run-00000001",
            environment_kind="disposable",
            database_name="mnemex_rehearsal_run_00000001",
            object_namespace="mnemex-rehearsal/another-run",
            environment_fingerprint="f" * 64,
        ),
    ],
)
def test_rehearsal_refuses_non_disposable_targets_before_backend_access(
    target: RecoveryTarget,
) -> None:
    backend = FakeRecoveryBackend()

    with pytest.raises(UnsafeRecoveryTargetError):
        run_recovery_rehearsal(
            target=target,
            manifest=_manifest(),
            objects=OBJECTS,
            backend=backend,
            observed_at=NOW,
        )

    assert backend.calls == []


def test_rehearsal_refuses_a_preexisting_target_before_restore_or_cleanup() -> None:
    backend = FakeRecoveryBackend(pristine=False)

    with pytest.raises(UnsafeRecoveryTargetError, match="new and empty"):
        run_recovery_rehearsal(
            target=_target(),
            manifest=_manifest(),
            objects=OBJECTS,
            backend=backend,
            observed_at=NOW,
        )

    assert backend.calls == [("inspect_pristine", _target().target_id)]


def test_rehearsal_restores_reconciles_and_only_normalizes_expired_running_leases() -> None:
    backend = FakeRecoveryBackend()

    evidence = run_recovery_rehearsal(
        target=_target(),
        manifest=_manifest(),
        objects=OBJECTS,
        backend=backend,
        observed_at=NOW,
    )

    assert evidence.result == "pass"
    assert evidence.issue_codes == ()
    assert evidence.normalized_lease_count == 1
    normalize_call = next(call for call in backend.calls if call[0] == "normalize_expired_leases")
    assert normalize_call[2] == (("security_notification", "expired-notification"),)
    assert backend.calls[-1] == (
        "cleanup",
        _target().target_id,
        (
            f"database:{_target().database_name}",
            f"objects:{_target().object_namespace}",
        ),
    )
    assert set(evidence.to_redacted_dict()) == {
        "contract_version",
        "result",
        "manifest_digest",
        "environment_fingerprint",
        "object_count",
        "normalized_lease_count",
        "issue_codes",
        "evidence_digest",
    }
    assert "snapshot-synthetic" not in evidence.to_redacted_json()
    assert "sha256/" not in evidence.to_redacted_json()


@pytest.mark.parametrize(
    ("backend", "expected_code"),
    [
        (
            FakeRecoveryBackend(objects=OBJECTS[:1]),
            "object_inventory_mismatch",
        ),
        (
            FakeRecoveryBackend(
                objects=(
                    OBJECTS[0],
                    ObjectInventoryEntry(
                        reference=OBJECTS[1].reference,
                        digest="c" * 64,
                        byte_size=OBJECTS[1].byte_size,
                    ),
                )
            ),
            "object_inventory_mismatch",
        ),
        (
            FakeRecoveryBackend(
                objects=OBJECTS + (_object("sha256/cc/cc/" + "c" * 64 + ".bin", b"extra"),)
            ),
            "object_inventory_mismatch",
        ),
        (FakeRecoveryBackend(mfa_keys=frozenset({3})), "mfa_key_versions_missing"),
        (
            FakeRecoveryBackend(notification_keys=frozenset({1})),
            "notification_key_versions_missing",
        ),
    ],
)
def test_rehearsal_reports_omitted_altered_extra_objects_and_missing_keys(
    backend: FakeRecoveryBackend, expected_code: str
) -> None:
    evidence = run_recovery_rehearsal(
        target=_target(),
        manifest=_manifest(),
        objects=OBJECTS,
        backend=backend,
        observed_at=NOW,
    )

    assert evidence.result == "fail"
    assert expected_code in evidence.issue_codes
    assert backend.calls[-1][0] == "cleanup"


def test_two_new_targets_produce_identical_redacted_evidence_without_reusing_state() -> None:
    first_backend = FakeRecoveryBackend()
    second_backend = FakeRecoveryBackend()

    first = run_recovery_rehearsal(
        target=_target("run-00000001"),
        manifest=_manifest(),
        objects=OBJECTS,
        backend=first_backend,
        observed_at=NOW,
    )
    first_calls_after_completion = tuple(first_backend.calls)
    second = run_recovery_rehearsal(
        target=_target("run-00000002"),
        manifest=_manifest(),
        objects=OBJECTS,
        backend=second_backend,
        observed_at=NOW,
    )

    assert first.to_redacted_json() == second.to_redacted_json()
    assert tuple(first_backend.calls) == first_calls_after_completion
    assert first_backend.calls[-1][1] == "mnemex-rehearsal-run-00000001"
    assert second_backend.calls[-1][1] == "mnemex-rehearsal-run-00000002"


def test_command_validates_target_before_constructing_a_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    def forbidden_factory(*args: object, **kwargs: object) -> FakeRecoveryBackend:
        nonlocal constructed
        constructed = True
        raise AssertionError("backend must not be built for an unsafe target")

    monkeypatch.setattr(
        "mnemex.recovery.management.commands.rehearse_restore.build_backend",
        forbidden_factory,
    )

    with pytest.raises(UnsafeRecoveryTargetError):
        Command().handle(
            target_id="production",
            environment_kind="production",
            database_name="mnemex",
            object_namespace="artifacts",
            environment_fingerprint="f" * 64,
            manifest="unused.json",
            object_inventory="unused.json",
            no_cleanup=False,
        )

    assert constructed is False


def test_command_validates_the_pinned_clock_before_constructing_a_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    def forbidden_factory(*args: object, **kwargs: object) -> FakeRecoveryBackend:
        nonlocal constructed
        constructed = True
        raise AssertionError("backend must not be built for an invalid pinned clock")

    monkeypatch.setattr(
        "mnemex.recovery.management.commands.rehearse_restore.build_backend",
        forbidden_factory,
    )

    with pytest.raises(CommandError, match="timezone-aware"):
        Command().handle(
            target_id=_target().target_id,
            environment_kind=_target().environment_kind,
            database_name=_target().database_name,
            object_namespace=_target().object_namespace,
            environment_fingerprint=_target().environment_fingerprint,
            observed_at="2026-08-18T12:00:00",
            manifest="unused.json",
            object_inventory="unused.json",
            restored_state="unused.json",
            no_cleanup=False,
        )

    assert constructed is False


def test_rehearsal_rejects_manifest_object_inventory_disagreement_before_backend_access() -> None:
    backend = FakeRecoveryBackend()
    altered = OBJECTS + (_object("sha256/cc/cc/" + "c" * 64 + ".bin", b"extra"),)

    with pytest.raises(ValidationError, match="manifest object inventory"):
        run_recovery_rehearsal(
            target=_target(),
            manifest=_manifest(),
            objects=altered,
            backend=backend,
            observed_at=NOW,
        )

    assert backend.calls == []


def test_management_command_runs_a_redacted_synthetic_bundle(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    manifest_path = root / "manifest.json"
    objects_path = root / "objects.json"
    restored_path = root / "restored.json"
    manifest = _manifest()
    object_records = [entry.canonical_record() for entry in OBJECTS]
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    objects_path.write_text(json.dumps(object_records), encoding="utf-8")
    restored_path.write_text(
        json.dumps(
            {
                "database": {
                    "snapshot_identity": manifest.database_snapshot_identity,
                    "application_schema_version": manifest.application_schema_version,
                    "environment_fingerprint": manifest.environment_fingerprint,
                },
                "objects": object_records,
                "mfa_key_versions": list(manifest.required_mfa_key_versions),
                "notification_key_versions": list(manifest.required_notification_key_versions),
                "leases": [],
                "application_issue_codes": [],
                "pristine": True,
            }
        ),
        encoding="utf-8",
    )
    output = io.StringIO()
    command = Command()
    command.stdout = OutputWrapper(output)

    returned = command.handle(
        target_id=_target().target_id,
        environment_kind=_target().environment_kind,
        database_name=_target().database_name,
        object_namespace=_target().object_namespace,
        environment_fingerprint=_target().environment_fingerprint,
        manifest=str(manifest_path),
        object_inventory=str(objects_path),
        restored_state=str(restored_path),
        observed_at=NOW.isoformat(),
        no_cleanup=False,
    )

    payload = json.loads(returned)
    assert payload["result"] == "pass"
    assert payload["issue_codes"] == []
    assert "snapshot_identity" not in payload
    assert "object_namespace" not in payload
    assert output.getvalue() == ""
