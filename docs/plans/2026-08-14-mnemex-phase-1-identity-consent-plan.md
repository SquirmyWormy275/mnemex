# MNEMEX Phase 1 identity and consent implementation plan

**Status:** authorized for implementation with synthetic isolated data. Production
PII and pilot activation remain gated by the evidence in
`2026-08-14-mnemex-approved-build-decisions.md`.

**Goal:** establish MNEMEX-owned person, claim, consent, audit, and privacy
boundaries using synthetic data only. This phase does not integrate a live show,
issue a portable package, or ingest real competitor PII.

## Implementation units

### U1 — Isolated development and test boundary

**Owner:** MNEMEX

Create an explicit application configuration model for development and test. Tests
must use disposable databases and synthetic fixtures only; missing test configuration
fails closed rather than falling back to an environment-provided MNEMEX URL.

**Verification:** a test proves production-like environment variables are rejected
by the test harness; a second proves each test database is unique and discarded.

### U2 — New identity and claim schema

**Owner:** MNEMEX

Create forward-only migrations for Person, Alias, encrypted LegalIdentityClaim,
IdentityClaim, GuardianRelationship, verification evidence metadata,
ProfilePreference, and immutable audit event. Preserve legacy competitors/results
unchanged; map them only through the separately versioned bulk-migration staging
pipeline.

**Verification:** constraints prove immutable person IDs, unique active federation
claim policy, alias provenance, claim-state transitions, and append-only audit
writes. Merge/split/redaction are revisioned operations, not table rewrites.

### U3 — Consent and recipient schema

**Owner:** MNEMEX

Create ConsentGrant, GuardianAuthorization, PublicProfileOptIn, PartnerShow,
ClientRegistration, AccountCredential metadata, and package issuance/validation
ledger models. Enforce subject/guardian authority, recipient, purpose, field group,
event/registration context, environment, issuance, expiry, revocation, policy
version, and retention rule.

**Verification:** authorization tests cover no grant, wrong recipient, wrong event,
expired/revoked grant, incomplete field permission, and approved exact scope.

### U4 — Identity-review service

**Owner:** MNEMEX

Replace placeholder identity functions with a conservative review workflow. Exact or
fuzzy matching may create a proposal only. First-name-only, competing federation
ID, merged identity, and consequential match cases require human approval and an
audit event. No automatic linkage reaches a portable profile or career record.

**Verification:** tests cover create/link/reject/merge/split/redact and prove every
identity-changing action has actor, reason, timestamp, and predecessor reference.

### U5 — MNEMEX account and grant boundary

**Owner:** MNEMEX

Create the Django 5.2 LTS application boundary and custom user model in the first
migration. Use maintained Django authentication/session primitives, Argon2id,
verified email/recovery flows, generic error responses, login throttling, server-side
session rotation, sensitive-action reauthentication, and mandatory MFA for
privileged staff. Add browser-mediated grants and guardian authorization. MNEMEX
owns this account system but does not become a third-party OAuth provider or
implement cryptographic primitives itself.

**Verification:** test enumeration resistance, password hashing configuration,
login throttling, session fixation/expiry/revocation, failed and replayed recovery,
staff MFA, guardian loss/change of authority, client/origin mismatch, and a complete
consent audit trail.

### U6 — Contract library and audit observability

**Owner:** MNEMEX

Create versioned Python contract models for portable-package headers, purpose,
recipient/event/environment binding, online validation receipts, package-issuance
records, request IDs, and audit events. The actual partner validation endpoint is
Phase 2; Phase 1 fixes its data model and idempotency rules.

**Verification:** schema tests reject unknown fields/versions and store safe
structured audit metadata without contact values or complete package payloads in
logs.

## Explicitly deferred

- Portable-profile signing/issuance and show import: Phase 2.
- Local roster snapshot, roster lock, and race-day rehearsal: Phase 3 in the show.
- Show result outbox/inbox/career reconciliation: Phase 4.
- STRATHMARK evidence export: Phase 5.
- Real PII and production provisioning require later evidence gates. Public career
  pages, broad results intake, and federation bulk migration are approved later
  phases, not Phase 1 work.

## Definition of done

- U1-U6 pass in isolated test databases with synthetic data.
- Legacy tables remain readable and untouched by the new services.
- The identity/consent API cannot disclose a field without a matching active grant.
- Audit events are append-only and carry no forbidden PII in logs.
- There is no production credential, show credential, or live external dependency
  in the default test suite.
- A handoff explains the Phase 2 dependency on the approved signing profile and
  registered Missoula sandbox client.
