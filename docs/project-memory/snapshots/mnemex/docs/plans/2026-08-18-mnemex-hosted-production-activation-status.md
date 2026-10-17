# MNEMEX hosted-production activation status

Status date: 2026-08-18

## Outcome

The hosted-activation foundation is implemented and locally coherent. MNEMEX is **not activated or deployed**. Production privileged authorization remains a literal `False` in production settings, and the fail-closed activation report currently returns `blocked` with every gate pending when no approved evidence is recorded.

This work used synthetic accounts, isolated databases, a temporary private-artifact root, and a disposable loopback PostgreSQL cluster. It did not use provider credentials, production data, real PII, external mail, a hosted database, or source-repository Git mutations.

## Implemented foundation

- Strict hosted settings for database TLS, fixed connection timeout, Redis TLS, separate atomic-security cache namespace, SMTP, key rings, allowed hosts, proxy trust, and a private Supabase bucket.
- Session-bound MFA assurance, route/origin/method/account/version-bound one-use action tickets, in-page step-up without automatic replay, and a rapid-submit guard.
- Queue-only allauth security-mail delivery through the durable encrypted outbox, with verified event-time recipients, deterministic message identity, fenced leases, bounded retries, uncertain-delivery handling, retention, and PII-free queue metrics.
- Versioned MFA and notification key rings plus resumable, fenced rotation jobs and historical-version availability checks.
- Server-only private-object storage adapter with opaque digest keys, bounded reads, integrity verification, no redirects carrying service credentials, and crash-recovery lifecycle records.
- Separate Railway web and worker process contracts, static-asset build settings, bounded supervised worker loops, readiness/liveness checks, and graceful drain seams.
- Immutable recovery-rehearsal evidence, restore target refusal, inventory comparison, object/key reconciliation, and operator runbooks.
- Immutable activation evidence, a closed 14-gate registry, deterministic redacted reports, and offline Ed25519 verification.
- Security-administrator portal for scope-bound staff invitations and two-person lost-factor recovery. Invitation secrets are shown once, never placed in a URL or notification, and only their purpose-bound digest is stored.
- Explicit suspension after recovery approval, factor and session revocation, required MFA re-enrollment, and separate privilege restoration.

## Acceptance evidence

| Gate | Result |
|------|--------|
| Complete isolated SQLite suite | `619 passed, 53 skipped` in 82.40 seconds |
| Complete disposable PostgreSQL 18 suite | `630 passed, 42 skipped` in 218.57 seconds |
| Final focused security/config/workbook regression | `89 passed` |
| Browser QA | Password + MFA login, stale-session step-up, rapid duplicate-submit attempt, one-time invitation, independent recovery approval, desktop and 375 x 812 mobile views |
| Browser defects found and closed | DOM-shadowed form action; action-ticket freshness ordering; duplicate form control IDs |
| Scoped Ruff lint | Passed for the activation/security/recovery surface and its tests |
| Scoped Ruff formatting | 71 non-migration files formatted |
| Scoped mypy | Success, no issues in 23 activation source files |
| Django checks | 0 issues under isolated test settings |
| Migration drift | No changes detected |
| JavaScript syntax | Passed for the privileged-submit controller |
| Fail-closed report | `Decision: blocked`; `Production privilege: hard_disabled`; G01-G14 pending without evidence |

The broader repository still has two known legacy mypy findings in `mnemex/store.py` and legacy Ruff/format debt outside this activation scope. `pip check` also reports an unrelated development-environment `opencv-python` / NumPy version mismatch; the runtime image dependency set does not install OpenCV.

## Activation gate ledger

Local contract evidence does not substitute for hosted or independently observed evidence.

| Gate | Current state | What remains |
|------|---------------|--------------|
| G01 Hosted configuration | Local validation complete | Observe the exact staging/production configuration without exposing values |
| G02 Shared auth controls | Atomic cache contracts complete | Run the multi-process suite against disposable TLS Redis |
| G03 MFA key rotation | SQLite and PostgreSQL rotation tests complete | Execute and record a staging rotation/restore rehearsal |
| G04 Security notifications | Queue-only allauth cutover, durable outbox, and worker complete locally | Verify authenticated SMTP handoff, retry, ambiguous-delivery review, and recovery mail in staging |
| G05 Privileged invitations | Automated and browser flows complete | Independent operator rehearsal with owner-approved staff records |
| G06 Staff recovery | Automated full ceremony and browser approval complete | Re-enroll a fresh factor and explicitly restore in the independent rehearsal |
| G07 Private object storage | Adapter and lifecycle tests complete | Verify private hosted bucket policy, create/read/delete integrity, and provider recovery |
| G08 Railway runtime | Process and build contracts complete | Build the image and observe separate staging web/worker services |
| G09 Hosted monitoring | PII-free health and queue metrics complete | Connect owner-selected hosted monitoring and observe alerts |
| G10 Recovery rehearsal | Synthetic restore contracts complete | Restore a provider backup into a pristine disposable target and reconcile object/key inventory |
| G11 Activation integrity | Report and offline signature tests complete | Owner-controlled signing key, signed evidence bundle, and independent verification |
| G12 Authority boundary | Contract retained | Confirm in final operating review that race day remains pinned and offline-capable |
| G13 Operator step-up | Live browser QA complete | Record fresh hosted browser evidence after staging deployment |
| G14 First operator rehearsal | Portal is ready | Independent human operator and approver complete the documented ceremony |

## Approved security-mail cutover

The owner explicitly approved `Approve queue-only security-mail cutover` on 2026-08-18 after the availability risk was disclosed. Generic django-allauth password, verified-contact, TOTP, and recovery-code security notices now create encrypted durable intents only; the request path never calls SMTP or falls back to immediate mail. Verified-recipient policy, exact replay, later security revisions, queue-failure auditing, real TOTP/password flows, and worker handoff are covered by isolated tests.

This approval closes the local implementation blocker only. A queue defect can still delay critical notices, so G04 remains pending until the staging SMTP and human recovery ceremony produce fresh evidence.

## Environment limitations observed

- No disposable Redis server was available, so the true cross-process atomic-cache gate remains pending.
- The Docker CLI was present but no Docker daemon was running, so the production image was not built locally.
- No Railway, Supabase, SMTP, monitoring, or backup-provider credentials were used.
- No hosted deployment or live canary was attempted.

## Next safe sequence

1. Run TLS Redis multi-process acceptance in a disposable environment.
2. Configure a staging-only Railway/Supabase/SMTP stack from the runbooks; keep production privilege disabled.
3. Build the image, migrate staging, verify the private bucket, and observe all worker queues.
4. Prove SMTP acceptance, safe retry, ambiguous-handoff review, and recovery mail with synthetic staging accounts.
5. Complete database/object/key recovery rehearsal in a pristine disposable target.
6. Run the independent first-operator invitation and recovery ceremony.
7. Collect fresh, redacted evidence; sign it offline; independently verify the report.
8. Make any production activation decision separately. No report or environment variable can enable privilege in the current code.

## Runbooks

- [Railway and Supabase](../runbooks/mnemex-railway-supabase.md)
- [Backup and restore](../runbooks/mnemex-backup-and-restore.md)
- [Security operations](../runbooks/mnemex-security-operations.md)
