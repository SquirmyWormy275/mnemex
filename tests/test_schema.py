"""Schema invariants and tier-classification correctness tests.

These are the only tests that should pass at end-of-Milestone-0.
Everything else (identity, store, ingest, export, contract) lands at M1+.
"""

from __future__ import annotations

import pytest

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


class TestStrathmarkDisciplineMap:
    """Each Tier 1 / Tier 2 discipline maps to a UNIQUE STRATHMARK token.

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
        # Standing Block != Single Buck. The two events have different
        # kinematics; collapsing them into a single "SB" token corrupts
        # downstream handicap math.
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


class TestCanonicalRow:
    """Construction, defaults, and basic invariants."""

    def test_minimal_row_constructs(self) -> None:
        row = CanonicalRow(source="stihl:event/12345")
        assert row.source == "stihl:event/12345"
        assert row.discipline == Discipline.UNDERHAND
        assert row.score_type == ScoreType.TIME
        assert row.event_circuit == EventCircuit.UNKNOWN
        assert row.final_score_policy == FinalScorePolicy.SINGLE_RUN
        assert row.extraction_status == ExtractionStatus.OK
        assert row.identity_resolution_required is False
        assert row.competitors == []
        assert row.runs == []

    def test_row_with_competitor(self) -> None:
        row = CanonicalRow(
            source="stihl:event/12345",
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
            source="ala_pdf:2025-09",
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
            source="ala_pdf:2025-09",
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

    def test_discipline_values_are_uppercase(self) -> None:
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
