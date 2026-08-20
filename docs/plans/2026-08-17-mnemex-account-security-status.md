# MNEMEX account security vertical slice status

**Status:** implemented and exercised locally with synthetic accounts; not production-enabled
**Date:** 2026-08-18

## Outcome

MNEMEX now owns an invite-only account flow built on maintained
`django-allauth[mfa]` primitives. A privileged browser must present a verified
email address, an active TOTP authenticator, a matching account security
revision, and a recent MFA authentication record stored in that exact
server-side session.

The browser requirement is intentionally separate from durable worker
authorization. Results and migration services revalidate the account, role,
tenant, verified email, and real authenticator without inventing a browser
session for background work.

## Implemented locally

- email-only, closed public signup and mandatory verified-email flow;
- password login followed by TOTP or a one-use recovery code;
- TOTP and recovery material encrypted through a versioned AES-GCM adapter;
- QR-code enrollment that becomes active only after a valid challenge;
- atomic cache claims spanning the complete TOTP tolerance window and
  row-locked one-use recovery-code consumption;
- best-effort application throttles for login/recovery flows, pending the
  hosted shared-cache and edge-rate-limit gate;
- MFA-only step-up before enrolled accounts can change passwords, email, TOTP,
  or recovery codes; password-only reauthentication cannot replace a factor;
- fully canonical, case-insensitively unique account email identities;
- fail-soft, audited security-notification delivery so a mail outage cannot
  split TOTP and recovery-code enrollment;
- security-version binding so password, recovery, or factor changes invalidate
  existing Django sessions;
- session-key rotation after MFA use;
- an eight-hour maximum privileged-session proof and a five-minute maximum for
  every privileged POST;
- fresh account, role, tenant, email, and authenticator checks on each
  privileged request or durable worker action;
- PII-free append-only audit events for verification, enrollment, use, failure,
  removal, reset, password change, and password recovery;
- operator-facing login, challenge, enrollment, recovery, and Security pages;
- production privileged authorization remains hard-disabled.

`mfa_enrolled_at` is compatibility metadata, not session proof. A password-only
session cannot reach Results Desk, identity review, export review, or legacy
migration workspaces even when that timestamp is present.

## Objective local evidence

| Check | Result |
| --- | --- |
| MFA/account and canonicalization-migration contract | **32 passed on PostgreSQL; 31 passed and 1 PostgreSQL-only skip on SQLite** |
| Full isolated SQLite suite | **416 passed, 49 skipped in 59.48s** |
| Disposable PostgreSQL MFA plus privileged portals | **58 passed in 19.25s** |
| Django system check | **0 issues** |
| Migration drift | **No changes detected** |
| Scoped Ruff | **Clean** |
| Scoped Mypy | **No issues in 16 source files** |

The PostgreSQL cluster used a synthetic database on loopback, was stopped after
the run, and its exact temporary data directory was removed. No real account,
PII, credential, email delivery service, or hosted database was used.

The contract tests cover password-only denial, a real password-to-TOTP login,
proof isolation across two browser sessions, exact freshness boundaries,
five-minute privileged mutation freshness, MFA-only account-security step-up,
session rotation, logout, security-version invalidation, live role revocation,
factor removal, email canonicalization, closed signup, recovery response
equivalence, notification failure, one-use recovery codes, concurrent TOTP and
PostgreSQL recovery-code claims, ciphertext tamper rejection, and the
production-disable gate.

## Production activation gates

Local correctness does not authorize hosted accounts. Before enabling
`MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED`, the owner must approve and prove:

- a shared cache whose `add` operation is proven atomic across every web process
  for TOTP claims, plus a separate shared/edge rate-limit control because
  allauth's application throttle is best-effort under concurrency;
- production mail delivery, verified sender configuration, bounce monitoring,
  and recovery-response abuse monitoring;
- MFA encryption-key generation, custody, rotation, backup, recovery, and
  retirement rehearsals without plaintext fallback;
- an approved privileged-account invitation and staff factor-recovery policy;
- session revocation/incident response, security-event alerting, and an
  independent authentication threat-model review;
- Railway process/static configuration, secrets injection, database migrations,
  deploy smoke checks, rollback, and recovery rehearsal;
- the existing jurisdiction, minor/guardian, PII, retention, object-storage,
  RPO/RTO, and public-profile gates.

Until those gates pass, production privileged operations remain unavailable.
The local implementation does not create a race-day network dependency: shows
still operate from their pinned local roster/profile snapshot after roster lock.

## Deferred operator step-up UX

The server rejects privileged POST requests once the five-minute MFA proof has
expired. The current redirect does not preserve form fields or uploaded file
bytes. An operator must reauthenticate, re-enter manual values, and reselect a
workbook. A body-preserving pre-submit step-up workflow is required before this
is presented as a polished hosted operator experience.
