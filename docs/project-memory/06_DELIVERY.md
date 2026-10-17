# Delivery, evidence and remaining qualification

Sources: [S01](SOURCE_INDEX.md#s01), [S07](SOURCE_INDEX.md#s07),
[S18](SOURCE_INDEX.md#s18), [S19](SOURCE_INDEX.md#s19),
[E01–E10](SOURCE_INDEX.md#e01). This is a dated delivery ledger. The structured
[delivery snapshot](DELIVERY_SNAPSHOT.json) preserves repository and artifact
metadata. A passing source checkpoint does not confer a pass on a later commit.

## What the October implementation actually delivered

Reusable operations are implemented in STRATHMARK, separate from its numerical
engines. They support operator-supplied event configuration, durable revisions,
forecast, fields, review, issue, outcomes, judge acceptance, progression, finals,
corrections, export and controlled editor handover. The standalone CLI and optional
authenticated GUI call the same operations. Missoula uses the real installed
component from its existing host runtime through a separate interpreter. STRATHEX
has an explicit managed mode while retaining its working retro CLI. MNEMEX has a
real authenticated sandbox source-result receiver. Synthetic portability,
crash/recovery and evaluation were executed, not just described.

| Repository | Application delivery checkpoint | Process/evidence |
| --- | --- | --- |
| STRATHMARK | Main `f184e9f2e110bd01d5fec2abd2ef1bfe6f22e214` | [PR 35](https://github.com/SquirmyWormy275/STRATHMARK/pull/35) merged; 25 PR checks; [main CI](https://github.com/SquirmyWormy275/STRATHMARK/actions/runs/38881349305) attempt 2 passed |
| STRATHEX | Main `bcfe4e50e1449b2585a037215c79f5a7e955e9da`, version 7.4.3 | [PR 34](https://github.com/SquirmyWormy275/STRATHEX/pull/34) merged; 11 PR checks; [main CI](https://github.com/SquirmyWormy275/STRATHEX/actions/runs/38885236056) passed |
| MNEMEX | Main `7a315946c92e24a125fc213c7d139eef6278f12c` | PRs [5](https://github.com/SquirmyWormy275/mnemex/pull/5), [6](https://github.com/SquirmyWormy275/mnemex/pull/6), [7](https://github.com/SquirmyWormy275/mnemex/pull/7) merged; Linux/Windows checks; [main CI](https://github.com/SquirmyWormy275/mnemex/actions/runs/38883117831) passed |
| Missoula | Draft [PR 125](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/pull/125), feature/modular-events-20261015 | Implementation pushed; merge held by the hosted backup and independent recovery-key proofs below |

The separate project-memory documentation branch and PR have their own final
Git/CI record. Refresh current refs to discover any later merges; the table is
not an instruction to reset a newer checkout.

## Published producer and installed reuse

`3.0.0rc11` is an actual PyPI release and GitHub prerelease
[v3.0.0rc11](https://github.com/SquirmyWormy275/STRATHMARK/releases/tag/v3.0.0rc11),
not a stable/production-qualification declaration. Tags `v3.0.0rc11` and
`pypi-v3.0.0rc11` target the application merge above. All six publication jobs
passed in [run 38884204894](https://github.com/SquirmyWormy275/STRATHMARK/actions/runs/38884204894).

| Artifact | SHA-256 |
| --- | --- |
| Wheel | `7151e43e6126d704fd09b634b82c20e08cc32b74580b2feb7613e380be45fdcd` |
| Source distribution | `2f9fecc63c287ce0e69c88059c449bfd8fe0915a71a8fde27ee68bee209bcbfe` |

An indexed, fresh core-only Python 3.13.15 environment with NumPy 2.5.4 and pandas
3.0.6 completed the CLI lifecycle for two supplied synthetic shows, including
correction, final reacceptance and export. It did not import Flask, MNEMEX or
STRATHEX. Shared-GUI browser report E03 has eleven passing checks; the directory
name `browser-workspace-9` is a run label, not the check count. The Python versions
and package digests are evidence inputs, not an instruction to silently upgrade
retained host dependencies.

Producer full-suite evidence was 3,242 passed / 47 optional skips, plus 29 focused
review regressions. STRATHEX had 381 passing tests and installed retro/managed
checks. MNEMEX had 638 passed / 53 optional skips and 19 owned PostgreSQL checks.
These are stage-specific receipts, not guaranteed counts for every future revision.

STRATHMARK's wiki was published at `bea618007ef72b465bfe9a8c0a487a5ed847e414`;
STRATHEX's at `43197c198b7282fad551c3a6da2a76ece1c76dd3`. Repository documentation
and exact profile contracts still govern eligibility.

## Memory delivery and the observed dependency change

Memory PR [8](https://github.com/SquirmyWormy275/mnemex/pull/8) adds the portable
handoff and standalone retrieval utility. Initial [CI 38984576046](https://github.com/SquirmyWormy275/mnemex/actions/runs/38984576046)
passed memory verification but failed four existing MFA enrollment tests on both
platforms after resolving newly released `django-allauth==65.20.0`. Isolated
application main 7a31594 reproduced the same four failures (27 passed, one skipped).
The [upstream release](https://allauth.org/news/2026/10/django-allauth-65.20.0-released/)
requires explicit reauthentication for protected views even after a recent login.

Tests now perform the real password confirmation before enrollment; application
security settings, privileges, encryption and assertions are unchanged. A new
security regression proves a wrong password discloses no enrollment secret.
MFA tests pass with both 65.19.7 and 65.20.0. The full local 65.20 suite passes
659 tests with 53 existing optional skips. The memory utility's twenty tests
include three additional reproduced review fixes: exactly one catalogue entry
per snapshot, status/source IDs in plain search, and portability through symlinked
ancestors while still rejecting symlinks inside the pack. Final CI/review remain
bound to the actual PR head; the initial failed run is preserved.

## Missoula exact checkpoints and honest review history

At source `47f9bb558816e07f35d2c54f3ed4454f0c6fc21e`, [CI 38897926622](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/actions/runs/38897926622)
passed all eight applicable jobs. Production `tournament-audit` was skipped.
Installed integration had 49 passing tests with no skips; recovery core R01–R03
had 90 passing checks; installed CLI R11 had seven checks; source acceptance-crash
R12 had thirteen. All reported owned cleanup passed. The synthetic GitHub merge
checkout was `bc89099c97a01c6a682b34ac8f1cd0ae3b75acee`, with parents the then-main
and the exact feature head. The report's dirty flag was solely generated
`managed-results.xml`; its collector evidence hash was
`e16f71a453059345780a389693645fcaef474bf4a575f9b6f148b74dea29b8d5`.

At that checkpoint review had no findings and eighteen earlier threads were
resolved. Later documentation commit `70109349dc668a73b30f1cd48fc33b201ab2375c`
passed all eight applicable jobs in [CI 38982953991](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/actions/runs/38982953991).
Its fresh review nevertheless identified three additional host consistency defects:
post-acceptance roster changes before awards, ghost pending result rows after an
unissued roster shrink, and wood-only shared-editor changes bypassing projection
validation. They were treated as implementation defects and reproduced in real
installed-component tests. Later checkpoint details are recorded in the delivery
snapshot/current PR and the follow-up record below; an earlier clean review is
not evidence that those defects never existed.

The earlier whole R01–R12 run had 197 passing checks and cleanup. Later stronger
R11 exercised two installed CLI shows, corrections and sixteen source revisions /
eight summaries. Clean application source `0727e9b63cdaaeb7ac994f5729d82b8114456d7d`
had fresh R09 and R12, thirteen checks each. E04–E08 preserve normalized recovery
receipts with original receipt hashes, source identity and cleanup outcomes.
Normalization excludes HTTP bodies, transient cookies and form/session material.

Retain failures as well as passes. Producer main attempt 1 hit an existing 100 ms
preflight/admission shadow timeout race; diagnostic repeats and 56 relevant tests
passed before the successful rerun, without loosening thresholds. Missoula run
38897053396 exposed a legacy return-dictionary shape regression and was cancelled
by the corrected head; the two-line compatibility correction and focused tests
are recorded in S18. A lost early baseline receipt is explicitly not counted as
a passing baseline. Do not manufacture a green history by deleting these records.

## Follow-up implementation checkpoint

Application source `62216f492facd3691293bd52d0d3884fe20974c1` fixes the three
additional findings. Awards now recheck current host registration/wood/profile;
unissued roster shrink removes only empty pending placeholders and refuses
recorded history, including a zero timer; every projected source configuration
validates fresh show wood/resources. Five installed-component regression cases
first failed for these defects, then passed. Initial RED runs also exposed test
fixture identity/envelope errors; those are retained and distinguished from actual
defect reproductions in the host execution record.

The focused suite passes 159 SQLite and 96 owned PostgreSQL tests, no skips;
PostgreSQL cleanup passes. Fresh R09 and R12 at the clean committed source each
pass thirteen checks with cleanup. All three follow-up review threads were
resolved with these fixes. [CI 38984242587](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/actions/runs/38984242587)
and the new review have their own exact-head status; consult the current delivery
snapshot/PR rather than inheriting an earlier green claim. The post-review
[verification comment](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/pull/125#issuecomment-6227013146)
records the local proof and unchanged merge hold.

## The gate preventing Missoula merge

The branch changes daily-backup's expected Alembic head from `a6b7c8d9e0f1` to
`a6d6dda4e480`. The [host release checklist](snapshots/Missoula-Pro-Am-Manager/docs/RELEASE_CHECKLIST.md#hosted-backup-restore-proof)
requires an exact-current-branch hosted read-only dump, runner-local restore and
encrypted artifact proof, plus a separately held approved recovery identity's
decryption/disposable restore rehearsal by the designated operator. Static
validation, a synthetic age proof, CI or possession of credentials cannot substitute.

These proofs have not been run. They touch operational data/key custody and were
not authorized merely by the implementation handover. Do not dispatch production
backup/audit workflows, bypass the gate, remove the head pin, or merge the green
draft. Missoula main automatically deploys on Railway and runs `flask db upgrade`.
When the required authorized operators and proofs exist, revalidate the exact
current head, resolve review, follow the repository squash process, and then
perform the documented commit/version/migration/deployment checks.

Actual Railway deployment verification, authenticated judge and tournament-bound
spectator checks are NOT_RUN for this branch. Production managed activation stays
hard-disabled. These are precise outstanding operational gates, not missing code
scaffolding and not permission to access production now.

## Evaluation and portability limits

The synthetic evaluation ran the packaged real V2 predictor with eight cases and
four matched outcome sets; E02/04_NUMERICS distinguish those receipts from model
accuracy claims. No private historical training or private-history run was done.
The prospective program still needs 100 genuinely later unexamined observations
from ten new competitions using its original frozen rc6 artifacts. That program
remains blocked pending real observations; rc11 results cannot be rebound to it.

Linux/source acceptance and owned PostgreSQL cleanup do not establish Windows
CNG/full V3 factory qualification, shared-database distributed fencing, another
real show's adapter, full MNEMEX profile portability or provider activation.
