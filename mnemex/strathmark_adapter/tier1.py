"""Disabled pre-review STRATHMARK projection retained for import compatibility."""

from __future__ import annotations


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    """Reject bypasses around the reviewed evidence-snapshot boundary."""
    raise PermissionError(
        "direct CanonicalRow projection is disabled; create reviewed SB/UH "
        "eligibility revisions and use StoredEvidenceSnapshotSource"
    )
