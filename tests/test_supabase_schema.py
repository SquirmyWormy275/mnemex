"""Integration tests for the MNEMEX Supabase schema.

Asserts that the migration produced the expected database structure:
  - All tables exist with the documented columns
  - Indexes are present
  - The canonical_chopping_results view filters correctly
  - The strathmark_read role can SELECT the view but NOT base tables
  - The strathex_write role can INSERT into strathex_inbox but NOT
    SELECT, UPDATE, or DELETE anywhere
  - Federation seed rows are present

Gated on MNEMEX_TEST_SUPABASE=1 + staging credentials. See conftest.py
and docs/supabase-setup.md.

Run via:
    MNEMEX_TEST_SUPABASE=1 \
    MNEMEX_TEST_SUPABASE_URL=https://<staging-ref>.supabase.co \
    MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY=<staging-key> \
    pytest tests/test_supabase_schema.py -v
"""

from __future__ import annotations

import pytest

# Marker on every test in this file: requires the supabase_credentials
# fixture (which skips when MNEMEX_TEST_SUPABASE is unset).
pytestmark = pytest.mark.usefixtures("supabase_credentials")


# ----------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------


class TestTablesExist:
    """Each table from the migration is queryable with a service-role client."""

    def test_competitors(self, supabase_client) -> None:
        resp = supabase_client.table("competitors").select("*").limit(0).execute()
        assert resp.data == []

    def test_results(self, supabase_client) -> None:
        resp = supabase_client.table("results").select("*").limit(0).execute()
        assert resp.data == []

    def test_ingestion_runs(self, supabase_client) -> None:
        resp = supabase_client.table("ingestion_runs").select("*").limit(0).execute()
        assert resp.data == []

    def test_reconciliation_queue(self, supabase_client) -> None:
        resp = (
            supabase_client.table("reconciliation_queue").select("*").limit(0).execute()
        )
        assert resp.data == []

    def test_strathex_inbox(self, supabase_client) -> None:
        resp = supabase_client.table("strathex_inbox").select("*").limit(0).execute()
        assert resp.data == []

    def test_federations(self, supabase_client) -> None:
        resp = supabase_client.table("federations").select("*").limit(1).execute()
        # Seed data should have populated this table.
        assert resp.data, "federations table is empty; the seed inserts didn't run"


# ----------------------------------------------------------------------------
# Federation seed data
# ----------------------------------------------------------------------------


class TestFederationSeedData:
    """The migration seeds nine federations: stihl, aaa, awfc, ala, lwc,
    osu, csu, uidaho, umont. Verify each is present."""

    EXPECTED_SLUGS = {
        "stihl",
        "aaa",
        "awfc",
        "ala",
        "lwc",
        "osu",
        "csu",
        "uidaho",
        "umont",
    }

    def test_all_expected_slugs_present(self, supabase_client) -> None:
        resp = supabase_client.table("federations").select("federation_slug").execute()
        present = {r["federation_slug"] for r in resp.data}
        missing = self.EXPECTED_SLUGS - present
        assert not missing, f"Missing federation seed rows: {missing}"

    def test_seed_rows_have_required_columns(self, supabase_client) -> None:
        resp = (
            supabase_client.table("federations")
            .select("*")
            .eq("federation_slug", "stihl")
            .execute()
        )
        assert resp.data, "stihl seed row missing"
        row = resp.data[0]
        assert row["display_name"]
        assert row["governing_body_full"]


# ----------------------------------------------------------------------------
# Canonical view filtering
# ----------------------------------------------------------------------------


class TestCanonicalChoppingResultsView:
    """The view exposes only canonical, chopping-discipline rows.
    Provisional rows, superseded rows, and non-chopping disciplines are
    hidden."""

    def _seed_competitor(
        self, supabase_client, competitor_id: str = "01HTESTCOMP000000000000001"
    ) -> str:
        supabase_client.table("competitors").upsert(
            {
                "competitor_id": competitor_id,
                "canonical_name": "Test Competitor",
                "federation_ids": {"stihl": "test_id"},
            },
            on_conflict="competitor_id",
        ).execute()
        return competitor_id

    def _seed_run(
        self, supabase_client, run_id: str = "01HTESTRUN0000000000000001"
    ) -> str:
        supabase_client.table("ingestion_runs").upsert(
            {
                "run_id": run_id,
                "source_type": "scraper",
                "started_at": "2026-05-04T00:00:00Z",
                "status": "succeeded",
            },
            on_conflict="run_id",
        ).execute()
        return run_id

    def _cleanup(self, supabase_client) -> None:
        supabase_client.table("results").delete().like(
            "source_id", "test:view:%"
        ).execute()

    def test_canonical_chopping_row_is_visible(self, supabase_client) -> None:
        self._cleanup(supabase_client)
        comp = self._seed_competitor(supabase_client)
        run = self._seed_run(supabase_client)
        supabase_client.table("results").insert(
            {
                "result_id": "01HTESTRES000000000VISIBLE1",
                "competitor_id": comp,
                "discipline": "STANDING_BLOCK",
                "event_date": "2024-09-15",
                "event_name": "Test Event A",
                "event_circuit": "stihl_pro",
                "division": "open",
                "governing_body": "stihl",
                "final_score": 24.31,
                "score_type": "time",
                "final_score_policy": "single_run",
                "source_type": "federation_upload",
                "source_id": "test:view:visible",
                "ingestion_run_id": run,
                "provisional": False,
            }
        ).execute()
        resp = (
            supabase_client.table("canonical_chopping_results")
            .select("*")
            .eq("result_id", "01HTESTRES000000000VISIBLE1")
            .execute()
        )
        assert len(resp.data) == 1
        self._cleanup(supabase_client)

    def test_provisional_row_is_hidden(self, supabase_client) -> None:
        self._cleanup(supabase_client)
        comp = self._seed_competitor(supabase_client)
        run = self._seed_run(supabase_client)
        supabase_client.table("results").insert(
            {
                "result_id": "01HTESTRES00000000PROVISION1",
                "competitor_id": comp,
                "discipline": "STANDING_BLOCK",
                "event_date": "2024-09-15",
                "event_name": "Test Event B",
                "event_circuit": "stihl_pro",
                "division": "open",
                "governing_body": "stihl",
                "final_score": 24.31,
                "score_type": "time",
                "final_score_policy": "single_run",
                "source_type": "scraper",
                "source_id": "test:view:provisional",
                "ingestion_run_id": run,
                "provisional": True,
                "canonical_id": None,
            }
        ).execute()
        resp = (
            supabase_client.table("canonical_chopping_results")
            .select("*")
            .eq("result_id", "01HTESTRES00000000PROVISION1")
            .execute()
        )
        assert resp.data == [], "provisional row leaked into canonical view"
        self._cleanup(supabase_client)

    def test_non_chopping_discipline_is_hidden(self, supabase_client) -> None:
        self._cleanup(supabase_client)
        comp = self._seed_competitor(supabase_client)
        run = self._seed_run(supabase_client)
        supabase_client.table("results").insert(
            {
                "result_id": "01HTESTRES000000000DENDROL1",
                "competitor_id": comp,
                "discipline": "DENDROLOGY",
                "event_date": "2024-09-15",
                "event_name": "Test Event C",
                "event_circuit": "awfc_college",
                "division": "open",
                "governing_body": "awfc",
                "final_score": 17.0,
                "score_type": "raw_score",
                "final_score_policy": "single_run",
                "source_type": "federation_upload",
                "source_id": "test:view:dendrology",
                "ingestion_run_id": run,
                "provisional": False,
            }
        ).execute()
        resp = (
            supabase_client.table("canonical_chopping_results")
            .select("*")
            .eq("result_id", "01HTESTRES000000000DENDROL1")
            .execute()
        )
        assert resp.data == [], "non-chopping (Tier 3) row leaked into canonical view"
        self._cleanup(supabase_client)

    def test_view_drops_provenance_columns(self, supabase_client) -> None:
        """The view exposes only consumer-facing columns. STRATHMARK should
        never see source_type, source_id, ingestion_run_id, provisional,
        canonical_id, reconciled_at, ingested_at, source_native_id.
        """
        self._cleanup(supabase_client)
        comp = self._seed_competitor(supabase_client)
        run = self._seed_run(supabase_client)
        supabase_client.table("results").insert(
            {
                "result_id": "01HTESTRES00000000COLUMNS01",
                "competitor_id": comp,
                "discipline": "UNDERHAND",
                "event_date": "2024-09-15",
                "event_name": "Test Event D",
                "event_circuit": "stihl_pro",
                "division": "open",
                "governing_body": "stihl",
                "final_score": 16.78,
                "score_type": "time",
                "final_score_policy": "single_run",
                "source_type": "federation_upload",
                "source_id": "test:view:columns",
                "ingestion_run_id": run,
                "provisional": False,
            }
        ).execute()
        resp = (
            supabase_client.table("canonical_chopping_results")
            .select("*")
            .eq("result_id", "01HTESTRES00000000COLUMNS01")
            .execute()
        )
        assert len(resp.data) == 1
        row = resp.data[0]
        forbidden = {
            "source_type",
            "source_id",
            "source_native_id",
            "ingestion_run_id",
            "ingested_at",
            "provisional",
            "canonical_id",
            "reconciled_at",
        }
        leaked = forbidden & set(row.keys())
        assert not leaked, f"Provenance columns leaked through view: {leaked}"
        self._cleanup(supabase_client)


# ----------------------------------------------------------------------------
# Indexes
# ----------------------------------------------------------------------------


class TestIndexesExist:
    """Verify the documented indexes are present via pg_indexes.

    pg_indexes is queryable from any role with default Postgres
    permissions; we use the service_role client to bypass RLS.
    """

    def _index_names(self, supabase_client, table: str) -> set[str]:
        # supabase-py doesn't expose direct SQL execution from the
        # client, but it does expose RPC calls. We use the postgrest
        # filter on pg_indexes via the public schema. If the project
        # doesn't have a `pg_indexes` view exposed, this falls back
        # to a no-op assertion that just confirms a query against the
        # table executes.
        try:
            resp = (
                supabase_client.from_("pg_indexes")
                .select("indexname")
                .eq("tablename", table)
                .execute()
            )
            return {r["indexname"] for r in resp.data or []}
        except Exception:
            # pg_indexes view may not be exposed in PostgREST schema
            # search path; skip the strict check and rely on the
            # idx-using queries in TestStathmarkSyncIndexUsage to
            # validate functionally.
            pytest.skip("pg_indexes is not exposed via PostgREST in this project")

    def test_results_has_discipline_last_modified_idx(self, supabase_client) -> None:
        names = self._index_names(supabase_client, "results")
        assert "idx_results_discipline_last_modified" in names

    def test_results_has_event_date_name_idx(self, supabase_client) -> None:
        names = self._index_names(supabase_client, "results")
        assert "idx_results_event_date_name" in names

    def test_results_has_competitor_id_idx(self, supabase_client) -> None:
        names = self._index_names(supabase_client, "results")
        assert "idx_results_competitor_id" in names

    def test_competitors_has_federation_ids_gin_idx(self, supabase_client) -> None:
        names = self._index_names(supabase_client, "competitors")
        assert "idx_competitors_federation_ids_gin" in names


# ----------------------------------------------------------------------------
# RLS policies (functional, not introspective)
#
# Best-tested via separate clients authenticated as the strathmark_read
# and strathex_write roles. Those clients require role-specific JWTs
# minted from the Supabase JWT secret.
#
# When MNEMEX_TEST_SUPABASE_STRATHMARK_JWT and
# MNEMEX_TEST_SUPABASE_STRATHEX_JWT are not set, these tests skip with
# a hint to set them. The schema-level tests above are the minimum bar;
# RLS verification is the ideal bar.
# ----------------------------------------------------------------------------


def _strathmark_client():
    import os

    jwt = os.environ.get("MNEMEX_TEST_SUPABASE_STRATHMARK_JWT")
    url = os.environ.get("MNEMEX_TEST_SUPABASE_URL")
    if not jwt or not url:
        pytest.skip(
            "MNEMEX_TEST_SUPABASE_STRATHMARK_JWT not set; skipping strathmark RLS tests. "
            "Mint a JWT with role=strathmark_read against the staging project."
        )
    from supabase import create_client

    return create_client(url, jwt)


def _strathex_client():
    import os

    jwt = os.environ.get("MNEMEX_TEST_SUPABASE_STRATHEX_JWT")
    url = os.environ.get("MNEMEX_TEST_SUPABASE_URL")
    if not jwt or not url:
        pytest.skip(
            "MNEMEX_TEST_SUPABASE_STRATHEX_JWT not set; skipping strathex RLS tests. "
            "Mint a JWT with role=strathex_write against the staging project."
        )
    from supabase import create_client

    return create_client(url, jwt)


class TestStrathmarkReadRole:
    """strathmark_read SELECTs the view; nothing else."""

    def test_can_select_canonical_view(self) -> None:
        client = _strathmark_client()
        resp = (
            client.table("canonical_chopping_results")
            .select("result_id")
            .limit(1)
            .execute()
        )
        assert resp.data is not None  # empty list is fine

    def test_cannot_read_results_base_table(self) -> None:
        client = _strathmark_client()
        with pytest.raises(Exception):
            client.table("results").select("*").limit(1).execute()

    def test_cannot_read_competitors(self) -> None:
        client = _strathmark_client()
        with pytest.raises(Exception):
            client.table("competitors").select("*").limit(1).execute()

    def test_cannot_insert_into_view(self) -> None:
        client = _strathmark_client()
        with pytest.raises(Exception):
            client.table("canonical_chopping_results").insert(
                {"result_id": "01HTESTNOPE000000000000001"}
            ).execute()


class TestStrathexWriteRole:
    """strathex_write INSERTs into strathex_inbox; nothing else."""

    def test_can_insert_into_inbox(self) -> None:
        client = _strathex_client()
        resp = (
            client.table("strathex_inbox")
            .insert(
                {
                    "inbox_id": "01HTESTINBOX0000000000001",
                    "strathex_event_id": "test_strathex_event_xyz_001",
                    "payload": {"test": "minimal"},
                }
            )
            .execute()
        )
        assert resp.data, "strathex_write should be able to INSERT into strathex_inbox"

    def test_cannot_select_from_inbox(self) -> None:
        client = _strathex_client()
        with pytest.raises(Exception):
            client.table("strathex_inbox").select("*").limit(1).execute()

    def test_cannot_read_results(self) -> None:
        client = _strathex_client()
        with pytest.raises(Exception):
            client.table("results").select("*").limit(1).execute()

    def test_cannot_read_view(self) -> None:
        client = _strathex_client()
        with pytest.raises(Exception):
            client.table("canonical_chopping_results").select("*").limit(1).execute()
