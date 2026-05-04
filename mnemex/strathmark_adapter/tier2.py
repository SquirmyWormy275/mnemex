"""STRATHMARK Tier 2 adapter (HHH / VHH hits-based events).

Feature-flag-DISABLED until STRATHMARK 0.5 ships with a `score_type` field.
v1 implements but gates behind MNEMEX_ENABLE_TIER2 env var. Activates when:
  - STRATHMARK >= 0.5 is installed
  - MNEMEX_ENABLE_TIER2=1 is set explicitly by the operator

Implementation lands in Milestone 6 (alongside Tier 1).
"""

from __future__ import annotations

import os


def is_enabled() -> bool:
    """Tier 2 export is disabled by default. Operator opts in via env var
    AND the installed STRATHMARK version must support `score_type`."""
    if os.environ.get("MNEMEX_ENABLE_TIER2", "0") != "1":
        return False
    try:
        import strathmark

        version = strathmark.__version__
        major, minor = version.split(".")[:2]
        return (int(major), int(minor)) >= (0, 5)
    except (ImportError, AttributeError, ValueError):
        return False


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    """Project Tier 2 (hits-based) MNEMEX rows.

    Implementation in Milestone 6, gated on STRATHMARK 0.5 release.
    """
    raise NotImplementedError(
        "Tier 2 projection lands in Milestone 6 (gated on STRATHMARK 0.5)"
    )
