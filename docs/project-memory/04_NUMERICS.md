# Numerical meaning, versioned profiles and evaluation

Sources: [S03](SOURCE_INDEX.md#s03), [S02](SOURCE_INDEX.md#s02),
[S04](SOURCE_INDEX.md#s04), [S05](SOURCE_INDEX.md#s05), [S08](SOURCE_INDEX.md#s08),
[S09](SOURCE_INDEX.md#s09), [S10](SOURCE_INDEX.md#s10), [S11](SOURCE_INDEX.md#s11),
[S24](SOURCE_INDEX.md#s24), [E02](SOURCE_INDEX.md#e02).

## The two clocks

The starter calls increasing numbers. A smaller mark starts earlier; a larger
mark starts later. The frontmarker is typically slower and starts first; the
backmarker is faster and waits. The rule is:

```text
start_mark_seconds + raw_cutting_duration_seconds = common_count_seconds
18                 + 27                           = 45
```

The mark is neither predicted cutting time nor a bonus subtracted afterward.
Raw duration is measured from legal start to completion; it must stay separately
labeled from the common-count completion. Do not send a generic `time` and make
the receiver guess the clock. Dual raw timers use the supported decimal-mean
rule; partial timers require explicit capture/review.

A simple illustrative handicap gives predicted times 60, 45, 30 and marks
3, 18, 33, aligning expected completions at 63. Adding the same constant to
all marks changes the count origin, not relative ability. This explains rebasing;
it does not replace each engine's own optimizer. Marks from independently based
heats cannot be compared as absolute ability or copied into a final. Reconstruct
the new actual field using underlying eligible evidence and selected engine.

Predicted alignment does not guarantee a dead heat. Wood, technique, break
behavior and integer marks introduce variation. A slow cut does not establish
intentional sandbagging. Associations' book conversions, winnings penalties and
X systems are governing-body rules, not universal project rules.

## Profiles must remain distinct

| Profile | Supported authority / limitation |
| --- | --- |
| V2 prior-only core | Established production baseline under its existing contracts; no numeric LLM or retired local XGBoost/cascade |
| Retained V2 direct/HTTP client | Explicit transport; HTTP never falls back to in-process Python |
| V2 shadow | Separate recommendation/settlement receipts; scoring-inert in Missoula |
| Managed event v1 / rc11 | Synthetic SB/UH using real V2 predictions, new persistent shared operations and explicit mark policy; not official-use activation |
| Full Linux V3 competition | Separate selected/pinned profile with Formula and trained ML, persistent local keys and complete lifecycle under its documented policy |
| Linux V3 numeric candidate | Unissued preview/seeding/field proposals; cannot approve, issue, enter official results or settle |
| Windows V7 / full factory | Frozen contract, source/model/Formula/signing and installation/CNG qualification; passing Linux/rehearsal checks does not satisfy it |
| Separate accuracy preview | Evaluation/development program kept outside official competition selection |

V3's general architecture includes assessor-family seams and a council concept.
The completed Linux local profile has no LLM council. V2 and current Missoula
official/shadow/managed numerical authority do not acquire an LLM because a
newer language model assists engineering or optional extraction. A full factory
cannot claim all-family qualification if concrete executors/evaluators/keys are
missing. Read the profile-specific contract, not a global statement about V3.

## Root selection and evidence freezing

Each standalone event or tournament root selects once. Tournament children
inherit the root. Selection records engine, mode, actor assertion, timestamp,
reason, exact contract/source and lock. It locks before the first numerical
operation. JSON saves reference persisted authority rather than become an
alternate mutable selector. A timeout, partial response, incompatibility or
outage cannot switch to another engine/runtime.

V2 uses a persisted exclusive `prediction_as_of` date. Same-day/future and
undated observations do not become evidence. When no event date is supplied,
retained STRATHEX uses the operator computer's local calendar date so crossing
UTC midnight cannot admit the just-completed event into later rounds. Quality,
division, heat, field-strength compatibility and same-tournament results do not
change V2 predictions. Manual overrides and supported residual behavior remain
under the existing V2 contract; do not claim ignored factors affect output.

V3's supported learning uses its separate legal tournament/round epoch. All
fields in a round share frozen authority; results cannot alter their own race.
Pre-field forecasts are seeding evidence and explicitly have `issued_mark=false`.
Exact membership/stands precede jointly assembled field marks. Approval and
issue are distinct. The existence of V3 round learning does not authorize it
inside the V2-backed managed family.

## The two managed mark-policy names

`v2-optimizer.v1` preserves the existing joint optimizer and rounded/clipped
fallback, with its historical system ceiling of 183. `mark3-ceil180.v1` is an
explicit new policy using unchanged V2 raw predictions:

```text
mark = 3 + ceil(slowest_prediction - competitor_prediction)
legal integer marks = 3 through 180
```

An excessive gap blocks preparation; it is not silently compressed. These names
and policies remain distinct in root/evidence records. Do not call the new
formula a correction to the old optimizer or rewrite historical marks.

Known wood quality 0–10 and unknown `null` can be recorded in V2, with no numerical
effect. A request requiring `quality_sensitive` is unsupported. The example
275 mm underhand block is synthetic configuration, not an instruction to change
Missoula wood. Each target discipline/material/diameter context matters; do not
compare unrelated events merely because all use seconds.

## Result and fairness interpretation

Raw cutting performance, completion placing, qualifying advancement and handicap
fairness answer different questions. A fast cut matters even when eliminated.
Equal completions may share positions. Advancement-boundary ties follow the
configured policy and explicit judge selections/reasons; alphabetical order is
not an authorized sporting tiebreak.

After correction, latest accepted outcomes are required for every summary result.
Unissued descendants invalidate; issued descendants remain frozen pending
director review. Host tournament points/payouts remain explicit derivations of
accepted source positions. An engine forecast cannot decide an appeal, prove
dishonesty or independently change an issued winner.

Cutting-time MAE alone does not establish handicap fairness. Fairness claims need
actual field, issue and outcome evidence, a predeclared interpretation of chances
or expected completions, and relevant sample sizes. Synthetic close finishes are
not real-world validation.

## Evaluation modes and actual evidence

The original release obligation remains part of the modular work:

1. **Synthetic verification:** reproducible plumbing/deterministic numerical checks.
2. **Historical replay:** authorized, read-only, explicitly retrospective evaluation.
3. **Prospective:** genuinely later, previously unexamined competition groups under
   frozen protocol/component identities.

Existing historical benchmark, accuracy audit, prospective-freeze and separate
preview implementations were reused. The new installed synthetic evaluator emits
readable and machine reports with total/evaluated/eligible/excluded counts and
reasons, prediction availability, abstentions/degradation, MAE, median absolute
error, tail/max errors, interval coverage **and width**, matched-baseline metrics,
and event/material/diameter/history-depth cohorts with sample counts.

[E02](SOURCE_INDEX.md#e02) retains the published-package synthetic report: eight
generated cases, all eight predictions available, four exact-context matched
baselines and four baseline-unavailable cases. The unavailable reason is retained;
the engine/baseline comparison uses the matched four, not different available
subsets. These toy errors/coverage are deterministic execution evidence, not an
accuracy or fairness ranking. The report explicitly denies official-use promotion.

```text
strathmark evaluate synthetic --output <new-directory>
```

Private historical replay/training was NOT_RUN because the code-change approval
does not authorize it. Prospective evaluation remains BLOCKED until at least
100 genuinely later unexamined results from ten new competitions are available
with the original frozen components. Repeatedly inspected development history
cannot be relabeled prospective. Do not lower the threshold or fabricate data.

Refactoring can change implementation identity even with identical output.
Preserve original rc6 frozen source/model/Formula/protocol references. Do not
replace their hashes with the modularized code, rebind stale qualification
evidence, or claim automatic transfer. A separate attributable comparison/protocol
can be established through its proper process. Designated Windows CNG/Formula
production verification remains a separate blocked gate.

## Verification traps to avoid

- A stubbed predictor can test a host policy but is not end-to-end numerical proof.
- A package installation or green source suite is not installed-artifact verification.
- A pre-field forecast receipt is not an issuable sheet.
- A local ephemeral test signature is not an installation-owned production identity.
- An old runtime's checkpoint may need its original component; do not silently
  mutate it under a new source-identity scheme.
- A release candidate package can be published while official activation remains off.
- Recorded zero marks in retained Missoula differ from managed Mark-3 minimums.
- Never conflate raw duration, common-count completion and a display mark.
