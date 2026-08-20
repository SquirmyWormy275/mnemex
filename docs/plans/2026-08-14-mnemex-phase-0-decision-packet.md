# MNEMEX Phase 0 decision packet

**Status:** owner directions D0-1 through D0-12 approved on 2026-08-14. This packet
makes no production deployment, database provisioning, credential generation, or
PII import. The authoritative selections and their binding interpretations are in
`2026-08-14-mnemex-approved-build-decisions.md`.

**Purpose:** resolve the decisions that make the universal-profile architecture safe
to implement, then authorize Phase 1 identity and consent work.

Use the local collaborative workshop at `docs/phase-0-decision-workshop.html` to
record owners, decisions, rationale, and an exportable Phase 1 handoff. It is a
local-only artifact and does not collect competitor data or contact a network.

## Current factual baseline

- The repository is an alpha historical-archive prototype. Its identity service
  and STRATHMARK adapters deliberately raise NotImplementedError.
- Its only migration models competitors, results, ingestion runs, an old
  STRATHEX inbox, and a reconciliation queue. It does not model accounts,
  consent, portable packages, partner clients, audit events, provenance revisions,
  or durable result inbox semantics.
- The store uses independent Supabase REST calls. It is not evidence of the
  transaction boundary needed for atomic result reconciliation.
- Existing Supabase setup/RLS documents are unproven deployment proposals. No
  production credentials or project state were inspected or used.
- STRATHMARK's current trusted boundary is its local evidence snapshot and
  local ledger; MNEMEX must not be on the race-day network path.

## Approved decision record

D0-1 through D0-12 are closed. Their selected options and binding implementation
interpretations live in `2026-08-14-mnemex-approved-build-decisions.md`. This packet
retains the resulting safety deliverables, not another decision questionnaire.

## Required Phase 0 deliverables

### A. Privacy and data classification

Create a field catalogue with: field name, owner, purpose, sensitivity, source,
verification state, recipients, retention, deletion/hold rule, and whether it is
portable, local-only, pseudonymous STRATHMARK evidence, or prohibited.

Acceptance evidence:

- Every candidate field is explicitly classified.
- The initial profile projection is a subset of approved portable fields.
- The STRATHMARK export is mechanically shown to exclude all direct PII.
- Test fixtures are synthetic and isolated from production systems.

### B. Threat model and partner trust model

Document actors, assets, trust boundaries, abuse cases, controls, and owners for:
account takeover, identity-link error, unapproved disclosure, stolen partner key,
replayed package/request, package used for another event, malicious result source,
late/out-of-order correction, locked-roster compromise, and backup/key loss.

Acceptance evidence:

- Threats name an owner, mitigation, detection signal, and test.
- Partner onboarding produces a registered client and a revocation contact.
- No shared service-role key leaves MNEMEX.

### C. Cryptographic and contract spike

Implement only a non-production prototype using synthetic fixtures that proves:

1. canonicalization yields identical bytes in independent producer/consumer code;
2. a signed package verifies from a locally pinned keyset with no network;
3. wrong client, event, purpose, environment, expiry, payload, or key state fails;
4. exact duplicate import is idempotent;
5. replayed request is rejected while a permitted network retry is accepted; and
6. key rotation and emergency revocation have defined offline behavior.

The spike must select no algorithm by convenience. It records the approved
algorithm, key types, provider/library, trust distribution, rotation overlap,
revocation format, and test vectors once D0-6 is approved.

### D. Transaction and recovery spike

Against an isolated disposable database, prove a single transaction can write:
inbox message, message receipt, provenance assertion, career-record revision, and
outbox/retry state. Inject failure before each logical write. The only permitted
outcomes are a complete committed revision with receipt or a safely resumable
unapplied message; no partial career record may be visible.

### E. Legacy-data inventory

For each existing table/document/export field, record: classification, target
aggregate, migration action (map, re-review, pseudonymize, quarantine, delete), and
rollback evidence. Run dual-read/export comparison against synthetic fixtures.

## Phase 0 exit checklist

- [x] D0-1 through D0-12 have approved directions recorded in the build-decision record.
- [ ] Data classification and privacy retention schedule are approved.
- [ ] Threat model and partner trust model are reviewed.
- [ ] Signing/request-authentication contract and golden test vectors are approved.
- [ ] Transaction/recovery spike passes crash injection in an isolated database.
- [ ] Legacy inventory has a written no-silent-migration rule.
- [ ] Development, staging, and production boundaries are documented; no production credential entered a test or repository.
- [ ] Missoula and STRATHMARK owners confirm the offline/race-day boundary.

## Phase 1 authorization boundary

Phase 1 is authorized with synthetic development data. It may not collect/import
real competitor PII, create a production project, issue partner credentials, or
enable public career visibility until the production activation evidence in the
approved decision record is complete.

## Results Desk authorization boundary

Planning and a synthetic-data prototype for Gillian's hosted Results Desk are
authorized. A hosted production service, real source files, or real competitor
data additionally requires the approved
data classification, account/RBAC, transaction, recovery, and provider/RLS
evidence. The desk never writes STRATHMARK directly: reviewed prior results reach
it only through the existing explicit evidence-snapshot workflow.
