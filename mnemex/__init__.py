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
    EventCircuit, ExtractionStatus, SourceType
    TIER1_DISCIPLINES, TIER2_DISCIPLINES, TIER3_DISCIPLINES
    STRATHMARK_DISCIPLINE_MAP, DEFAULT_SCORE_POLICY

Ingestion runs:
    IngestionRun, generate_run_id, start_run, complete_run, fail_run, mark_partial

Identity:
    CanonicalAthlete, Match, NeedsReview
    match, commit_link, merge, split, redact

Store (Supabase-backed; see docs/supabase-setup.md):
    write_competitor, write_ingestion_run, write_results
    read_canonical, read_results_full, read_competitor,
    read_competitor_by_federation_id, read_ingestion_run
    queue_for_reconciliation
    export_canonical_jsonl
    health_check

STRATHMARK adapter:
    to_strathmark_results, write_strathmark_jsonl

Ingest:
    IngestSource (ABC)
    StihlIngest, CollegeExcelIngest, NewsletterIngest, ImageIngest, ManualCsvIngest

Most names below are placeholders during Milestone 0/1; concrete implementations
land in Milestones 1-6.
"""

from __future__ import annotations

__version__ = "0.1.0a0"

# Schema
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
    SourceType,
    TIER1_DISCIPLINES,
    TIER2_DISCIPLINES,
    TIER3_DISCIPLINES,
    STRATHMARK_DISCIPLINE_MAP,
    DEFAULT_SCORE_POLICY,
)

# Ingestion runs
from mnemex.ingestion_runs import (  # noqa: F401
    IngestionRun,
    generate_run_id,
    start_run,
    complete_run,
    fail_run,
    mark_partial,
)

# Identity
from mnemex.identity import (  # noqa: F401
    CanonicalAthlete,
    Match,
    NeedsReview,
)

# Store (Supabase-backed). Functions raise RuntimeError at call time
# if MNEMEX_SUPABASE_URL / MNEMEX_SUPABASE_SERVICE_ROLE_KEY are unset,
# so import-time has no credential dependency.
from mnemex.store import (  # noqa: F401
    write_competitor,
    write_ingestion_run,
    write_results,
    read_canonical,
    read_results_full,
    read_competitor,
    read_competitor_by_federation_id,
    read_ingestion_run,
    queue_for_reconciliation,
    export_canonical_jsonl,
    health_check,
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
    "SourceType",
    "TIER1_DISCIPLINES",
    "TIER2_DISCIPLINES",
    "TIER3_DISCIPLINES",
    "STRATHMARK_DISCIPLINE_MAP",
    "DEFAULT_SCORE_POLICY",
    # ingestion runs
    "IngestionRun",
    "generate_run_id",
    "start_run",
    "complete_run",
    "fail_run",
    "mark_partial",
    # identity dataclasses (functions land at M1)
    "CanonicalAthlete",
    "Match",
    "NeedsReview",
    # store (Supabase-backed; see docs/supabase-setup.md)
    "write_competitor",
    "write_ingestion_run",
    "write_results",
    "read_canonical",
    "read_results_full",
    "read_competitor",
    "read_competitor_by_federation_id",
    "read_ingestion_run",
    "queue_for_reconciliation",
    "export_canonical_jsonl",
    "health_check",
    # strathmark_adapter, ingest names land in M1-M6 and become
    # first-class re-exports here at that point.
]
