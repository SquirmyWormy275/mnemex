"""Guard for every discipline outside the approved SB/UH snapshot scope."""

from __future__ import annotations


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    raise PermissionError("non-SB/UH export is prohibited; broad results remain in MNEMEX only")
