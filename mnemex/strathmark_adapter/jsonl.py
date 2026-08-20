"""Disabled legacy JSONL path retained so old imports fail closed."""

from __future__ import annotations


def write(rows, output_path):  # type: ignore[no-untyped-def]
    raise PermissionError(
        "direct JSONL export is disabled; use the reviewed STRATHMARK 2.x snapshot source"
    )
