"""Athlete identity service.

Cross-source dedup is the load-bearing engineering problem of MNEMEX.
This module owns the matching algorithm, the canonical-athlete store,
and the audit log of every link / merge / split.

Public API:
  match(name, context) -> Match | NeedsReview
  commit_link(canonical_id, name_as_recorded, source) -> None
  merge(keep_id, absorb_id, operator) -> None
  split(canonical_id, row_assignments, operator) -> tuple[str, str]
  redact(canonical_id, reason, operator) -> None

Storage:
  data/identity_canonical.jsonl  -- CanonicalAthlete records (append-only)
  data/identity_audit.jsonl      -- match / link / merge / split / redact events

Matching rules (per the design doc's Identity dedup service section):
  1. STIHL athlete URLs are gold -- same URL = same canonical_id
  2. Exact name match + last-name present -> Match(confidence=1.0); enters review
  3. Fuzzy match >= 95% + last-name present -> Match(confidence=score); enters review
  4. First-name-only or initials-only -> NeedsReview (NEVER auto-link)
  5. Below 95% fuzzy or ambiguous -> NeedsReview with top-3 candidates

NO identity link bypasses review, even at confidence 1.0. The threshold
determines whether the row enters review pre-populated (one-click confirm)
or unpopulated (manual lookup) -- never whether it skips review.

Implementation lands in Milestone 1. This module is a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class CanonicalAthlete:
    """A canonical athlete identity. Aliases accumulate as new spelling
    variants are confirmed by reviewers.

    Federation IDs (`federation_ids`):
        Map of federation slug -> the federation's own athlete identifier
        for this person. The same person commonly has IDs in multiple
        federations as their career progresses (collegiate to professional,
        regional to national, country to country). Examples:

            {"stihl": "12345",
             "awfc": "OSU-2022-018",
             "ala": "ala_member_5587",
             "aaa": "aaa_2024_chopper_44"}

        Federation slugs are short lowercase strings keyed by federation
        identifier. The slug taxonomy will be formalized when the federations
        module lands; for now any consistent short slug is acceptable.
        Common slugs in current use: "stihl" (STIHL Pro Series), "awfc"
        (AWFC collegiate conclaves), "ala" (American Lumberjack Association),
        "aaa" (Australian Axemen's Association), "canlog" (Canadian Logging
        Association), "lwc" (Lumberjack World Championship roster).

    Disambiguation tiebreakers (`birth_year`, `hometown`):
        Optional, populated only when needed to disambiguate between two
        real people sharing a name.

        - `birth_year` is the year only (e.g., 1995). Storing full
          date-of-birth (1995-03-12) is NOT permitted. Year alone is enough
          to disambiguate without storing full PII.
        - `hometown` is city/state ("Missoula, MT" or "Sydney, NSW").
          Street addresses are NOT permitted.

        Both fields are removable on athlete request via the future
        `mnemex identity redact` CLI. The redaction primitive in this
        module supports clearing these fields without tombstoning the
        whole canonical record.
    """

    canonical_id: str  # MNEMEX-issued, stable across renames
    primary_name: str  # canonical display name (Title Case)
    aliases: list[str] = field(default_factory=list)
    # Federation-specific identifiers, keyed by federation slug. See class
    # docstring for slug examples. Replaces the previous single
    # `stihl_athlete_id` field; STIHL is now just one entry in the map.
    federation_ids: dict[str, str] = field(default_factory=dict)
    school_team_history: list[tuple[int, str]] = field(
        default_factory=list
    )  # [(year, team)]
    eligibility: list[tuple[int, str]] = field(
        default_factory=list
    )  # [(year, "college"|"pro"|"both")]
    # Disambiguation tiebreakers. See class docstring for privacy constraints.
    birth_year: Optional[int] = None  # year only, never full DOB
    hometown: Optional[str] = None  # city/state, no street address
    notes: Optional[str] = None
    redacted: bool = False
    redacted_at: Optional[str] = None
    redacted_reason: Optional[str] = None
    merged_into: Optional[str] = None  # if this id was absorbed via merge


@dataclass
class Match:
    """A confidence-scored match proposal. The reviewer confirms before commit."""

    canonical_id: str
    confidence: float  # 0.0 .. 1.0
    candidate_athlete: CanonicalAthlete


@dataclass
class NeedsReview:
    """No confident match. The reviewer either picks a candidate or
    creates a new canonical_id."""

    candidates: list[CanonicalAthlete]  # top-3 closest matches, may be empty
    reason: str  # "first_name_only", "below_threshold", etc.


def match(name_as_recorded: str, context: dict) -> Union[Match, NeedsReview]:
    """Propose a canonical_id for a name encountered during ingest.

    `context` carries hints the matcher uses to disambiguate (gender of
    event, partner names in pair events, division, source_circuit).

    Implementation in Milestone 1.
    """
    raise NotImplementedError("match() lands in Milestone 1")


def commit_link(
    canonical_id: str, name_as_recorded: str, source: str, operator: str
) -> None:
    """Record that name_as_recorded resolves to canonical_id. Adds the
    name to the canonical athlete's aliases if it isn't already known.

    Implementation in Milestone 1.
    """
    raise NotImplementedError("commit_link() lands in Milestone 1")


def merge(keep_id: str, absorb_id: str, operator: str) -> None:
    """Discover Athlete A and B are the same person; merge into A.

    All canonical rows referencing absorb_id are rewritten to keep_id.
    absorb_id is tombstoned (kept in identity store with merged_into=keep_id,
    never reused).

    Generates a corrections/merge-YYYY-MM-DD.jsonl for STRATHMARK propagation.
    Implementation in Milestone 1.
    """
    raise NotImplementedError("merge() lands in Milestone 1")


def split(
    canonical_id: str, row_assignments: dict[str, str], operator: str
) -> tuple[str, str]:
    """Reverse a wrong merge. Returns (retained_id, new_id).

    `row_assignments` maps each affected row's source_native_id to either
    "retain" (stay with canonical_id) or "split" (move to new_id).

    Generates a corrections/split-YYYY-MM-DD.jsonl for STRATHMARK propagation.
    Implementation in Milestone 1.
    """
    raise NotImplementedError("split() lands in Milestone 1")


def redact(canonical_id: str, reason: str, operator: str) -> None:
    """Tombstone an athlete's canonical record (privacy / right-to-erasure).

    Drops primary_name, aliases, notes. Preserves a salted SHA-256 hash
    of the original primary name for audit reconstruction. All canonical
    rows referencing the canonical_id keep the row but replace
    competitor.name_as_recorded with "[redacted]". Numeric/event data stays.

    Generates a corrections/redact-YYYY-MM-DD.jsonl for STRATHMARK propagation.
    Implementation in Milestone 1.
    """
    raise NotImplementedError("redact() lands in Milestone 1")
