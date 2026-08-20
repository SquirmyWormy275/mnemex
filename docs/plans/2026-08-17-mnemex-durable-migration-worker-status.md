# MNEMEX durable legacy migration worker status

**Date:** 2026-08-17
**Status:** implemented and exercised locally; not production-ready
**Authority:** subordinate to the approved MNEMEX architecture, D0-1 through D0-12, and the bulk legacy migration workbench contract

## Outcome

Legacy archive publication no longer runs inside the operator's web request. An
authorized manager records a rationale and enqueues an immutable APPLY request.
A bounded worker claims the job, reads the approved private workbook only while
the tenant, run, job, and claim remain locked and reauthorized, and commits at
most 250 source rows per deterministic checkpoint.

```text
exact-digest reviewer approval
  -> manager rationale + durable enqueue
  -> tenant-fair claim with opaque token and generation fence
  -> locked creator/tenant reauthorization + private source read
  -> heartbeat before each deterministic checkpoint
  -> completed | retry wait | terminal failed | cancelled
  -> exact replay, lease takeover, or rationale-bearing replacement
```

This worker does not change MNEMEX's authority boundary. A valid legacy row may
publish privately under D0-12, but it does not become an identity link, public
career fact, or STRATHMARK-eligible result without the separate approved reviews.

## Implemented local contract

- Active APPLY requests are idempotent by run, approved manifest digest, and
  chunk size. The request rationale is required and immutable.
- Claims carry an opaque token, owner, monotonically increasing generation,
  heartbeat, and lease expiry. Every write rechecks the active claim.
- The queue selects tenant organizations by their earliest actual claim-ready
  time before applying its bounded candidate cap. Expired RUNNING work is ordered
  by lease expiry, not its older enqueue time.
- Claim count is fencing evidence; failure count is the retry budget. Graceful
  stops can be reclaimed without exhausting healthy work. Expired takeovers and
  real failures consume the bounded failure budget and use capped backoff.
- Creator role and tenant status are rechecked before a claim is returned and
  again inside the locked private-source read. Revocation terminalizes the job
  before claim loss is reported.
- A lost or withdrawn claim is a bounded worker outcome, not an unhandled batch
  crash. No old owner may mutate a superseding claim.
- Terminal recovery appends a new rationale-bearing job sequence. Failed history
  remains immutable, while a replacement may resume only verified checkpoints
  from an earlier FAILED or CANCELLED job with the same tenant, run, manifest,
  and chunk contract.
- Worker failure signaling counts only the latest unsuperseded request sequence,
  so a completed replacement resolves its predecessor without deleting history.
- Legacy migration forward normalization preserves valid terminal history,
  terminalizes exhausted legacy work, and leaves at most one active job for an
  immutable request. Reverse migration maps new retry/cancel states to the prior
  vocabulary before schema reversal.
- Run, job, and checkpoint bulk mutation paths fail closed. Checkpoint resume and
  reconciliation revalidate tenant, run, request-chain, table, row range, digest,
  ingestion, and staged-result evidence.

## Verification evidence

All evidence used synthetic data and isolated databases.

| Gate | Result |
| --- | --- |
| Current full isolated SQLite suite | **385 passed, 48 skipped in 164.93s** |
| Focused SQLite worker/domain/apply recovery set | **47 passed, 3 PostgreSQL-only skipped in 49.53s** before the final predecessor-chain regression |
| Final disposable PostgreSQL 18 worker/apply set | **51 passed in 157.55s** |
| PostgreSQL concurrency coverage | Competing claimers selected one job exactly once |
| PostgreSQL fairness coverage | A ready tenant beyond more than 100 busy jobs was claimable; a genuinely older pending tenant outranked more than 100 recently expired leases |
| Replacement recovery | A predecessor committed one checkpoint, failed terminally, and its replacement completed without duplicate publication |
| Migration executor | Forward exhaustion/history normalization and reverse status mapping passed |
| Independent residual review | Correctness, security/tenant isolation, and reliability reviewers reported **PASS** after fixes |

The PostgreSQL cluster was loopback-only, contained one synthetic test database,
and was stopped and permanently removed after the run.

## Production blockers

The local contract does not authorize hosted execution or real data. Production
still requires:

- session-bound MFA and the broader privileged-account activation gates;
- Railway build, release, web, and worker process manifests with one explicit
  migration owner;
- a continuously supervised worker loop, graceful deploy drain, queue depth and
  lease-age metrics, structured alerts, and operator cancellation/recovery views;
- hosted immutable private-object storage and database/object backup, restore,
  and reconciliation;
- hard process-kill, real signal, network interruption, high-contention load,
  restore, and rollback rehearsals against an authorized non-production corpus;
- measured query and memory ceilings for the 25,000-row accepted boundary;
- database-native composite tenant constraints or equivalent database policy for
  defense against privileged raw-database writes;
- approved real-corpus data rights, mapping packs, exception ownership,
  reconciliation thresholds, RPO/RTO, and retention.

## Safety boundary

No real workbook, PII, production credential, partner credential, public profile,
deployment, or direct STRATHMARK database write was used or enabled. Race day
remains independent of live MNEMEX. Results reach STRATHMARK only through the
separate reviewed evidence snapshot and consumer-side import.
