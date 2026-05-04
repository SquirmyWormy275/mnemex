"""MNEMEX — Timbersports historical archive.

Third leg of the STRATHEX ecosystem alongside STRATHEX (live tournament
management) and STRATHMARK (handicap engine). MNEMEX scrapes historical
results from federations / events / scorebooks and feeds STRATHMARK's
training data via the Tier 1 contract.

Scope discipline: historical-only. Live-result entry belongs in STRATHEX.
See docs/MNEMEX-design-2026-05-04.md for the full design rationale.

Public API
----------

Schema:
    CanonicalRow, CompetitorRef, RunResult
    Discipline, ScoreType, FinalScorePolicy, Division, DQReason
    EventCircuit, ExtractionStatus
    TIER1_DISCIPLINES, TIER2_DISCIPLINES, TIER3_DISCIPLINES
    STRATHMARK_DISCIPLINE_MAP, DEFAULT_SCORE_POLICY

Store:
    read_canonical, read_pending, commit_pending

Identity:
    CanonicalAthlete, match, commit_link, redact

STRATHMARK adapter:
    to_strathmark_results, write_strathmark_jsonl

Ingest:
    IngestSource (ABC)
    StihlIngest, CollegeExcelIngest, NewsletterIngest, ImageIngest, ManualCsvIngest

Most names below are placeholders during Milestone 0; concrete implementations
land in Milestones 1-6.
"""

from __future__ import annotations

__version__ = "0.1.0a0"

# Schema (Milestone 1)
from mnemex.schema import (  # noqa: F401
    CanonicalRow,
    CompetitorRef,
    RunResult,
    Discipline,
    ScoreType,
    FinalScorePolicy,
    Division,
    DQReason,
    EventCircuit,
    ExtractionStatus,
    TIER1_DISCIPLINES,
    TIER2_DISCIPLINES,
    TIER3_DISCIPLINES,
    STRATHMARK_DISCIPLINE_MAP,
    DEFAULT_SCORE_POLICY,
)

__all__ = [
    "__version__",
    # schema
    "CanonicalRow",
    "CompetitorRef",
    "RunResult",
    "Discipline",
    "ScoreType",
    "FinalScorePolicy",
    "Division",
    "DQReason",
    "EventCircuit",
    "ExtractionStatus",
    "TIER1_DISCIPLINES",
    "TIER2_DISCIPLINES",
    "TIER3_DISCIPLINES",
    "STRATHMARK_DISCIPLINE_MAP",
    "DEFAULT_SCORE_POLICY",
    # store, identity, strathmark_adapter, ingest names land in M1-M6 and
    # become first-class re-exports here at that point.
]
