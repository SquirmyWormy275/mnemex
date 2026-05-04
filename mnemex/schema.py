"""MNEMEX canonical schema.

The schema is the contract between ingest sources, the canonical store,
the export hub, and the STRATHMARK adapter. Every CanonicalRow that
reaches data/canonical.jsonl conforms to the structure here.

See docs/MNEMEX-design-2026-05-04.md for the full design rationale.

Schema invariants (asserted in tests/test_schema.py and at row construction):

  1. If `runs` is non-empty:
        `final_score` MUST equal apply_policy(runs, final_score_policy)
        where apply_policy is defined per FinalScorePolicy:
          SINGLE_RUN       -> runs[0].value
          BEST_OF_RUNS     -> min(values) for ScoreType.TIME / HITS;
                              max(values) for DISTANCE / RAW_SCORE
          AVERAGE_OF_RUNS  -> arithmetic mean of completed (non-DQ) runs
          SUM_OF_RUNS      -> sum of completed runs
  2. If `runs` is empty:
        `final_score` is the source-published number;
        `final_score_policy` MUST equal SINGLE_RUN.
  3. For ScoreType.RAW_SCORE (knowledge events):
        `final_score` is the raw integer count cast to float
        (e.g., "17 of 20" -> 17.0). Maximum-possible value goes in
        `extraction_notes` (e.g., "max=20").
  4. For ScoreType.PLACE_ONLY:
        `final_score` = `place` cast to float (1st -> 1.0). `runs` is empty.
        PLACE_ONLY rows are filtered out of any analytics path that
        assumes "lower score = better."
  5. For row-level DQ (`dq_reason` set, no completed run):
        `final_score=None`. STRATHMARK Tier 1 projection skips the row.

Tier classification (which disciplines export to STRATHMARK):

  TIER1_DISCIPLINES -- export cleanly against STRATHMARK 0.4.1 today.
                       Time-scored speed events.
  TIER2_DISCIPLINES -- need STRATHMARK to grow a `score_type` field
                       (HHH/VHH are hits-based). v1 implements but
                       feature-flag-disables.
  TIER3_DISCIPLINES -- captured in MNEMEX archive only, NEVER exported
                       to STRATHMARK. STRATHMARK is a handicap engine;
                       distance / knowledge / place-only events don't
                       belong there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from enum import Enum
from typing import Optional


class ScoreType(str, Enum):
    """How a result is scored. Inverse-ordering: lower-is-better for
    TIME / HITS; higher-is-better for DISTANCE / RAW_SCORE; PLACE_ONLY
    is always lower-is-better but doesn't flow into STRATHMARK."""

    TIME = "time"  # seconds; lower is better
    HITS = "hits"  # integer count; lower is better
    DISTANCE = "distance"  # meters / feet; higher is better (caber, axe-throw distance)
    RAW_SCORE = "raw_score"  # written-test points; higher is better
    PLACE_ONLY = (
        "place_only"  # finishing position published, no time (axe throw, log roll)
    )


class Division(str, Enum):
    """Division taxonomy observed across STIHL pro, college (AWFC),
    and ALA / CANLOG association shows. Mixes skill-level and gender;
    the schema also has a separate `gender` field which is used when
    Division alone is ambiguous."""

    OPEN = "open"
    MASTERS_INTERMEDIATE = "M/I"  # ALA / college Masters/Intermediate
    NOVICE_INTERMEDIATE = "N/I"  # ALA Novice/Intermediate
    WOMEN = "women"
    MEN = "men"
    MIXED = "mixed"
    JUNIOR = "junior"
    PRO = "pro"
    ROOKIE = "rookie"


class DQReason(str, Enum):
    """Controlled vocabulary for DQ / scratch / DNF outcomes. Per-source
    free-text strings ("dq-time", "DQ time", "DQ-T") normalize to these
    via mnemex/ingest/dq_aliases.py (added at M1)."""

    DQ_TIME = "dq_time"  # exceeded time limit
    DQ_DISC = "dq_disc"  # missed discriminator (e.g., specific saw cut)
    DQ_CUT_OUT = "dq_cut_out"  # saw event ended improperly
    DQ_FELL = "dq_fell"  # fell off platform
    DQ_FOOTHOLD = "dq_foothold"  # foothold violation
    DQ_SCOOPS = "dq_scoops"  # axe scooping violation
    SCRATCH = "scratch"  # withdrew before competing
    DNF = "dnf"  # did not finish


class ExtractionStatus(str, Enum):
    """Status field on rows in the pending queue. Distinct from DQReason
    (a row-level competitive outcome) and the review-queue state machine
    (pending -> verified -> committed). Once a row is committed,
    extraction_status is no longer relevant.

    See Operational Concerns / Vision-LLM error handling in the design doc."""

    OK = "ok"  # extraction succeeded; row fully populated
    FAILED_TRANSIENT = "failed_transient"  # network/HTTP error after retry budget
    FAILED_TIMEOUT = "failed_timeout"  # per-call timeout exceeded
    FAILED_PARSE = "failed_parse"  # model returned invalid / non-schema JSON
    PARTIAL = "partial"  # JSON valid but row count below source count
    PENDING_STALE = (
        "pending_stale"  # > 14 days in pending; surfaced via review --failures
    )
    PENDING_BUDGET = (
        "pending_budget"  # deferred to next budget window (cost ceiling hit)
    )
    NEEDS_INPUT = "needs_input"  # human-resolvable identity gap
    # (first-name-only entry with no contextual hint)


class Discipline(str, Enum):
    """Each enum value corresponds to exactly one real-world event. No overloading.

    Standing Block Chop and Single Buck are distinct events with distinct keys
    even though both are colloquially called "SB" by their respective circuits.
    Collapsing them would corrupt downstream handicap math.
    """

    UNDERHAND = "UNDERHAND"  # Underhand Chop (axe, horizontal block)
    STANDING_BLOCK = "STANDING_BLOCK"  # Standing Block Chop (axe, vertical block)
    SINGLE_BUCK = "SINGLE_BUCK"  # one person, crosscut saw
    DOUBLE_BUCK = "DOUBLE_BUCK"  # pair, crosscut saw
    JACK_AND_JILL = "JACK_AND_JILL"  # mixed-gender pair, crosscut saw
    HORIZONTAL_HARDHIT = "HORIZONTAL_HARDHIT"  # HHH -- hits to break horizontal block
    HORIZONTAL_SPEED = "HORIZONTAL_SPEED"  # HS / HSC -- time on horizontal block
    VERTICAL_HARDHIT = "VERTICAL_HARDHIT"  # VH / VHH -- hits to break vertical block
    VERTICAL_SPEED = "VERTICAL_SPEED"  # VS / VSC -- time on vertical block
    OBSTACLE_POLE = "OBSTACLE_POLE"  # OP
    POLE_CLIMB = "POLE_CLIMB"
    CHOKER_RACE = "CHOKER_RACE"
    POWER_SAW = "POWER_SAW"
    HOT_SAW = "HOT_SAW"
    STOCK_SAW = "STOCK_SAW"
    SPRINGBOARD_1BD = "SPRINGBOARD_1BD"  # one-board springboard
    SPRINGBOARD_2BD = "SPRINGBOARD_2BD"  # two-board springboard
    AXE_THROW = "AXE_THROW"
    SPEED_AXE_THROW = "SPEED_AXE_THROW"
    CABER_THROW = "CABER_THROW"
    BIRLING = "BIRLING"  # logrolling
    PULP_TOSS = "PULP_TOSS"  # pair
    DENDROLOGY = "DENDROLOGY"  # knowledge -- tree ID
    TIMBER_CRUISE = "TIMBER_CRUISE"  # knowledge -- forestry estimation
    TRAVERSE = "TRAVERSE"
    STEEPLE_CHASE = "STEEPLE_CHASE"
    WRAPPER_THROW = "WRAPPER_THROW"
    TEAM_RELAY = "TEAM_RELAY"


class FinalScorePolicy(str, Enum):
    """How `final_score` is derived from `runs`. See Schema invariant 1."""

    SINGLE_RUN = "single_run"  # one run, value is final
    BEST_OF_RUNS = (
        "best_of_runs"  # min(values) for TIME/HITS; max() for DISTANCE/RAW_SCORE
    )
    AVERAGE_OF_RUNS = "average_of_runs"  # arithmetic mean of completed runs
    SUM_OF_RUNS = "sum_of_runs"  # rare; documented for forward-compat


class EventCircuit(str, Enum):
    """The circuit / federation an event belongs to. UNKNOWN is a forced
    fallback the review queue MUST resolve before commit."""

    STIHL_PRO = "stihl_pro"
    AWFC_COLLEGE = "awfc_college"
    ALA_SHOW = "ala_show"
    CANLOG_SHOW = "canlog_show"
    LWC = "lwc"  # Lumberjack World Championship (Hayward, WI)
    REGIONAL = "regional"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Tier classification: which disciplines export to STRATHMARK.
# ---------------------------------------------------------------------------

TIER1_DISCIPLINES: frozenset[Discipline] = frozenset(
    {
        # Time-scored speed events that STRATHMARK 0.4.1 handles cleanly.
        # All have ScoreType.TIME and (optionally) wood metadata.
        Discipline.UNDERHAND,
        Discipline.STANDING_BLOCK,
        Discipline.SINGLE_BUCK,
        Discipline.DOUBLE_BUCK,
        Discipline.JACK_AND_JILL,
        Discipline.OBSTACLE_POLE,
        Discipline.POWER_SAW,
        Discipline.HOT_SAW,
        Discipline.STOCK_SAW,
        Discipline.SPRINGBOARD_1BD,
        Discipline.SPRINGBOARD_2BD,
        Discipline.HORIZONTAL_SPEED,
        Discipline.VERTICAL_SPEED,
    }
)

TIER2_DISCIPLINES: frozenset[Discipline] = frozenset(
    {
        # Hits-based axe events. Need STRATHMARK >= 0.5 with a `score_type` field
        # so the prediction cascade can treat hits and time as different scales.
        # v1 implements the projection behind a feature flag.
        Discipline.HORIZONTAL_HARDHIT,
        Discipline.VERTICAL_HARDHIT,
    }
)

TIER3_DISCIPLINES: frozenset[Discipline] = frozenset(
    {
        # Captured in MNEMEX archive only. NEVER exported to STRATHMARK.
        # STRATHMARK is a handicap engine; distance / knowledge / place-only
        # events don't model in handicap math.
        Discipline.AXE_THROW,
        Discipline.SPEED_AXE_THROW,
        Discipline.CABER_THROW,
        Discipline.BIRLING,
        Discipline.PULP_TOSS,
        Discipline.DENDROLOGY,
        Discipline.TIMBER_CRUISE,
        Discipline.TRAVERSE,
        Discipline.STEEPLE_CHASE,
        Discipline.WRAPPER_THROW,
        Discipline.TEAM_RELAY,
        Discipline.POLE_CLIMB,  # uses pole equipment STRATHMARK has no model for
        Discipline.CHOKER_RACE,  # multi-run + obstacle structure outside handicap math
    }
)

# Sanity invariant -- asserted in tests/test_schema.py:
#   set(Discipline) == TIER1_DISCIPLINES | TIER2_DISCIPLINES | TIER3_DISCIPLINES
#   and the three sets are pairwise disjoint.


# Mapping from MNEMEX Discipline -> string token STRATHMARK expects in
# HistoricalResult.discipline. Each mapping is unique; no overloading.
# STRATHMARK 0.4.1's existing data uses tokens "SB" and "UH" only -- the
# expanded tokens below land via a coordinated STRATHMARK 0.4.2 release
# (see Reviewer Concern: STRATHMARK token-vocabulary expansion).
STRATHMARK_DISCIPLINE_MAP: dict[Discipline, str] = {
    Discipline.UNDERHAND: "UH",
    Discipline.STANDING_BLOCK: "STB",  # NOT "SB" -- avoid collision with Single Buck
    Discipline.SINGLE_BUCK: "SBUCK",
    Discipline.DOUBLE_BUCK: "DBUCK",
    Discipline.JACK_AND_JILL: "JJ",
    Discipline.OBSTACLE_POLE: "OP",
    Discipline.POWER_SAW: "PSAW",
    Discipline.HOT_SAW: "HSAW",
    Discipline.STOCK_SAW: "SSAW",
    Discipline.SPRINGBOARD_1BD: "SPR1",
    Discipline.SPRINGBOARD_2BD: "SPR2",
    Discipline.HORIZONTAL_SPEED: "HS",
    Discipline.VERTICAL_SPEED: "VS",
}


# Per-discipline default FinalScorePolicy. Ingest parsers use this when
# the source does not specify policy explicitly. Override at the row level
# when the source DOES specify (e.g., college sheets often show
# "Time 1, Time 2, Ave" -- that's AVERAGE_OF_RUNS).
DEFAULT_SCORE_POLICY: dict[Discipline, FinalScorePolicy] = {
    Discipline.UNDERHAND: FinalScorePolicy.SINGLE_RUN,
    Discipline.STANDING_BLOCK: FinalScorePolicy.SINGLE_RUN,
    Discipline.SINGLE_BUCK: FinalScorePolicy.SINGLE_RUN,
    Discipline.DOUBLE_BUCK: FinalScorePolicy.SINGLE_RUN,
    Discipline.JACK_AND_JILL: FinalScorePolicy.SINGLE_RUN,
    Discipline.OBSTACLE_POLE: FinalScorePolicy.AVERAGE_OF_RUNS,  # 1st run + 2nd run
    Discipline.POLE_CLIMB: FinalScorePolicy.BEST_OF_RUNS,  # 1st climb + 2nd climb
    Discipline.CHOKER_RACE: FinalScorePolicy.BEST_OF_RUNS,  # 1st run + 2nd run
    Discipline.HORIZONTAL_SPEED: FinalScorePolicy.AVERAGE_OF_RUNS,  # Time 1, Time 2, Ave
    Discipline.VERTICAL_SPEED: FinalScorePolicy.AVERAGE_OF_RUNS,
    Discipline.HORIZONTAL_HARDHIT: FinalScorePolicy.AVERAGE_OF_RUNS,  # Hits 1, Hits 2, Ave
    Discipline.VERTICAL_HARDHIT: FinalScorePolicy.AVERAGE_OF_RUNS,
    Discipline.AXE_THROW: FinalScorePolicy.SINGLE_RUN,  # PLACE_ONLY in ALA
    Discipline.SPEED_AXE_THROW: FinalScorePolicy.SINGLE_RUN,
    Discipline.BIRLING: FinalScorePolicy.SINGLE_RUN,
    Discipline.CABER_THROW: FinalScorePolicy.BEST_OF_RUNS,
    Discipline.PULP_TOSS: FinalScorePolicy.SINGLE_RUN,
    Discipline.DENDROLOGY: FinalScorePolicy.SINGLE_RUN,
    Discipline.TIMBER_CRUISE: FinalScorePolicy.SINGLE_RUN,
    Discipline.TRAVERSE: FinalScorePolicy.SINGLE_RUN,
    Discipline.STEEPLE_CHASE: FinalScorePolicy.SINGLE_RUN,
    Discipline.WRAPPER_THROW: FinalScorePolicy.SINGLE_RUN,
    Discipline.TEAM_RELAY: FinalScorePolicy.SINGLE_RUN,
    Discipline.POWER_SAW: FinalScorePolicy.SINGLE_RUN,
    Discipline.HOT_SAW: FinalScorePolicy.SINGLE_RUN,
    Discipline.STOCK_SAW: FinalScorePolicy.SINGLE_RUN,
    Discipline.SPRINGBOARD_1BD: FinalScorePolicy.SINGLE_RUN,
    Discipline.SPRINGBOARD_2BD: FinalScorePolicy.SINGLE_RUN,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompetitorRef:
    """A reference to a canonical athlete on a row.

    `canonical_id` is the MNEMEX-issued stable ID. `name_as_recorded`
    preserves the source's exact spelling for audit, even after identity
    matching collapses spelling variants.
    """

    canonical_id: str
    name_as_recorded: str
    school_team: Optional[str] = None  # e.g., "UM-A" -- nullable for pro events
    division: Optional[str] = None  # "Open", "Master", "Junior", etc.


@dataclass(frozen=True)
class RunResult:
    """One run of a multi-run event. `value` and `dq_reason` are
    mutually exclusive -- a completed run has a value; a DQed run has
    a reason and value=None."""

    run_index: int
    value: Optional[float]
    dq_reason: Optional[DQReason] = None


@dataclass
class CanonicalRow:
    """A single competitor's result in a single discipline at a single event.

    Pair events (DOUBLE_BUCK, JACK_AND_JILL) emit ONE row with TWO
    competitors in the `competitors` list. Team relays similarly.

    `source` format is ALWAYS `<source_type>:<instance_id>`:
      "stihl:event/12345"            (STIHL event URL fragment)
      "awfc_excel:um-pro-am-2026"    (AWFC Excel host slug)
      "ala_pdf:2025-09"              (ALA newsletter month)
      "image:<sha256-of-image-bytes>:v<prompt_version>"
      "manual:<user_id>"
      "federation_publish:<slug>:<batch_id>"
    """

    # provenance
    source: str
    source_native_id: Optional[str] = None
    ingested_at: str = ""  # ISO 8601 UTC
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None

    # event
    event_name: str = ""
    event_date: Optional[Date] = None
    event_circuit: EventCircuit = EventCircuit.UNKNOWN
    event_url: Optional[str] = None

    # discipline
    discipline: Discipline = Discipline.UNDERHAND
    score_type: ScoreType = ScoreType.TIME
    division: Optional[Division] = None
    gender: Optional[str] = None  # "M" | "F" | "MIXED" | None

    # competitors (pairs and teams supported natively)
    competitors: list[CompetitorRef] = field(default_factory=list)

    # results
    runs: list[RunResult] = field(default_factory=list)
    final_score: Optional[float] = None
    final_score_policy: FinalScorePolicy = FinalScorePolicy.SINGLE_RUN
    dq_reason: Optional[DQReason] = None
    place: Optional[int] = None
    points: Optional[int] = None  # college-style place-points

    # wood (only when published; NULL otherwise)
    wood_species: Optional[str] = None
    wood_diameter_mm: Optional[int] = None
    wood_quality: Optional[int] = None  # 1..10; STRATHMARK convention
    wood_quality_imputed: bool = False
    wood_metadata_source: str = ""  # "published" | "not_published" | "imputed_default"

    # special markers (WR, NR, PB, SB-meaning-Season-Best)
    special_markers: list[str] = field(default_factory=list)

    # extraction metadata (image / Excel / PDF ingest only)
    extraction_confidence: Optional[float] = None
    extraction_notes: Optional[str] = None
    extraction_status: ExtractionStatus = ExtractionStatus.OK
    identity_resolution_required: bool = False
