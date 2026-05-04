"""Schema invariants and tier-classification correctness tests.

Covers:
  - The 5 enums (ScoreType, Division, DQReason, ExtractionStatus, SourceType)
  - The Discipline enum and tier-classification invariants
  - STRATHMARK_DISCIPLINE_MAP uniqueness and Tier-3 exclusion
  - DEFAULT_SCORE_POLICY total coverage
  - CanonicalRow construction with the new provenance + reconciliation fields
"""

from __future__ import annotations

from mnemex.schema import (
    DEFAULT_SCORE_POLICY,
    STRATHMARK_DISCIPLINE_MAP,
    TIER1_DISCIPLINES,
    TIER2_DISCIPLINES,
    TIER3_DISCIPLINES,
    CanonicalRow,
    CompetitorRef,
    Discipline,
    DQReason,
    EventCircuit,
    ExtractionStatus,
    FinalScorePolicy,
    RunResult,
    ScoreType,
    SourceType,
)


class TestTierClassification:
    """Schema invariant: every Discipline belongs to exactly one tier."""

    def test_every_discipline_classified(self) -> None:
        all_classified = TIER1_DISCIPLINES | TIER2_DISCIPLINES | TIER3_DISCIPLINES
        all_disciplines = set(Discipline)
        unclassified = all_disciplines - all_classified
        assert not unclassified, (
            f"Disciplines not in any tier: {unclassified}. "
            f"Every Discipline must be in TIER1, TIER2, or TIER3."
        )

    def test_tiers_are_disjoint(self) -> None:
        assert not (
            TIER1_DISCIPLINES & TIER2_DISCIPLINES
        ), "TIER1 and TIER2 must be disjoint"
        assert not (
            TIER1_DISCIPLINES & TIER3_DISCIPLINES
        ), "TIER1 and TIER3 must be disjoint"
        assert not (
            TIER2_DISCIPLINES & TIER3_DISCIPLINES
        ), "TIER2 and TIER3 must be disjoint"

    def test_tier1_contains_known_speed_events(self) -> None:
        # Sanity-check the load-bearing Tier 1 entries.
        assert Discipline.UNDERHAND in TIER1_DISCIPLINES
        assert Discipline.STANDING_BLOCK in TIER1_DISCIPLINES
        assert Discipline.SINGLE_BUCK in TIER1_DISCIPLINES
        assert Discipline.HORIZONTAL_SPEED in TIER1_DISCIPLINES
        assert Discipline.VERTICAL_SPEED in TIER1_DISCIPLINES

    def test_tier3_contains_caber_and_dendrology(self) -> None:
        # Sanity-check the load-bearing "never exported" entries.
        assert Discipline.CABER_THROW in TIER3_DISCIPLINES
        assert Discipline.DENDROLOGY in TIER3_DISCIPLINES
        assert Discipline.AXE_THROW in TIER3_DISCIPLINES
        assert Discipline.BIRLING in TIER3_DISCIPLINES

    def test_total_discipline_count_is_32(self) -> None:
        # 28 original + 4 new forestry knowledge events = 32.
        # If this test fails because the count grew on purpose, update the
        # number and the per-tier counts below.
        assert len(set(Discipline)) == 32

    def test_tier_counts(self) -> None:
        # Concrete counts catch silent reclassification regressions.
        assert len(TIER1_DISCIPLINES) == 13
        assert len(TIER2_DISCIPLINES) == 2
        assert len(TIER3_DISCIPLINES) == 17  # 13 original + 4 new knowledge events


class TestNewKnowledgeDisciplines:
    """The four forestry knowledge events added in the additive-schema PR."""

    def test_new_disciplines_exist(self) -> None:
        assert Discipline.WILDLIFE_ID.value == "WILDLIFE_ID"
        assert Discipline.COMPASS_PACING.value == "COMPASS_PACING"
        assert Discipline.FORESTRY_BOWL.value == "FORESTRY_BOWL"
        assert Discipline.WOOD_ID.value == "WOOD_ID"

    def test_new_disciplines_are_tier3(self) -> None:
        for d in (
            Discipline.WILDLIFE_ID,
            Discipline.COMPASS_PACING,
            Discipline.FORESTRY_BOWL,
            Discipline.WOOD_ID,
        ):
            assert d in TIER3_DISCIPLINES, f"{d.name} must be Tier 3 (knowledge event)"
            assert d not in TIER1_DISCIPLINES
            assert d not in TIER2_DISCIPLINES

    def test_new_disciplines_have_score_policy(self) -> None:
        # Forestry knowledge events default to SINGLE_RUN; quiz format,
        # one score per athlete per event.
        for d in (
            Discipline.WILDLIFE_ID,
            Discipline.COMPASS_PACING,
            Discipline.FORESTRY_BOWL,
            Discipline.WOOD_ID,
        ):
            assert DEFAULT_SCORE_POLICY[d] == FinalScorePolicy.SINGLE_RUN


class TestStrathmarkDisciplineMap:
    """Each Tier 1 discipline maps to a UNIQUE STRATHMARK token.

    SB collision (Standing Block vs Single Buck both -> "SB") was a
    correctness defect caught at /plan-eng-review iter-3 and fixed by
    using STB / SBUCK as distinct tokens.
    """

    def test_every_tier1_has_a_token(self) -> None:
        unmapped = TIER1_DISCIPLINES - set(STRATHMARK_DISCIPLINE_MAP.keys())
        assert not unmapped, f"Tier 1 disciplines without STRATHMARK token: {unmapped}"

    def test_tokens_are_unique(self) -> None:
        tokens = list(STRATHMARK_DISCIPLINE_MAP.values())
        duplicates = {t for t in tokens if tokens.count(t) > 1}
        assert not duplicates, (
            f"Duplicate STRATHMARK tokens: {duplicates}. "
            f"Each Discipline must map to a unique token."
        )

    def test_sb_collision_is_resolved(self) -> None:
        # Standing Block != Single Buck. Different kinematics.
        assert (
            STRATHMARK_DISCIPLINE_MAP[Discipline.STANDING_BLOCK]
            != STRATHMARK_DISCIPLINE_MAP[Discipline.SINGLE_BUCK]
        ), "Standing Block and Single Buck must have distinct STRATHMARK tokens"

    def test_no_tier3_discipline_has_a_token(self) -> None:
        # Tier 3 events never export. Adding them to the map would be a bug.
        leaked = TIER3_DISCIPLINES & set(STRATHMARK_DISCIPLINE_MAP.keys())
        assert (
            not leaked
        ), f"Tier 3 disciplines must not appear in STRATHMARK_DISCIPLINE_MAP: {leaked}"


class TestDefaultScorePolicy:
    """Every Discipline has a default FinalScorePolicy. Ingest parsers
    fall back to this when the source doesn't specify."""

    def test_every_discipline_has_a_default(self) -> None:
        missing = set(Discipline) - set(DEFAULT_SCORE_POLICY.keys())
        assert not missing, f"Disciplines without DEFAULT_SCORE_POLICY entry: {missing}"

    def test_covers_all_32_disciplines(self) -> None:
        # Concrete count check; DEFAULT_SCORE_POLICY must grow alongside Discipline.
        assert len(DEFAULT_SCORE_POLICY) == 32


class TestSourceType:
    """SourceType drives the provisional-flag default and reconciliation strategy."""

    def test_three_expected_values(self) -> None:
        values = {st.value for st in SourceType}
        assert values == {"scraper", "federation_upload", "strathex_finalization"}

    def test_scraper_value(self) -> None:
        assert SourceType.SCRAPER.value == "scraper"

    def test_federation_upload_value(self) -> None:
        assert SourceType.FEDERATION_UPLOAD.value == "federation_upload"

    def test_strathex_finalization_value(self) -> None:
        assert SourceType.STRATHEX_FINALIZATION.value == "strathex_finalization"


class TestCanonicalRowProvenance:
    """The new provenance fields replacing the legacy `source: str` field."""

    def test_minimal_row_constructs_with_defaults(self) -> None:
        # No required positional args; every field has a sensible default.
        row = CanonicalRow()
        assert row.source_type == SourceType.SCRAPER
        assert row.source_id == ""
        assert row.source_native_id is None
        assert row.ingestion_run_id is None
        assert row.ingested_at == ""
        assert row.verified_at is None
        assert row.verified_by is None
        assert row.discipline == Discipline.UNDERHAND
        assert row.score_type == ScoreType.TIME
        assert row.event_circuit == EventCircuit.UNKNOWN
        assert row.final_score_policy == FinalScorePolicy.SINGLE_RUN
        assert row.extraction_status == ExtractionStatus.OK
        assert row.identity_resolution_required is False
        assert row.competitors == []
        assert row.runs == []

    def test_scraper_row_provisional_by_default(self) -> None:
        # Documented default: scraped rows are provisional, canonical_id is None.
        row = CanonicalRow(
            source_type=SourceType.SCRAPER,
            source_id="stihl:event/12345",
        )
        assert row.provisional is True
        assert row.canonical_id is None

    def test_federation_upload_row_construction(self) -> None:
        row = CanonicalRow(
            source_type=SourceType.FEDERATION_UPLOAD,
            source_id="awfc:um-pro-am-2026:batch-1",
            provisional=False,
        )
        assert row.source_type == SourceType.FEDERATION_UPLOAD
        # Note: the *default* is provisional=True; federation uploads must set
        # provisional=False explicitly. The reconciliation module enforces this
        # invariant at row commit time (lands at M1+).
        assert row.provisional is False

    def test_strathex_finalization_row_construction(self) -> None:
        row = CanonicalRow(
            source_type=SourceType.STRATHEX_FINALIZATION,
            source_id="strathex_event_uuid_abc123",
            provisional=False,
        )
        assert row.source_type == SourceType.STRATHEX_FINALIZATION
        assert row.provisional is False


class TestCanonicalRowReconciliation:
    """The reconciliation fields: canonical_id self-FK, reconciled_at, last_modified_at."""

    def test_canonical_id_default_none(self) -> None:
        # Non-null only when this row has been superseded by another row.
        row = CanonicalRow()
        assert row.canonical_id is None

    def test_canonical_id_records_superseder(self) -> None:
        # Reconciliation sets this to the superseding row's ID.
        scraped_row = CanonicalRow(
            source_type=SourceType.SCRAPER,
            source_id="stihl:event/12345",
            canonical_id="federation_upload_row_abc",  # superseded by this id
            reconciled_at="2026-05-04T20:00:00Z",
        )
        assert scraped_row.canonical_id == "federation_upload_row_abc"
        assert scraped_row.reconciled_at == "2026-05-04T20:00:00Z"

    def test_reconciled_at_default_none(self) -> None:
        row = CanonicalRow()
        assert row.reconciled_at is None

    def test_last_modified_at_default_empty(self) -> None:
        row = CanonicalRow()
        assert row.last_modified_at == ""


class TestCanonicalRowResults:
    """Existing result-handling tests carry over; rewritten to use new
    provenance fields rather than the legacy `source: str`."""

    def test_row_with_competitor(self) -> None:
        row = CanonicalRow(
            source_type=SourceType.SCRAPER,
            source_id="stihl:event/12345",
            discipline=Discipline.UNDERHAND,
            final_score=16.78,
            competitors=[
                CompetitorRef(
                    canonical_id="canonical/erin-lavoie-1985",
                    name_as_recorded="Erin LaVoie",
                ),
            ],
        )
        assert len(row.competitors) == 1
        assert row.competitors[0].canonical_id == "canonical/erin-lavoie-1985"
        assert row.final_score == 16.78

    def test_pair_event_has_two_competitors(self) -> None:
        row = CanonicalRow(
            source_type=SourceType.SCRAPER,
            source_id="ala_pdf:2025-09",
            discipline=Discipline.JACK_AND_JILL,
            final_score=8.34,
            competitors=[
                CompetitorRef(
                    canonical_id="canonical/lauren-bergman-2001",
                    name_as_recorded="Lauren Bergman",
                ),
                CompetitorRef(
                    canonical_id="canonical/cody-labahn-1985",
                    name_as_recorded="Cody Labahn",
                ),
            ],
        )
        assert len(row.competitors) == 2

    def test_dq_row_has_no_final_score(self) -> None:
        row = CanonicalRow(
            source_type=SourceType.SCRAPER,
            source_id="ala_pdf:2025-09",
            discipline=Discipline.HOT_SAW,
            final_score=None,
            dq_reason=DQReason.DNF,
        )
        assert row.final_score is None
        assert row.dq_reason == DQReason.DNF


class TestEnumValues:
    """Stable string values for serialization. Renaming an enum value
    breaks data on disk; the schema migration policy explicitly forbids it."""

    def test_score_type_values(self) -> None:
        assert ScoreType.TIME.value == "time"
        assert ScoreType.HITS.value == "hits"
        assert ScoreType.PLACE_ONLY.value == "place_only"

    def test_discipline_values_match_names(self) -> None:
        # Every Discipline value is the same as its name (no string
        # diverges from the symbol). Catches typos and accidental renames.
        for d in Discipline:
            assert d.value == d.name, f"Discipline.{d.name} value drifted: {d.value}"

    def test_extraction_status_includes_pending_states(self) -> None:
        # Pending-queue states surfaced in `mnemex review --failures`.
        assert ExtractionStatus.PENDING_BUDGET.value == "pending_budget"
        assert ExtractionStatus.PENDING_STALE.value == "pending_stale"
        assert ExtractionStatus.NEEDS_INPUT.value == "needs_input"


class TestRunResult:
    def test_completed_run(self) -> None:
        r = RunResult(run_index=1, value=27.25)
        assert r.value == 27.25
        assert r.dq_reason is None

    def test_dq_run(self) -> None:
        r = RunResult(run_index=1, value=None, dq_reason=DQReason.DQ_TIME)
        assert r.value is None
        assert r.dq_reason == DQReason.DQ_TIME
