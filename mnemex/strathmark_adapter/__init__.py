"""STRATHMARK adapter package.

Projects MNEMEX CanonicalRow records onto STRATHMARK's HistoricalResult
shape and serializes the result for STRATHMARK's import_legacy.py.

v1 ships JSONL only (jsonl.py). HTTP and Supabase adapters are stubs
that raise NotImplementedError until v1.1+.

Tier classification:
  Tier 1 -- exports cleanly against STRATHMARK 0.4.1 today
  Tier 2 -- ships v1, feature-flag-DISABLED until STRATHMARK 0.5
  Tier 3 -- never exported (STRATHMARK is a handicap engine; Tier 3 is
            captured in MNEMEX archive only)
"""

from __future__ import annotations

from mnemex.strathmark_adapter.tier1 import to_strathmark_results  # noqa: F401

__all__ = ["to_strathmark_results", "write_strathmark_jsonl"]


def write_strathmark_jsonl(rows, output_path):  # type: ignore[no-untyped-def]
    """Serialize Tier 1 projection of MNEMEX rows to a JSONL file ready
    for STRATHMARK's import_legacy.py.

    Implementation in Milestone 6.
    """
    raise NotImplementedError("write_strathmark_jsonl lands in Milestone 6")
