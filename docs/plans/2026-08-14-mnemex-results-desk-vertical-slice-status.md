# MNEMEX Results Desk vertical-slice status

**Date:** 2026-08-14; updated 2026-08-17
**Status:** implemented and exercised locally; not production-ready
**Authority:** subordinate to the approved architecture and build decisions

## Outcome

The first integrated Results Desk-to-STRATHMARK workflow exists locally:

```text
manual row / CSV / explicitly selected XLSX worksheet
  -> immutable source manifest + versioned mapping
  -> deterministic row validation
  -> valid row automatically publishes; invalid/conflicting row quarantines
  -> explicit human identity reconciliation or append-only relink correction
  -> explicit SB/UH export-eligibility review
  -> immutable, cutoff-bound, pseudonymous STRATHMARK 2.x evidence snapshot
  -> authenticated download and explicit STRATHMARK import
```

Automatic publication is the approved D0-12 decision, not an open design
question. Publication records a deterministic-valid source assertion in the
private archive. It does not auto-link a person, make a result public, or make a
row STRATHMARK-eligible.

## Implemented local workflow

- Authorized, tenant-scoped Results Desk dashboard, starter CSV, custom mappings,
  expandable manual-entry grid, CSV upload, explicit XLSX worksheet selection,
  and run outcomes. Multi-sheet workbooks fail closed until a sheet is named.
- Private local digest-addressed storage for uploaded source artifacts, plus a
  source-manifest equivalent for manual batches.
- Immutable source manifests and mapping provenance; ingestion pins the mapping
  digest used for that run.
- Deterministic validation with upload, archive, row, column, cell, numeric, and
  PostgreSQL integer bounds; duplicate/blank headers and CSV overflow columns are
  rejected instead of silently remapped.
- Exact retry/idempotency, immutable published rows, contiguous source-revision
  correction chains, and latest-current revision selection for export.
- Broad-discipline source capture with explicit identity cases and no automatic
  name-based person merge.
- Tenant-scoped identity queue with consent-grant validation for consent-based
  links, non-enumerating person labels, and append-only link correction/relink.
- Append-only export eligibility review, visible exclusions, candidate and full
  manifest size limits, exact score-bound checks, and immutable snapshot lineage.
- STRATHMARK 2.x schema/version contract, PII-free evidence envelope, and an
  explicit local `ResultStore` round trip.
- Responsive Results Desk manual-entry layout and human-readable organization and
  mapping labels. The local grid can add or remove rows through a 25-row batch.
- Tenant-scoped issue CSV download for quarantined/conflicting rows, with stable
  validation codes, physical source coordinates, and correction guidance.
- Synthetic bulk legacy migration workbench with multi-sheet discovery, explicit
  table plans, five-way no-write preview, exact-digest approval, bounded resumable
  apply through a rationale-bearing durable worker queue, reconciliation CSV,
  and logical withdrawal. See the dedicated
  [workbench status](2026-08-15-mnemex-bulk-legacy-migration-workbench-status.md).
- Server-signed, actor-bound snapshot capture time; temporal reconstruction and
  paginated, bounded-query export/exclusion review.
- Test gates that reject remote/non-test Django databases and remote Supabase test
  targets. Session-bound MFA is implemented locally; production privileged actions
  remain disabled until the hosted account-security and operational gates below pass.

## Authority and trust boundaries

- **MNEMEX owns:** person identity, aliases, consent, portable profile, reconciled
  career assertions, provenance, and reviewed prior-result snapshots.
- **A participating show owns:** registration, entries, partners, waivers,
  payments, event-local eligibility decisions, roster, marks, scoring, official
  results, corrections, and final event state.
- **STRATHMARK owns:** its explicit evidence import, predictions, calculation
  receipts, and settlement revisions. It does not receive legal identity,
  contact details, aliases, raw source payloads, or direct MNEMEX writes.
- **Race day:** a show must operate from its pinned local roster/profile snapshot.
  No live MNEMEX dependency is permitted after roster lock.

## Adversarial review fixes incorporated

The local slice was hardened after domain, security, product/operations, and
browser review. Fixes include:

- session-bound TOTP/recovery proof, session rotation, exact freshness, and
  five-minute privileged-POST reauthentication while production privilege
  remains fail-closed;
- tenant-scoped authorization and non-enumerating private identity choices;
- real consent-grant validation for competitor/guardian consent assertions;
- reachable append-only identity relink/correction workflow;
- immutable source artifacts, mappings, published rows, career revisions,
  eligibility revisions, and snapshot manifests;
- contiguous correction chains and exclusion of superseded source revisions;
- duplicate/blank header and CSV overflow rejection;
- bounded decimal canonicalization and source revisions safe for PostgreSQL;
- snapshot candidate/full-manifest limits and exact pre-float score bounds;
- loopback-only legacy Supabase integration tests;
- ignored blank manual rows and a usable stacked mobile-entry layout.

## Verification evidence

Scoped feature, browser, contract, migration-drift, lint, and type checks were
reported green during the local workflow. Browser exercise covered the complete
synthetic path from manual entry through snapshot download without a server 500
or browser-console error.

| Final aggregate check | Result |
| --- | --- |
| Current full isolated SQLite suite | **416 passed, 49 skipped in 59.48s** |
| Current focused disposable PostgreSQL MFA/portal set | **58 passed in 19.25s**; cluster stopped and removed |
| Earlier full disposable local PostgreSQL 18 regression baseline | **344 passed, 41 skipped in 107.36s**, before final artifact-lifecycle review hardening |
| Current focused PostgreSQL artifact/upload set | **18 passed in 8.44s** |
| Current disposable PostgreSQL 18 durable-worker/apply set | **51 passed in 157.55s**, including competing claims, tenant fairness, migration forward/reverse, and predecessor-checkpoint recovery |
| PostgreSQL consent-lock regression | **29 passed in 3.08s** after replacing a nullable outer-join lock with separate row locks |
| Local browser workflow | **Passed:** dynamic 3-to-5-row form, 1 published result, explicit identity link, reachable relink correction, eligible review, and 1-row immutable snapshot. The 708-byte downloaded JSON contained none of the source name, public/private aliases, or operator email. |
| Migration drift | **No changes detected** |
| Django system/deployment checks | Test settings: **0 issues**. Production deploy check: only intentional HSTS subdomain/preload warnings W005/W021. |
| Scoped Ruff format/lint and Mypy | Scoped Ruff clean; targeted Mypy clean across **56 source files**. |

Green local evidence is scoped evidence, not production-readiness evidence.

## Explicit production blockers

The following are required before real PII, partner credentials, public access,
or production privileged operations can be enabled:

- hosted account-security activation: a shared atomic TOTP-claim cache, separate
  shared/edge rate-limit controls beyond allauth's best-effort application limits,
  trusted proxy/IP configuration, mail delivery, authenticator-key custody/rotation,
  approved staff recovery policy, monitoring, and independent security review;
- approved jurisdiction/minor/guardian rules and production encryption-key
  custody, rotation, backup, and restore evidence;
- private hosted object storage with server-only credentials, RLS/grant review,
  malware policy, versioned backup, restore, and database/object reconciliation;
- keyed HMAC pseudonym generation with approved secret custody, rotation,
  recovery, and compatibility policy;
- continuous hosted migration-worker supervision, queue/lease observability,
  alerting, and real process-kill/signal/load/restore rehearsals beyond the local
  bounded one-shot worker;
- Railway build/release/process manifests, migration ownership, static serving,
  health smoke checks, observability, and rollback rehearsal;
- approved RPO, RTO, database/object retention, deletion/hold policy, restore
  cadence, and successful recovery rehearsal;
- portable-profile issuance/validation, pairwise show adapters, two-tenant
  conformance, and the offline pinned roster/profile snapshot;
- competitor opt-in public pages and revocation/dispute/minor-transition behavior;
- approved real-corpus data-rights inventory, mapping packs, exception owners,
  reconciliation thresholds, and restore/withdrawal rehearsal;
- authenticated finalized-show result inbox and show-owned durable outbox for
  finalized results and approved corrections.

## Deferred local limitations

- Ordinary Results Desk XLSX intake remains one explicitly selected worksheet per
  run. The separate legacy workbench now inventories multi-sheet archives, but
  automatic mapping suggestions and authorized real-corpus mapping packs remain
  deferred.
- Uploaded files use a local digest-addressed adapter with a durable object
  registry, expiring write attempts, rollback-safe abandonment, and bounded
  orphan reconciliation. Hosted storage and full restore reconciliation remain
  unimplemented. Manual batches retain a manifest and digest but do not yet have
  a retrieval/download artifact.
- Large-corpus pagination, load testing, and production-scale acceptance gates are
  not complete.
- Issue-row download and guidance exist; in-portal edit/retry and source-conflict
  resolution mutations remain deferred.
- Organization-row locking serializes ingestion across operator keys, but a
  threaded PostgreSQL contention/load gate is still required before production.
- Durable migration APPLY claims, leases, heartbeat/retry/backoff, append-only
  terminal replacement, and checkpoint recovery are implemented locally in a
  bounded one-shot worker. Continuous hosted supervision and full source-object
  restore reconciliation remain production gates; this is not a service loop.
- A privileged POST whose five-minute MFA proof expires is rejected before
  mutation, but its form fields and uploaded file are not preserved across the
  reauthentication redirect. Operators must re-enter/reselect the submission;
  body-preserving pre-submit step-up remains deferred.

## Legacy paths

The scheduled legacy Supabase-to-JSONL export is disabled: the workflow has no
schedule and is manual-only. Direct legacy STRATHMARK adapters fail closed. The
two Supabase setup/RLS runbooks are marked deprecated and are not authoritative
for the Django/PostgreSQL/private-object architecture.

## Safety boundary

This work used synthetic data and isolated local databases. It does not authorize
real PII, production or partner credentials, public career profiles, deployment,
or a direct write to any STRATHMARK database. Results reach STRATHMARK only by an
explicit reviewed evidence snapshot and consumer-side import.
