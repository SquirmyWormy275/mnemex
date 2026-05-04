"""STRATHMARK Tier 3 adapter — placeholder.

Tier 3 events (Caber Throw, Axe Throw, Speed Axe, Birling, Pulp Toss,
Dendrology, Timber Cruise, Traverse, Steeple Chase, Wrapper Throw,
Team Relay, Pole Climb, Choker Race) are NEVER exported to STRATHMARK.

STRATHMARK is a handicap engine. Distance / knowledge / place-only events
don't model in handicap math. Tier 3 stays in MNEMEX archive forever
and is queryable via the export hub (CSV / JSON / Excel) for federation use.

This module exists only so the package layout matches the design doc.
Calling anything in it raises NotImplementedError.
"""

from __future__ import annotations


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    raise NotImplementedError(
        "Tier 3 disciplines are NEVER exported to STRATHMARK. "
        "STRATHMARK is a handicap engine. See design doc Premise 15."
    )
