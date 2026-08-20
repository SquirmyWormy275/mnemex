# MNEMEX approved build decisions

**Decision date:** 2026-08-14
**Status:** authoritative build direction
**Source:** owner-exported MNEMEX build handoff

These decisions replace the recommendations in the Phase 0 workshop. The selected
option is authoritative even where it was not the recommended option.

“Approved” means implementation may proceed with synthetic, isolated data. It does
not authorize production PII, credentials, public access, or a pilot until the
objective activation evidence listed below exists.

## Selected options

| ID | Approved selection | Architectural consequence |
| --- | --- | --- |
| D0-1 | C: Include minors in the first pilot | Guardian relationships, age-aware consent, revocation, access, retention, and correction flows are Phase 1 requirements. |
| D0-2 | B: Expanded profile including legal identity | Legal identity is an encrypted claim set separated from display identity, public pages, logs, and show projections. |
| D0-3 | B: Opt-in public pages in pilot | Public career pages exist in the pilot but remain disabled per competitor until explicit opt-in. |
| D0-4 | C: Build MNEMEX authentication | MNEMEX owns accounts, sessions, recovery, MFA, and security audit. It uses maintained framework primitives and does not invent password/session cryptography. |
| D0-5 | B: Multiple shows from the start | Organization isolation, client registration, revocation, and pairwise show references exist in the first schema. At least two show tenants participate in portability conformance. |
| D0-6 | B: Online validation only | Portable projections are validated online during registration and immediately before roster lock. The show then pins a local snapshot and makes no MNEMEX call on race day. |
| D0-7 | A: Server-side transaction boundary | Inbox, provenance, career revision, receipt, and outbox effects commit in one server-side PostgreSQL transaction. |
| D0-8 | A: Approve recovery and retention before production PII | Production PII waits for approved RPO/RTO, retention schedule, database restore, object restore, key recovery, and deletion/hold tests. |
| D0-9 | B: Bulk-migrate legacy history first | Legacy data is bulk processed before pilot career activation, but passes through immutable staging/quarantine and never auto-links ambiguous identities. |
| D0-10 | A: Integrated MNEMEX Results Desk | One Railway-hosted MNEMEX modular monolith provides the Results Desk; Supabase supplies PostgreSQL and private object storage. |
| D0-11 | A: Capture broad results; export reviewed SB/UH only | The archive accepts broad disciplines. STRATHMARK receives only reviewed, eligible, prior SB/UH rows through its explicit snapshot contract. |
| D0-12 | C: Automatic publish after upload | Deterministic-valid source rows automatically publish to the archive. Identity reconciliation, career verification, public projection, and STRATHMARK export eligibility remain separate states. |

## Binding interpretations

### Online validation and race day

Online-only validation applies before roster lock. A participating show stores the
exact portable projection, MNEMEX validation receipt, local participant mapping,
and its own roster digest. After lock, the show does not query, refresh, or mutate
MNEMEX state. If MNEMEX is unavailable before lock, the show follows its local
manual-registration policy; if unavailable after lock, there is no operational
effect.

### Automatic publication and reviewed export

Automatic publication is not automatic trust escalation:

```text
source file / manual entry
          |
          v
deterministic validation ---- failure ----> quarantine
          |
          v
published source row
          |
          +---- identity uncertain -------> reconciliation case
          |
          +---- career use ---------------> reconciled career assertion
          |
          +---- public page --------------> competitor opt-in projection
          |
          +---- STRATHMARK ---------------> human-reviewed SB/UH export eligibility
```

Exact duplicate uploads return the existing outcome. A changed payload with the
same source identity becomes a correction/conflict, not an overwrite.

### Bulk migration

“Bulk migrate first” means run the entire eligible legacy corpus through a versioned
staging and reconciliation pipeline before pilot career activation. It does not
mean copying legacy rows directly into Person or CareerRecord, accepting fuzzy
matches automatically, or deleting the source corpus. Every migrated row retains
source identity, source digest, parser/mapping version, migration run, and review
state.

### MNEMEX-owned authentication

MNEMEX owns the product and database boundary for authentication. The implementation
uses Django 5.2 LTS authentication/session primitives, a custom user model created
in the first migration, Argon2id password storage, generic authentication errors,
rate limits, rotating server-side sessions, verified recovery channels, and
mandatory MFA for privileged staff. WebAuthn/passkeys may be added behind the same
credential model; MNEMEX does not implement cryptographic algorithms itself.

## Production activation evidence still required

These are parameters and proofs, not reopened product choices:

- Named jurisdiction policy, pilot age rules, guardian verification/authority,
  consent wording, withdrawal handling, and minor-to-adult transition.
- Approved legal-identity field catalogue with purpose, recipient, retention,
  verification level, public/private status, and deletion/hold rule per field.
- Authentication threat model, recovery policy, staff MFA enforcement, abuse-rate
  limits, session lifetimes, and independent security review.
- Named participating shows, client custodians, incident contacts, allowed origins,
  environments, and revocation process.
- Online validation timeout/fallback policy and a complete offline-after-lock show
  rehearsal.
- RPO, RTO, database retention, object-storage retention, restore cadence, and
  successful database-plus-object restore rehearsal.
- Legacy source inventory, data-rights basis, migration mapping version, identity
  review thresholds, exception owner, reconciliation report, and rollback proof.
- Upload schema/mapping acceptance thresholds and the exact rule that promotes a
  published SB/UH row to STRATHMARK export eligibility.

Until those exist, development and automated tests use isolated databases and
synthetic fixtures only.

## References used for security/provider constraints

- Django 5.2 is an LTS line supported through April 2028:
  https://www.djangoproject.com/download/
- Django password and session primitives:
  https://docs.djangoproject.com/en/5.2/topics/auth/passwords/
  and https://docs.djangoproject.com/en/5.2/topics/http/sessions/
- OWASP authentication, password-storage, and session guidance:
  https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Supabase Data API and Storage require grants/RLS; service credentials bypass RLS
  and must remain server-side:
  https://supabase.com/docs/guides/api/securing-your-api and
  https://supabase.com/docs/guides/storage/security/access-control
- Supabase database backups do not restore Storage objects, so source-file recovery
  needs a separate verified mechanism:
  https://supabase.com/docs/guides/platform/backups
