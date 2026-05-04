"""STRATHMARK Tier 1 adapter — projects MNEMEX CanonicalRow records to
STRATHMARK's HistoricalResult shape.

See "STRATHMARK adapter contract" in the design doc for the projection rules
and the field-loss table.

Implementation lands in Milestone 6.
"""

from __future__ import annotations

# strathmark imports happen lazily inside to_strathmark_results() so that
# `import mnemex` succeeds even when strathmark is not installed (e.g. in a
# minimal test env). See pyproject.toml [project.dependencies] for the pin.


def to_strathmark_results(rows):  # type: ignore[no-untyped-def]
    """Project Tier 1 MNEMEX rows down to STRATHMARK HistoricalResult records.

    Filtering rules (logged via mnemex.logger; never silent):
      - row.discipline not in TIER1_DISCIPLINES -> filter
      - row.dq_reason set or row.final_score is None -> filter
      - row.score_type != ScoreType.TIME -> filter (defensive; Tier 1 is time-only)

    Mapping rules:
      - discipline: STRATHMARK_DISCIPLINE_MAP[row.discipline]
      - time: row.final_score (canonicalized per FinalScorePolicy by ingest)
      - species: row.wood_species or "Unknown"
      - diameter_mm: row.wood_diameter_mm or 0
      - quality: row.wood_quality or 5 (with quality_imputed flag preserved
                 in MNEMEX store, not propagated to STRATHMARK 0.4.1)
      - date: row.event_date
      - Pair events emit one HistoricalResult per competitor with the same time

    Implementation in Milestone 6.
    """
    raise NotImplementedError("Tier 1 projection lands in Milestone 6")
