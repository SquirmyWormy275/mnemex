"""JSONL serializer — the v1 STRATHMARK integration path.

Writes Tier 1 projection of MNEMEX rows to a JSONL file ready for
STRATHMARK's `import_legacy.py --commit --input <file>`.

Implementation lands in Milestone 6.
"""

from __future__ import annotations


def write(rows, output_path):  # type: ignore[no-untyped-def]
    """Serialize Tier 1 HistoricalResult records as one JSON object per line.

    Implementation in Milestone 6.
    """
    raise NotImplementedError("JSONL writer lands in Milestone 6")
