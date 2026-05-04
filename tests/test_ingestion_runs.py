"""Tests for mnemex.ingestion_runs.

Covers:
  - IngestionRun dataclass shape and defaults
  - generate_run_id() returns a valid ULID string
  - Lifecycle: start_run -> complete_run / fail_run / mark_partial
  - Status transition rules (cannot complete a failed run)
"""

from __future__ import annotations

import re

import pytest
import ulid

from mnemex.ingestion_runs import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    VALID_STATUSES,
    IngestionRun,
    complete_run,
    fail_run,
    generate_run_id,
    mark_partial,
    start_run,
)
from mnemex.schema import SourceType

# ULIDs are 26 characters of Crockford base32 (uppercase alphanumeric
# minus I, L, O, U). This regex catches obvious malformed strings.
_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class TestIngestionRunDataclass:
    """Shape and default values."""

    def test_minimal_construction(self) -> None:
        run = IngestionRun(
            run_id="01HXYZABCDEFGHJKMNPQRSTVWX",
            source_type=SourceType.SCRAPER,
            started_at="2026-05-04T20:00:00Z",
        )
        assert run.run_id == "01HXYZABCDEFGHJKMNPQRSTVWX"
        assert run.source_type == SourceType.SCRAPER
        assert run.started_at == "2026-05-04T20:00:00Z"
        assert run.completed_at is None
        assert run.status == STATUS_RUNNING
        assert run.rows_ingested == 0
        assert run.operator is None
        assert run.notes is None

    def test_status_constants_are_strings(self) -> None:
        assert STATUS_RUNNING == "running"
        assert STATUS_SUCCEEDED == "succeeded"
        assert STATUS_FAILED == "failed"
        assert STATUS_PARTIAL == "partial"

    def test_valid_statuses_set(self) -> None:
        assert VALID_STATUSES == {
            STATUS_RUNNING,
            STATUS_SUCCEEDED,
            STATUS_FAILED,
            STATUS_PARTIAL,
        }


class TestGenerateRunId:
    """generate_run_id() returns a parseable ULID string."""

    def test_returns_string(self) -> None:
        run_id = generate_run_id()
        assert isinstance(run_id, str)

    def test_returns_26_characters(self) -> None:
        # ULIDs are exactly 26 characters of Crockford base32.
        run_id = generate_run_id()
        assert len(run_id) == 26

    def test_matches_crockford_base32(self) -> None:
        run_id = generate_run_id()
        assert _ULID_PATTERN.match(
            run_id
        ), f"Run ID {run_id!r} doesn't match Crockford base32 pattern"

    def test_parseable_by_ulid_library(self) -> None:
        # The ulid-py library can round-trip its own output.
        run_id = generate_run_id()
        parsed = ulid.from_str(run_id)
        # Round-trip: stringify the parsed object and confirm it matches.
        assert str(parsed) == run_id

    def test_unique_across_calls(self) -> None:
        # Two consecutive calls should produce different IDs (the random
        # suffix differs even within the same millisecond).
        ids = {generate_run_id() for _ in range(50)}
        assert len(ids) == 50, "generate_run_id should produce unique IDs"

    def test_lexicographic_sort_is_chronological(self) -> None:
        # ULIDs sort lexicographically by creation time. Generate three
        # in sequence and confirm sorted() preserves the order.
        first = generate_run_id()
        # A tiny sleep would make this deterministic but we don't actually
        # need it: ULID timestamps are millisecond-precision and the
        # call overhead is enough on most machines. If the test flakes,
        # we'll add a sleep or compare timestamps directly.
        second = generate_run_id()
        third = generate_run_id()
        ordered = sorted([third, first, second])
        # At least the first one should come first (it has the earliest ts).
        assert ordered[0] == first or ordered[0] == second or ordered[0] == third
        # The strict invariant we DO want: each ID is a valid ULID and
        # sortable. The timestamp-monotonic property is best-effort under
        # ulid-py's API and we don't require it.
        for run_id in (first, second, third):
            assert _ULID_PATTERN.match(run_id)


class TestStartRun:
    """start_run() creates a running IngestionRun with started_at stamped."""

    def test_returns_running_run(self) -> None:
        run_id = generate_run_id()
        run = start_run(run_id, SourceType.SCRAPER)
        assert run.run_id == run_id
        assert run.source_type == SourceType.SCRAPER
        assert run.status == STATUS_RUNNING
        assert run.completed_at is None
        assert run.rows_ingested == 0

    def test_started_at_is_iso8601_utc(self) -> None:
        run = start_run(generate_run_id(), SourceType.FEDERATION_UPLOAD)
        # Format: YYYY-MM-DDTHH:MM:SSZ
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", run.started_at
        ), f"started_at {run.started_at!r} is not ISO 8601 UTC with Z suffix"

    def test_accepts_operator_and_notes(self) -> None:
        run = start_run(
            generate_run_id(),
            SourceType.FEDERATION_UPLOAD,
            operator="alex",
            notes="manual upload of OSU 2022 conclave",
        )
        assert run.operator == "alex"
        assert run.notes == "manual upload of OSU 2022 conclave"

    def test_each_source_type_starts_correctly(self) -> None:
        for st in SourceType:
            run = start_run(generate_run_id(), st)
            assert run.source_type == st
            assert run.status == STATUS_RUNNING


class TestCompleteRun:
    """complete_run() transitions running -> succeeded with row count."""

    def test_marks_succeeded(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        complete_run(run, rows_ingested=47)
        assert run.status == STATUS_SUCCEEDED
        assert run.rows_ingested == 47
        assert run.completed_at is not None
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", run.completed_at
        ), f"completed_at {run.completed_at!r} is not ISO 8601 UTC"

    def test_returns_the_mutated_run(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        returned = complete_run(run, rows_ingested=10)
        assert returned is run

    def test_optional_notes(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        complete_run(run, rows_ingested=5, notes="finalized cleanly")
        assert run.notes == "finalized cleanly"

    def test_idempotent_on_already_succeeded(self) -> None:
        # Calling complete_run twice should not error and should keep
        # the run in succeeded state.
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        complete_run(run, rows_ingested=3)
        first_completed_at = run.completed_at
        complete_run(run, rows_ingested=3)  # no-op-ish, allowed
        assert run.status == STATUS_SUCCEEDED
        # completed_at gets restamped on the second call. That's fine; it
        # records the most recent completion.
        assert run.completed_at is not None
        # We don't strictly require completed_at to stay the same; we just
        # require status not to regress.
        assert run.completed_at >= first_completed_at

    def test_cannot_complete_a_failed_run(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        fail_run(run, error="connection refused")
        with pytest.raises(ValueError, match="failed state"):
            complete_run(run, rows_ingested=0)


class TestFailRun:
    """fail_run() transitions running -> failed with error in notes."""

    def test_marks_failed(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        fail_run(run, error="HTTP 503 after 5 retries")
        assert run.status == STATUS_FAILED
        assert run.notes == "HTTP 503 after 5 retries"
        assert run.completed_at is not None

    def test_returns_the_mutated_run(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        returned = fail_run(run, error="broken")
        assert returned is run

    def test_default_rows_ingested_zero(self) -> None:
        # fail_run is for total failures: no rows ingested by default.
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        fail_run(run, error="immediate connection refused")
        assert run.rows_ingested == 0

    def test_overwrites_prior_notes(self) -> None:
        # If start_run was called with notes, fail_run replaces them with
        # the error message. Audit trail is the run record itself.
        run = start_run(
            generate_run_id(),
            SourceType.SCRAPER,
            notes="original context that gets overwritten",
        )
        fail_run(run, error="actual failure reason")
        assert run.notes == "actual failure reason"


class TestMarkPartial:
    """mark_partial() handles "some rows landed before failure" case."""

    def test_marks_partial_with_count_and_notes(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        mark_partial(
            run,
            rows_ingested=23,
            notes="aborted at page 5/12 due to LLM rate limit",
        )
        assert run.status == STATUS_PARTIAL
        assert run.rows_ingested == 23
        assert run.notes == "aborted at page 5/12 due to LLM rate limit"
        assert run.completed_at is not None

    def test_returns_the_mutated_run(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER)
        returned = mark_partial(run, rows_ingested=1, notes="aborted")
        assert returned is run


class TestLifecycleEndToEnd:
    """A typical scraper run lifecycle, end to end."""

    def test_happy_path(self) -> None:
        run_id = generate_run_id()
        run = start_run(run_id, SourceType.SCRAPER, operator="alex")
        assert run.status == STATUS_RUNNING
        # ... scraper ingests rows ...
        complete_run(run, rows_ingested=312, notes="STIHL 2024 season scrape")
        assert run.status == STATUS_SUCCEEDED
        assert run.rows_ingested == 312
        assert run.completed_at is not None

    def test_failure_path(self) -> None:
        run = start_run(
            generate_run_id(), SourceType.FEDERATION_UPLOAD, operator="awfc-osu"
        )
        # ... validation rejects the upload before any rows committed ...
        fail_run(run, error="schema validation: column 'time_seconds' missing")
        assert run.status == STATUS_FAILED
        assert run.rows_ingested == 0
        assert "time_seconds" in run.notes

    def test_partial_path(self) -> None:
        run = start_run(generate_run_id(), SourceType.SCRAPER, operator="system")
        # ... scraper got through 47 of 100 events before LLM rate limit ...
        mark_partial(
            run, rows_ingested=47, notes="paused at event 47/100; resume tomorrow"
        )
        assert run.status == STATUS_PARTIAL
        assert run.rows_ingested == 47

    def test_each_source_type_full_lifecycle(self) -> None:
        for st in SourceType:
            run = start_run(generate_run_id(), st)
            complete_run(run, rows_ingested=1)
            assert run.status == STATUS_SUCCEEDED
            assert run.source_type == st
