# Resume safely in another harness

Read [START_HERE](START_HERE.md), current repository instructions and the
[decision register](DECISIONS.md). These commands are reproducible entry points,
not permission to run production operations. Source procedures and their current
versions govern the details. Sources: S01, S04, S06, S17–S27, S31–S36.

## First ten minutes

1. Clone or locate all four repositories. Record `git status --short`, current
   branch, `git rev-parse HEAD`, remote URL and current instructions. Preserve
   uncommitted work and operator data. Fetch remotes without resetting a checkout.
2. Read current open PRs and their exact-head checks/reviews. Compare with
   [delivery](06_DELIVERY.md); do not reopen already merged implementation or
   turn selected choices into another decision questionnaire.
3. Create an isolated worktree/branch for new changes. Use isolated virtual
   environments and temporary synthetic storage **before importing** legacy
   runtimes. Read STRATHEX ONBOARDING and the runtime contract before startup.
4. Choose the numerical and operational profile explicitly. Write down root,
   engine/runtime, mark policy, version/digest, synthetic/live status, selected
   publisher and the source of evidence. Never select a fallback after failure.
5. Run the appropriate isolated baseline. Verify the installed wheel outside the
   producer checkout for cross-repository tests. Record source hashes, command,
   environment, result, skip reasons and owned cleanup.

Repository remotes are `https://github.com/SquirmyWormy275/` plus `STRATHMARK`,
`STRATHEX`, `Missoula-Pro-Am-Manager`, `mnemex`. The October execution workspace was
`/home/kingoftheeast/Repo-Updates/modular-tournament-20261015`. Its `evidence/`
contains larger logs/JUnit/ownership records; the portable memory stores selected
safe receipts and source hashes. A new machine need not recreate these absolute
paths. Missing local receipts must remain missing, not be silently fabricated.

Before the blocked Missoula merge, PR 125's current
`feature/modular-events-20261015` head contains the integration; deployed `main`
does not. Read that feature's current contracts/tests and base a continuation
on its current fetched head. Absence of managed code on production main is not
evidence that the implementation was never delivered. The first three shared
application repositories are already merged; start their new work from current
main while preserving each exact application/release checkpoint.

## Installed component and supplied input

Choose a fresh Python environment compatible with the producer package. For the
October pinned reproduction, install `strathmark==3.0.0rc11` explicitly, check its
wheel hash against delivery and run `strathmark capabilities`. For an optional
GUI install the documented workspace extra in that producer environment. Do not
add the producer's Python/NumPy/pandas stack to Missoula's retained Python 3.10 /
legacy 2.x environment or rewrite its dependency pin to force compatibility.

```text
strathmark capabilities
strathmark example --output /private/new-event.json
strathmark event create --database /private/operations.sqlite3 --show synthetic:demo --request-id create-demo-1 --input /private/new-event.json
strathmark event status --database /private/operations.sqlite3 --show synthetic:demo --event-id synthetic:demo:underhand
strathmark calculate --input /private/request.json --json
```

The example is labeled synthetic; edit its show/event IDs and all required
configuration coherently before creation. Consult current CLI `--help` and S06
for exact operation flags. The full config contains roster stable IDs and history,
wood/discipline, exact prediction cutoff, engine/policy, stands/gear, timers,
round rules and selected publication owner. User input is not a Python expression
or a path to execute. A CLI request uses supplied data and does not require Flask,
MNEMEX or STRATHEX. The example generator is a convenience, not the only workflow.

Before every state-changing operation, inspect the current revision/editor and
retain a unique request ID plus exact payload. On a lost response retry that
identity; do not invent a new operation to work around ambiguity. Use explicit
handover to move between CLI/host/GUI. Calculation/forecast alone does not issue.
Review exact sheet bytes/digest, explicitly issue, collect source-linked outcomes,
judge-accept and progress. A correction creates a new immutable revision and
requires fresh final acceptance/export/host reconciliation as applicable.

## Shared GUI

```text
strathmark workspace-account --auth-file /private/accounts.json --actor director --show synthetic:demo
strathmark workspace-key --session-key-file /private/session.key
strathmark workspace --database /private/operations.sqlite3 --auth-file /private/accounts.json --session-key-file /private/session.key
```

Passwords are prompted; never commit account/session-key files. The workspace
binds loopback by default on port 8789 with scoped accounts, CSRF and signed
sessions. Use a supported authenticated/secure deployment procedure before any
network exposure. A GUI account does not alter numerical eligibility. STRATHEX's
managed delegation flags must precede its remainder arguments; use its current
S25 guide and `--help`. Legacy entry without managed flags keeps the retro path.

## Missoula adapter workflow

Use synthetic test configuration with the explicit separate producer interpreter
and a new owned authority database. ProductionConfig forces managed off. A fresh
single-run individual SB/UH handicap event is eligible for this bounded test;
existing heats/results, partnered/dual/triple modes, shadow authority or live
configuration refuse binding. Configure actual show wood, all active entrants,
valid gear declarations and physical stands first.

Host creates durable command intent before sending to the source. If creation is
uncertain, recover its original actor/request/config receipt. A second candidate
must not replace a successful source create. Read latest source state and recover
host projection after transport failure. Projection advances monotonically under
the tournament/event locks. Resolve host flight placements explicitly before
replacing an unissued field; issued/started/completed history is never erased.

Host scheduling owns whole-show order. Shared operations do not start or reorder
a whole flight. Managed fields enter existing Heat/HeatAssignment scheduling.
Legacy gear repair, scratch and registration deletion paths protect delegated
state. A source configuration cannot silently change the show's timer/wood/roster
or physical resources.

Accept a current source export atomically under a source fence that remains held
through the host transaction's actual commit. Acceptance stores attempts, durable
career deliveries, summary projection and receipt together. Then explicitly apply
host awards using the accepted current finalized summary and current host facts.
Payout settlement remains a separate organizer action. A nonfinal correction
reopens host finalization; previously recorded awards remain until deliberate
reconciliation. Bulk awards acquire one batch source guard before host locks.
Do not simulate distributed hosted qualification from the local SQLite fence.

Deliver bounded career messages only to an explicitly configured sandbox MNEMEX
receiver using a registered scoped credential. Outage is queued/retryable;
committed-response loss returns the same receipt. A 409 or changed source revision
is evidence to reconcile, not a reason to overwrite or auto-link a person.

## Meaningful verification for changes

| Area changed | Minimum relevant verification |
| --- | --- |
| Numerical profile or policy | Exact engine/version eligibility, field-relative math, cutoff/evidence leakage, policy boundary, no-fallback behavior and installed package |
| Shared operations/GUI | Revision/request conflicts, handover, review/issue, progression/correction/export, independent installed CLI; authenticated GUI workflow when changed |
| Host adapter | Real installed producer + real MNEMEX receiver, fresh migrated SQLite and owned PostgreSQL, sporting-rule regressions, actual transaction/failure races |
| Schema/recovery | Clean migrations/drift checks, owned recovery drills with source head and cleanup, applicable release gates |
| MNEMEX contracts | Scoped credential/source ownership, correction order, conflict/idempotency/provenance and Linux/Windows tests; owned PG when transaction behavior changes |
| Memory/docs | Dependency-free verify, retrieval smoke and meaningful integrity tests; confirm source dates/status and current instructions |

Recovery scenarios R01–R12 are defined in S21. R09 covers code/schema rollback,
R11 installed component portability and R12 managed source/acceptance crashes.
Use `scripts/recovery_drills.py --help` and a fresh owned output directory;
PostgreSQL runs use unprivileged user/network namespaces and disposable resources.
Record both checks and cleanup. A synthetic restore is evidence about its exact
lab, not a substitute for hosted backup/key proofs. Do not run drills against an
operational database because a credential happens to be available.

## Repository delivery and the next permitted steps

Commit coherent verified changes, push feature branches, use repository PR checks
and review, and merge through its permitted process. Do not force-push, bypass
protection or erase failed evidence. STRATHMARK publication follows S07; merged
code and an available release artifact are separate states. Read existing wiki
publication instructions when its public workflow changes.

Missoula PR 125 remains draft until S19's exact hosted backup/restore and
independent key-recovery proofs exist. Do not merge while those gates are absent.
After an authorized merge, verify Railway's actual revision/version, Alembic head,
logs and authenticated judge/tournament-scoped spectator behavior. None of those
production post-merge checks has been performed for this feature.

Future MNEMEX work proceeds through the approved plan, preserving all twelve D0
choices. Full portable profiles and the fourteen hosted activation gates remain
separate from the already implemented source-result inbox. Request only truly
missing provider/operator/jurisdiction inputs at the point needed, not a new
architecture approval round. Do useful isolated implementation while a distinct
external gate remains pending.
