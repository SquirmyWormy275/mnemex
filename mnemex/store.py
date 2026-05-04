"""MNEMEX canonical store.

Supabase is the canonical store. The schema is defined in
mnemex/migrations/20260504_001_initial_schema.sql and provisioned per
docs/supabase-setup.md.

This module is the thin abstraction layer the rest of MNEMEX talks to.
Callers go through `write_results`, `read_canonical`, `write_competitor`,
etc. - they do NOT touch the supabase-py client directly. If the store
ever changes again (sharding, alternate backend, caching tier), the
abstraction here absorbs the change.

Configuration:
    Two env vars are required:
        MNEMEX_SUPABASE_URL              - the project's REST URL
        MNEMEX_SUPABASE_SERVICE_ROLE_KEY - the service_role key

    Both come from the local .env (loaded via python-dotenv at process
    start). Per the standing rule, neither value is ever pasted into
    Claude.ai chat or echoed to logs.

Test gating:
    The integration tests in tests/test_supabase_schema.py and
    tests/test_store_supabase.py run against the staging project, which
    is selected via:
        MNEMEX_TEST_SUPABASE=1
        MNEMEX_TEST_SUPABASE_URL              - staging project URL
        MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY - staging service-role key
    When MNEMEX_TEST_SUPABASE is unset (the default), every Supabase test
    skips with `pytest.importorskip` / `pytest.skip` semantics.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import asdict, is_dataclass
from typing import Any, Optional

from mnemex.ingestion_runs import IngestionRun
from mnemex.identity import CanonicalAthlete
from mnemex.schema import CanonicalRow

# ----------------------------------------------------------------------------
# Client construction
# ----------------------------------------------------------------------------

# supabase-py is imported lazily so test environments without credentials
# can still import this module (e.g., to check that public names exist).
_CLIENT = None


def _get_client() -> Any:
    """Return a memoized supabase client constructed from MNEMEX_SUPABASE_URL
    and MNEMEX_SUPABASE_SERVICE_ROLE_KEY env vars.

    Raises RuntimeError when either env var is missing. Lazy-imports
    supabase-py so the dependency only loads if the store is actually used.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    url = os.environ.get("MNEMEX_SUPABASE_URL")
    key = os.environ.get("MNEMEX_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "MNEMEX store requires MNEMEX_SUPABASE_URL and "
            "MNEMEX_SUPABASE_SERVICE_ROLE_KEY to be set in the environment. "
            "See docs/supabase-setup.md."
        )

    from supabase import create_client  # type: ignore[import-not-found]

    _CLIENT = create_client(url, key)
    return _CLIENT


def _reset_client_for_tests() -> None:
    """Test helper: discard the memoized client so tests can swap env vars
    between cases. Production code should never call this."""
    global _CLIENT
    _CLIENT = None


# ----------------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------------


def _row_to_dict(
    row: CanonicalRow,
    competitor_id: str,
    partner_competitor_id: Optional[str] = None,
    governing_body: Optional[str] = None,
) -> dict:
    """Project a CanonicalRow into the columns of the `results` table.

    The SQL schema is denser than the dataclass on some axes (handicap_mark,
    log_length_mm, log_specification, no_time_flag, scratch_flag, governing_body)
    and sparser on others (gender, event_url, verified_at, verified_by,
    wood_quality, wood_quality_imputed, wood_metadata_source, points,
    special_markers, extraction_*, identity_resolution_required).

    Mismatched fields are dropped silently here. Callers that need to
    persist them should track the divergence in a follow-on PR (see
    PR-2 summary "Decisions made beyond the prompt").
    """
    if not row.source_id:
        raise ValueError("CanonicalRow must have source_id set before write")
    if not row.ingestion_run_id:
        raise ValueError("CanonicalRow must have ingestion_run_id set before write")
    if row.event_date is None:
        raise ValueError("CanonicalRow must have event_date set before write")

    payload: dict[str, Any] = {
        "competitor_id": competitor_id,
        "discipline": row.discipline.value,
        "event_date": row.event_date.isoformat(),
        "event_name": row.event_name,
        "event_circuit": row.event_circuit.value,
        "division": row.division.value if row.division else "",
        "governing_body": governing_body or row.event_circuit.value,
        "log_species": row.wood_species,
        "log_diameter_mm": row.wood_diameter_mm,
        "log_length_mm": None,
        "log_specification": None,
        "final_score": row.final_score,
        "score_type": row.score_type.value,
        "final_score_policy": row.final_score_policy.value,
        "handicap_mark": None,
        "partner_competitor_id": partner_competitor_id,
        "dq_flag": row.dq_reason is not None,
        "dq_reason": row.dq_reason.value if row.dq_reason else None,
        "no_time_flag": row.dq_reason is not None and row.final_score is None,
        "scratch_flag": False,
        "runs": [asdict(r) for r in row.runs] if row.runs else None,
        "source_type": row.source_type.value,
        "source_id": row.source_id,
        "source_native_id": row.source_native_id,
        "ingestion_run_id": row.ingestion_run_id,
    }
    return payload


def _athlete_to_dict(athlete: CanonicalAthlete) -> dict:
    """Project a CanonicalAthlete into the columns of the `competitors` table."""
    return {
        "competitor_id": athlete.canonical_id,
        "canonical_name": athlete.primary_name,
        "federation_ids": athlete.federation_ids,
        "aliases": athlete.aliases,
        "birth_year": athlete.birth_year,
        "hometown": athlete.hometown,
        "eligibility": (
            [{"year": y, "status": s} for y, s in athlete.eligibility]
            if athlete.eligibility
            else None
        ),
    }


def _ingestion_run_to_dict(run: IngestionRun) -> dict:
    """Project an IngestionRun into the columns of the `ingestion_runs` table."""
    return {
        "run_id": run.run_id,
        "source_type": run.source_type.value,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "status": run.status,
        "rows_ingested": run.rows_ingested,
        "operator": run.operator,
        "notes": run.notes,
    }


# ----------------------------------------------------------------------------
# Public API: writes
# ----------------------------------------------------------------------------


def write_competitor(athlete: CanonicalAthlete) -> str:
    """Upsert a competitor into the `competitors` table by competitor_id.

    Returns the competitor_id (echoed back from the upsert response so
    callers can verify the row landed).
    """
    client = _get_client()
    payload = _athlete_to_dict(athlete)
    resp = (
        client.table("competitors")
        .upsert(payload, on_conflict="competitor_id")
        .execute()
    )
    if not resp.data:
        raise RuntimeError(
            f"write_competitor: upsert returned no data for {athlete.canonical_id}"
        )
    return resp.data[0]["competitor_id"]


def write_ingestion_run(run: IngestionRun) -> str:
    """Upsert an IngestionRun into the `ingestion_runs` table.

    Idempotent on run_id, so calling write_ingestion_run again with the
    same run after a state transition (running -> succeeded / failed /
    partial) replaces the row with the new state.
    """
    client = _get_client()
    payload = _ingestion_run_to_dict(run)
    resp = (
        client.table("ingestion_runs").upsert(payload, on_conflict="run_id").execute()
    )
    if not resp.data:
        raise RuntimeError(
            f"write_ingestion_run: upsert returned no data for {run.run_id}"
        )
    return resp.data[0]["run_id"]


def write_results(
    rows: list[CanonicalRow],
    competitor_id_resolver,  # callable: CompetitorRef -> competitor_id (string)
    governing_body_resolver=None,  # callable: CanonicalRow -> governing_body string; optional
) -> list[str]:
    """Bulk-insert results rows. Returns the list of result_ids assigned
    by the database (Supabase generates the ULIDs server-side via a
    DEFAULT, OR the caller supplies them; we let callers supply for
    deterministic round-trip in tests).

    `competitor_id_resolver` translates the per-row CompetitorRef list into
    competitor_id strings. The resolver knows whether the competitor is
    already in the `competitors` table or needs to be created via
    write_competitor first; this module does NOT make that choice.

    Pair events (DOUBLE_BUCK, JACK_AND_JILL) emit ONE row in the SQL
    table with both competitor_id and partner_competitor_id populated;
    the dataclass's two-element competitors list maps to the two FK columns.

    Team relays (3+ competitors) raise NotImplementedError. The current
    SQL schema can't represent them (only competitor_id +
    partner_competitor_id columns exist). Tracked as a follow-on schema
    extension; see PR-2 summary "Decisions made beyond the prompt".
    """
    if not rows:
        return []

    client = _get_client()
    payloads: list[dict] = []
    for row in rows:
        if not row.competitors:
            raise ValueError(
                f"CanonicalRow with source_id={row.source_id!r} has no competitors; "
                "cannot persist a result without a competitor link"
            )
        if len(row.competitors) > 2:
            raise NotImplementedError(
                f"Team-relay row with {len(row.competitors)} competitors not "
                "supported by the current SQL schema (only competitor_id + "
                "partner_competitor_id columns). Schema extension TBD."
            )

        primary_competitor_id = competitor_id_resolver(row.competitors[0])
        partner_competitor_id = (
            competitor_id_resolver(row.competitors[1])
            if len(row.competitors) == 2
            else None
        )
        governing_body = (
            governing_body_resolver(row) if governing_body_resolver else None
        )

        payloads.append(
            _row_to_dict(
                row,
                competitor_id=primary_competitor_id,
                partner_competitor_id=partner_competitor_id,
                governing_body=governing_body,
            )
        )

    resp = client.table("results").insert(payloads).execute()
    if not resp.data:
        raise RuntimeError("write_results: insert returned no data")
    return [r["result_id"] for r in resp.data]


# ----------------------------------------------------------------------------
# Public API: reads
# ----------------------------------------------------------------------------


def read_canonical(
    discipline: Optional[str] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
) -> Iterator[dict]:
    """Yield rows from the canonical_chopping_results view.

    This is the same view STRATHMARK reads via its strathmark_read role.
    From MNEMEX's own code (using service_role) we can also read the base
    `results` table directly when we need provenance fields; that's what
    `read_results_full` is for.

    Args:
        discipline: filter to a specific discipline value (matches
            Discipline enum values, e.g. "STANDING_BLOCK")
        since: ISO 8601 timestamp; only rows with last_modified_at > since
            are returned. Used by the STRATHMARK incremental sync.
        limit: cap result count (None = no limit; rely on view-level limits)

    Yields dicts whose keys are the view's columns. CanonicalRow does NOT
    round-trip cleanly because the view drops provenance/operational
    fields by design; for full-fidelity reads use `read_results_full`.
    """
    client = _get_client()
    q = client.table("canonical_chopping_results").select("*")
    if discipline is not None:
        q = q.eq("discipline", discipline)
    if since is not None:
        q = q.gt("last_modified_at", since)
    if limit is not None:
        q = q.limit(limit)
    resp = q.execute()
    for row in resp.data or []:
        yield row


def read_results_full(
    where: Optional[dict] = None,
    limit: Optional[int] = None,
) -> Iterator[dict]:
    """Yield rows from the `results` base table with full provenance fields.

    Service-role only. Used by reconciliation (PR 5), JSONL export (this
    PR), and ingestion audit. STRATHMARK never reaches this surface; it
    only sees `read_canonical`.
    """
    client = _get_client()
    q = client.table("results").select("*")
    if where:
        for col, val in where.items():
            q = q.eq(col, val)
    if limit is not None:
        q = q.limit(limit)
    resp = q.execute()
    for row in resp.data or []:
        yield row


def read_competitor(competitor_id: str) -> Optional[dict]:
    """Fetch a single competitor by competitor_id. Returns None if missing."""
    client = _get_client()
    resp = (
        client.table("competitors")
        .select("*")
        .eq("competitor_id", competitor_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]


def read_competitor_by_federation_id(
    federation_slug: str, federation_id: str
) -> Optional[dict]:
    """Fetch a competitor by their federation-specific ID via the JSONB
    GIN index. Returns None if no competitor is linked to that federation
    ID."""
    client = _get_client()
    # Use Supabase JSONB containment: federation_ids @> {"slug": "id"}
    resp = (
        client.table("competitors")
        .select("*")
        .contains("federation_ids", {federation_slug: federation_id})
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]


def read_ingestion_run(run_id: str) -> Optional[dict]:
    """Fetch an ingestion run by run_id."""
    client = _get_client()
    resp = (
        client.table("ingestion_runs")
        .select("*")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]


# ----------------------------------------------------------------------------
# Reconciliation queue (schema lands now; worker lands in PR 5)
# ----------------------------------------------------------------------------


def queue_for_reconciliation(provisional_result_id: str) -> str:
    """Insert a row into reconciliation_queue with status='pending'. The
    queue_id is generated by the caller (ULID) so we keep deterministic
    round-trip in tests. Returns the queue_id."""
    from mnemex.ingestion_runs import generate_run_id  # ULIDs reused here

    queue_id = generate_run_id()
    client = _get_client()
    client.table("reconciliation_queue").insert(
        {
            "queue_id": queue_id,
            "provisional_result_id": provisional_result_id,
            "status": "pending",
        }
    ).execute()
    return queue_id


# ----------------------------------------------------------------------------
# JSONL export (called by .github/workflows/jsonl-export.yml)
# ----------------------------------------------------------------------------


def export_canonical_jsonl(output_path: str, since: Optional[str] = None) -> int:
    """Stream canonical chopping results to a JSONL file. Returns the
    number of rows written.

    Args:
        output_path: filesystem path to write to
        since: optional ISO 8601 cutoff; only rows with
            last_modified_at > since are written. Used by the rolling
            7-day window in the scheduled GitHub Action.
    """
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for row in read_canonical(since=since):
            # Supabase returns datetime / date as ISO strings already
            f.write(json.dumps(row, default=str, separators=(",", ":")))
            f.write("\n")
            count += 1
    return count


# ----------------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------------


def health_check() -> dict:
    """Cheap connectivity check. Returns {"ok": True, "tables_seen": [...]}
    on success; raises on failure. Used by `mnemex doctor` (M7) and by
    CI integration test setup."""
    client = _get_client()
    # Supabase doesn't expose a generic ping endpoint; smoke-test via a
    # tiny query against federations (the smallest table in the schema).
    resp = client.table("federations").select("federation_slug").limit(1).execute()
    return {
        "ok": True,
        "tables_seen": ["federations"],
        "sample_count": len(resp.data or []),
    }
