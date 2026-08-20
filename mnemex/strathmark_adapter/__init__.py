"""Compatibility guards for the retired pre-review STRATHMARK adapters.

Use ``mnemex.export.adapters.StoredEvidenceSnapshotSource`` with the
STRATHMARK 2.x offline evidence-snapshot contract. Direct JSONL and raw-row
projection paths are disabled because they bypass human eligibility review.
"""

from __future__ import annotations

from mnemex.strathmark_adapter.tier1 import to_strathmark_results  # noqa: F401

__all__ = ["to_strathmark_results", "write_strathmark_jsonl"]


def write_strathmark_jsonl(rows, output_path):  # type: ignore[no-untyped-def]
    raise PermissionError(
        "direct JSONL export is disabled; use the reviewed STRATHMARK 2.x snapshot source"
    )
