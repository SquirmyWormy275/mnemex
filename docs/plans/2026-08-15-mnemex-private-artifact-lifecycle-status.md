# MNEMEX private artifact lifecycle status

**Date:** 2026-08-15
**Status:** complete as a local recovery slice; not a hosted object-store or worker service
**Authority:** subordinate to D0-7, D0-8, D0-10, and the approved MNEMEX architecture

## Outcome

Results Desk and legacy-migration uploads now register database evidence before
bytes enter the shared content-addressed namespace. A request failure never
deletes a digest object synchronously.

```text
begin durable write attempt with expiry
  -> atomically install or verify digest-addressed bytes
  -> create/reuse immutable SourceArtifact in the business transaction
  -> link write attempt in the same transaction

request rollback / process death
  -> abandoned or expired durable attempt
  -> bounded registry-locked reconciliation
  -> preserve referenced bytes, remove exact unreferenced bytes,
     or block unexpected/missing storage state for recovery review
```

One registry row represents each digest-derived object reference. Every upload
creates its own tenant-bound write attempt. Reconciliation locks the registry row,
so cleanup and a concurrent same-content upload cannot race to delete the new
request's object. Exact bytes are the only bytes the collector will remove.

## Implemented contract

- Immutable artifact-object registry with digest, relative private reference, and
  byte size.
- Tenant-bound write attempts with active expiry, linked provenance, abandoned,
  cleaned, preserved, and blocked terminal states.
- Atomic source-artifact linkage and validation of organization, digest, reference,
  and size.
- Rollback-safe failure handling in ordinary Results Desk and legacy workbook
  uploads; failures become durable abandoned attempts instead of request-time
  deletion.
- Expired-process recovery and bounded reconciliation through
  `mnemex.worker --reconcile-artifacts-once --limit N`.
- Registry locking across byte installation, so an expired writer cannot resume
  after cleanup and create an object with no unresolved ledger evidence.
- Write attempts must begin active, use the lifecycle service for transitions,
  and cannot be rewritten after reaching a terminal state.
- Fail-closed behavior for unexpected bytes, missing referenced bytes, invalid
  lifecycle transitions, tenant mismatch, and immutable-provenance mutation.

## Verification evidence

All evidence used synthetic bytes and isolated databases.

| Gate | Result |
| --- | --- |
| Full isolated SQLite suite after final review fixes | **345 passed, 45 skipped in 55.45s** |
| Earlier full disposable PostgreSQL 18 regression baseline | **344 passed, 41 skipped in 107.36s**, before the final lifecycle-review hardening |
| Current focused PostgreSQL artifact/upload set | **18 passed in 8.44s** |
| PostgreSQL registry-lock and install-lock races | **2 passed** within the current focused set |
| Integrated SQLite Results Desk/legacy set | **159 passed, 2 skipped in 49.11s** |
| Django system check | 0 issues |
| Migration drift | No changes detected |
| Scoped Ruff | Lint and format clean |
| Scoped Mypy | 0 issues in changed source files |

PostgreSQL first exposed and then verified the fix for a nullable outer-join
`FOR UPDATE` bug that SQLite could not represent. Dedicated two-thread tests
prove both directions of the race: a same-object writer blocks behind cleanup,
and cleanup blocks while registered installation holds the registry lock. No
final full-PostgreSQL rerun is claimed after the last review fixes; the current
PostgreSQL evidence is the focused 18-test set above.

## Remaining production gates

- Supabase private Storage (or another approved hosted adapter), server-only
  credentials, immutable versions, malware policy, and provider-specific failure
  handling.
- A continuously claimed worker process with heartbeat, retry/backoff, alerting,
  graceful shutdown, and deployment ownership. The current entry point performs
  one bounded reconciliation batch and exits.
- A complete restore reconciliation that scans every linked `SourceArtifact`
  against object presence, digest, size, permissions, retention, and backup state.
- Approved RPO/RTO/retention, separate object backup, restore rehearsal, orphan
  grace policy, and incident runbook.
- Hosted activation of the locally implemented session-bound MFA path and the
  other production PII gates recorded in the Results Desk and account-security
  status documents.

No real workbook, PII, hosted credential, deployment, Git staging/commit/push, or
direct STRATHMARK database write was used or enabled.
