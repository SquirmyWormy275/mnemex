# Decision register

Generated from [DECISIONS.json](DECISIONS.json). Current instructions and
contracts govern. Status is explicit; a design approval is not production activation.

## ECO-01: Incremental reusable ecosystem; Missoula first

Status: **current**. Scope: all four repositories. Authority: Owner-approved handover and/or cited maintained contract.

Build modular tournament capabilities with Missoula as the integration testbed from the outset, preserving the live show and STRATHEX retro CLI.

Rationale: The owner explicitly approved reuse and implementation through a working host rather than another planning/decision-list exercise.

Consequences: Implement/test real vertical workflows; preserve existing behavior and prove a second synthetic show before claiming real multi-show adapters.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S12](SOURCE_INDEX.md#s12), [S24](SOURCE_INDEX.md#s24).

## ECO-02: Component ownership

Status: **current**. Scope: architecture. Authority: Owner-approved handover and/or cited maintained contract.

MNEMEX owns person identity/consent/cross-show provenance; STRATHMARK owns predictions and delegated single-event operations; hosts own registration, whole-show scheduling, points and payouts.

Rationale: The approved boundaries keep source authority and presentation separate while making components reusable.

Consequences: No show DB writes from MNEMEX, no payout logic in shared calculations and no duplicate advancement algorithms in UI adapters.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S28](SOURCE_INDEX.md#s28), [S31](SOURCE_INDEX.md#s31).

## ECO-03: Two explicit integration modes

Status: **current**. Scope: host/component boundary. Authority: Owner-approved handover and/or cited maintained contract.

Support calculation-only and explicitly delegated operations. A calculation-only host retains event workflow authority; delegated events use STRATHMARK operational state.

Rationale: Getting a prediction is a different act from delegating review, issue and advancement.

Consequences: Never infer authority transfer from a calculation response or silently opt an existing event into managed mode.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S06](SOURCE_INDEX.md#s06), [S17](SOURCE_INDEX.md#s17).

## ECO-04: One shared operational core

Status: **current**. Scope: CLI GUI host. Authority: Owner-approved handover and/or cited maintained contract.

CLI, optional shared GUI, Missoula adapter and STRATHEX managed presentation call the same event operations.

Rationale: The owner wants interchangeable presentation without rebuilding domain algorithms or context.

Consequences: Keep fields, review, issue, correction, progression, source receipts and invariants in shared operations, not wrappers.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S06](SOURCE_INDEX.md#s06).

## ECO-05: Real standalone operator-supplied-data CLI

Status: **current**. Scope: STRATHMARK. Authority: Owner-approved handover and/or cited maintained contract.

Provide a standalone installed CLI accepting user event configuration and numeric requests, not only generated demos or a Missoula wrapper.

Rationale: Independent installed use proves the modular component is reusable beyond one host.

Consequences: Core install imports neither host nor MNEMEX; examples are optional labeled synthetic inputs.

Sources: [S01](SOURCE_INDEX.md#s01), [S06](SOURCE_INDEX.md#s06), [E01](SOURCE_INDEX.md#e01).

## ECO-06: Optional shared GUI

Status: **current**. Scope: presentation. Authority: Owner-approved handover and/or cited maintained contract.

The shared GUI is optional, authenticated and backed by the same operations/history as CLI, with explicit editor handover.

Rationale: Operators can change interface without creating a second authority or numerical implementation.

Consequences: Protect accounts/sessions/CSRF, default to loopback, review exact sheet digests and never treat GUI availability as engine qualification.

Sources: [S01](SOURCE_INDEX.md#s01), [S06](SOURCE_INDEX.md#s06), [E03](SOURCE_INDEX.md#e03).

## ECO-07: Explicit immutable root selection; no engine fallback

Status: **current**. Scope: numerical/operational roots. Authority: Owner-approved handover and/or cited maintained contract.

Choose engine/runtime and mark policy explicitly at the competition root; children inherit. Failure never triggers another engine or policy.

Rationale: Fallback would change numerical authority and destroy reproducible evidence.

Consequences: Refuse unavailable/ineligible selections; retain identity/version/digest and require new authorized roots for different policy.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S03](SOURCE_INDEX.md#s03), [S24](SOURCE_INDEX.md#s24).

## ECO-08: Offline race-day operation

Status: **current**. Scope: MNEMEX and hosts. Authority: Owner-approved handover and/or cited maintained contract.

MNEMEX supports pre-event validation and post-event reconciliation; pinned local show operation must not need MNEMEX availability during competition.

Rationale: An identity service outage must not decide the show or make locked registrations unusable.

Consequences: Validate online before import/roster lock, then use authorized local snapshots; queue results for later delivery.

Sources: [S01](SOURCE_INDEX.md#s01), [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S31](SOURCE_INDEX.md#s31).

## ECO-09: Retain STRATHEX retro behavior

Status: **current**. Scope: STRATHEX terminal. Authority: Owner-approved handover and/or cited maintained contract.

Keep the existing retro CLI, Excel judge artifact, saves and existing V2/V3 pins working; managed mode is explicitly selected before legacy startup.

Rationale: The owner expressly required preservation, and legacy startup has operator workbook/database side effects.

Consequences: Use a separate selected interpreter for managed delegation and isolated storage for tests; do not rewrite normal startup into a different product.

Sources: [S01](SOURCE_INDEX.md#s01), [S24](SOURCE_INDEX.md#s24), [S25](SOURCE_INDEX.md#s25), [S26](SOURCE_INDEX.md#s26), [S27](SOURCE_INDEX.md#s27).

## ECO-10: Synthetic first bounded managed profile

Status: **current**. Scope: managed v1. Authority: Owner-approved handover and/or cited maintained contract.

Qualify fresh synthetic single-run individual handicap SB/UH using the real packaged V2 predictor, configured wood, explicit Mark-3 policy and dual timers in Missoula.

Rationale: A narrow real engine workflow is reviewable without claiming broader official eligibility.

Consequences: Refuse existing history, partnered/dual/triple/shadow/live binding; production managed activation remains disabled.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S06](SOURCE_INDEX.md#s06), [S17](SOURCE_INDEX.md#s17).

## OPS-01: Durable exact request retries and controlled editor handover

Status: **current**. Scope: managed operations. Authority: Owner-approved handover and/or cited maintained contract.

Retain stable request ID, actor, exact payload/digest, expected revision and editor. Exact retries recover receipts; changed payloads conflict.

Rationale: Response loss is ambiguous success, not permission to issue a second operation.

Consequences: Recover original requests, refuse stale mutation and use explicit handover rather than concurrent independent editors.

Sources: [S06](SOURCE_INDEX.md#s06), [S17](SOURCE_INDEX.md#s17), [E01](SOURCE_INDEX.md#e01), [E04](SOURCE_INDEX.md#e04).

## OPS-02: Review and issue are separate commitments

Status: **current**. Scope: managed field lifecycle. Authority: Owner-approved handover and/or cited maintained contract.

Forecast/proposed sheet, review, explicit issue, outcomes, judge acceptance and finalization are separate durable actions bound to exact field/sheet identity.

Rationale: A number or reviewed draft is not authority to start or a final official result.

Consequences: Changed preparation invalidates dependent unissued artifacts; preserve issued identity/history, use explicit correction revisions.

Sources: [S01](SOURCE_INDEX.md#s01), [S06](SOURCE_INDEX.md#s06), [S17](SOURCE_INDEX.md#s17).

## OPS-03: Progression recomputes field-relative marks

Status: **current**. Scope: qualifying semifinals finals. Authority: Owner-approved handover and/or cited maintained contract.

Qualify entrants by configured rules and resolve boundary ties explicitly; each new field recalculates its own marks.

Rationale: Start offsets depend on the exact competing field, not a portable athlete mark.

Consequences: Never copy qualifying marks into a final or silently resolve judge ties by UI ordering.

Sources: [S03](SOURCE_INDEX.md#s03), [S06](SOURCE_INDEX.md#s06), [E01](SOURCE_INDEX.md#e01).

## OPS-04: Insert-only source creation ownership

Status: **current**. Scope: Missoula initial binding. Authority: Owner-approved handover and/or cited maintained contract.

An uncertain source create can only be adopted through its original source actor/request/config receipt; another candidate cannot replace it.

Rationale: A later refused creation must not overwrite a successful but response-lost event or mapping.

Consequences: Keep durable pending intents, source creation evidence and superseded-candidate conflicts; recovery may differ from the latest submitted candidate. Reacquire/revalidate host facts after durable intent and hold through actual source creation/projection/commit; reject invalid persisted show scopes before link allocation.

Sources: [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18), [E17](SOURCE_INDEX.md#e17).

## OPS-05: Monotonic locked host projection

Status: **current**. Scope: Missoula adapter. Authority: Owner-approved handover and/or cited maintained contract.

Reload under tournament/event locks, verify identity/config and move cached state/physical fields only forward in source revision.

Rationale: Delayed responses retain their own receipts but must not overwrite a newer correction or fresh host facts.

Consequences: Recheck wood for every config and current roster/divisions/gear before newer physical fields. Hold underlying PostgreSQL wood/competitor locks or the real host SQLite writer through commit, including uncoordinated writers. Receipt-only no-field forecast recovery publishes no physical heat. Protect scheduled/issued/started/completed fields.

Sources: [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18), [E14](SOURCE_INDEX.md#e14), [E16](SOURCE_INDEX.md#e16).

## OPS-06: Accept source export atomically through actual DB commit

Status: **current**. Scope: Missoula result acceptance. Authority: Owner-approved handover and/or cited maintained contract.

Hold the actual source fence through the host DBAPI commit; accept source attempts, career outbox, summary and receipt in one host transaction.

Rationale: A subprocess verification that ends before commit leaves a race for later source revisions.

Consequences: Refuse stale exports; preserve rollback/retry; batch source guards before host locks. Local coordination is not distributed hosted qualification.

Sources: [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18), [E04](SOURCE_INDEX.md#e04), [E08](SOURCE_INDEX.md#e08).

## OPS-07: Explicit host awards and correction reconciliation

Status: **current**. Scope: Missoula scoring. Authority: Owner-approved handover and/or cited maintained contract.

Host points/payouts use accepted current finalized source positions, current host registration and explicit award application; settlement is separate.

Rationale: Accepting a correction must not silently pay, repay or leave a nonfinal event eligible for final awards.

Consequences: Reopen host finalization on a nonfinal correction, preserve old award facts until deliberate reconciliation and rebuild college/team or pro totals.

Sources: [S12](SOURCE_INDEX.md#s12), [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18), [E14](SOURCE_INDEX.md#e14), [E16](SOURCE_INDEX.md#e16).

## OPS-08: Protect source-owned state from legacy writers

Status: **current**. Scope: Missoula legacy routes. Authority: Owner-approved handover and/or cited maintained contract.

Legacy score writes, scratch/deletion and gear repair must not mutate delegated fields/results; host-owned events continue to work.

Rationale: Managed ownership would be meaningless if unrelated legacy writers could alter accepted source facts.

Consequences: Guard global routes, college/team deletion, repairs and schedule writes; explicitly unschedule safe pending fields with digest binding before replacement.

Sources: [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18).

## OPS-09: Safe roster shrink preserves history

Status: **current**. Scope: Missoula unissued revision. Authority: Owner-approved handover and/or cited maintained contract.

When adopting an unissued smaller roster, reconcile removed host placeholders only if they are empty pending results; any score/mark/award/settlement/reason history blocks deletion. Apply the same empty-placeholder reconciliation to initial binding; recorded history refuses the fresh opt-in.

Rationale: Ghost pending rows corrupt finalization, while deleting recorded zero timers or reviewed marks destroys history.

Consequences: Verify and reconcile under host locks; a refused projection retains source intent for recovery instead of erasing facts.

Sources: [S17](SOURCE_INDEX.md#s17), [S18](SOURCE_INDEX.md#s18), [E14](SOURCE_INDEX.md#e14), [E17](SOURCE_INDEX.md#e17).

## OPS-10: Bounded supervised career delivery

Status: **current**. Scope: host to MNEMEX. Authority: Owner-approved handover and/or cited maintained contract.

Deliver accepted source attempts/corrections through a durable bounded outbox to the explicit authenticated sandbox inbox, outside scoring/finalization.

Rationale: MNEMEX downtime or committed-response loss must not block the show or duplicate career records.

Consequences: Retain source/digest/receipt provenance, retry exact messages, reconcile conflicts and leave people unresolved without authorization. Non-object acknowledgement JSON remains pending for retry; malformed local RPC responses are controlled failures.

Sources: [S17](SOURCE_INDEX.md#s17), [S31](SOURCE_INDEX.md#s31), [E04](SOURCE_INDEX.md#e04), [E17](SOURCE_INDEX.md#e17).

## NUM-01: Common count is start mark plus raw duration

Status: **current**. Scope: all handicap semantics. Authority: Owner-approved handover and/or cited maintained contract.

common_count_completion = start_mark + raw_cutting_duration. Larger marks start later; raw duration remains raw evidence.

Rationale: Owner reaffirmed the common-count start semantics; subtraction ranks the same performance incorrectly.

Consequences: Sort common-count completion in handicap time scoring. Keep DNS/DNF/DQ, timer average, raw result and issue provenance separate.

Sources: [S01](SOURCE_INDEX.md#s01), [S03](SOURCE_INDEX.md#s03), [S12](SOURCE_INDEX.md#s12), [S22](SOURCE_INDEX.md#s22), [S24](SOURCE_INDEX.md#s24).

## NUM-02: Mark-3 is an explicit new policy

Status: **current**. Scope: managed mark3-ceil180.v1. Authority: Owner-approved handover and/or cited maintained contract.

Use integer mark = 3 + ceil(max_field_prediction - entrant_prediction), with allowed marks 3 through 180. Block out-of-range fields.

Rationale: The approved Mark-3 conversion is deliberately distinct from retained optimizer behavior.

Consequences: Do not compress/clamp to fit, substitute zero or alter the legacy optimizer policy. Marks are recalculated per field.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S03](SOURCE_INDEX.md#s03), [S06](SOURCE_INDEX.md#s06).

## NUM-03: Retain legacy optimizer policy separately

Status: **current**. Scope: v2-optimizer.v1. Authority: Owner-approved handover and/or cited maintained contract.

Retained V2 joint-optimizer/clipped historical behavior remains versioned separately; its historical maximum can be 183.

Rationale: Compatibility and historical evidence cannot be silently rewritten to match the new Mark-3 policy.

Consequences: Root policy identity must be visible in receipts; never treat a retained 183 ceiling as permission for managed marks above 180.

Sources: [S01](SOURCE_INDEX.md#s01), [S03](SOURCE_INDEX.md#s03), [S24](SOURCE_INDEX.md#s24).

## NUM-04: V2 predictor is real and numerical LLM workflow is retired

Status: **current**. Scope: V2. Authority: Owner-approved handover and/or cited maintained contract.

Use the packaged V2 predictor and its supported evidence contract. Numeric LLM/council calculation is retired for V2.

Rationale: The handover requires real reproducible numerical behavior, not mock values or speculative LLM adjustments.

Consequences: Do not confuse V3 council/family architecture with permission to alter V2 or introduce an unavailable fallback.

Sources: [S01](SOURCE_INDEX.md#s01), [S10](SOURCE_INDEX.md#s10), [S24](SOURCE_INDEX.md#s24).

## NUM-05: Wood quality record-only for V2

Status: **current**. Scope: V2 evidence and managed config. Authority: Owner-approved handover and/or cited maintained contract.

Accept supported known quality on 0–10 or null; record it but V2 does not change predictions for it. quality_sensitive is unsupported.

Rationale: Evidence may retain context without claiming an unqualified numerical feature.

Consequences: Never invent quality from a photo, coerce unknown to a meaningful zero or silently activate quality-sensitive calculations.

Sources: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02), [S03](SOURCE_INDEX.md#s03), [S10](SOURCE_INDEX.md#s10).

## NUM-06: Prior-only reviewed evidence; no leakage

Status: **current**. Scope: numeric evidence export. Authority: Owner-approved handover and/or cited maintained contract.

Use only eligible reviewed SB/UH prior results at the declared cutoff; same-day, future and undated rows are not V2 prior evidence.

Rationale: Prediction evaluation must not learn from the outcome it is predicting or broaden trust just because an archive contains a row.

Consequences: Retain source dates/review/provenance; distinguish source outcomes from model training eligibility.

Sources: [S01](SOURCE_INDEX.md#s01), [S10](SOURCE_INDEX.md#s10), [S11](SOURCE_INDEX.md#s11), [S28](SOURCE_INDEX.md#s28), [S31](SOURCE_INDEX.md#s31).

## NUM-07: Distinct V3 runtime profiles

Status: **current**. Scope: retained V3. Authority: Owner-approved handover and/or cited maintained contract.

Full Linux competition, unissued Linux preview and Windows full-factory/CNG are distinct exact contracts. Do not label all Linux V3 preview-only.

Rationale: Runtime/engine eligibility is profile-specific and bound to source/digest/qualification.

Consequences: Inspect CURRENT_RUNTIME_CONTRACT and producer V3 docs; managed v1 stays V2, Linux tests do not establish Windows CNG eligibility.

Sources: [S05](SOURCE_INDEX.md#s05), [S08](SOURCE_INDEX.md#s08), [S09](SOURCE_INDEX.md#s09), [S24](SOURCE_INDEX.md#s24).

## NUM-08: Retained zero is not managed minimum

Status: **current**. Scope: legacy official vs managed marks. Authority: Owner-approved handover and/or cited maintained contract.

An explicitly reviewed legacy zero start mark is valid and needs review evidence. Managed Mark-3 has minimum three.

Rationale: Zero must not also mean no review; different policy roots have different domains.

Consequences: Preserve mark_assigned_at/review state and never use default 0.0 as proof a late entrant was reviewed.

Sources: [S03](SOURCE_INDEX.md#s03), [S12](SOURCE_INDEX.md#s12), [S22](SOURCE_INDEX.md#s22).

## EVAL-01: Synthetic evaluation proves only declared synthetic scope

Status: **current**. Scope: carried-forward evaluation. Authority: Owner-approved handover and/or cited maintained contract.

Keep the actual packaged-predictor synthetic evaluation: eight cases and four matched outcome sets, with runtime/source/data scope explicit.

Rationale: Synthetic execution is useful portability/regression evidence, not real-world accuracy qualification.

Consequences: Report metrics and unresolved limitations honestly; no private-history execution or training is implied.

Sources: [S01](SOURCE_INDEX.md#s01), [S10](SOURCE_INDEX.md#s10), [S11](SOURCE_INDEX.md#s11), [E02](SOURCE_INDEX.md#e02).

## EVAL-02: Frozen prospective qualification remains blocked

Status: **blocked**. Scope: original rc6 prospective program. Authority: Owner-approved handover and/or cited maintained contract.

Require at least 100 genuinely later previously unexamined results from ten new competitions under the original frozen components.

Rationale: Prospective evidence cannot be manufactured from examined old data or transferred to a different candidate by changing hashes.

Consequences: Wait for real future observations; keep rc6 freeze and rc11 delivery separate; do not rehash artifacts to mark qualification passed.

Sources: [S01](SOURCE_INDEX.md#s01), [S10](SOURCE_INDEX.md#s10), [S11](SOURCE_INDEX.md#s11).

## SHOW-01: Missoula canonical show contract wins

Status: **current**. Scope: Missoula. Authority: Owner-approved handover and/or cited maintained contract.

Follow docs/DOMAIN_CONTRACT.md, then tests, FlightLogic, reconnaissance and historical requirements. Preserve the documented show behavior.

Rationale: Older requirements/algorithm notes contain known contradictions and are not a new owner decision.

Consequences: Record conflicts and governing corrections; never simplify sporting rules to fit shared operations.

Sources: [S01](SOURCE_INDEX.md#s01), [S12](SOURCE_INDEX.md#s12), [S13](SOURCE_INDEX.md#s13), [S14](SOURCE_INDEX.md#s14).

## SHOW-02: Atomic whole-show scheduling

Status: **current**. Scope: Missoula scheduling. Authority: Owner-approved handover and/or cited maintained contract.

Plan/validate complete show schedules using fresh inputs and publish atomically; invalid constraints reject without destroying the prior schedule.

Rationale: Partial schedule mutation can strand competitors and invalidate issued/started state.

Consequences: Preserve host show ordering, partner/run spacing, gear and capacity constraints; shared event operations do not reorder whole flights.

Sources: [S12](SOURCE_INDEX.md#s12), [S13](SOURCE_INDEX.md#s13), [S17](SOURCE_INDEX.md#s17).

## SHOW-03: Physical stands and left-hand constraints

Status: **current**. Scope: Missoula resources. Authority: Owner-approved handover and/or cited maintained contract.

Stock Saw uses stands 7/8 for both pro and college. Left-handed springboard uses its configured left-handed dummy (conventionally stand 4), at most once per heat; expand or reject invalid generation.

Rationale: Later canonical corrections supersede older Stock Saw 1/2 and same-heat left-handed springboard overflow descriptions. This is a springboard-specific resource rule.

Consequences: No same-heat invalid overflow or arbitrary resource expansion; validate source fields against actual configured stands.

Sources: [S12](SOURCE_INDEX.md#s12), [S13](SOURCE_INDEX.md#s13), [S14](SOURCE_INDEX.md#s14), [S17](SOURCE_INDEX.md#s17).

## SHOW-04: Gear sharing is a hard scheduling constraint

Status: **current**. Scope: Missoula gear. Authority: Owner-approved handover and/or cited maintained contract.

Normalize declarations/groups, respect valid event-specific sharing and physical concurrent limits, and reject impossible assignments before mutation.

Rationale: Ignoring gear when everyone shares it does not make the schedule runnable.

Consequences: Use canonical gear services and tests; managed fields are protected from legacy repair. Saw constraints remain per documented group/capacity.

Sources: [S12](SOURCE_INDEX.md#s12), [S15](SOURCE_INDEX.md#s15), [S17](SOURCE_INDEX.md#s17).

## SHOW-05: College teams and points

Status: **current**. Scope: Missoula college. Authority: Owner-approved handover and/or cited maintained contract.

Teams have at most eight members with at least two of each gender; closed-event entry cap six, configurable open events, placement points 10/7/5/3/2/1.

Rationale: These are the owner/canonical competition rules, not generic defaults to replace.

Consequences: Split tied placement points as documented; rebuild individual/team aggregates after accepted changes; preserve pro vs college distinctions.

Sources: [S12](SOURCE_INDEX.md#s12), [S14](SOURCE_INDEX.md#s14).

## SHOW-06: Pro shared-position purse

Status: **current**. Scope: Missoula payouts. Authority: Owner-approved handover and/or cited maintained contract.

Pro entrants sharing a position receive that position's configured amount each; do not split a single prize pool among them.

Rationale: Host purse semantics differ from collegiate tie-point averaging.

Consequences: Source positions drive explicit host awards; payout templates and settlement remain host-owned.

Sources: [S12](SOURCE_INDEX.md#s12), [S17](SOURCE_INDEX.md#s17).

## SHOW-07: Dual stopwatches and raw facts

Status: **current**. Scope: Missoula timed events. Authority: Owner-approved handover and/or cited maintained contract.

Preserve two judge stopwatches per physical timed run and average per the documented policy; retain individual readings and raw duration.

Rationale: Timing evidence and common-count placement are different facts.

Consequences: Do not count absent/DNS/DNF/DQ as numeric zero; corrections retain issued/source identity and reviewer.

Sources: [S12](SOURCE_INDEX.md#s12), [S17](SOURCE_INDEX.md#s17).

## SHOW-08: Partnered axe and normalized state

Status: **current**. Scope: Missoula storage. Authority: Owner-approved handover and/or cited maintained contract.

Partnered Axe Throw keeps its documented prelim/final Event.event_state state machine; HeatAssignment and normalized relay/Birling tables are canonical for their domains.

Rationale: Historical JSON roster/stand/Birling/relay stores have been removed or superseded by migrations.

Consequences: Use Heat.set_roster and actual relationships; never recreate parallel stale JSON authority.

Sources: [S12](SOURCE_INDEX.md#s12), [S13](SOURCE_INDEX.md#s13), [S14](SOURCE_INDEX.md#s14), [S16](SOURCE_INDEX.md#s16).

## SHOW-09: Pro-Am Relay lottery and program

Status: **current**. Scope: Missoula relay. Authority: Owner-approved handover and/or cited maintained contract.

Relay teams have eight members: two each pro men/pro women/college men/college women; $5 lottery entry does not guarantee selection. Preserve four-event order and closing placement.

Rationale: Relay mixes groups and has separate participation, money and show-program semantics.

Consequences: Saw, Standing Butcher, Underhand Butcher, Team Axe Balloon; no college points, documented college prize-money exception; preserve Chokerman run-two closer.

Sources: [S12](SOURCE_INDEX.md#s12), [S14](SOURCE_INDEX.md#s14), [S16](SOURCE_INDEX.md#s16).

## SHOW-10: Offline score submissions retain identity

Status: **current**. Scope: Missoula offline operations. Authority: Owner-approved handover and/or cited maintained contract.

Offline score queues and replay use signed/context-bound receipts and explicit conflict handling, not an unauthenticated alternate scoring channel.

Rationale: Offline operation must preserve the same authority, event/field context and duplicate protections as online entry.

Consequences: Keep HMAC/session/event boundaries, replay receipts and judge confirmation; do not treat cached browser state as final authority.

Sources: [S12](SOURCE_INDEX.md#s12), [S18](SOURCE_INDEX.md#s18), [S20](SOURCE_INDEX.md#s20).

## D0-1: Minors in the first pilot (owner option C)

Status: **planned**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Support minors from the first pilot, with guardian and age-aware controls.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Guardian authority, consent/revocation/retention and transition at adulthood are required; authentication alone does not verify guardianship.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-2: Expanded legal identity (owner option B)

Status: **planned**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Build the expanded legal-identity profile, separated from display/competitive identity.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Encrypt private claims; do not expose legal/contact values to logs, public pages or ordinary show/numerical projections.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-3: Opt-in public pages in the pilot (owner option B)

Status: **planned**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Include per-person opt-in public profile pages in the intended pilot.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Private is the default. Archive publication and a successful login do not make a person public.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-4: MNEMEX-owned authentication (owner option C)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Use MNEMEX's own account/UX boundary with maintained framework auth/crypto primitives.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Account auth, person identity verification, guardian authority and partner grants remain independent.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-5: Multiple shows from the start (owner option B)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Support multiple shows from the first schema/tenancy design.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Register tenant/client ownership, pairwise references, scoped credentials and revocation; do not retrofit global public correlation IDs.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-6: Online validation before lock; offline afterward (owner option B)

Status: **planned**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Use online-only package validation before import/roster lock, then a pinned local snapshot during the event.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: No race-day MNEMEX dependency or silent refresh of a locked roster; manual registration remains available.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-7: Server-side atomic transaction (owner option A)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Commit inbox/provenance/career-reconciliation/receipt/outbox effects in a server-side transaction.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Do not approximate transactional authority with client-side chained writes; preserve exact retry and conflict receipts.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-8: Recovery and retention before real PII (owner option A)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Approve and prove recovery/retention obligations before ingesting real personally identifying data.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: RPO/RTO, DB/private-object/key restores and deletion/legal-hold behavior are required; local passing tests are insufficient.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-9: Legacy bulk migration first (owner option B)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Migrate legacy career sources through explicit bulk staging/quarantine/reconciliation before pilot legacy activation.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Preserve originals, exact-digest approvals, review and resumable checkpoints; do not auto-link ambiguous names.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-10: Integrated Django Results Desk on Railway/Supabase (owner option A)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Use a single Django modular monolith with integrated Results Desk, hosted on Railway with Supabase PostgreSQL/private objects.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Shared domain/migrations for web/workers; provider configuration/recovery remain explicit activation gates.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-11: Broad result capture; narrow reviewed SB/UH export (owner option A)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Archive broad results while keeping STRATHMARK 2.x evidence export restricted to reviewed eligible prior SB/UH.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Archive coverage does not widen numeric eligibility, consent, trust or discipline support.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## D0-12: Automatic valid-source publication (owner option C)

Status: **current**. Scope: MNEMEX approved August 14 design. Authority: Explicit owner-approved D0 selection in S29; delivery scope separately tracked.

Automatically publish deterministic-valid uploaded rows to the private archive.

Rationale: This is the owner's recorded selection, including choices that differ from the document's recommendation. Do not restart the options round.

Consequences: Identity reconciliation, verification/trust, public visibility, consent and STRATHMARK eligibility remain separate review states.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## MNE-01: Immutable opaque Person identity

Status: **current**. Scope: MNEMEX identity. Authority: Owner-approved handover and/or cited maintained contract.

Use an opaque immutable person ID distinct from account, email, name, federation ID, pairwise show reference and numerical pseudonym.

Rationale: Names and accounts change; correlation and legal identity have different disclosure/authority boundaries.

Consequences: Never recycle IDs or silently name-link people; merge/split/redact preserves provenance and tombstones.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## MNE-02: Purpose-scoped grants and portable projections

Status: **planned**. Scope: planned full portable profiles. Authority: Owner-approved handover and/or cited maintained contract.

Portable profiles require explicit recipient/show/purpose/field scope, approval/version, expiry/revocation and retention acknowledgment; projected packages bind issuer/audience/digest/context.

Rationale: A profile is a scoped projection, not a replica of legal identity or a universal bearer credential.

Consequences: Validate before import/lock, retain exact receipt/digest/local mapping, respect revocation for future disclosure and keep manual registration.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30).

## MNE-03: Source archive preserves extraction provenance

Status: **current**. Scope: Results Desk. Authority: Owner-approved handover and/or cited maintained contract.

Preserve original artifacts/digests, selected sheet/row/cell, parser/mapping version, operator/reviewer, validation, correction and supersession.

Rationale: Extracted rows are evidence of a source, not inherently verified person facts.

Consequences: Multi-sheet XLSX requires explicit selection; LLM outputs are untrusted and cannot invent source values; conflicts quarantine.

Sources: [S28](SOURCE_INDEX.md#s28), [S30](SOURCE_INDEX.md#s30), [S32](SOURCE_INDEX.md#s32).

## MNE-04: Narrow sandbox receiver is implemented; full portability is not

Status: **current**. Scope: October MNEMEX delivery. Authority: Owner-approved handover and/or cited maintained contract.

mnemex.show-result.v1 accepts registered source-attributed immutable attempts/corrections and receipts, leaving identities unresolved.

Rationale: The bounded real receiver validates integration without pretending all portable-profile features or production activation are done.

Consequences: Do not create Person/career/public links automatically or write directly to host scoring tables.

Sources: [S31](SOURCE_INDEX.md#s31), [S32](SOURCE_INDEX.md#s32), [E10](SOURCE_INDEX.md#e10).

## MNE-05: Scoped machine identity and immutable correction stream

Status: **current**. Scope: source-result inbox. Authority: Owner-approved handover and/or cited maintained contract.

Enforce source/client ownership, expiring revocable hashed credentials, issued-field/entry binding, immutable payload digests and contiguous correction predecessors.

Rationale: An alternate message ID must not bypass a changed source revision conflict or poison another stream.

Consequences: Exact retries recover receipts; out-of-order revisions wait; retain conflict and authenticating-credential provenance; unknown historical attribution stays null.

Sources: [S31](SOURCE_INDEX.md#s31), [S32](SOURCE_INDEX.md#s32), [E10](SOURCE_INDEX.md#e10).

## MNE-06: Maintained authentication and fresh privileged actions

Status: **current**. Scope: MNEMEX local security foundation. Authority: Owner-approved handover and/or cited maintained contract.

Use Django/allauth, Argon2id, verified email, privileged TOTP/recovery, session rotation/revocation, eight-hour privileged freshness and five-minute sensitive-POST freshness.

Rationale: The approved own-auth choice does not mean inventing cryptography or skipping action-specific authorization.

Consequences: Sensitive tickets bind route/origin/session/method/account/security version; in-page step-up preserves form/files and requires explicit confirmation.

Sources: [S32](SOURCE_INDEX.md#s32), [S34](SOURCE_INDEX.md#s34).

## MNE-07: Queue-only security mail

Status: **current**. Scope: MNEMEX August 18 cutover. Authority: Owner-approved handover and/or cited maintained contract.

Security notifications create encrypted durable intents and use bounded fenced workers; the request path does not fall back to SMTP.

Rationale: Owner approved queue-only after availability implications were disclosed; unknown handoff must be reviewed rather than blindly duplicated.

Consequences: Retain event-time verified recipients, deterministic identity, retries, leases and uncertain-handoff evidence. Hosted SMTP/recovery proofs remain open.

Sources: [S32](SOURCE_INDEX.md#s32), [S33](SOURCE_INDEX.md#s33), [S34](SOURCE_INDEX.md#s34).

## MNE-08: Recover DB, private artifacts and historical keys together

Status: **current**. Scope: MNEMEX recovery. Authority: Owner-approved handover and/or cited maintained contract.

Recovery includes DB, private objects, versioned encryption keys and reconciled inventory, not only a database backup.

Rationale: A restored row is unusable if its private evidence or required historical key is absent.

Consequences: Keep key retirement blockers, resumable re-encryption, artifact leases/orphan reconciliation and independent provider recovery proofs.

Sources: [S33](SOURCE_INDEX.md#s33), [S34](SOURCE_INDEX.md#s34), [S35](SOURCE_INDEX.md#s35), [S36](SOURCE_INDEX.md#s36).

## MNE-09: Production privileged activation stays hard-disabled

Status: **blocked**. Scope: MNEMEX production. Authority: Owner-approved handover and/or cited maintained contract.

All fourteen activation gates remain unclosed; a registry/report/offline signature verifier cannot enable production privilege.

Rationale: Local CI cannot prove hosted configuration, provider recovery, independent operators or custody.

Consequences: No environment toggle shortcut or implied live pilot. Follow G01–G14 evidence and operator ceremonies.

Sources: [S33](SOURCE_INDEX.md#s33), [S34](SOURCE_INDEX.md#s34), [S35](SOURCE_INDEX.md#s35), [S36](SOURCE_INDEX.md#s36).

## DEL-01: Repository process with precise source evidence

Status: **current**. Scope: delivery. Authority: Owner-approved handover and/or cited maintained contract.

Commit/push/merge verified changes through each repository's permitted PR process, preserving exact head/main/CI/review/artifact and failure receipts.

Rationale: Merged, published, activated and verified are different states; a later commit does not inherit an exact-head result.

Consequences: Fetch before edits, isolate baselines, record skips and cleanup, do not bypass branch protection or erase failures.

Sources: [S01](SOURCE_INDEX.md#s01), [S07](SOURCE_INDEX.md#s07), [S18](SOURCE_INDEX.md#s18), [S19](SOURCE_INDEX.md#s19).

## DEL-02: Missoula backup/key proofs block merge

Status: **blocked**. Scope: Missoula PR 125. Authority: Owner-approved handover and/or cited maintained contract.

Keep the feature draft/unmerged until exact-current-branch hosted read-only backup/restore/encrypted-artifact proof and separately held recovery-identity decryption/restore rehearsal exist.

Rationale: The branch advances the backup Alembic expectation and main automatically deploys/migrates; the repository release checklist explicitly requires these proofs.

Consequences: No production workflow dispatch, gate bypass, schema-pin removal or merge merely because CI is green. Authorized operators must supply the exact proofs.

Sources: [S01](SOURCE_INDEX.md#s01), [S18](SOURCE_INDEX.md#s18), [S19](SOURCE_INDEX.md#s19), [S20](SOURCE_INDEX.md#s20).

## DEL-03: No private data or numerical requalification by implication

Status: **current**. Scope: evaluation and release. Authority: Owner-approved handover and/or cited maintained contract.

Routine implementation authorization does not authorize private historical training/runs, operational data tests, official activation or changing frozen qualification artifacts.

Rationale: Availability of credentials/data is not the owner's permission for a new operational use.

Consequences: Use synthetic isolated proof, keep NOT_RUN/BLOCKED explicit and request only the specific genuinely required external input when needed.

Sources: [S01](SOURCE_INDEX.md#s01), [S07](SOURCE_INDEX.md#s07), [S10](SOURCE_INDEX.md#s10), [S11](SOURCE_INDEX.md#s11), [S19](SOURCE_INDEX.md#s19), [S33](SOURCE_INDEX.md#s33).

## MEM-01: Model-neutral memory stored in MNEMEX Git

Status: **current**. Scope: new owner memory request October 16. Authority: Owner-approved handover and/or cited maintained contract.

Store a thorough cross-repository handoff in MNEMEX Markdown/JSON/source snapshots with a single entry point and offline search/context/integrity tooling.

Rationale: The owner wants to switch harness/model without rebuilding hours of context; implemented MNEMEX has no general project-memory ingest API.

Consequences: Link AGENTS/CLAUDE/README; avoid Django/database dependency, keep decisions/rationale/status/sources and preserve the coverage limit on unseen conversations.

Sources: [S37](SOURCE_INDEX.md#s37), [S01](SOURCE_INDEX.md#s01), [S31](SOURCE_INDEX.md#s31), [S32](SOURCE_INDEX.md#s32).

## MEM-02: Technical memory is separate from person/career data

Status: **current**. Scope: memory storage boundary. Authority: Owner-approved handover and/or cited maintained contract.

Do not put design decisions into Person, consent, source-result or career tables or pretend this pack is an application memory endpoint.

Rationale: The technical handoff has different semantics and disclosure rules from competitor data.

Consequences: No PII/keys/credentials/datasets in the pack; source snapshots are dated reference, current user/repository instructions still govern.

Sources: [S37](SOURCE_INDEX.md#s37), [S28](SOURCE_INDEX.md#s28), [S31](SOURCE_INDEX.md#s31), [S32](SOURCE_INDEX.md#s32).

## OLD-01: Historical-only scraper and JSONL canonical store retired

Status: **superseded**. Scope: MNEMEX history. Authority: Owner-approved handover and/or cited maintained contract.

The old historical-only scraper/static archive/JSONL-git canonical design is superseded by the approved universal profile service and integrated Desk.

Rationale: August 14 owner selections changed product scope and transactional requirements.

Consequences: Do not resurrect the retired scheduled production exporter; legacy JSONL may remain an explicit compatibility/export surface.

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S30](SOURCE_INDEX.md#s30), [S32](SOURCE_INDEX.md#s32).
