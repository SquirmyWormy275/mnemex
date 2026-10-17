# Missoula: sporting and operational rules to preserve

Governing source: [S12, DOMAIN_CONTRACT](SOURCE_INDEX.md#s12). It outranks
algorithm detail in [S13, FlightLogic](SOURCE_INDEX.md#s13), feature recon notes
and historical chats. [S14](SOURCE_INDEX.md#s14), [S15](SOURCE_INDEX.md#s15) and
[S16](SOURCE_INDEX.md#s16) preserve the owner's requirements and rationale.
Where old requirements conflict with a later explicit canonical correction,
use the correction. These are Missoula rules, not mandatory rules for every show.

## Program and registration

Missoula is a two-day competition: Friday college and Saturday professional,
with a separately configured Friday Night Feature and selected college spillover
on Saturday. College heats normally run in event batches; the pro show interleaves
events in flights to maintain variety and competitor rest. A show can select
events according to wood/resources without enabling both gendered variants of
every possible event.

College teams are organized by school, up to eight competitors and at least two
per gender under the owner requirements. A school can submit multiple teams.
Closed events count toward the six-event entry limit. The traditional open set
can be configured open or closed for that year's show; do not hard-code one
year's event choices into a universal event implementation. Individual points
combine into team totals, with Bull/Belle and overall-team reporting. The stated
place points are 10, 7, 5, 3, 2, 1; ties use the implemented split-place rules.

Pro registration is individual, with per-event fees, ALA membership assertion,
relay lottery interest, optional shirts and event-specific gear/partner details.
Pro events track purses rather than college-style show-wide individual points.
Keep show contact/payment/waiver information out of STRATHMARK's numerical inputs.

## Build order and transaction boundary

The canonical workflow is:

```text
import/enter -> configure events/Friday/spillover/flight sizing
-> fresh blocking preflight -> generate heats -> build pro flights
-> Pro-Am Relay final-flight placement -> college spillover integration
-> dependent saw-block/field preparation -> score/publish/settle
```

Full-show generation uses one transaction with fresh pre-generation input
validation under the schedule-writer lock and post-generation validation before
the final commit. A failure rolls back heats, flights, relay, spillover and
dependent stand state together. A background/one-click path must execute the
same chain, not declare success after only building flights.

Do not treat not-yet-generated flights or spillover as pre-generation input
failures. Resolve minutes-mode flight count against the newly generated heat
count. Count mode uses the operator's saved flight count. Algorithmic defaults
and heuristics are implementation detail beneath the canonical requirements.

## Partners and gear

A partnered entrant requires a real valid pair. Both must be active and entered
in the same applicable event with reciprocal references. Blank, ambiguous,
unresolved, self-referential or nonreciprocal declarations block generation.
Gender rules come from the event: Jack & Jill is mixed, Double Buck is the
configured same-gender pair, and college pair membership respects team rules.

Partner repair can normalize reciprocal typo matches and pair genuinely unclaimed
entrants. A named/inbound/ambiguous claim needs an operator decision. Repair must
not rewrite completed results and locks once results are completed/finalized.
Partnered Axe has its own prelim/final state machine and pair authority in
`Event.event_state`; standard heat generation cannot substitute for it. Its
preflight proves complete unique entrants, prelim scores and advanced finalists.
Completed prelims can be replaced by a first finals card; scored finals remain
protected.

Sharing equipment is different from competing as partners. Race axes, saws,
handles, springboards and climbing gear can impose different-heat constraints.
A college school may own one shared saw or several; school membership alone is
not proof that two entrants share the same physical equipment. Equipment-family
and event-specific declarations must be resolved through the existing services.
Stock Saw and show-provided Obstacle Pole saws do not acquire invented personal
gear constraints. See the detailed owner catalogue in S15.

Generation must place every eligible unit without a same-heat gear conflict.
Expand heat count as needed. If no valid layout exists, fail before replacing
the schedule. Never fall back to ignoring gear conflicts. Malformed declarations
for unrelated events remain a preflight concern rather than blocking a direct
generation operation for an independent event.

## Physical stands and runs

| Event/resource | Current rule |
| --- | --- |
| Stock Saw, college and pro | Physical saw stands **7 and 8**; solo heats alternate 7/8, paired heats use both |
| Hand saw events | Eight physical stands in reset groups 1–4 and 5–8; capacity four per active heat |
| Springboard | One configured left-handed dummy, conventionally stand 4; at most one LH cutter per heat; spread/expand heats before replacement |
| Standing Block / Cookie Stack | Shared physical location; enforce mutual exclusion/conflict spacing |
| College Obstacle Pole | Dual run, Pole 1 / Pole 2, best time |
| Pro Obstacle Pole | Single run |
| College Speed Climb | Dual course/stand handling, Pole 2 / Pole 4 |
| Chokerman | Dual courses; run 2 is mandatory Saturday spillover and the closing suffix |

Dual-run entrants change physical stand/course in run 2, including a one-person
heat. A second run eliminates course bias; the derived best time must reflect
the event's scoring order. College/pro differences are intentional. The optional
pro springboard slow-heat flag helps avoid repeating very long cuts across many
heats, without overriding physical handedness constraints.

Managed SB/UH fields use the actual configured host capacity and WoodConfig;
the example's 275 mm diameter is test data. The shared component receives the
actual field/stand restrictions. It cannot assume unlimited interchangeable stands.

## Flights, relay and spillover

Friday college heats are not pro flights except selected Saturday spillover.
Within every event, heat numbers stay ascending across the whole Saturday show.
Manual reorder APIs reject invalid order; an after-the-fact audit warning is not
enforcement. The flight builder uses event variety, competitor rest and stand
conflicts. Advisory quality tradeoffs remain distinct from forbidden layouts.

The Pro-Am Relay breaks down the college/pro divide. Randomly drawn teams have
exactly eight members: two each of pro men, pro women, college men and college
women. The sequence is partnered sawing, standing butcher block, underhand
butcher block, then team axe throw stopping on the balloon. The lottery costs
$5 whether selected or not; participation is not guaranteed. Relay results do
not count toward college individual/team points; the owner identifies it as the
college participants' prize-money exception. Current schedule placement is in
the final pro flight before college spillover, preserving the mandatory closer.

Chokerman run 2 closes the final Saturday flight, in ascending heat order.
Other selected college spillover uses the saved round-robin/cluster planner and
global spacing/shared-stand checks. Later pending integrations insert before an
existing Chokerman closing block. A guideline priority for extra spillover is
men's Standing Block Speed, men's Hard Hit, women's Speed, women's Hard Hit,
then men's Obstacle Pole; it is an operator guideline, not automatic policy.

Once any flight starts, flight/roster editing, event setup, Friday selection,
Saturday priority, dependent saw-block reassignment and legacy gear heat sync
freeze at the published-running-order boundary. Completed heats/placements/stands
are history. Dedicated scratch/correction workflows retain explicit authority.
Cross-process production schedule serialization relies on PostgreSQL's tournament
parent lock; SQLite's in-process guard is not a multi-process production claim.

## Scoring, marks and reports

Every heat entrant needs a result or explicit non-finish before completion.
Missing current-run values do not become complete because an earlier run exists.
DNF/DQ/scratch needs no invented number. A one-timer partial result follows the
review path and prevents automatic finalization. A valid zero throw/score differs
from an absent value. Clearing all runs clears derived best/total values.

T1/T2 measure raw cutting duration from the competitor's own legal start. Raw
duration remains raw in storage, reports and exports. Handicap completion is
**start mark + raw duration**. The owner reaffirmed this on October 13; old
subtraction was an implementation error. There was no historical backfill or
automatic re-finalization. Recorded final positions stay authoritative until an
explicit correction.

Retained official handicap scoring requires a deliberately reviewed mark for
every active entrant. A reviewed zero is a valid intentional scratch mark; the
database default `0.0` is not review. Managed Mark-3 is a different policy with
legal marks 3–180. Never use the managed minimum to rewrite retained events.

Reports show recorded final positions before unplaced rows and preserve ties.
College individual points rebuild affected team totals. Pro shared-position ties
receive the configured purse for that shared position under the existing policy.
An accepted delegated correction needs a fresh explicit award decision; automatic
payout settlement is not source result acceptance.

## Authority modes and offline receipts

Retained official host events, scoring-inert shadow events and newly delegated
events are separate. Shadow recommendations cannot be imported into official
mark fields through normal review/issue controls. The shadow settlement outbox
is numerical feedback, not MNEMEX career publication.

Delegated events prevent competing legacy mark/scoring/advancement writes.
Global scratches and college/team deletion cannot remove retained managed entries.
Registration gear sync skips managed fields while preserving independent host
repair. Pending scheduled unissued field replacement requires explicit
digest-bound unscheduling; issued or started history cannot be released this way.

Accepted score requests have durable request-ID receipts. Undo supersedes rather
than deletes them. A field identity binds roster, stands and placement, not an
optimistic version incremented by taking an edit lock. Scoring-state digests
still reject stale writes. Ordinary forms keep CSRF; the existing prepared offline
replay route has its separate authenticated user-bound HMAC contract.

## Known source conflicts

Old owner/algorithm text mentions Stock Saw stands 1–2; use the later 7–8 rule.
FlightLogic contains old same-heat LH overflow and gear-ignore fallback text;
the canonical contract requires valid complete placement or refusal. Its old
preflight ordering does not override the atomic canonical workflow. Archive
these sources for rationale, but use [the conflict register](08_HISTORY.md) and
current cited tests before changing the show.
