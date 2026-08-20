from __future__ import annotations

import json

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from mnemex.recovery.models import RecoveryManifest, RecoveryRehearsalRecord
from mnemex.recovery.services import (
    ObjectInventoryEntry,
    RecoveryManifestPayload,
    canonical_object_inventory_digest,
    manifest_payload_digest,
    recovery_rehearsal_evidence_digest,
)


def _object(reference: str, content: bytes) -> ObjectInventoryEntry:
    import hashlib

    return ObjectInventoryEntry(
        reference=reference,
        digest=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


def test_object_inventory_digest_is_canonical_and_order_independent() -> None:
    first = _object("sha256/aa/aa/" + "a" * 64 + ".xlsx", b"first")
    second = _object("sha256/bb/bb/" + "b" * 64 + ".csv", b"second")

    assert canonical_object_inventory_digest((first, second)) == (
        canonical_object_inventory_digest((second, first))
    )


def test_object_inventory_rejects_duplicate_references() -> None:
    entry = _object("sha256/aa/aa/" + "a" * 64 + ".xlsx", b"first")

    with pytest.raises(ValidationError, match="duplicate object reference"):
        canonical_object_inventory_digest((entry, entry))


def test_manifest_payload_normalizes_key_versions_and_is_self_authenticating() -> None:
    objects = (
        _object("sha256/aa/aa/" + "a" * 64 + ".xlsx", b"first"),
        _object("sha256/bb/bb/" + "b" * 64 + ".csv", b"second"),
    )
    manifest = RecoveryManifestPayload.build(
        database_snapshot_identity="snapshot-synthetic-20260818",
        objects=objects,
        required_mfa_key_versions=(3, 1, 3),
        required_notification_key_versions=(2, 1),
        application_schema_version="mnemex-schema-2026-08-18",
        environment_fingerprint="f" * 64,
    )

    assert manifest.required_mfa_key_versions == (1, 3)
    assert manifest.required_notification_key_versions == (1, 2)
    assert manifest.object_count == 2
    assert manifest.payload_digest == manifest_payload_digest(manifest)
    assert manifest.to_dict() == json.loads(manifest.to_json())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_snapshot_identity", ""),
        ("object_inventory_digest", "NOT-A-DIGEST"),
        ("object_count", -1),
        ("required_mfa_key_versions", (0,)),
        ("application_schema_version", ""),
        ("environment_fingerprint", "0" * 63),
    ],
)
def test_manifest_payload_rejects_invalid_recovery_metadata(field: str, value: object) -> None:
    values: dict[str, object] = {
        "database_snapshot_identity": "snapshot-synthetic-20260818",
        "object_inventory_digest": "a" * 64,
        "object_count": 1,
        "required_mfa_key_versions": (1,),
        "required_notification_key_versions": (1,),
        "application_schema_version": "mnemex-schema-2026-08-18",
        "environment_fingerprint": "f" * 64,
        "payload_digest": "",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RecoveryManifestPayload(**values)  # type: ignore[arg-type]


def test_manifest_payload_rejects_a_tampered_digest() -> None:
    manifest = RecoveryManifestPayload(
        database_snapshot_identity="snapshot-synthetic-20260818",
        object_inventory_digest="a" * 64,
        object_count=1,
        required_mfa_key_versions=(1,),
        required_notification_key_versions=(1,),
        application_schema_version="mnemex-schema-2026-08-18",
        environment_fingerprint="f" * 64,
        payload_digest="b" * 64,
    )

    with pytest.raises(ValidationError, match="payload digest"):
        manifest.verify()


@pytest.mark.django_db(transaction=True)
def test_recovery_manifest_and_rehearsal_records_are_append_only() -> None:
    """Use the isolated test database even before the parent registers the app."""

    existing_tables = set(connection.introspection.table_names())
    manifest_table = RecoveryManifest._meta.db_table
    created = manifest_table not in existing_tables
    if created:
        with connection.schema_editor() as editor:
            editor.create_model(RecoveryManifest)
            editor.create_model(RecoveryRehearsalRecord)
    try:
        objects = (_object("opaque/first.bin", b"first"),)
        payload = RecoveryManifestPayload.build(
            database_snapshot_identity="snapshot-synthetic-20260818",
            objects=objects,
            required_mfa_key_versions=(1,),
            required_notification_key_versions=(1,),
            application_schema_version="mnemex-schema-2026-08-18",
            environment_fingerprint="f" * 64,
        )
        manifest = RecoveryManifest.objects.create(
            database_snapshot_identity=payload.database_snapshot_identity,
            object_inventory_digest=payload.object_inventory_digest,
            object_count=payload.object_count,
            required_mfa_key_versions=list(payload.required_mfa_key_versions),
            required_notification_key_versions=list(payload.required_notification_key_versions),
            application_schema_version=payload.application_schema_version,
            environment_fingerprint=payload.environment_fingerprint,
            payload_digest=payload.payload_digest,
        )
        evidence_digest = recovery_rehearsal_evidence_digest(
            result="pass",
            manifest_digest=payload.payload_digest,
            environment_fingerprint=payload.environment_fingerprint,
            object_count=payload.object_count,
            normalized_lease_count=1,
            issue_codes=(),
        )
        record = RecoveryRehearsalRecord.objects.create(
            manifest=manifest,
            result=RecoveryRehearsalRecord.Result.PASS,
            environment_fingerprint=payload.environment_fingerprint,
            issue_codes=[],
            normalized_lease_count=1,
            evidence_digest=evidence_digest,
            observed_at=timezone.now(),
        )

        manifest.database_snapshot_identity = "different-snapshot"
        with pytest.raises(PermissionDenied, match="append-only"):
            manifest.save()
        with pytest.raises(PermissionDenied, match="append-only"):
            RecoveryManifest.objects.filter(pk=manifest.pk).update(object_count=9)
        with pytest.raises(PermissionDenied, match="append-only"):
            record.delete()

        tampered = RecoveryRehearsalRecord(
            manifest=manifest,
            result=RecoveryRehearsalRecord.Result.PASS,
            environment_fingerprint=payload.environment_fingerprint,
            issue_codes=[],
            normalized_lease_count=1,
            evidence_digest="e" * 64,
            observed_at=timezone.now(),
        )
        with pytest.raises(ValidationError, match="evidence digest"):
            tampered.full_clean()
    finally:
        if created:
            with connection.schema_editor() as editor:
                editor.delete_model(RecoveryRehearsalRecord)
                editor.delete_model(RecoveryManifest)
