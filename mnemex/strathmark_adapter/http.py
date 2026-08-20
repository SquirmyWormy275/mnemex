"""Disabled direct HTTP path; MNEMEX emits reviewed offline snapshots only."""

from __future__ import annotations


def post(rows, endpoint, token=None, dry_run=False):  # type: ignore[no-untyped-def]
    raise PermissionError(
        "direct STRATHMARK HTTP writes are prohibited; use StoredEvidenceSnapshotSource"
    )
