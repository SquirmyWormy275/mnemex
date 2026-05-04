"""Tests for mnemex.identity.

Covers the CanonicalAthlete dataclass shape (federation_ids map, privacy
fields, redaction state). Function-level tests for match / merge / split /
redact land at Milestone 1 alongside the implementations.
"""

from __future__ import annotations

import pytest

from mnemex.identity import CanonicalAthlete, Match, NeedsReview


class TestCanonicalAthleteShape:
    """The dataclass replaces the previous single `stihl_athlete_id` field
    with a federation_ids map and adds birth_year / hometown for
    disambiguation."""

    def test_minimal_construction(self) -> None:
        athlete = CanonicalAthlete(
            canonical_id="canonical/erin-lavoie-1985",
            primary_name="Erin LaVoie",
        )
        assert athlete.canonical_id == "canonical/erin-lavoie-1985"
        assert athlete.primary_name == "Erin LaVoie"
        assert athlete.aliases == []
        assert athlete.federation_ids == {}
        assert athlete.school_team_history == []
        assert athlete.eligibility == []
        assert athlete.birth_year is None
        assert athlete.hometown is None
        assert athlete.notes is None
        assert athlete.redacted is False
        assert athlete.redacted_at is None
        assert athlete.redacted_reason is None
        assert athlete.merged_into is None

    def test_federation_ids_is_a_dict(self) -> None:
        # Default empty; populated incrementally as federation roster
        # uploads / scrapes link to this canonical_id.
        athlete = CanonicalAthlete(
            canonical_id="canonical/cody-labahn-1985",
            primary_name="Cody Labahn",
        )
        assert isinstance(athlete.federation_ids, dict)
        assert athlete.federation_ids == {}

    def test_no_stihl_athlete_id_field(self) -> None:
        # The single stihl_athlete_id field was removed in the additive-
        # schema PR. STIHL is now just one entry in federation_ids.
        athlete = CanonicalAthlete(
            canonical_id="canonical/x",
            primary_name="X",
        )
        # hasattr returns True for descriptors but False for dataclass
        # fields that don't exist; works for the regression check.
        assert not hasattr(athlete, "stihl_athlete_id")

    def test_federation_ids_accepts_documented_slugs(self) -> None:
        # Slugs documented in the dataclass docstring: stihl, awfc, ala,
        # aaa, canlog, lwc. Any consistent short slug is acceptable until
        # the federations module formalizes the taxonomy.
        athlete = CanonicalAthlete(
            canonical_id="canonical/multi-fed-athlete",
            primary_name="Multi Fed",
            federation_ids={
                "stihl": "12345",
                "awfc": "OSU-2022-018",
                "ala": "ala_member_5587",
                "aaa": "aaa_2024_chopper_44",
                "canlog": "canlog_id_99",
                "lwc": "LWC-ROSTER-2024-77",
            },
        )
        assert athlete.federation_ids["stihl"] == "12345"
        assert athlete.federation_ids["awfc"] == "OSU-2022-018"
        assert athlete.federation_ids["ala"] == "ala_member_5587"
        assert athlete.federation_ids["aaa"] == "aaa_2024_chopper_44"
        assert athlete.federation_ids["canlog"] == "canlog_id_99"
        assert athlete.federation_ids["lwc"] == "LWC-ROSTER-2024-77"
        assert len(athlete.federation_ids) == 6

    def test_federation_ids_independent_per_instance(self) -> None:
        # The default_factory=dict prevents the classic mutable-default bug
        # where two athletes share the same federation_ids dict.
        a = CanonicalAthlete(canonical_id="a", primary_name="A")
        b = CanonicalAthlete(canonical_id="b", primary_name="B")
        a.federation_ids["stihl"] = "111"
        assert (
            b.federation_ids == {}
        ), "federation_ids on different athletes must not share state"


class TestCanonicalAthletePrivacyFields:
    """birth_year and hometown have explicit privacy constraints that the
    docstring documents and the tests exercise."""

    def test_birth_year_is_year_only(self) -> None:
        athlete = CanonicalAthlete(
            canonical_id="canonical/x",
            primary_name="X",
            birth_year=1995,
        )
        # Year is a plain int, not a date or datetime; storing month/day
        # is not supported by the schema.
        assert isinstance(athlete.birth_year, int)
        assert athlete.birth_year == 1995

    def test_birth_year_default_none(self) -> None:
        # Optional. Only set when needed for disambiguation.
        athlete = CanonicalAthlete(canonical_id="canonical/x", primary_name="X")
        assert athlete.birth_year is None

    def test_hometown_default_none(self) -> None:
        athlete = CanonicalAthlete(canonical_id="canonical/x", primary_name="X")
        assert athlete.hometown is None

    def test_hometown_accepts_city_state(self) -> None:
        athlete = CanonicalAthlete(
            canonical_id="canonical/x",
            primary_name="X",
            hometown="Missoula, MT",
        )
        assert athlete.hometown == "Missoula, MT"

    def test_hometown_accepts_international_city_region(self) -> None:
        athlete = CanonicalAthlete(
            canonical_id="canonical/y",
            primary_name="Y",
            hometown="Sydney, NSW",
        )
        assert athlete.hometown == "Sydney, NSW"

    def test_disambiguation_pair(self) -> None:
        # Two real people sharing a name distinguished by birth_year + hometown.
        a = CanonicalAthlete(
            canonical_id="canonical/john-smith-1980-mt",
            primary_name="John Smith",
            birth_year=1980,
            hometown="Missoula, MT",
        )
        b = CanonicalAthlete(
            canonical_id="canonical/john-smith-1995-or",
            primary_name="John Smith",
            birth_year=1995,
            hometown="Eugene, OR",
        )
        # Same display name; distinct canonical_ids and tiebreakers.
        assert a.primary_name == b.primary_name
        assert a.canonical_id != b.canonical_id
        assert a.birth_year != b.birth_year
        assert a.hometown != b.hometown


class TestRedactionState:
    """Redaction fields are dormant until the redact() function lands at M1.
    This test covers the dataclass shape only."""

    def test_redacted_flag_default_false(self) -> None:
        athlete = CanonicalAthlete(canonical_id="x", primary_name="X")
        assert athlete.redacted is False

    def test_redaction_metadata_can_be_set(self) -> None:
        athlete = CanonicalAthlete(
            canonical_id="x",
            primary_name="X",
            redacted=True,
            redacted_at="2026-05-04T20:00:00Z",
            redacted_reason="athlete request",
        )
        assert athlete.redacted is True
        assert athlete.redacted_at == "2026-05-04T20:00:00Z"
        assert athlete.redacted_reason == "athlete request"


class TestMatchAndNeedsReview:
    """Sanity checks on the match-result dataclasses (Match / NeedsReview).
    Behaviour-level tests for match() / commit_link() / merge() / split() /
    redact() land at Milestone 1."""

    def test_match_construction(self) -> None:
        athlete = CanonicalAthlete(canonical_id="canonical/x", primary_name="X")
        m = Match(
            canonical_id="canonical/x",
            confidence=0.97,
            candidate_athlete=athlete,
        )
        assert m.canonical_id == "canonical/x"
        assert m.confidence == 0.97
        assert m.candidate_athlete is athlete

    def test_needs_review_with_empty_candidates(self) -> None:
        nr = NeedsReview(candidates=[], reason="first_name_only")
        assert nr.candidates == []
        assert nr.reason == "first_name_only"

    def test_needs_review_with_top_three_candidates(self) -> None:
        candidates = [
            CanonicalAthlete(canonical_id=f"canonical/{i}", primary_name=f"Athlete {i}")
            for i in range(3)
        ]
        nr = NeedsReview(candidates=candidates, reason="below_threshold")
        assert len(nr.candidates) == 3
        assert nr.reason == "below_threshold"


class TestMatchFunctionPlaceholder:
    """The match() / merge() / split() / redact() / commit_link() functions
    raise NotImplementedError at M0; behavioural tests land at M1."""

    def test_match_raises_not_implemented(self) -> None:
        from mnemex.identity import match

        with pytest.raises(NotImplementedError):
            match("Erin LaVoie", {})

    def test_merge_raises_not_implemented(self) -> None:
        from mnemex.identity import merge

        with pytest.raises(NotImplementedError):
            merge("a", "b", "operator")
