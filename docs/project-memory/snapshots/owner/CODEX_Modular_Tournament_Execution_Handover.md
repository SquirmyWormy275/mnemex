# Codex Execution Handover: Modular Tournament Management

**Owner:** Alex Kaper  
**Prepared:** October 15, 2026 — America/Los_Angeles  
**Task:** Implement the approved cross-repository architecture and its working integrations.  
**Primary integration testbed:** Missoula Pro-Am Manager  
**Status of this handover:** Implementation instructions, not evidence that the work is already complete.

## 1. Mission and authorization

Build reusable tournament capabilities that can serve Missoula and subsequent shows without rebuilding their handicap, identity, history, or event workflows. Keep Missoula usable and preserve its documented show structure and sporting rules throughout.

Alex approved the modular direction and all six additions from the latest planning discussion, and authorized the associated implementation and repository changes. Proceed with the engineering work, tests, documentation, commits, pull requests, and verified merges within this scope. Do not stop at another architecture proposal or ask Alex to reapprove decisions already recorded here.

Use the repository's permitted branch/review process. Do not bypass protected branches, required reviews, or failing checks. Determine what merges trigger before merging: package publication and a live application deployment are different consequences. Preserve standing publication policies, but do not expose a new official workflow or mutate operational data merely because code is merged.

This instruction authorizes development, not destructive database operations, disclosure of private records, paid infrastructure purchases, private-data model training, or bypassing installation-specific production qualification. Keep new managed-event functionality opt-in and non-operational in live shows until its applicable release gates pass.

If a dependency or qualification gate is unavailable, finish the independent implementation and verification that can proceed. Record the exact blocked gate; do not report it as passed, dilute the test, or stop all unrelated work.

### Repositories in scope

All are under `SquirmyWormy275`:

| Repository | Role in this work | Observed `main` at handover preparation |
| --- | --- | --- |
| `STRATHMARK` | Independent calculation engine, reusable handicapped-event operations, standalone CLI, optional shared GUI | `adbf67a908946d3467db02e3472654c562170c45` |
| `Missoula-Pro-Am-Manager` | Working show application and continuous integration testbed | `3a61ec7e519744f90f3e80f1a95eaab526b34af0` |
| `STRATHEX` | Functional retro CLI/demo/reference client; also accesses the shared GUI | `4ab8b9a8630df1bb7de1da9a1ea6cddbfb73d2ff` |
| `mnemex` | Shared competitor identity, portable profiles, reconciled career records, and reviewed historical evidence | `207a3294576ec819416e4f4a70c4f078b4a3ae34` |

These are observation checkpoints, not instructions to reset a repository or freeze an old version. Fetch current refs, inspect open work, and reconcile changes before editing. The source references at the end are pinned to these checkpoints.

Do not modify unrelated repositories, undergraduate coursework, or invent another product from a dictated spelling. MNEMEX is the records/profile component discussed here. No second real tournament has been selected: use a plainly labeled synthetic show to prove reuse.

## 2. Approved product decisions — do not reopen

1. **Missoula is the testbed from the outset.** Integrate and test there incrementally, in parallel with preserving STRATHEX. Do not put Missoula behind completion of a separate demo-only project.
2. **Modularity applies to the whole design.** Different shows select supported events and configure rules, resources, divisions, scheduling, and presentation. They should not need forks of the underlying event behavior.
3. **STRATHMARK has two integration modes.** Calculation-only access remains independent; full delegation additionally manages handicapped-event preparation, judging, heats, and progression. Neither requires a particular GUI.
4. **A standalone STRATHMARK CLI is a deliverable.** It must support operator-supplied data and useful event operations, not just fixed synthetic examples. Preserve the existing STRATHEX terminal workflows and retro presentation as well.
5. **The graphical handicap workspace is shared and optional.** A host may open it, use its own GUI, or use a CLI against the same application operations. Do not build separate handicap implementations for each presentation.
6. **An event has one authoritative operational state.** CLI and GUI resume the same event and revision history. Begin with controlled editor handover, not competing copies of a competition.
7. **MNEMEX is the long-term person and career-record service.** Prepare its integration boundary now. Preserve existing authorized real-data inputs; full MNEMEX deployment is not a prerequisite to the first working integration.
8. **Hosted STRATHMARK may require internet initially.** Preserve supported local execution. This does not make live MNEMEX access a race-day requirement or authorize silent engine/runtime failover.
9. **Preserve Missoula's sporting requirements.** Generalization changes implementation boundaries, not the show's rules. Do not impose Missoula's special rules on every future show either.
10. **Prove reuse and recovery.** Run the component under Missoula and a second synthetic show without component source edits. Test restart, ambiguous saves, corrections, outages, and synchronization from the beginning.
11. **Separate numerical changes from extraction.** Preserve selected-engine behavior while moving boundaries. Reconcile numerical contradictions explicitly before authorizing the affected new official path.
12. **Update repository guidance, not just chat.** Record the current architecture and implementation status where the next agent can find them. Preserve historical decisions as history rather than erasing them or leaving them as competing current instructions.

The earlier verification-only handover's restrictions against new architecture and MNEMEX work are superseded **for this approved effort**. Its regression, data-isolation, recovery, and evidence requirements still apply. Reuse completed work instead of performing the old handover again blindly.

## 3. Starting facts and mandatory reconnaissance

The observations below describe the reviewed source, not a certification of deployed installations:

- The installed `strathmark` CLI currently accepts only `demo` and constructs two synthetic competitors. Full interactive tournament behavior is presently in STRATHEX. Implement the missing standalone CLI rather than claiming it already exists. [S1], [S7], [S8]
- Missoula has a retained embedded official-mark path and a separate remote shadow path. Shadow sheets are deliberately non-importable and cannot become official through ordinary review or issue. These are not the new delegated-event workflow. [S9], [S10]
- STRATHMARK has existing numerical and lifecycle capabilities, with explicit V2/V3 and installation distinctions. Reuse them. Current documentation still assigns much official workflow and human authorization to the consumer. [S3], [S4]
- STRATHEX's current contract includes direct Python, HTTP, local V3, engine locking, canonical Excel results, and local recovery. Preserve these supported distinctions; do not treat every API or installed package as interchangeable. [S7]
- MNEMEX has local identity/results/export foundations, but its README marks full show-portability adapters and production activation incomplete. Do not claim a live integration based on a schema or a simulated receiver. [S15]
- Missoula already has substantive synthetic recovery drills, including actual PostgreSQL/Gunicorn crash and restore scenarios. Extend them; do not replace them with mocks and call that equivalent. [S12]

### Read before making changes

Read the applicable `AGENTS.md`, contributor instructions, and nested instructions in every checkout. Then read:

**STRATHMARK:** `docs/wiki/Handicap-Mark-Math.md` in full; `ONBOARDING.md`; `README.md`; `docs/ARCHITECTURE.md`; relevant V2/V3 engine, deployment, consumer-migration, Linux runtime, and package-release documents. Inspect the current CLI, calculator, contracts, application services, persistence, and tests. [S1], [S2], [S3], [S4], [S5], [S6]

**Missoula:** `CLAUDE.md` in full; `docs/DOMAIN_CONTRACT.md`; `FlightLogic.md`; `docs/Alex's Docs/ProAM requirements`; applicable gear-sharing, relay, scoring, scheduling, wood, and event-format documents; `docs/MARK_ASSIGNMENT_WORKFLOW.md`; `docs/STRATHMARK_SHADOW_OPERATIONS.md`; `docs/RECOVERY_DRILLS.md`; rollback and current release documentation. Inspect actual implementation and tests, not just README summaries. [S9], [S10], [S11], [S12], [S13], [S14]

**STRATHEX:** `AGENTS.md`; `ONBOARDING.md`; `docs/CURRENT_RUNTIME_CONTRACT.md`; `docs/ARCHITECTURE.md`; current tournament and engine-selection guides; adapter, terminal, persistence, and replay code. Beware importing the legacy main program: startup can open operator data and enter menus. [S7], [S8]

**MNEMEX:** `AGENTS.md`; `CLAUDE.md`; `README.md`; the approved universal-profile architecture, build decisions, implementation plan, Results Desk/export status, and applicable activation/recovery instructions. [S15], [S16], [S17], [S18]

Inspect open PRs, branches, dependency pins, CI, and any changes since the checkpoints. Do not overwrite another agent's work. Establish a baseline before extraction and distinguish preexisting failures from new regressions. Do not label versioned V2 restrictions as universal V3 behavior.

The newest owner decision governs the approved product direction. Missoula's canonical domain contract governs existing show behavior unless the owner explicitly changes the sporting rule. Where those concern different layers, reconcile them rather than declaring one whole document obsolete.

## 4. Target ownership and integration boundaries

| Responsibility | Owning component |
| --- | --- |
| Permanent person identity, aliases, portable-profile permissions, reconciled cross-show career history and provenance | MNEMEX |
| Numerical predictions, supported wood interpretation, uncertainty, marks, model/engine identity, calculation evidence | STRATHMARK calculation layer |
| Fully delegated handicap-event operational state, fields, review, issue, results, corrections, advancement under the configured rules | STRATHMARK event-operations layer, acting for authorized show officials |
| Registration, entries, waivers, payments, overall program, flights, cross-event resources/rest constraints, tournament standings and payouts | Tournament host, initially Missoula |
| Terminal prompts, graphical forms, display, navigation, and launch behavior | Respective CLI/GUI client; no independent numerical or progression authority |

### Calculation-only versus full delegation

**Calculation-only:** the consumer owns its event workflow and requests predictions/marks through the supported API or library. A calculation response is not an official start authorization. Preserve this lightweight use case.

**Fully delegated:** the host creates/links an event managed by STRATHMARK. Authorized officials review, issue, record, advance, and correct through STRATHMARK operations, whether reached from its CLI, its GUI, or the host's GUI. Missoula displays and consumes accepted results; it must not independently recompute that event's official placing or progression.

Keep approval, issue, official result acceptance, publication, and payout settlement distinct. Software does not replace the organizer's rulemaking, judges, appeals, or permissions. A points or payout correction can require explicit action in the host after the delegated event's result is corrected.

### Event scheduling and resources

STRATHMARK manages the delegated event's fields and progression. Missoula still coordinates the whole show. Pass relevant capacity, gear-sharing, stand, handedness, and schedule constraints through the contract; STRATHMARK must not assume unlimited interchangeable stands or ignore conflicts with other events.

Agree exact heat membership and physical stands before calculating or issuing field-relative marks. A relevant roster, wood, or stand change must invalidate an unissued preparation through the documented revision mechanism. A mere edit-lock change must not masquerade as a changed physical field.

The module can publish next-round readiness and scheduling requirements. The host chooses where those rounds fit in the program. Do not autonomously reorder the entire show from inside STRATHMARK.

### Operational storage versus career storage

MNEMEX holding career records does not prohibit local operational storage, receipts, archives, or caches. It means there is one durable cross-show person/history authority, with explicit references back to the originating official records.

For an integrated event, designate the host as the default outward publisher to MNEMEX after it has accepted the module's official result revision. A standalone session must also have an explicit source-show/export identity. Preserve STRATHMARK's source references through the host. Do not send two unrelated versions of the same result from both applications.

Prediction settlement evidence and an official career result are different records. Do not use the shadow settlement outbox as a substitute for MNEMEX result publication.

## 5. Implementation shape and contracts

Use the leanest design compatible with the existing code. Keep reusable logic independent of Flask/Django requests, browser sessions, terminal prompts, and Missoula's ORM. Keep optional GUI/hosting dependencies out of calculation-only and CLI-only installations where practicable. Prefer existing frameworks and storage/transaction primitives over a new plugin framework, event bus, orchestration stack, or generic microservice rewrite.

A supported local adapter may call the same application operations directly. A hosted adapter may call them over the network. Select the transport and runtime explicitly. Neither UI may implement alternative marks, field validation, official completion calculations, or advancement logic.

Do not force Missoula's supported Python environment to import an incompatible V3 runtime. Inspect exact interpreter and source/contract requirements; use a tested service or process boundary where required. Package version, numeric engine version, model version, and consumer-contract version are distinct. [S3], [S6], [S7]

### Define a small, versioned event contract

Reuse existing compatible contracts. Add only the missing higher-level event boundary; do not casually alter frozen V2/V3 endpoints. Specify the following semantics before wiring clients:

| Contract area | Required contents/behavior |
| --- | --- |
| Identity | Show, tournament, event occurrence, round, heat, attempt, entry/competitor references; stable mapping to host-local records |
| Configuration | Discipline, format, wood species/diameter/quality with explicit unknowns, division rules, capacities/resources, progression and tie policy |
| Authority | Calculation-only or delegated mode, actor permissions, selected engine/runtime, rule-policy version, official-use eligibility |
| Evidence | Historical cutoff or supported round epoch, immutable input snapshot references, model/calibration/source identities |
| Commands | Stable request identity, expected event revision, canonical payload binding, explicit success/conflict/recovery outcomes |
| Results | Raw timer readings where required, raw cutting duration, start count, common-count completion, official position, non-finish status, result revision |
| Synchronization | Source result/revision, delivery identity, accepted/pending/conflicting state, corrections and voids without erasing prior history |
| Capabilities | Supported disciplines, formats, runtime/profile, commands, versions, and official-use limitations; unsupported combinations fail explicitly |

A single common-count completion convention must be explicit: start mark plus raw cutting duration. Never send an unlabeled `time` and require the receiver to guess which clock it represents. Preserve precision and units; follow Missoula's current dual-timer behavior where applicable. [S9], [S10]

Use stable identity references, not name matching, for consequential writes. Permit authorized display names in a workspace but keep sensitive profile data out of numerical evidence, logs, and model inputs. MNEMEX's internal person ID, show-scoped identity reference, and pseudonymous engine identity must not be collapsed into one publicly reusable key. [S16]

### Configurable events, not forks

Separate discipline, competition format, event parameters, and show-specific configuration. The initial example is **275 mm handicapped underhand**. This is a synthetic test configuration, not permission to change Missoula's actual configured block sizes or live event program.

A versioned configuration must govern qualifying places, number/capacity of heats, semifinals/finals, ties at advancement boundaries, scratches, non-finishes, and any authorized manual override. No arbitrary advancement based on alphabetical order or raw time where the rules do not permit it.

Keep the first event family bounded and fully working. Define a simple extension boundary for additional event families; do not attempt to rebuild all sporting disciplines before delivering the handicap integration.

### One event state through both interfaces

Create a persistent event identity and a controlled edit/handover mechanism. An interface change does not duplicate state, unlock the engine selection, lose receipts, or invalidate issued marks. Reject stale edits. Read-only views may coexist; initial mutating access must have one clear ownership/concurrency rule.

Implement the complete lifecycle: configuration and roster; preliminary forecasts when supported; exact fields; calculation; review; issue; complete outcomes; official result acceptance; advancement; later fields; finalization; correction; export/reconciliation. These are required semantics, not an instruction to replace existing state-machine names.

Keep model/evidence freezing consistent with the selected engine. Recalculate later fields from supported underlying evidence, not by copying independently rebased heat marks. A correction affecting a not-yet-issued next round must invalidate/review dependent preparation. Never silently rewrite already-issued or completed downstream races.

## 6. Preserve Missoula's domain behavior

Turn the current domain requirements into a regression checklist tied to tests before changing paths. At minimum preserve:

- Registration/import, event configuration, preflight, heats, flights, relay, spillover, dependent field-preparation recomputation, scoring, publication, and payouts in their documented sequence.
- Real reciprocal pairs; rejection of invalid/ambiguous partner declarations; dedicated Partnered Axe prelim/final behavior rather than generic heat treatment.
- Gear-sharing separation; resource capacity; springboard handedness; actual physical stands; dual-run stand changes and the documented college/pro distinctions.
- Saturday sequencing, Pro-Am Relay placement, mandatory closing spillover, ascending event heat sequence, and protection of completed scheduling history.
- Required entrants' complete results or explicit non-finishes; partial-timer review; best-run and cumulative scoring; ties; finalization and correction rules.
- Authentication, role and tournament scope, CSRF, durable accepted-request receipts, offline replay protections, reporting, and payout records.

The canonical contract specifically requires all Stock Saw to use physical stands 7 and 8 and identifies several older conflicting documents as stale. Preserve the current canonical rule, not the outdated wording. [S9]

Missoula must start and operate unrelated/non-handicapped events without STRATHMARK or MNEMEX configured. An unavailable managed-event dependency blocks the affected operation visibly, not the entire show. It must not cause a hidden local calculation fallback. Local registration and the existing authorized non-module workflows remain usable.

Host-local event summaries are not substitutes for round/heat history. Missoula's current `EventResult` uniqueness is per event/competitor/type; inspect the schema before mapping a multi-round delegated event. Do not overwrite qualifying results with final results merely to fit one summary row. Preserve every heat/attempt separately and derive the host's event-level summary. [S13]

New mode fields and mappings require proper additive migrations, defaults preserving old records, and database constraints. Do not merely repurpose `shadow`, overload unrelated JSON state, or silently convert all old `official` events.

## 7. Numerical policy: explicit reconciliation, not hidden changes

First capture synthetic reference outputs for the supported existing engines and profiles. Extraction should preserve their numerical results and evidence semantics. Do not modify the calculator to make an interface test easier.

Record and resolve these conflicts in a small numerical-policy section of the architecture agreement:

| Issue | Required treatment |
| --- | --- |
| Owner's project rule: minimum start count 3; whole-second marks; ceiling of predicted gap; maximum 180 | Preserve this as the target project rule requiring explicit treatment. Do not declare it obsolete because a later repository uses optimization. Preserve historical/versioned behavior until a separately identified policy change is implemented and tested. |
| Current mark documentation allows engine-specific optimization instead of universally requiring simple gaps | Identify the actual implemented policies and distinguish them from prediction/model choice. Do not silently replace a preserved optimizer or quietly market it as the original gap formula. [S5] |
| Missoula permits an explicitly reviewed zero-second mark on its retained path | This conflicts with the project's Mark-3 minimum for the target workflow. Preserve old records/old paths; never treat an unreviewed default zero as an intentional mark. New official policy must be explicit. [S9], [S10] |
| V2 does not numerically use wood quality | Display that limitation accurately; do not invent a quality multiplier inside Missoula or the GUI. Supported quality range and zero/poor-quality handling need explicit engine-policy validation. [S7] |
| V2 excludes same-day evidence; eligible V3 profiles support later-round learning | Preserve the selected profile's actual cutoff/epoch semantics. New results cannot change their own race or silently alter another field in the same frozen round. [S3], [S7] |
| Missoula's current authority contract excludes numeric LLM participation, while some V3 designs include a council | Keep current Missoula restrictions until an explicit compatible deployment/policy decision. Do not enable a council, change models, or remove qualification gates as an incidental integration change. [S3], [S9] |

The stated simple-gap rule is `3 + ceil(slowest_predicted_time - competitor_predicted_time)`. Same integer marks are allowed; display start sheets in ascending order. If that rule yields a value above the maximum, do not silently clip/compress marks and claim the rule was followed. Treat incompatible fields/policies as an explicit official-use blocker until their permitted handling is defined.

Capture known, unknown, and unsupported wood/context values without inventing predictive effect. Preserve the expectation that higher-quality wood represents softer/faster conditions where the selected model supports it. The older statement about both softer and firmer wood favoring the frontmarker is ambiguous; do not convert that wording into an unexplained numeric adjustment.

Proceed with the interface and modularity implementation while this reconciliation occurs. A working demonstration may disclose preserved-engine limitations. An affected new official workflow must not claim those requirements are satisfied until the corresponding policy tests and qualification pass. Track any remaining sporting-policy choice explicitly; it is not permission to stall all engineering or hide the conflict.

## 8. Execution sequence and deliverables

### Phase A — Baseline, architecture agreement, and compatibility map

1. Fetch all four repositories and inspect local state, open work, current CI, and deployment/publication triggers. Use clean worktrees/branches; preserve uncommitted owner work and comments.
2. Build a concise feature inventory: implemented, partial, missing, and blocked. Identify reusable services and tests before writing replacements.
3. Run appropriate isolated baseline checks and capture exact source, runtime, dependencies, commands, and failures.
4. Establish one canonical cross-repository architecture agreement. Prefer `STRATHMARK/docs/MODULAR_ECOSYSTEM.md` unless an existing suitable document already owns this purpose. Add short pointers in each repository rather than four drifting copies.
5. Keep one execution/status record in Missoula, preferably `docs/MODULAR_EXECUTION_STATUS.md`, linking evidence and cross-repository PRs. Record the compatibility matrix and numerical-policy inventory there or by a single linked section.
6. Reconcile the stale generic-platform retirement, delegated-event ownership, standalone CLI description, hosted/local deployment assumptions, and MNEMEX independence in current guidance. Mark historical material explicitly historical. [S16]

**Exit:** Clear boundaries, current baseline, and executable contract tests started. Do not stop after this documentation phase.

### Phase B — STRATHMARK application operations and standalone CLI

1. Reuse the numerical engine and existing lifecycle/storage capabilities. Extract only missing event-level coordination from consumers into a presentation-independent layer.
2. Implement the versioned calculation-only and delegated-event contracts, validation, revision checks, recoverable commands, persistence, and clean import boundaries.
3. Add a standalone CLI for supplied-data calculation and event create/open/status, prepare/calculate, review/issue, outcomes, advancement, correction, and export. Retain `strathmark demo` compatibility.
4. Offer readable plain-text operator output and structured machine-readable output where useful. An unsupported action must produce a useful failure, not a fabricated result. Keep command entrypoints thin; put behavior in library modules.
5. Test with authorized-input formats using synthetic fixtures. Do not require a live show database, real competitor data, hosted service, or GUI installation for the local smoke test.
6. Preserve immutable competition-root engine selection and inheritance. Never upgrade a saved event's engine/model merely because a package was upgraded.

**Exit:** A real event can be operated and resumed through the installed CLI, using actual engine execution on synthetic history, without importing Missoula or STRATHEX.

### Phase C — Missoula's opt-in integration, immediately alongside Phase B

1. Introduce an explicit managed-event integration mode and durable mappings, separate from retained official and shadow semantics.
2. Bind Missoula registrations/configured fields to the shared contract. Use stable identifiers, full context, and complete entrant accounting.
3. Add judge/admin navigation and event-status integration. Before the shared GUI exists, exercise the same operational integration through the available API/CLI and focused operator controls; do not defer Missoula integration until the demo is finished.
4. For delegated events, stop competing local mark assignment, scoring finalization, and advancement mutations. Keep required host scheduling, reporting, public views, standings, and payout derivations.
5. Accept official event-result revisions durably and update projections transactionally within Missoula. Make pending delivery/reconciliation visible. Preserve per-round attempts and source provenance.
6. Preserve existing legacy events, all unconverted features, domain requirements, offline protections, and missing-plugin usability. Test SQLite and the relevant PostgreSQL application paths.

**Exit:** The first synthetic handicapped event works through Missoula's normal show context, without embedded handicap computation on the delegated path.

### Phase D — Shared graphical workspace and STRATHEX parity

1. Build the reusable handicap-event GUI over the same operations. Do not build an entire replacement tournament GUI in this tranche.
2. Provide event/round/heat deep links, clear wood and roster context, mark review, issue confirmation, outcome entry, progression, correction, and sync status.
3. Preserve the retro CLI and existing STRATHEX features. Route newly delegated handicap behavior through the shared component, not a second private implementation. Add an explicit path to launch/resume the shared GUI.
4. Support moving between CLI and GUI against the same event/revisions. Test stale editor refusal and deliberate handover. No implicit state migration between separate local and remote authorities.
5. Add authenticated operator and show/event-scoped authorization using maintained mechanisms. Existing V3 service credentials grant broad service authority; they are not browser credentials and actor headers alone do not prove a person's permissions. [S3]
6. Do not expose secrets through launch URLs, browser storage, logs, or exports. Validate launch targets and origin/audience. Use a proper authenticated/scoped handoff; never make a public URL an authorization token by assumption.
7. Exercise actual browser behavior, including normal CSRF protection, keyboard use, field errors, printed start sheets, and returned errors. Runtime and eligibility restrictions must be identical in CLI and GUI.

**Exit:** The same event is usable through terminal, shared GUI, and Missoula integration without rule duplication. A host's own GUI remains a supported consumer of the operations API.

### Phase E — MNEMEX-facing boundary and real-data readiness

1. Reuse reviewed historical snapshot concepts and identity/revision contracts. Preserve explicit evidence cutoffs, eligibility, and privacy boundaries.
2. Implement and test the narrow adapter/export/reconciliation pieces needed for this event flow. Do not make full public profiles, provider deployment, or all historical migration prerequisites for this tranche.
3. Keep existing operator-supplied workbook/history inputs working behind their adapter. Do not put private workbooks in public fixtures, commits, screenshots, or build artifacts.
4. Build one source-attributed result/correction delivery path. Offline or unavailable MNEMEX leaves a durable pending item; it must not undo a valid event result or lose the correction.
5. Test duplicate, reordered, conflicting, unlinked-identity, and voided records. Preserve authorized stable mappings without auto-linking ambiguous names.
6. Label simulated receivers, explicit downloaded snapshots, implemented local adapters, and verified live integration accurately. Do not directly write into another component's database.

**Exit:** The identity/history/results boundary is implemented and tested to the extent supported by current MNEMEX code; any remaining receiver or activation gate is precisely recorded, not hidden by a mock.

### Phase F — Portability, failure recovery, and release hardening

1. Run one complete Missoula synthetic event and the same component under a second synthetic show profile without modifying component source or importing Missoula into STRATHMARK.
2. Include multiple qualifying heats and enough entrants for semifinals and final. Cover a tie at advancement, a scratch/non-finish, an issued sheet, a restart, and a result correction with downstream effects.
3. Extend the existing recovery suite and perform the acceptance checks below. Do not add publicly selectable crash endpoints or fault-injection headers.
4. Verify optional components can be absent. Validate the installed distribution outside the source checkout, CLI help and actual operation, GUI launch, schema migration, and compatibility with old data/saves.
5. Run cross-repository consumer tests against exact proposed producer artifacts/commits. Coordinate version and source pin changes; do not change every consumer to an untested `latest`.
6. Complete or verify the earlier prediction-evaluation release work described below. Reuse existing implementations and report what was already present instead of rebuilding it.

**Exit:** Reproducible functional/recovery evidence, with any blocked environment or qualification labeled accurately.

### Phase G — Merge, publish as authorized, and close out

1. Commit coherent slices with focused tests and human-readable explanations. Coordinate producer-first merges and tested consumer pins; use compatible additive contracts to avoid a half-upgraded deployed system.
2. Verify required checks on exact revisions. Do not merge a failing dependency chain or remove required checks to make it pass.
3. Follow STRATHMARK's existing package/release policy, including a fresh version when appropriate and verification of publication and installed artifacts. Never move an existing release tag or claim publication from a green source test alone. [S2], [S6]
4. Update maintained docs, relevant wiki source, and separately published wikis according to each repository's process; verify the remote result when publishing.
5. Keep new live-event activation explicit. A green CI run does not supply real signing keys, operator rehearsal, installed-model evidence, or provider restore qualification.
6. Leave the repository status record current, including exact implemented scope, commands, tests, PRs/commits, compatibility, and remaining gates. The final report must distinguish merged code, published packages, deployed services, and live official activation.

## 9. Required acceptance tests

These are implementation requirements, not more product decisions for Alex.

| Area | Required proof |
| --- | --- |
| Independent installation | STRATHMARK installs/runs without importing Missoula or STRATHEX; calculation/CLI paths do not require the GUI or MNEMEX. |
| Calculation-only integration | A plain client requests supported calculations without creating a managed tournament or granting official issue. |
| Event lifecycle | Complete preparation, review, issue, outcomes, semifinals/final, finalization, and correction against persistent state. |
| Interface parity | Equivalent CLI/API/GUI operations preserve numerical outputs, event revisions, selected engine, issued records, advancement, and official results. |
| Second show | A different synthetic configuration uses the same installed component with no source edits or Missoula imports; prove isolation, not only a changed logo. |
| Domain regressions | Missoula's canonical show sequence, partnerships, gear/resources, stands, flights/spillover, timers, scoring, reporting and payouts retain expected behavior. |
| Exact fields and history | Preparation binds the actual field; future/ineligible history is rejected according to the selected engine; marks are not copied between rebased fields. |
| Identity and privacy | Duplicate display names stay distinct; mismatched or unauthorized identifiers fail; numeric evidence excludes sensitive profile data; no cross-show leakage. |
| Authorized operation | Anonymous/wrong-role/wrong-show writes fail; CLI and GUI cannot bypass issue/finalization restrictions; normal CSRF protection remains enabled. |
| Concurrency and retries | Exact accepted retries return the original outcome; changed payloads conflict; stale UI or restored client state cannot overwrite a later correction. |
| Pre-commit crash | No half-written event, score, approval, result projection, or accepted-request receipt survives as success. |
| Post-commit response loss | Retry recovers committed state without duplicate issue, advancement, result acceptance, delivery, or payout effect. |
| Restart and restore | Restore into fresh isolated storage and resume; stale/corrupt/incompatible candidates are refused; old backups cannot silently create a second active authority. |
| Outages and optional modules | Unrelated events and local registration remain usable; affected managed operations fail visibly; accepted state is retained; there is no automatic engine/runtime fallback. |
| Results and MNEMEX boundary | Every heat/attempt survives; final summary is separate; duplicates/reordering/corrections/voids and receiver downtime have durable explicit outcomes. |
| Compatibility and release | Existing official/shadow events and STRATHEX saves retain authority; additive migrations and rollback compatibility work; installed artifacts match tested versions. |
| Prediction evaluation | Synthetic, historical, and prospective modes stay distinct; matched cohorts, availability, error/coverage metrics, and frozen-component requirements are reproducible and honestly reported. |

Include explicit tests for min/max/integer marks, ties, zero-versus-unreviewed values, raw duration versus common-count completion, and unsupported quality policies under each applicable version. A synthetic forecast fixture can test plumbing, but at least one end-to-end supported path must run the real numerical engine on synthetic evidence. Do not describe a stubbed calculator as end-to-end numerical proof.

### Preserve and extend the existing recovery program

The current Missoula runbook defines R01–R03 as the core and R04–R10 as extended scenarios. Keep their identity and baseline assertions. [S12]

- R01 fresh PostgreSQL restoration, R02 score pre-commit crash, R03 post-commit response loss.
- R04 database outage, R05 invalid/encrypted backup handling, R06 real browser offline replay, R07 worker crash/retry.
- R08 shadow-delivery durability, R09 compatible code/schema rollback, R10 SQLite restoration.

Add managed-event counterparts rather than relabeling R08 as proof of an official STRATHMARK or MNEMEX service. Its documented receiver is simulated. Test real supported cross-repository interfaces separately.

Do not conflate client internet loss, hosted STRATHMARK outage, operator-laptop loss, and MNEMEX unavailability. Their failure and recovery boundaries differ.

### Carry forward the original prediction-evaluation release

The earlier work also requested a reproducible STRATHMARK prediction-evaluation release. Include it in this effort; do not let the modularity work erase that obligation. First inspect what has already landed. The repository already has historical benchmark, accuracy-audit, prospective-freeze, and separate accuracy-preview machinery. Preserve and reuse those paths. [S19]

Provide three clearly distinguished modes: a reproducible **synthetic verification** run; an authorized, read-only **historical replay**; and **prospective evaluation** of genuinely later, previously unexamined competition groups. Supply documented commands and machine-readable plus readable reports. Synthetic correctness is not real-world accuracy, and repeatedly examined historical data is not an untouched prospective test.

Report evaluated/eligible/excluded counts with reasons, prediction availability and abstentions, MAE, median absolute error, tail errors, interval coverage **and width**, matched-baseline comparisons, and event/material/diameter/history-depth slices with their sample counts. Do not omit hard cases, compare different available subsets as though matched, or infer handicap fairness from cutting-time MAE alone. Actual field/issue/outcome evidence is needed for a fairness claim.

Preserve frozen protocol and model/Formula/source identities. The reviewed prospective protocol requires at least **100 later results from ten new competitions**; verify the current contract before execution. Missing future observations remain pending collection, not manufactured from the development cohort. Do not lower this threshold to get a green report. [S19]

A refactor may change implementation identity even when numerical outputs match. Retain the original frozen profile; do not rewrite its hashes, silently rebind it to the modularized code, or claim its prospective qualification transfers automatically. Establish a separately attributable comparison/protocol where required.

Keep the separate accuracy-preview program out of official competition selection. A better historical score, a working evaluator, or passing regression limits does not automatically promote a candidate, enable a council, or change issued marks. Private artifacts remain private. No additional training or private historical run is authorized merely by a code-change instruction.

**Acceptance:** Existing evaluation paths still reproduce their supported checks; a clean synthetic evaluation runs with documented commands; reports contain honest cohort/availability/metric distinctions; any private-data or genuinely future evaluation is explicitly marked unavailable/not run when its inputs are absent.

## 10. Outage and manual-continuation policy

For the initial hosted workflow, provide a deliberate director-controlled procedure:

- Retain an independently accessible issued start sheet and minimum event context before a heat starts. A sheet inaccessible behind the failed service is not an outage contingency.
- Already-issued heats may continue under the approved manual procedure. Record actual outcomes with their exact issued-sheet and field references, then reconcile them after recovery.
- Fields without valid issued sheets pause unless the director explicitly authorizes traditional/manual handicapping under the show's rules. Record that authority change; do not label manually assigned marks as engine-issued receipts.
- Do not run automatic cloud-to-local engine failover or create a parallel live event. Resume the original authority or complete an explicit, fenced recovery/authority-transfer procedure.
- Record what the system can and cannot do offline. A browser cache alone is not a durable, authenticated recovery plan.

Synthetic drills must prove the software side of this procedure. Do not claim that a generated runbook establishes independent human rehearsal or a live event's approved recovery objectives.

## 11. Data, test, and environment safety

Use isolated synthetic workbooks, explicitly unique temporary database paths, local disposable PostgreSQL, and dedicated test settings. Set STRATHMARK isolation variables before imports/test collection. MNEMEX tests must use their isolated settings and must not inherit hosted provider credentials. Follow each repo's stronger existing rules.

Do not test against `instance/proam.db`, the operator's actual workbook, live ResultStore, real MNEMEX data, existing production signing authority, or a hosted database merely because credentials are available. Do not execute the legacy STRATHEX startup in a test without isolating its paths. [S3], [S8], [S15]

Do not alter host services, terminate unrelated processes, prune containers, or delete databases by broad naming patterns. Reuse the owned-resource protections in the recovery lab. Missing namespaces, PostgreSQL tools, browser binaries, signing keys, models, or supported interpreters are explicit missing prerequisites, not reasons to fake a passing drill. [S12]

Keep secrets out of code, fixtures, command output, screenshots, and artifacts. Human-readable reports should reference redacted identities/digests, not private payloads.

Run tests in appropriately separated environments when interpreter/dependency requirements differ. Report the runtime and database actually tested. SQLite success is not PostgreSQL parity; synthetic Linux evidence is not designated Windows qualification; no hosted provider test means no hosted provider claim.

## 12. Documentation reconciliation and numerical release boundaries

Update current instructions where the new architecture changes responsibility. Do not merely add a new design document while old `AGENTS.md`, `CLAUDE.md`, README, wiki, or contract text still tells agents to implement the opposite boundary.

The important reconciliations are:

1. **Generic platform retirement:** preserve the historical warning against speculative wholesale rebuilding, but explicitly reaffirm reusable multi-show components and incremental Missoula-led generalization. [S16]
2. **Official-event ownership:** distinguish calculation-only consumer authority from delegated-event operations. The latter belongs to the shared component acting for authorized officials, while the host retains whole-show responsibilities. [S4], [S9]
3. **Hosted versus local:** permit the approved hosted STRATHMARK profile without erasing supported local CLI behavior or making MNEMEX a race-day dependency. [S7], [S16]
4. **CLI and GUI:** identify which commands/workspaces actually exist, which are installed, and which profiles they support. A browser launcher or synthetic demo alone is not the completed CLI/event workflow. [S1]
5. **Numerical scope:** preserve accurate version-specific quality, cutoff, optimization, council, and eligibility statements. Do not treat documentation wording as a substitute for validated numerical behavior.

Use concise, human-readable current-state prose. Keep the cross-repository authority and evidence map centralized. Do not turn every user-guide paragraph into a chain of approval IDs. Preserve the owner's comments and established code documentation style.

## 13. Completion standard and final report

The intended first functional proof is:

> A configurable handicapped event operates in Missoula through the reusable STRATHMARK component; the same event is accessible through CLI and the optional shared GUI; qualifying heats progress through semifinals to a final; the workflow survives restart and a correction; the identical component works under a second synthetic show configuration; results/history interfaces are ready for MNEMEX without requiring it live during competition.

Do not call this complete based solely on schemas, documentation, a new screen, fake successful calls, one happy-path demo, or a package that only works from its source checkout.

At closeout report, compactly:

| Item | Report exactly |
| --- | --- |
| Implemented | Working features by repository; actual commands and launch paths |
| Verification | Exact commands, runtimes, database engines, source/artifact identities, pass/fail/blocked/not-run results |
| Repository delivery | Branches, commits, PRs, merge state, producer/consumer pins |
| Operational state | Published package versus deployed service versus official-use activation |
| Remaining work | Specific unfinished functionality or external/numerical/qualification gates, with next executable step |

Use distinct statuses: `IMPLEMENTED`, `VERIFIED`, `MERGED`, `PUBLISHED`, `DEPLOYED`, `OFFICIAL-USE ENABLED`, and `BLOCKED`. Do not substitute one for another.

Do not claim to continue unattended work after the active Codex session ends. If execution is interrupted, commit a coherent safe checkpoint when appropriate and update the status record with exact resumption instructions. Do not mark unfinished work complete to close the task.

## 14. Source references and evidence limits

The links below establish the observed starting state. Refresh current repository contents before changing them; the handover is not a substitute for reading current code and instructions. No application, deployment, or test was run to prepare this handover. The visible preceding conversation contains repository reads, not verified implementation of this plan.

[S1]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/strathmark/cli.py
[S2]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/AGENTS.md
[S3]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/ONBOARDING.md
[S4]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/docs/ARCHITECTURE.md
[S5]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/docs/wiki/Handicap-Mark-Math.md
[S6]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/pyproject.toml
[S7]: https://github.com/SquirmyWormy275/STRATHEX/blob/4ab8b9a8630df1bb7de1da9a1ea6cddbfb73d2ff/docs/CURRENT_RUNTIME_CONTRACT.md
[S8]: https://github.com/SquirmyWormy275/STRATHEX/blob/4ab8b9a8630df1bb7de1da9a1ea6cddbfb73d2ff/AGENTS.md
[S9]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/docs/DOMAIN_CONTRACT.md
[S10]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/docs/MARK_ASSIGNMENT_WORKFLOW.md
[S11]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/CLAUDE.md
[S12]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/docs/RECOVERY_DRILLS.md
[S13]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/models/event.py
[S14]: https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/blob/3a61ec7e519744f90f3e80f1a95eaab526b34af0/config.py
[S15]: https://github.com/SquirmyWormy275/mnemex/blob/207a3294576ec819416e4f4a70c4f078b4a3ae34/README.md
[S16]: https://github.com/SquirmyWormy275/mnemex/blob/207a3294576ec819416e4f4a70c4f078b4a3ae34/docs/plans/2026-08-14-mnemex-universal-profile-architecture.md
[S17]: https://github.com/SquirmyWormy275/mnemex/blob/207a3294576ec819416e4f4a70c4f078b4a3ae34/docs/plans/2026-08-14-mnemex-approved-build-decisions.md
[S18]: https://github.com/SquirmyWormy275/mnemex/blob/207a3294576ec819416e4f4a70c4f078b4a3ae34/docs/plans/2026-08-14-mnemex-approved-implementation-plan.md
[S19]: https://github.com/SquirmyWormy275/STRATHMARK/blob/adbf67a908946d3467db02e3472654c562170c45/docs/ACCURACY_AND_COUNCIL.md

### Source index

- [S1] STRATHMARK's currently limited installed CLI.
- [S2] STRATHMARK agent and automatic publication instructions.
- [S3] Engine/runtime, test isolation, and qualification boundaries.
- [S4] Existing STRATHMARK architecture and official-system boundary.
- [S5] Mark meaning, both clocks, rebasing, and engine-specific optimization.
- [S6] Package metadata, extras, and executable entry points.
- [S7] STRATHEX's current runtime, quality limitations, selection, transport, and persistence.
- [S8] STRATHEX contributor rules and startup/data safeguards.
- [S9] Missoula's canonical sporting and operational contract.
- [S10] Retained official versus scoring-inert shadow workflows.
- [S11] Missoula identity, implementation map, and contributor instructions.
- [S12] Existing concrete recovery drills and their limitations.
- [S13] Current event/result schema and uniqueness boundaries.
- [S14] Current show/event/resource configuration.
- [S15] MNEMEX's implemented versus planned capabilities.
- [S16] Profile/history authority, race-day independence, and conflicting retirement wording.
- [S17] Approved multi-show MNEMEX build decisions.
- [S18] MNEMEX implementation phases and modular-monolith direction.
- [S19] Existing evaluation machinery, preview separation, and prospective minimum cohort.

**Begin with Phase A, then implement the working component and Missoula integration. Keep the owner-facing summary brief and the repository execution record precise.**
