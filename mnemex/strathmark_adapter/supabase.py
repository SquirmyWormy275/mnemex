"""Disabled direct database path; STRATHMARK owns its local snapshot store."""

from __future__ import annotations


def write(rows, schema="strathmark_staging", dry_run=False):  # type: ignore[no-untyped-def]
    raise PermissionError(
        "direct STRATHMARK database writes are prohibited; use StoredEvidenceSnapshotSource"
    )
