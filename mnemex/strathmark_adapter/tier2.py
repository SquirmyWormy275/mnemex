"""Non-SB/UH STRATHMARK export is prohibited by current policy."""

from __future__ import annotations


def is_enabled() -> bool:
    return False


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    raise PermissionError("non-SB/UH export is prohibited; broad results remain in MNEMEX only")
