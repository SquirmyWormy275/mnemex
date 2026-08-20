# MNEMEX approved implementation plan

**Status:** ready for implementation sequencing with synthetic isolated data
**Architecture source:** `2026-08-14-mnemex-universal-profile-architecture.md`
**Decision source:** `2026-08-14-mnemex-approved-build-decisions.md`

## Outcome

Build MNEMEX as one hosted modular monolith that gives competitors a portable
identity and career profile, gives Gillian an integrated Results Desk, supports
multiple registered shows, and exports only reviewed prior SB/UH evidence to
STRATHMARK. Railway runs the application. Supabase supplies PostgreSQL and private
object storage. Shows pin local roster snapshots before race day.

The first implementation uses synthetic data only. Production PII is a later
activation gate, not an implicit consequence of merging code.

## What already exists

| Existing capability | Reuse decision |
| --- | --- |
| `mnemex/schema.py` canonical result concepts and discipline mappings | Reuse as input to the new result contracts; revise where the approved domain model differs. |
| `mnemex/identity.py` match/merge/split/redact API shape | Preserve the audited operation concepts; replace `NotImplementedError` paths with transaction-backed proposal/review services. |
| Ingestion adapters and spreadsheet dependencies (`pandas`, `openpyxl`) | Reuse parsers behind immutable source-artifact and ingestion-run boundaries. |
| Current Supabase REST store | Retire as a write boundary. Server-side Django/PostgreSQL transactions own authoritative writes. |
| Existing `competitors`, `results`, `ingestion_runs`, and reconciliation tables | Treat as legacy source data; inventory and bulk-migrate through staging/quarantine. |
| Existing STRATHMARK JSONL/adapters | Reuse only as contract evidence. The approved output is the explicit reviewed evidence snapshot, never a live database write. |
| Phase 0 decision workshop | Keep as the human decision record/export tool; it is not an application administration surface. |

## Selected application shape

Use Django 5.2 LTS and PostgreSQL as a modular monolith. “Build MNEMEX
authentication” means MNEMEX owns the accounts and UX while Django supplies the
maintained password, permission, session, CSRF, form, and migration primitives.
The project does not implement password hashing, cookie signing, or WebAuthn
cryptography itself.

```text
 Competitor / guardian       Gillian / staff        Participating shows
          |                        |                         |
          +------------------------+-------------------------+
                                   |
                         Railway HTTPS service
                    +--------------------------------+
                    | Django modular monolith        |
                    |                                |
                    | accounts + guardians           |
                    | identity + consent + profiles  |
                    | partners + online validation   |
                    | results desk + reconciliation  |
                    | career + public projection     |
                    | audit + privacy operations     |
                    +---------------+----------------+
                                    |
                    +---------------+----------------+
                    |                                |
          Supabase PostgreSQL              Private object storage
          transactions/RLS/audit           source files/evidence
                    |
                    +---- reviewed SB/UH snapshot ----> STRATHMARK local import

Participating show before lock: online validation -> local participant -> roster lock
Participating show after lock:  pinned local roster only, no MNEMEX dependency
```

Run web and worker process types from the same repository, image, migrations, and
domain code. The worker handles spreadsheet parsing, bulk migration, reconciliation,
outbox retries, and export generation. Do not split these into network services.

## Domain modules

| Module | Owns | Does not own |
| --- | --- | --- |
| Accounts | user credentials, sessions, recovery, MFA state, privileged roles | person verification or guardian authority |
| Identity | Person, aliases, encrypted legal claims, federation claims, merge/split/redaction revisions | show registration or event results |
| Guardianship and consent | guardian relationships, authority evidence, age transitions, grants, revocation, public opt-in | legal conclusions or show waivers |
| Partners and portability | organizations, clients, environments, pairwise show refs, projections, online validation receipts | event-local participant state after import |
| Results Desk | source artifacts, mappings, staged/published rows, validation failures, corrections | confident person links or STRATHMARK marks |
| Reconciliation and career | identity-link cases, source assertions, career revisions, disputes | alteration of a show's official result |
| STRATHMARK export | reviewed SB/UH eligibility, cutoff snapshot, digest/manifest | live sync, PII, post-cutoff mutation |
| Audit/privacy | immutable security/domain audit, access/export/redaction/hold workflows | operational business data mutation without the owning service |

## Core data model

All IDs are opaque UUID/ULID values. Mutable business objects carry a revision or
optimistic concurrency value. Source and audit records are append-only.

### Account and identity

- `UserAccount`: email/login identity, state, verification timestamps, security
  version; separate from `Person` so staff or guardians need not be competitors.
- `AccountCredential`: method, framework identifier, created/last-used/revoked state;
  never stores plaintext secrets.
- `PrivilegedRoleAssignment`: results manager, export reviewer, identity reviewer,
  privacy officer, partner administrator.
- `Person`: immutable person ID, account link state, merge/redaction state.
- `Alias`: value, source, confidence, review state, validity.
- `IdentityClaim`: typed encrypted value or keyed lookup token, source, verification,
  evidence reference, validity, dispute state.
- `LegalIdentityClaim`: legal-name components, birth attribute approved by the field
  catalogue, issuer/verification, encryption version, retention rule.
- `GuardianRelationship`: adult account, minor person, relationship/authority basis,
  verification, jurisdiction/policy version, effective and revoked dates.

### Consent, public visibility, and portability

- `ConsentGrant`: subject, acting account/guardian, recipient client, purpose,
  field groups, event/registration context, issued/expiry/revocation, policy version.
- `PublicProfileOptIn`: person, selected public fields/career scope, policy version,
  effective/revoked state; absent means private.
- `PartnerOrganization`, `PartnerClient`, `PartnerCredential`: tenant, environment,
  scopes, allowed origins, custodian, incident contact, rotation/revocation.
- `PortableProfileVersion`: immutable projection bytes/digest, grant, audience,
  purpose, expiry, show-person reference.
- `ValidationReceipt`: package/digest, client, decision, reasons, request ID,
  validation time, idempotency outcome.

### Results, migration, and career

- `SourceArtifact`: private object reference, SHA-256, original name, size/type,
  uploader, source organization, received time, retention class.
- `IngestionRun`: artifact/manual batch, parser/mapping version, idempotency key,
  counts, lifecycle, worker lease, error summary.
- `StagedResult`: source coordinates, raw normalized values, validation outcomes,
  proposed identity candidates; never public/exportable.
- `PublishedSourceResult`: immutable source result/revision and payload digest. A
  deterministic-valid row may be created automatically.
- `ReconciliationCase`: uncertain identity, mapping conflict, correction, or dispute;
  records proposals and human decisions.
- `CareerAssertionRevision`: person-linked reconciled copy, source revision,
  verification/display state, predecessor.
- `ExportEligibilityRevision`: SB/UH review decision, reviewer, cutoff eligibility,
  reason, predecessor; automatic publication cannot create this state.
- `LegacyMigrationRun`: source inventory/mapping version, checkpoints, counts,
  exception report, rollback manifest.
- `AuditEvent`: actor, action, target reference, correlation ID, before/after digests,
  policy/version, timestamp; no raw secret or unnecessary PII.

## Critical state machines

```text
RESULT INGESTION

created -> parsing -> validating
                       |      |
                       |      +-> quarantine -> corrected -> validating
                       |
                       +-> publishing -> published_source
                                           |
                         +-----------------+------------------+
                         |                 |                  |
                   identity case     career revision    SB/UH export review
                                                               |
                                                       eligible / rejected

IDENTITY LINK

unresolved -> proposed -> approved -> active -> disputed -> corrected/superseded
                    \-> rejected

PORTABLE PROFILE

draft -> consented -> issued -> validated online -> pinned by show -> expired/revoked
                                      |
                            no MNEMEX transition after show lock
```

## Transaction and idempotency rules

1. Authoritative mutations run inside one server-side PostgreSQL transaction.
2. Upload idempotency is `(source organization, artifact digest, mapping version)`.
   An exact retry returns the existing run. A different artifact cannot reuse the
   same operator key.
3. Published result identity is `(source organization, source result ID, source
   revision)`. Same identity plus changed payload opens a conflict.
4. Result inbox processing atomically writes inbox receipt, provenance assertion,
   career revision or reconciliation case, and retry/outbox state.
5. Validation receipt idempotency is `(client, request ID, package ID, digest)`.
6. Corrections append monotonically ordered revisions and never update original
   source bytes.
7. Workers claim durable jobs with leases and checkpoint bulk work. Restart resumes
   from the last committed batch without duplicate publication.

## Security and PII boundaries

- Use a custom Django user model in migration 0001. Changing it later is costly.
- Configure Argon2id first, password blocklist/length validation, generic login and
  recovery responses, throttling, CSRF protection, secure/HTTP-only/SameSite cookies,
  server-side sessions, session rotation, and sensitive-action reauthentication.
- Require MFA for results manager, export reviewer, identity reviewer, privacy
  officer, partner administrator, and superuser roles before production access.
- Encrypt legal identity, date/birth attributes, verified contact values, guardian
  evidence, and private source artifacts with versioned key references.
- Keep pairwise show references and pseudonymous STRATHMARK IDs distinct from the
  internal person ID.
- Keep Supabase secret/service credentials only in Railway server/worker processes.
  Browser requests never receive them and every exposed table has explicit grants
  and RLS.
- Store uploaded workbooks in a private bucket. Validate extension, MIME, size,
  decompression limits, parser limits, and malware policy before parsing.
- Log references and digests, not passwords, tokens, contacts, legal names, birth
  attributes, workbook cell contents, or portable-profile payloads.

## Results Desk operator flow

```text
Gillian uploads XLSX/CSV or opens manual-entry grid
  -> select source show/event and mapping template
  -> preview columns and validation results
  -> submit once
  -> worker parses and validates every row
  -> valid rows publish automatically in one run with row-level outcomes
  -> invalid rows remain quarantined with actionable messages
  -> Gillian corrects mapping/data and retries only failed rows
  -> identity cases remain separate from source publication
  -> export reviewer explicitly approves eligible prior SB/UH rows
  -> MNEMEX produces a cutoff-bound snapshot for STRATHMARK import
```

The manual-entry grid writes a `SourceArtifact`-equivalent batch manifest so manual
and spreadsheet rows have the same provenance, validation, correction, and
idempotency behavior.

## Deployment and recovery

- Railway services: `web` and `worker`, same immutable build; release command applies
  forward-only migrations once. Health endpoint verifies process readiness without
  leaking dependency detail.
- Supabase: PostgreSQL primary and private Storage buckets. Application traffic uses
  server-side database credentials; browser access is limited by explicit RLS or
  routed through Django.
- Environments: isolated local/test, staging, production projects and credentials.
  Test configuration refuses non-local/non-ephemeral databases.
- Recovery: database PITR/logical backup plus a separate versioned object backup.
  Supabase database backups do not contain Storage objects, so a restore is not
  successful until artifacts, database references, digests, and permissions all
  reconcile.
- Deployment order: backup/restore point -> migrate -> web/worker rollout -> smoke
  checks -> worker enablement. Rollback uses application rollback compatible with
  forward schema, not destructive down migrations.

## Implementation phases and objective gates

### Phase A: project and transaction foundation

- Add Django 5.2 LTS project, settings split, custom user model, PostgreSQL access,
  migrations, health check, web/worker entry points, and isolated test settings.
- Add audit primitives, service-layer transaction wrapper, idempotency records, and
  synthetic factories.
- Gate: test suite proves it cannot connect to configured staging/production hosts;
  crash injection proves all-or-nothing transaction behavior.

### Phase B: accounts, minors, legal identity, and consent

- Build account verification/recovery/MFA, Person/claims, guardian authority,
  age-transition, consent grants, public opt-in, merge/split/redaction, and access
  request foundations.
- Gate: authorization matrix tests cover competitor, guardian, minor transition,
  results staff, reviewer, identity reviewer, privacy officer, and partner clients;
  no ungranted field is disclosed.

### Phase C: integrated Results Desk and bulk migration

- Build private upload/manual entry, mapping templates, validation preview, durable
  worker pipeline, automatic source publication, quarantine, corrections, and
  versioned legacy migration.
- Gate: exact re-upload is idempotent; mixed valid/invalid batches have explicit
  row outcomes; invalid identity never auto-links; kill/restart resumes without
  duplicate rows; source-file and database restore reconcile by digest.

### Phase D: career reconciliation and opt-in public profiles

- Build reconciliation queue, career revisions, dispute/correction flow, competitor
  claim/review experience, and opt-in public pages.
- Gate: public pages show only opted-in approved fields and reconciled career facts;
  revocation and guardian/age changes apply correctly without deleting audit history.

### Phase E: multiple shows, online portability, and offline lock

- Build partner/client administration, pairwise references, grants, projection,
  online validation receipts, two sandbox show tenants, and reference adapter.
- Gate: cross-tenant access fails; changed/expired/wrong-purpose/wrong-event/replayed
  packages fail; exact retry succeeds idempotently; a show completes the full event
  rehearsal after network loss at lock.

### Phase F: show result reconciliation and STRATHMARK export

- Build authenticated show result inbox/outbox contract, correction chains, export
  review, and explicit pseudonymous SB/UH cutoff snapshot.
- Gate: duplicate/reordered/conflicting corrections converge visibly; STRATHMARK
  receives no direct PII or unsupported discipline; automatic publication alone
  never reaches the export; past STRATHMARK receipts remain immutable.

### Phase G: production activation and pilot

- Complete policy parameters, threat model, penetration/security review, data-rights
  review, RLS review, recovery/retention approval, restore rehearsal, monitoring,
  access review, incident runbooks, and pilot rehearsal.
- Gate: every production activation item in the approved decision record has named
  evidence and owner sign-off. Only then provision real competitor accounts/data.

## Test coverage plan

```text
ACCOUNT AND CONSENT
  [PLAN] create/verify/login/logout/recovery/MFA/session rotation
  [PLAN] generic errors and throttling resist account enumeration
  [PLAN] guardian grants, revocation, authority loss, minor becomes adult
  [PLAN] legal identity never appears in logs/public/show projection without grant

RESULTS DESK [E2E]
  [PLAN] upload -> map -> preview -> automatic publish -> row report
  [PLAN] invalid/malicious/oversized/corrupt workbook -> quarantine + clear recovery
  [PLAN] duplicate submit, two tabs, worker crash, retry, mapping-version change
  [PLAN] manual entry follows identical provenance and correction path

LEGACY MIGRATION
  [PLAN] checkpoint/restart, ambiguous names, conflicting federation IDs, rollback
  [PLAN] source/published counts and digests reconcile without silent drops

PORTABILITY [E2E]
  [PLAN] grant -> projection -> online validation -> local import -> roster lock
  [PLAN] expiry/revocation before lock; outage before lock; outage after lock
  [PLAN] two shows receive non-correlatable refs and cannot cross-read

RECONCILIATION
  [PLAN] exact retry, changed-payload conflict, out-of-order correction, pair/team result
  [PLAN] transaction crash at every write boundary yields full commit or resumable state

STRATHMARK CONTRACT [E2E]
  [PLAN] reviewed prior SB/UH -> snapshot -> local import -> expected digest/data
  [PLAN] unreviewed, post-cutoff, PII, unsupported discipline, correction-after-cutoff rejected
```

Every behavior starts RED, then the minimum GREEN implementation, then refactor.
Database tests use disposable PostgreSQL only. No test reads or writes a Supabase
staging/production project.

## Production failure modes

| Failure | Required behavior | Planned evidence |
| --- | --- | --- |
| Railway web unavailable before roster lock | Show sees a clear retry/manual-registration path; no partial import. | Portability outage E2E. |
| MNEMEX unavailable after lock | Event continues from local snapshot without warning loops or background mutation. | Network-loss race-day rehearsal. |
| Worker dies during 10,000-row import | Lease expires and resumes at checkpoint; committed rows deduplicate. | Kill/restart integration test. |
| Automatic mapping is wrong | Row is traceable to artifact/cell/mapping version; correction appends a revision. | Mapping-change/conflict tests. |
| Two legacy people have the same name | Source rows publish, person link stays unresolved. | Ambiguous identity tests. |
| Database restores but workbook object does not | Recovery reconciliation reports missing digest and blocks affected provenance/export. | Database-plus-object restore drill. |
| Service credential leaks | Credential revoked/rotated, sessions and jobs reviewed, incident scope queryable without secrets in logs. | Credential-compromise tabletop and rotation test. |
| Guardian authority changes | Future grants stop; public/private projections and audit follow the approved policy. | Guardian revocation/transition tests. |
| Unreviewed row approaches STRATHMARK | Export query excludes it by database constraint/service rule. | Negative export contract test. |

## Workstream order

| Lane | Work | Depends on |
| --- | --- | --- |
| A | Django/test foundation -> accounts/security -> guardian/consent | none, then sequential shared schema |
| B | Result contract fixtures -> parser/mapping validation prototypes | Phase A contracts and test isolation |
| C | Partner/portable contract fixtures -> show adapter fixtures | Phase A identifiers and consent model |
| D | Deployment manifests -> staging recovery scripts/runbooks | Phase A application entry points |

After Phase A merges, B, C, and D can proceed in parallel while A continues account
and consent work. Results persistence waits for the shared domain migrations. Public
profile work waits for identity/consent. STRATHMARK work waits for Results Desk and
career reconciliation. Parallel lanes must not edit the same migrations.

## NOT in scope

- Live MNEMEX access during race-day operations.
- Direct MNEMEX writes to a show database or STRATHMARK database.
- Show registration, entries, waivers, payments, partner selection, scoring,
  official results, or operational eligibility decisions.
- Automatic identity merging from names, fuzzy scores, or bulk migration.
- Exporting non-SB/UH disciplines to the current STRATHMARK model.
- Default-public profiles or legal identity on public pages.
- A separate Results Desk microservice, Supabase dashboard as the operator product,
  or browser-held service credentials.
- General OAuth/OIDC provider duties, a digital wallet, or custom cryptographic
  algorithms.

## Architecture completion gate before feature code

Feature implementation begins only after the architecture, approved decision
record, and this implementation plan agree on:

- online pre-lock validation and local post-lock authority;
- automatic source publication versus reviewed trust/export states;
- custom MNEMEX accounts using maintained framework primitives;
- multiple-show tenant isolation;
- bulk legacy migration through quarantine;
- Railway/Supabase boundaries and separate object recovery;
- synthetic-only test isolation.

Those points are now aligned. The next code change is Phase A, starting with the
isolated failing tests and Django custom-user migration, not a production deploy.

## Implementation status

Phase A's local code foundation was implemented on 2026-08-14. Its isolated unit
and disposable-PostgreSQL gates are green. Exact evidence and the unchanged
production boundary are recorded in
`2026-08-14-mnemex-phase-a-implementation-status.md`.

Phase B slice 1 (person, encrypted legal identity, guardian authority, partner
tenancy, consent, public opt-in, and the initial authorization matrix) is also
implemented locally. The remaining Phase B workflows and exact verification
evidence are recorded in `2026-08-14-mnemex-phase-b-slice-1-status.md`; Phase B as
a whole is not yet closed.
