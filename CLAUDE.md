# Working in MNEMEX

Begin with the owner-requested, model-neutral
[project memory](docs/project-memory/START_HERE.md) for the ecosystem direction,
settled decisions, domain/numerical rules, delivery evidence and next actions.
`python tools/project_memory.py verify` checks its inventory; `search` and
`context --topic resume` work offline without Django or a model provider.
The pack is technical repository memory; it is separate from person/career
data and does not override current user or repository instructions.

The October 15 approved modular effort adds a bounded
[synthetic show-result inbox](docs/SHOW_RESULT_CONTRACT.md). It preserves
unlinked source attempts and explicit receipts without enabling full profile
portability or production. Shared components are developed incrementally with
Missoula as the integration testbed; the historical warning against speculative
wholesale platform replacement does not prohibit this approved work.


MNEMEX is the STRATHEX ecosystem's universal competitor identity, portable-profile,
career-history and provenance service. Its integrated Results Desk preserves and
reconciles source results. This repository is `SquirmyWormy275/mnemex`.

## Read these first

1. [README.md](README.md): implemented behavior, local checks and remaining scope.
2. [Approved architecture](docs/plans/2026-08-14-mnemex-universal-profile-architecture.md).
3. [Approved build decisions](docs/plans/2026-08-14-mnemex-approved-build-decisions.md).
4. [Implementation plan](docs/plans/2026-08-14-mnemex-approved-implementation-plan.md)
   and the status records linked from the README for the area being changed.

The August 14 decisions supersede the earlier historical-only scraper proposal,
JSONL/git store and static archive deployment plan. The May design document,
legacy Supabase runbooks and milestone backlog in `TODOS.md` are historical
context, not authority to replace the Django application or reopen settled
product choices. Preserve them with their dates.

## Ownership and trust boundaries

- MNEMEX owns the person, aliases, encrypted legal identity, consent grants,
  reconciled career record and provenance chain.
- A show owns registration, entries, waivers, partners, payments and whole-show
  scheduling. For calculation-only events it owns marks/results; for explicitly
  delegated events STRATHMARK operations own fields, marks, results and progression
  on behalf of its authorized officials. The host accepts source revisions and
  retains points/payout authority. MNEMEX does
  not score an event or decide its winner.
- Before roster lock, a show may validate a consented, purpose-bounded profile
  projection. At lock it pins a local snapshot; race-day operation must not
  depend on a live MNEMEX connection. Show adapters remain planned.
- Deterministic-valid source rows publish to the private archive automatically;
  invalid or conflicting rows are quarantined. Publication does not grant a
  trusted identity link, public career status or export eligibility.
- Identity reconciliation, public opt-in and STRATHMARK export eligibility are
  separate review/consent states. Do not promote one by changing another.
- STRATHMARK explicitly imports an immutable, human-reviewed, pseudonymous
  **prior SB/UH evidence snapshot through its 2.x contract**. MNEMEX never writes
  directly to STRATHMARK's database. Broad archived disciplines do not widen
  that export contract.

## Implementation

Extend the existing Django 5.2 LTS modular monolith and its account, people,
consent, results, migration, career, export, recovery and activation services.
Use maintained authentication primitives and existing versioned encryption/key
services. Preserve tenant scope, idempotency, exact source digests, append-only
corrections, fenced worker leases and private-artifact recovery.

Legacy scraper/CLI/Supabase modules remain for compatibility. Do not use them as
an alternate authority, bypass Results Desk validation or restore the retired
scheduled Supabase-to-JSONL production workflow.

Treat source files and extraction responses as untrusted inputs. Keep originals
and their provenance; never invent results, silently reconcile an ambiguous
person or fill missing source values to obtain export eligibility.

## Local verification and CI

Use synthetic fixtures and isolated test settings. From an activated virtual
environment, the following commands work in PowerShell or a Linux shell:

```text
python -m pip install -e ".[dev,strathmark]"
python manage.py check --settings=mnemex.web.settings.test
python manage.py makemigrations --check --dry-run --settings=mnemex.web.settings.test
python -m pytest -q -p no:cacheprovider
```

The `strathmark` extra installs the supported 2.x library for contract tests.
When testing an unpublished sibling change, install that checkout explicitly
and report its revision. Do not silently substitute V3.

`pyproject.toml` selects `mnemex.web.settings.test` for pytest. Tests use in-memory
SQLite by default and ignore production `DATABASE_URL`/Supabase credentials.
An optional `MNEMEX_TEST_DATABASE_URL` must name a disposable local database
containing `test`; remote hosts and non-test names are rejected. Supabase
integration tests are separately gated by `MNEMEX_TEST_SUPABASE=1` and require
loopback test services. Vision-provider tests are optional and must not call
paid or live providers in default CI.

[CI](.github/workflows/ci.yml) runs Django system checks, migration-drift checks
and the existing synthetic pytest suite on Linux and Windows. It does not run
the legacy export, provision providers, deploy the application or establish
production activation evidence. Optional/provider tests retain their skips;
report executed, skipped and failed checks separately.

Keep CLI output plain and useful: errors identify the affected input and the
next action. Follow the existing schema's compatibility rules; do not rename
or remove persisted enum values without an explicit migration.

## Contributor workflow

Keep the existing gstack and Superpowers workflow conventions. gstack supplies
plan reviews, `/review`, browser `/qa`, branch finishing through `/ship`, and
`/retro`. For multi-file features, refactors and new modules, use the
Superpowers brainstorming, writing-plans and executing-plans workflow with TDD.
Quick maintenance fixes use the direct gstack review workflow. Codex QA remains
the independent QA layer after `/review`.

These review tools do not supersede the approved architecture or reopen settled
product decisions. Check the branch before release/deploy commands, preserve
user changes and report the commands and verification actually performed.
When investigating unexpected Python imports, check stale bytecode before
changing source that already matches the approved behavior.

## Production and delivery

Hosted activation remains incomplete. Follow the current README, hosted
activation status and runbooks for the exact missing provider, restore,
operator and signature evidence. A passing local suite or CI run cannot enable
production privileges, real PII, public profiles or direct downstream writes.

`manage.py runserver` is a development server, not a deployment procedure.
Do not add production credentials, contact providers or deploy as part of a
routine code change. Use branches and reviewable PRs, preserve user changes,
update affected status/runbook documentation and record actual verification.
