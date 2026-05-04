"""Ingestion-run tracking.

Every scraper run, federation upload, or STRATHEX finalization webhook is
modeled as a single IngestionRun. CanonicalRow records carry the run_id as
a foreign key (`CanonicalRow.ingestion_run_id`), which lets us:

  - replay or roll back any single ingest
  - tie reconciliation outcomes back to a specific scraper run
  - surface "what changed today" for STRATHMARK's incremental sync
  - audit an operator's actions across batches

The run_id is a ULID (Crockford base32, 26 characters, sortable by creation
time, useful for operational debugging). ULIDs sort lexicographically by
timestamp, so `ORDER BY run_id DESC` gives newest-first without a separate
created_at index.

Run lifecycle:

    run_id = generate_run_id()
    run = start_run(run_id, SourceType.SCRAPER, operator="alex")
    try:
        # ... do the work, accumulate rows ...
        rows_count = ingest_some_rows(run_id)
        complete_run(run, rows_ingested=rows_count)
    except Exception as e:
        fail_run(run, error=str(e))

A `partial` status is also supported for the case where some rows ingested
cleanly but the run aborted before finishing. Operators set this manually
via `mark_partial(run, rows_ingested=N, notes="aborted at page 5/12")` so
the audit trail captures intent rather than crashing into `failed`.

This module owns the dataclass and lifecycle helpers only. The persistence
backend (Supabase table or JSONL file) lives in mnemex/store.py and is
implemented at Milestone 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import ulid

from mnemex.schema import SourceType

# Status values for IngestionRun.status. Strings rather than an enum to
# keep the persistence layer simple (Supabase text column or JSONL string).
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_PARTIAL = "partial"

VALID_STATUSES = frozenset(
    {STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_PARTIAL}
)


@dataclass
class IngestionRun:
    """One ingestion run. Created when a scraper / upload / finalization
    starts; finalized when it completes, fails, or is marked partial.

    `run_id` is a ULID string (26 characters, Crockford base32). Sortable
    by creation time.
    """

    run_id: str
    source_type: SourceType
    started_at: str  # ISO 8601 UTC
    completed_at: Optional[str] = None  # ISO 8601 UTC; null while running
    status: str = STATUS_RUNNING
    rows_ingested: int = 0
    operator: Optional[str] = None  # username / federation admin id / "system"
    notes: Optional[str] = None  # freeform; failure reason or partial-run context


def generate_run_id() -> str:
    """Return a fresh ULID string, suitable for IngestionRun.run_id.

    ULIDs are 26 characters of Crockford base32. The first 10 characters
    encode a millisecond-precision timestamp; the last 16 are randomness.
    Lexicographic sort = chronological sort.
    """
    return str(ulid.new())


def _utc_now_iso() -> str:
    """ISO 8601 UTC timestamp with seconds precision and `Z` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def start_run(
    run_id: str,
    source_type: SourceType,
    operator: Optional[str] = None,
    notes: Optional[str] = None,
) -> IngestionRun:
    """Create a new IngestionRun in `running` state.

    The caller is responsible for persisting the returned IngestionRun via
    mnemex.store (lands at Milestone 1). This helper just constructs the
    dataclass and stamps the started_at timestamp.
    """
    return IngestionRun(
        run_id=run_id,
        source_type=source_type,
        started_at=_utc_now_iso(),
        status=STATUS_RUNNING,
        operator=operator,
        notes=notes,
    )


def complete_run(
    run: IngestionRun,
    rows_ingested: int,
    notes: Optional[str] = None,
) -> IngestionRun:
    """Mark a run as succeeded. Mutates the run in-place AND returns it.

    Returning the mutated run lets callers chain or assign without a
    no-return surprise. Idempotent: calling complete_run on an already-
    completed run is a no-op (status stays succeeded).

    Raises ValueError if the run is already in a terminal failed state.
    """
    if run.status == STATUS_FAILED:
        raise ValueError(
            f"Cannot complete run {run.run_id}: already in failed state. "
            f"Use mark_partial if some rows ingested before failure."
        )
    run.status = STATUS_SUCCEEDED
    run.completed_at = _utc_now_iso()
    run.rows_ingested = rows_ingested
    if notes is not None:
        run.notes = notes
    return run


def fail_run(
    run: IngestionRun,
    error: str,
    rows_ingested: int = 0,
) -> IngestionRun:
    """Mark a run as failed. Mutates in-place and returns. The error
    message becomes the run's notes (overwriting any prior notes).

    If `rows_ingested > 0`, the caller should usually use mark_partial
    instead so the audit trail reflects that some rows landed before the
    failure. fail_run is for total failures (no rows ingested).
    """
    run.status = STATUS_FAILED
    run.completed_at = _utc_now_iso()
    run.rows_ingested = rows_ingested
    run.notes = error
    return run


def mark_partial(
    run: IngestionRun,
    rows_ingested: int,
    notes: str,
) -> IngestionRun:
    """Mark a run as partial. Some rows ingested cleanly before the run
    aborted. The notes field captures the abort context (e.g.,
    "aborted at page 5/12 due to LLM rate limit").
    """
    run.status = STATUS_PARTIAL
    run.completed_at = _utc_now_iso()
    run.rows_ingested = rows_ingested
    run.notes = notes
    return run
