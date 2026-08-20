# MNEMEX bulk legacy migration workbench status

**Date:** 2026-08-15; updated 2026-08-17
**Status:** complete as a synthetic local vertical slice; not production-ready
**Authority:** subordinate to the approved MNEMEX architecture and D0-1 through D0-12

## Outcome

The synthetic bulk-migration workbench is implemented locally under the Results
Desk. It is designed for Gillian's archive workflow without granting identity or
STRATHMARK trust:

```text
private multi-sheet XLSX
  -> bounded workbook discovery
  -> explicit include/ignore decision for every sheet
  -> explicit rectangular table regions and mapping rules
  -> immutable five-way no-write preview
  -> separate organization-scoped exact-digest approval
  -> manager rationale + durable APPLY enqueue
  -> tenant-fair fenced worker claim
  -> deterministic 250-row apply checkpoints + heartbeat
  -> exact replay or crash/resume
  -> privacy-limited reconciliation CSV
  -> optional append-only logical withdrawal
```

A deterministic-valid source row may publish under approved decision D0-12. The
workbench never performs name-based person matching, never turns a source row into
a portable career fact, and never marks a row STRATHMARK-eligible. Those remain
separate identity and export-review decisions.

## Implemented local contract

- Private digest-addressed XLSX inventory with tenant, source key, data-rights
  reference, parser version, artifact digest, and source-state digest.
- Discovery for visible, hidden, and very-hidden sheets while preserving exact
  sheet names, order, dimensions, header candidates, and formula coordinates.
- Explicit disposition of every sheet. Included sheets require bounded rectangular
  table plans; ignored sheets require a reason. Empty header-candidate lists are
  valid for summary sheets.
- Column, constant, and stable artifact-coordinate mapping rules. Unknown rules,
  duplicate/blank headers, mapped formulas, overlapping regions, sparse implied
  cell workloads, excessive tables, and excessive planned rows fail closed.
- Immutable row previews with physical source coordinates, canonical payload
  digests, source-state digests, and publishable/quarantined/duplicate/conflict/
  ignored classifications.
- Exact dry-run manifest reconstruction before approval and apply. New or mutated
  preview evidence invalidates the approval before publication.
- Tenant-scoped reviewer approval, manager apply/resume, 250-row partition keys,
  checkpoint counters, append-only decisions, reconciliation manifests, and
  logical withdrawal.
- Durable APPLY jobs with immutable request rationale, tenant-scoped fair
  claiming, opaque claim tokens, generation fencing, expiring leases,
  heartbeat, bounded retry/backoff, graceful-stop handling, and a bounded
  one-shot worker command.
- Claim count and failure budget are separate. Graceful stops do not consume the
  failure budget; expired takeovers and real failures do. Terminal recovery
  appends a new rationale-bearing job sequence while preserving the old job and
  any verified predecessor checkpoints.
- Tenant-scoped, non-enumerating portal routes. The reconciliation CSV omits sheet
  names, competitor names, source-result identifiers, and artifact object paths.
- Hardened ordinary Results Desk provenance: ingestion-run mapping digests,
  immutable staged rows, artifact/mapping/organization validation, published-row
  graph validation, and reconciliation-time checkpoint graph revalidation.

## Adversarial fixes incorporated

Independent review and real-browser exercise found and resolved:

- side-by-side table regions producing colliding stable source identifiers;
- mutable run digests and mutable committed-checkpoint counters;
- missing table-region count, overlap, and planned-row limits;
- approval that did not reconstruct the exact persisted preview set;
- shared content-addressed upload cleanup that could delete a concurrently
  committed object;
- database rollback after object installation leaving an untracked orphan; uploads
  now register an expiring durable write before storage and never delete shared
  objects in the request failure path;
- sparse far-corner XLSX cells causing dense implied-cell scanning;
- cross-tenant and transitively mutable result/checkpoint provenance graphs;
- cross-tenant run identifier existence leaks;
- ignored summary sheets with no header candidates failing configuration;
- the operator-facing `applied rows` label counting quarantined rows; it now reads
  `processed rows` while checkpoint columns show published versus quarantined;
- ignored-sheet rationale text visually colliding with the disposition label.
- graceful worker stops exhausting healthy jobs, terminal failures with no
  recovery path, lost claims aborting a whole worker batch, and queue scans that
  could starve later tenants;
- revoked creator authority or inactive tenants reaching private workbook reads,
  historical failed jobs keeping the worker unhealthy after a successful
  replacement, and replacement jobs being unable to resume predecessor
  checkpoints;
- legacy job migration rewriting valid terminal history or leaving exhausted
  work non-claimable, and checkpoint/job/run bulk-write tenant grafts.

## Verification evidence

All verification used synthetic data and isolated databases.

| Gate | Result |
| --- | --- |
| Current full isolated SQLite suite | **385 passed, 48 skipped in 164.93s** |
| Earlier full disposable local PostgreSQL 18 regression baseline | **344 passed, 41 skipped in 107.36s**, before final artifact-lifecycle review hardening |
| Current focused PostgreSQL artifact/upload set | **18 passed in 8.44s** |
| Current PostgreSQL registry/install lock races | **2 passed** within the focused set |
| Focused hardened PostgreSQL result/apply/scale set | **60 passed in 72.75s** |
| Current disposable PostgreSQL 18 durable-worker/apply set | **51 passed in 157.55s**, including competing claimers, more-than-100-tenant fairness, migration forward/reverse, and predecessor-checkpoint recovery |
| Integrated Results Desk/career/export/legacy slice | **167 passed, 1 skipped in 32.33s** |
| Synthetic 28/38/42-sheet discovery | Passed |
| Synthetic 2,001-row apply/replay | 9 checkpoints; exact replay and accounting passed |
| PostgreSQL connection-close/resume | Passed; first committed 250-row checkpoint remained unchanged |
| Django system check | 0 issues |
| Migration drift | No changes detected |
| Scoped Ruff | Lint clean; format contract clean |
| Scoped Mypy | 0 issues in hardened result/legacy files |
| Real-browser workflow | Passed upload through withdrawal with no browser errors |

The 2,001-row scale observation used **8,616 database queries** and took about
**3.30 seconds on SQLite** and **7.54 seconds on local PostgreSQL 18**. This proves
bounded correctness and resume behavior, not production throughput.

Browser acceptance used a disposable local SQLite database, a synthetic two-sheet
workbook, and an isolated Chrome profile. It verified one publishable row, one
quarantined `invalid_number` row, exact-digest approval, one committed checkpoint,
one published source result, a three-line privacy-limited reconciliation CSV,
mobile layout without horizontal overflow, and logical withdrawal. Screenshots and
the synthetic CSV are outside the repository under the Codex visualization folder.

## Production blockers

This slice must remain disabled for real PII and hosted privileged operation until
all of the following are complete:

- Real MFA proof bound to the current session, with freshness, recovery,
  reauthentication, throttling, and email verification. Production privileged
  authorization is intentionally hard-disabled today.
- Hosted private object storage with server-only credentials, malware policy,
  immutable versions, database/object backup and restore, and reconciliation.
  Local uploads now have a durable object registry, expiring write attempts, and a
  bounded rollback/crash orphan collector, but no hosted adapter or complete
  database-versus-object restore scan exists.
- Hosted continuous worker-process supervision, queue/lease metrics, alerting,
  operational cancellation/recovery controls, and real process-kill, signal,
  load, and restore rehearsals. Durable cross-process claims, leases,
  heartbeat expiry, retry/backoff, terminal replacement, and checkpoint recovery
  are implemented locally through a bounded one-shot worker, not a Railway
  service loop.
- Query-plan and batching work. The current 2,001-row path issues 8,616 queries and
  materializes workbook and manifest structures in-process.
- Database-native composite tenant constraints or equivalent database policy for
  the result/checkpoint graph. Application validation and reconciliation detect
  ordinary ORM and low-level tampering, but raw-database defense remains a gate.
- A controlled rollback/preflight policy for the result ingestion partition-key
  migration; reversing it after partitioned runs can violate the prior uniqueness
  shape.
- Approved real-corpus data-rights inventory, mapping packs, exception ownership,
  reconciliation thresholds, and a restore/withdrawal rehearsal using an
  authorized non-production copy. No real AWFC or Missoula workbook was opened.
- Railway process/build/release manifests, migration ownership, static serving,
  health checks, alerting, rollback rehearsal, and approved RPO/RTO/retention.

## Safety and authority boundary

No real PII, production credential, partner credential, public profile, hosted
deployment, or direct STRATHMARK database write was enabled. Race day remains
independent of live MNEMEX. Results can reach STRATHMARK only through the separate
reviewed evidence-snapshot contract and consumer-side import.
