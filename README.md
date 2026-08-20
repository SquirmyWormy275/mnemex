# MNEMEX

MNEMEX is the STRATHEX ecosystem's universal competitor identity,
portable-profile, career-history, and provenance service.

A competitor maintains one profile containing verified identity, aliases,
federation identifiers, consented contact details, eligibility history,
preferences, and reconciled competitive history. With explicit consent,
MNEMEX will issue a purpose- and event-bounded profile projection to a
participating show.

MNEMEX is also the home of the integrated Results Desk. Authorized results
staff can upload a spreadsheet or enter historical results manually, preserve
source provenance, reconcile a result to a person through explicit review, and
build reviewed prior-results snapshots for STRATHMARK 2.x.

## Authority boundary

MNEMEX owns the person, portable profile, consent grants, reconciled career
record, and provenance chain. A show owns its registration, entries, partners,
waivers, payments, event-local eligibility decisions, roster, marks, scoring,
official results, corrections, and finalized event state.

Shows may validate a profile with MNEMEX during registration and pre-event
preparation. At roster lock, the show pins its own local snapshot. Race-day
operation must not require a live MNEMEX connection. Finalized results and
approved corrections return later through auditable, idempotent reconciliation.

MNEMEX never writes directly to STRATHMARK. STRATHMARK explicitly imports an
immutable, reviewed, pseudonymous evidence snapshot.

## Current local state

The architecture and initial build decisions are approved. The following work is
implemented locally and has not been production-enabled or deployed:

| Area | Current state |
| --- | --- |
| Django 5.2 LTS modular-monolith foundation | Implemented locally |
| Email-based account model, roles, tenant scopes, audit, and idempotency | Implemented foundation |
| Invite-only authentication, verified email, TOTP/recovery, session proof, and throttling | Implemented locally with encrypted authenticator material, MFA-only security changes, atomic TOTP/recovery claims, canonical email identity, eight-hour privileged freshness, five-minute privileged-POST freshness, session rotation, and revocation; production privileged actions remain disabled |
| Security-administrator operations | Implemented locally: scope-bound staff invitations, one-time code acceptance, two-person lost-factor recovery, session/factor revocation, role suspension, MFA re-enrollment, and explicit restoration |
| In-page sensitive-action assurance | Implemented locally: populated fields and selected files stay in the page while MFA is refreshed; submission uses a route-, origin-, session-, method-, account-, and security-version-bound one-use ticket with a deliberate confirmation step |
| Durable security-notification queue | Implemented locally with queue-only allauth account-security delivery, verified event-time recipient snapshots, deterministic message identity, fenced leases, bounded retry, uncertain-handoff review, retention, and PII-free metrics; hosted SMTP evidence remains pending |
| Versioned MFA and notification encryption keys | Implemented locally with strict key-ring parsing, historical-version restore checks, resumable MFA re-encryption, fenced claims, and retirement blockers |
| Person, alias, encrypted legal identity, guardian, and consent foundation | Implemented locally |
| Results Desk manual entry | Implemented locally |
| CSV and explicitly selected XLSX worksheet ingestion | Implemented locally; multi-sheet workbooks fail closed until a sheet is named |
| Deterministic automatic publication and row quarantine | Implemented locally |
| Explicit identity reconciliation and append-only relink correction | Implemented locally |
| Human export-eligibility review | Implemented locally |
| Immutable STRATHMARK 2.x reviewed SB/UH snapshot | Implemented locally; explicit download/import only |
| Synthetic bulk legacy migration workbench | Implemented locally: multi-sheet discovery, explicit table plans, five-way dry run, exact-digest approval, rationale-bearing durable APPLY queue, resumable 250-row checkpoints, reconciliation CSV, and logical withdrawal |
| Durable legacy APPLY worker | Implemented locally as a bounded one-shot worker with tenant-fair claiming, fenced leases, heartbeat expiry, retry/backoff, append-only terminal recovery, graceful stop, and checkpoint resume; no hosted service loop |
| Private-artifact write recovery | Implemented locally: durable registry/write leases, rollback-safe abandonment, and bounded orphan reconciliation |
| Hosted private-artifact adapter | Implemented locally for a private Supabase Storage bucket with server-only credentials, opaque digest keys, create-only writes, bounded verified reads, redirect refusal, and no browser URL surface; no hosted bucket has been provisioned or tested |
| Railway process contract | Implemented locally: one image, separate Gunicorn web and supervised worker services, one web pre-deploy migration owner, fingerprinted static assets, bounded queue work, graceful drain boundaries, and redacted health signals; no image has been deployed |
| Backup and recovery contract | Implemented locally with immutable manifests, pristine-target refusal, database/object/key reconciliation, expired-lease normalization, exact cleanup, and redacted evidence; provider restore evidence is still pending |
| Activation evidence | Implemented locally as a closed 14-gate registry, immutable evidence, deterministic redacted reports, environment binding, freshness checks, and offline Ed25519 verification; the report cannot enable production privilege |
| Portable-profile/show adapters and offline roster snapshots | Planned; not implemented |
| Opt-in public career pages | Planned; not implemented |
| Railway/Supabase production deployment and full private-object restore | Not activated |

Automatic publication is the approved D0-12 behavior. A deterministic-valid
source row publishes to the private archive; an invalid or conflicting row is
quarantined. Publication does **not** create a trusted identity link, public
career fact, or STRATHMARK eligibility. Each of those requires its separate
review or consent state.

No real PII, production credential, partner credential, public profile,
deployment, or direct STRATHMARK database write is enabled by this repository
state. See the [Results Desk status](docs/plans/2026-08-14-mnemex-results-desk-vertical-slice-status.md)
and [bulk migration workbench status](docs/plans/2026-08-15-mnemex-bulk-legacy-migration-workbench-status.md)
and [artifact lifecycle status](docs/plans/2026-08-15-mnemex-private-artifact-lifecycle-status.md)
and [durable migration worker status](docs/plans/2026-08-17-mnemex-durable-migration-worker-status.md)
and [account security status](docs/plans/2026-08-17-mnemex-account-security-status.md)
and [hosted activation status](docs/plans/2026-08-18-mnemex-hosted-production-activation-status.md)
for the exact limitations and production blockers.

The binding documents are:

- `docs/plans/2026-08-14-mnemex-universal-profile-architecture.md`
- `docs/plans/2026-08-14-mnemex-approved-build-decisions.md`
- `docs/plans/2026-08-14-mnemex-approved-implementation-plan.md`

Older archive design documents and direct Supabase client modules are legacy
proposals/code. They do not override the approved authority, consent, race-day,
publication, or export boundaries. The legacy Supabase-to-JSONL workflow is
production-disabled, has no schedule, and can only be invoked manually; its
Supabase runbooks are explicitly deprecated.

## Safe local checks

Use synthetic data only. These PowerShell commands explicitly select the
isolated Django test settings:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# Install the sibling checkout when running the STRATHMARK 2.x contract tests:
.\.venv\Scripts\python.exe -m pip install -e "..\STRATHMARK"
$env:DJANGO_SETTINGS_MODULE = "mnemex.web.settings.test"
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The test settings use isolated in-memory SQLite by default and ignore
`DATABASE_URL` and Supabase credentials. To exercise PostgreSQL semantics, set
`MNEMEX_TEST_DATABASE_URL` to a disposable **local** database whose name
contains `test`. Remote hosts and non-test database names are rejected before a
connection is attempted.

Legacy Supabase integration tests are separately gated by
`MNEMEX_TEST_SUPABASE=1` and accept only loopback-hosted Supabase test services.
Do not use a shared or hosted Supabase project.

`manage.py runserver` is a development server, not a production runbook. The
production settings deliberately disable privileged workflows even though the
session-bound MFA and hosted configuration paths are implemented locally. Provider
provisioning, real shared-Redis evidence, authenticated SMTP/bounce/complaint evidence,
a built Railway image, a hosted private bucket, provider backup/restore evidence, edge
throttling, independent operator rehearsal, offline owner signature, and a separate
activation decision remain unfinished.

## Repository layout

```text
mnemex/
  accounts/              invite-only login, verified email, MFA/recovery, session assurance, roles
  activation/            immutable activation evidence and fail-closed report generation
  people/                person, alias, encrypted legal identity, guardian authority
  consent/               scoped grants, disclosure filtering, public opt-in foundation
  partners/              participating-show organizations and clients
  results/               Results Desk portal, artifacts, mappings, ingestion, quarantine
  legacy_migration/      synthetic bulk archive inventory, dry run, approval, checkpoints
  career/                explicit identity reconciliation and append-only career links
  export/                export review and STRATHMARK 2.x evidence snapshots
  foundation/            audit, idempotency, and transaction primitives
  recovery/              backup manifests and disposable restore-rehearsal contract
  web/                   Django settings, routes, WSGI/ASGI, health endpoints
  worker.py              bounded supervised artifacts, APPLY, notification, and key-rotation queues
  supervisor.py          fair task scheduling, redacted failures, and graceful stop boundaries
  schema.py              canonical result dataclasses and discipline definitions
  identity.py            legacy identity code pending migration/reconciliation
  store.py               legacy direct Supabase abstraction; not an authority boundary
  ingest/                legacy historical source ingestion modules
  strathmark_adapter/    fail-closed legacy direct exporters

tests/                    synthetic tests and isolated contract fixtures
docs/plans/               architecture, approved decisions, plans, and status records
docs/runbooks/            hosted operations, recovery, and staff-security ceremonies
```

## License

Proprietary, pending finalization.
