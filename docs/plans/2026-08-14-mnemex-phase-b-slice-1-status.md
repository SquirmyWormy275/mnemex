# MNEMEX Phase B slice 1 status

Date: 2026-08-14

## Outcome

The first Phase B identity and consent slice is implemented locally. It builds the
domain and authorization boundary needed before account UX, portable-profile APIs,
or the Results Desk can disclose competitor data.

Implemented:

- `Person` is separate from `Account`; staff and guardians need not be competitors;
- opaque person IDs, age classification/policy version, lifecycle state, and
  optimistic revision values;
- aliases with source, confidence, review, validity, and explicit public/private
  state;
- legal identity claims stored only as AES-256-GCM authenticated ciphertext with a
  versioned key reference and HMAC-SHA256 lookup token;
- strict legal-identity field catalogue and ISO birth-date validation;
- guardian relationships with jurisdiction, policy, evidence reference,
  verification, validity, and revocation state;
- multiple-show organization/client registry with environment, purpose, and field
  group bounds;
- purpose-, recipient-, context-, field-, expiry-, and policy-bound consent grants;
- private-by-default public profiles with a narrow public field allowlist;
- adulthood transition that atomically revokes guardian authority, guardian-issued
  grants, and guardian-issued public opt-ins;
- all five privileged role assignments, ineffective until MFA enrollment and
  mutually scoped by the authorization matrix;
- live disclosure checks that reload and lock grant, person, partner client, and
  optional guardian state before returning any field;
- PII-minimized audit events for consent issue/revocation, public opt-in, and age
  transition.

No encryption key is loaded from production configuration. Tests inject synthetic
keys; production key custody remains a separate activation gate.

## Verification evidence

| Check | Result |
| --- | --- |
| Focused Phase B SQLite suite | 19 passed |
| Combined Phase A+B disposable PostgreSQL 18 suite | 40 passed |
| Repository suite excluding versioned STRATHMARK contract | 120 passed, 42 skipped, 3 deselected |
| Full repository suite | 122 passed, 42 skipped, 1 failed |
| Known full-suite failure | legacy MNEMEX contract pins STRATHMARK `<0.6`; installed STRATHMARK is 2.0.0 |
| Migration drift | no changes detected |
| Django system checks | 0 issues |
| Ruff | lint and formatting passed for 48 scoped files |
| Mypy | 26 Phase A+B source files passed with Django stubs |

PostgreSQL verification caught and fixed a backend-specific locking bug: a joined
`FOR UPDATE` attempted to lock the nullable guardian side. The implementation now
locks the grant, person, client, and optional guardian as explicit rows. The final
PostgreSQL run passed, after which the server was stopped and its verified temp
cluster directory removed.

## Gate assessment

This slice passes its implemented authorization and non-disclosure contracts, but
the complete Phase B gate is not yet closed. Remaining Phase B work includes:

- email verification, generic recovery responses, session rotation, throttling,
  sensitive-action reauthentication, and an actual maintained MFA flow;
- guardian evidence submission/review and jurisdiction-specific age policy;
- generic/federation claims plus reviewed merge, split, dispute, and redaction;
- privacy access/export/hold requests;
- production encryption-key custody, rotation, backup, and restore evidence;
- production RLS and independent authorization tests.

This status does not authorize real PII, a public profile, partner credentials, or
deployment.
