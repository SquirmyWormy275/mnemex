# MNEMEX universal competitor profile architecture

**Status:** build direction approved on 2026-08-14; no feature implementation has started.

The authoritative selections are recorded in
`2026-08-14-mnemex-approved-build-decisions.md`. Selection resolves product and
architecture direction. Production activation still requires the concrete policy,
security, recovery, and migration evidence named by the acceptance gates.

## Decision

MNEMEX is the STRATHEX ecosystem's universal competitor identity,
portable-profile, career-history, and provenance system. A competitor keeps one
MNEMEX profile and, with explicit consent, carries a purpose- and event-bounded
projection into a participating show.

MNEMEX is a normal pre-event registration/preparation dependency, but never a
live-network race-day dependency. Before roster lock, the show validates the
profile projection online with MNEMEX, records the returned validation receipt,
and creates its own local participant and roster records. At lock, the show pins
those records and its own snapshot digest. After lock, operations use only that
local snapshot and do not revalidate against MNEMEX. Finalized results and
approved corrections return through a durable, idempotent outbox.

| System | Authoritative state |
| --- | --- |
| MNEMEX | person identity, aliases, federation IDs, consent, portable-profile versions, verified claims, and provenance-backed career history |
| Participating show | registration, entries, partners, waivers, payments, event-specific eligibility decisions, roster, marks, scoring, official results, publication, and payouts |
| STRATHMARK | reproducible predictions, evidence snapshots, calculation receipts, and numeric settlement/void revisions |

No system overwrites another system's authoritative state. References and
reconciled copies are allowed; authority does not transfer.

## Evidence and conflict resolution

This architecture follows: (1) current executable contracts, (2) Missoula
docs/DOMAIN_CONTRACT.md, (3) current STRATHMARK V2/Shadow/offline/deployment
contracts, (4) current source docs, then (5) historical/archived material.

| Existing proposal | Status | Resolution |
| --- | --- | --- |
| MNEMEX is historical-only | Retired | It now owns the portable person/profile and reconciled career record in addition to historical ingestion. |
| JSONL/git is MNEMEX canonical storage | Retired | JSONL remains an export, not an access-controlled transactional identity/consent store. |
| Existing Supabase schema is proven production authority | Unverified | It is a prototype proposal until deployment, RLS, backup/restore, and incident controls are demonstrated. |
| Live Supabase sync is required on race day | Retired | Show and STRATHMARK operate from verified local snapshots. |
| Numeric LLM/cascade and same-tournament weighting | Retired for marks | Current STRATHMARK V2 prior-only contract prevails. |
| STRATHEX generic platform concept | Retired as architecture source | Preserve the Missoula operating workflow rather than speculative SaaS extraction. |

The current MNEMEX schema, ingestion work, aliases/federation IDs, and provenance
ideas are migration inputs, not fixed requirements.

## Invariants

1. person_id is opaque, immutable, non-reassignable, and never derived from
   name, email, or a federation/show ID.
2. MNEMEX retains private profile data; a show receives only fields covered by a
   current consent grant for its declared purpose.
3. A show maps show_person_ref to its own local participant ID and never
   exposes it publicly or uses it as its primary key.
4. The event-local roster snapshot is the only profile source during race-day
   operation.
5. MNEMEX updates never mutate a locked roster. Later changes are either a
   future import or a show-owned auditable local correction.
6. MNEMEX provides claims/evidence; show officials make final event eligibility
   decisions.
7. Every integration message contains actor, timestamp, schema version,
   idempotency key, correlation ID, payload digest, and immutable audit event.
8. Corrections append revisions. They never erase source result history.
9. PII, waivers, payments, medical data, and private notes never enter
   STRATHMARK's evidence contract.

## Context

    Competitor -> MNEMEX: profile + consent
    MNEMEX -> Show: authorized profile projection + online validation receipt
    Show -> Event operations: pinned local roster; no network required
    MNEMEX -> STRATHMARK: pseudonymous prior-result export
    STRATHMARK -> Event operations: receipts and numeric revisions
    Event operations -> MNEMEX: finalized results/corrections via durable outbox
    MNEMEX -> Competitor: reconciled career history

## Domain model

| MNEMEX aggregate | Required fields and rules |
| --- | --- |
| Person | person_id, account state, merge/redaction state. A merge creates a tombstone/alias chain and never reuses an ID. |
| IdentityClaim | type, encrypted/hashable value, issuer, verification state, evidence ref, valid period. Includes federation IDs and verified contacts. |
| Alias | display value, source, confidence, review status. Alias alone is never identity proof. |
| ProfilePreference | accessibility, communication, display, competitive preferences, classified by purpose. |
| ConsentGrant | subject, recipient show/client, purpose, permitted field groups, issuance/expiry/revocation, retention acknowledgement, user/policy evidence. |
| PortableProfileVersion | projection policy, contents digest, issued/expiry, immutable version, and online validation state. |
| PartnerShow / ClientRegistration | partner organization, approved environments/origins, scopes, client status, authentication credentials, contacts, and revocation/rotation history. |
| AccountCredential | MNEMEX account authentication method, recovery/MFA policy reference, active/revoked state, and security audit references. |
| CareerRecord | source result/revision refs, discipline, participation role, status; reconciled copy only. |
| ProvenanceAssertion | source system/ref/revision, payload digest, evidence locator, ingestion/reconciliation identity. |
| ReconciliationCase | inbound message, validation/conflict state, decision/audit record; cannot change the show source record. |

| Show aggregate | MNEMEX reference | Show authority |
| --- | --- | --- |
| LocalParticipant | optional show_person_ref, source package digest | local display/contact copy, event joins, local verification |
| EventRosterSnapshot | package manifest/digests and issuer verification | local snapshot, lock state, event audit |
| Registration / Entry | optional participant link | entries, division, waiver, payment, acceptance |
| EligibilityDecision | optional claim evidence ref | event-specific decision, reason, reviewer, appeal |
| CompetitionOutcome | local participant and roster snapshot | marks, outcomes, scoring, officialization, corrections |
| ReconciliationOutboxItem | source result/revision + digest | durable post-event delivery state |

| Identifier | Scope |
| --- | --- |
| person_id | internal MNEMEX person record; never public/show-primary |
| show_person_ref | pairwise opaque reference for one approved show; not correlatable across shows |
| profile_version_id / package_id | immutable MNEMEX projection validated online before lock |
| event_roster_snapshot_id | local show/event lock boundary |
| show_result_id + source_result_revision_id | authoritative show outcome and correction chain |
| career_record_id | MNEMEX reconciled record, referring to source IDs |

## Identity, verification, and consent

Account authentication, identity verification, and competitive identity resolution
are separate. Account control enables profile access; evidence verifies particular
claims when needed; matching links aliases/federation records to a person.
Matching may propose links, but first-name-only, ambiguous, or consequential links
require human review. Preserve the existing merge/split audit concept and add
claim states: unverified, self_asserted, source_asserted, verified, expired,
revoked, and disputed.

Consent is a concrete grant, not a global share toggle. It names the recipient
show/client, purpose, field groups, verification threshold, event/time boundary,
expiry/revocation, retention acknowledgement, and the user action/policy version
that authorized it. Revocation stops future disclosure; it does not retroactively
erase a lawful show registration, waiver, payment, official result, or audit
record.

MNEMEX owns its account, session, recovery, MFA, and authorization experience but
is not a general-purpose identity provider for third parties. It uses maintained
framework primitives and browser-mediated, user-approved grants to registered
partner shows. Partner service calls use narrowly scoped, rotating credentials over
TLS, never a shared database service role. Future OpenID Connect
authorization-code-plus-PKCE remains a separate threat-modeled decision.

Before Phase 2, publish the partner-request authentication profile. It binds each
online request to a registered client, environment, method, path, audience, body
digest, issued-at window, and unique request ID. A durable replay store retains
enough data to distinguish a network retry from a replay attack. Credential
rotation, retry rules, TLS requirements, rate limits, and clock-skew tolerance are
versioned contract rules, not adapter choices.

## Portable profile contract

The portable package is a versioned projection, never a database replica or bearer
credential.

    mnemex.portable-profile.v1
      header: schema_version, package_id, issuer, audience_show_id,
              recipient_client_id, environment, purpose_id, source_event_id,
              registration_context_id, issued_at, expires_at, consent_grant_id,
              profile_version_id, payload_sha256
      subject: show_person_ref, display_name, permitted public aliases
      verified_claims: permitted fields plus verification state/evidence references
      preferences: permitted operational preferences
      eligibility_evidence: claims and validity; never the show decision
      career_summary: opt-in aggregate/statements only
      provenance: necessary package/evidence references

A show submits the projection digest to MNEMEX's online validation endpoint before
import and again immediately before roster lock. MNEMEX validates schema, audience,
recipient client, environment, purpose, event/registration context, consent,
expiry, and digest, then returns an immutable validation receipt. The show stores
the exact bytes/digest and receipt. Same package_id with different bytes is a
security conflict; exact repeat validation in the same authorized context is
idempotent.

Before Phase 2, publish the normative validation profile: canonical-JSON version,
digest algorithm, authenticated endpoint contract, registered-client credential
rotation, clock-skew rule, idempotency semantics, receipt schema, and golden
conformance vectors. Before roster lock, the show validates every imported
projection and pins the bytes, receipt, and its own roster digest. It never calls
the validation endpoint on race day.

A package must be current when the show verifies and locks it. Its recorded
projection remains usable only by that locked event roster through finalization,
even if its ordinary package expiry passes during a multi-day event. It cannot be
reused for a new registration or refreshed after expiry without a new authorized
package.

    1. Competitor begins registration and selects MNEMEX profile.
    2. Show initiates user-approved profile request.
    3. Competitor reviews field scope, purpose, and event, then approves.
    4. MNEMEX returns portable-profile.v1 with scoped show_person_ref.
    5. Show validates it online and creates/updates local participant.
    6. Competitor completes local entry, waiver, and payment.

Manual registration remains supported. A later link requires consent and may not
automatically merge distinct local people. MNEMEX failure is a pre-event condition,
not a race-day failure.

## Offline roster snapshot

MNEMEX packages become a local, append-only EventRosterSnapshot manifest:
event/show ID, local participant ID, optional show_person_ref, source package
digest, permitted display projection, local overrides with actor/reason, manifest
digest, issuer verification, creation time, and roster-lock time. It is encrypted
locally and included in the show's backup/recovery process.

    Draft -> Refreshed -> Verified -> Locked -> Operating -> Finalized
          -> ReconciliationPending -> Reconciled

Once locked, profile changes are available updates only. They cannot background-sync
into active operations. The full Missoula sequence—import, configure, preflight,
heats, flights, relay/spillover, field preparation, scoring, publication, payout—
must pass an intentional network-loss rehearsal from local roster state.
STRATHMARK must likewise work only from its verified local evidence snapshot and
ledger.

MNEMEX checks that a consent grant is active immediately before issuing a package;
the show checks and records the grant ID, status, policy version, check time, and
package expiry immediately before roster lock. Revoked packages cannot be imported,
refreshed, or newly locked. Post-lock use is the already-authorized local event
record, subject to the agreed retention and dispute policy.

## Event contracts and reconciliation

### Show result envelope

    mnemex.show-result.v1
      envelope: message_id, idempotency_key, schema_version, source_show_id,
                source_event_id, source_result_id, source_result_revision_id,
                occurred_at, finalized_at, correlation_id, payload_sha256
      outcome_group: immutable shared-outcome ID and ordered participant list
                     (show_person_ref or unresolved show identity, role, status,
                      career-reconciliation consent or approved policy-basis ref)
      event: source event metadata and version
      outcome: discipline, participation role, score/time/DQ/void, official status
      provenance: source record/revision, roster digest, approval metadata,
                  evidence attachments by reference
      authentication: registered show client and credential version

It excludes payments, waivers, contact details, medical data, private notes, and
internal staff detail. An unlinked competitor result is permitted but enters an
identity reconciliation case; it never creates a confident person link by itself.

The show inserts an outbox item in the same local transaction as result
finalization/correction. A worker sends authenticated messages after the event with retry,
bounded concurrency, and visible dead-letter/review state. Delivery never blocks
show finalization.

MNEMEX gives one immutable payload digest ownership of each source_show_id,
source_result_id, and source_result_revision_id tuple. Exact retries return the
original receipt; any changed payload for that source revision is rejected and
opens a review/security case regardless of idempotency key. A group outcome has
one shared source revision and produces role-aware career projections for each
listed participant. Inbox processing verifies partner/key/schema/digest/revision,
resolves every participant or opens a case, then writes the inbox event,
provenance assertion, career-record revision, and status atomically.

Corrections reference the original source result, monotonically increment source
revision, include reason/approver/digest, and append a chain in MNEMEX. MNEMEX
merge/split/redaction appends MNEMEX provenance; it never alters show source
history. An eligible history correction marks a future STRATHMARK evidence export
superseded; it cannot silently revise a past receipt.

Each participant's career projection requires the captured career-reconciliation
grant or another approved policy-basis reference. If it is absent, revoked before
the relevant capture time, or disputed, MNEMEX keeps only quarantined provenance or
rejects it according to the approved policy. For out-of-order delivery, each source
revision is received, verified-pending-predecessor, applied-contiguous, superseded,
or conflict. MNEMEX stores valid out-of-order messages immutably but derives its
current career projection only from the highest contiguous verified revision chain.

### STRATHMARK evidence contract

MNEMEX exports a separate pseudonymous prior-result envelope with only namespaced
competitor ID, eligible finalized history, event code, required physical/time
fields, source reference, date, and digest. STRATHMARK imports it explicitly
under an exclusive cutoff into its local evidence store. MNEMEX never sends
profiles, PII, live marks, identity claims, or post-cutoff data to STRATHMARK.

### Gillian's hosted Results Desk

Gillian needs a hosted, role-controlled operator surface to turn historical
spreadsheets and manual entries into provenance-backed results. The recommended
deployment choice is an integrated MNEMEX Results Desk: a Railway-hosted web
service backed by Supabase relational storage and object storage. That is a
proposal, not a selected provider or production deployment; D0-10 records the
owner choice and the provider/RLS/recovery proof remains a production gate.

The desk accepts CSV/XLSX uploads and manual entry. Uploads move through
`draft -> parsed -> needs_review | validation_failed -> submitted ->
approved/published -> superseded`; manual entries follow the same review and
publication path. It records source-file digest, original filename/storage
reference, sheet and row/cell reference, mapping/parser version, operator,
reviewer, timestamps, corrections, and supersession link. It must never silently
merge names into a universal person: uncertain identity links remain reviewable
provenance.

The approved scope captures broad historical results so the archive can grow, but
only reviewed eligible SB/UH prior records become candidates for STRATHMARK's
explicit evidence snapshot. A deterministic-valid upload automatically publishes
its immutable source rows to the MNEMEX archive. Publication does not assert a
confident person link, verified career fact, or STRATHMARK eligibility: ambiguous
identity remains unresolved, public career projection requires reconciliation,
and STRATHMARK export requires a separate reviewed-export state. Failed rows are
quarantined rather than partially published. The desk never writes STRATHMARK
directly, never provides live race-day data, and never changes a show’s official
event state.

## Authority matrix

| Data/action | MNEMEX | Show | STRATHMARK |
| --- | --- | --- | --- |
| Person ID, aliases, federation links | authoritative | references | pseudonymous evidence reference |
| Consent/profile field scope | authoritative | records receipt/use | none |
| Local event-facing participant projection | source suggestion | authoritative after import | none |
| Registration, partner, waiver, payment | none | authoritative | none |
| Operational eligibility | evidence source | authoritative decision | none |
| Career history | reconciled representation | source event record | bounded prior-data consumer |
| Historical result intake | provenance and reviewed publication | source evidence/provider context | explicit snapshot consumer only |
| Marks/predictions/receipts | none | consumer/reviewer | authoritative |
| Official outcome/correction | attributed copy | authoritative source/revision | numeric outcome pathway only |

## Security, RBAC, and PII

| Role | May do | Must not do |
| --- | --- | --- |
| Competitor | manage own profile, aliases, grants, visibility, correction request | alter a show result or another person |
| Identity reviewer | resolve reviewed identity links/merges/splits | export contacts or change show outcomes |
| Privacy officer | fulfill access/redaction/hold workflows | routine identity changes without audit |
| Show registration staff | import authorized package, manage local registration | read ungranted fields/change MNEMEX claims |
| Show event official | eligibility and result finalization/correction | issue MNEMEX verification claims |
| Results manager (Gillian) | upload/map/manual-enter results, correct mappings, and inspect automatic publication outcomes | bypass validation/quarantine; modify STRATHMARK directly |
| Results export reviewer | mark published SB/UH rows export-eligible and supersede reviewed export decisions | alter original source evidence or show event state |
| Show integration service | scoped package/result APIs | broad DB access or cross-show query |
| STRATHMARK adapter | pseudonymous prior-history export | profile PII or MNEMEX writes |

Required controls: encrypted PII/evidence storage, TLS, data classification,
hashed identity-match tokens where feasible, separation of public aliases from
private claims, partner/show isolation, least-privilege short-lived credentials,
authenticated replay-protected requests, append-only audit events, PII-free logs/metrics,
and encrypted backups governed by retention policy.

## Deployment and recovery

MNEMEX needs a transactional primary database, immutable audit/event storage,
encrypted evidence object store, queue workers, partner-key registry, and an opt-in,
policy-gated career projection separated from private profiles. Each public page
remains private until the competitor opts in. Supabase Postgres and Storage are the
selected hosted data services, but production activation remains blocked until
migrations, RLS, database and object restore, monitoring, and incident controls are
proven.

If D0-10 selects the integrated Results Desk, the Railway web service and Supabase
data/object-store boundary must be deployed as one reviewed operator workflow:
separate environments, least-privilege results-manager/reviewer roles, encrypted
source storage, quarantine for invalid uploads, durable provenance revisions, and
no service-role credential in the browser. The desk remains outside the race-day
path and its published records reach STRATHMARK only at an explicit snapshot
refresh before the cutoff.

Phase 0 selects and proves the transaction boundary: a server-side worker or
database RPC must commit inbox, provenance, career revision, and receipt state in
one database transaction. Crash-injection tests cover failure between every logical
write and prove either atomic receipt issuance or resumable processing without a
partial career record.

Phase 0 also produces a legacy-data migration ADR and inventory: classify every
existing identity/result field; map, pseudonymize, re-review, or quarantine it;
preserve source-result provenance; define person-ID and alias transitions; backfill
verification/provenance state; run dual-read/export reconciliation; verify rollback
and redaction; and block profile portability for legacy records until this gate
passes. The migration model gives each legacy history item a competitor-visible
status: unclaimed, claimed-pending-review, source-asserted, verified, disputed, or
excluded. It provides a review/appeal path and distinguishes an official source
result from MNEMEX's reconciled representation. This gate does not block a newly
created, consented profile with no legacy linkage; it blocks only legacy-derived
profile assertions and career history until that record's migration gate passes.

| Failure mode | Required behavior |
| --- | --- |
| MNEMEX unavailable before lock | Profile import is unavailable; show may use manual/local registration per policy. |
| MNEMEX unavailable after lock | No live lookup/mutation; show proceeds from pinned roster. |
| Show offline during event | Local DB and STRATHMARK continue; result messages remain in durable outbox. |
| Recovery | Replay exact messages, deduplicate, show backlog/receipt state; never re-enter results manually. |
| Bad snapshot/validation receipt | Reject and preserve evidence; do not lock affected roster or fall back to unverified data. |
| Identity dispute | Quarantine mapping/career view; official show result remains unchanged. |

Before production PII: prove encrypted backups, point-in-time recovery, restore
rehearsal, key-loss recovery, inbox/outbox replay, signing-key rotation, and
incident runbooks. Owner-approved RPO/RTO and retention are launch prerequisites.

The credential lifecycle records owner, purpose, audience, activation/retirement
windows, and revocation receipt. The incident runbook covers emergency disablement,
queue quarantine/reverification, replacement credentials, the continuing audit
status of historic artifacts, and the separate handling of unlocked versus
already-locked snapshots.

## ADRs

1. **MNEMEX owns the person and portable career record.** Historical archive is a capability, not its definition.
2. **Shows retain event authority.** MNEMEX never decides eligibility, scoring, payment, waiver, or publication.
3. **Portable profiles use online pre-lock validation.** The show stores a validation receipt and pins its own immutable local snapshot; MNEMEX is not called after lock.
4. **Race day uses a local pinned roster.** MNEMEX is preparation infrastructure, not a live event dependency.
5. **Results use inbox/outbox reconciliation.** Authenticated idempotent envelopes and append-only revisions replace live coupling.
6. **MNEMEX owns its account system.** It uses maintained framework authentication, password/session primitives, MFA, recovery, and audit controls rather than inventing cryptography or becoming a third-party OAuth provider.
7. **Multiple shows are modeled from the first migration.** Tenant boundaries, client registration, and revocation exist before either integration; adapters may still be delivered incrementally.
8. **Railway plus Supabase is the selected hosted Results Desk shape.** It is not production-authorized until RLS, storage recovery, secret custody, and restore evidence pass.
9. **Automatic publication preserves layers of trust.** Source rows may publish automatically after deterministic validation; identity reconciliation, public career projection, and STRATHMARK export remain separate states.
10. **Legacy history is bulk-migrated through quarantine.** Bulk processing never means automatic person linking or destructive overwrite.

## Phased implementation and gates

| Phase | Primary responsibility | Deliverable | Objective exit gate |
| --- | --- | --- | --- |
| 0. Architecture/safety | MNEMEX owner with show/STRATHMARK review | data classification, threat model, partner trust model, canonicalization/online-validation/API/retention decisions, credential-compromise runbook, transactional-boundary ADR, legacy-data inventory/migration ADR, isolated test topology | ADR approval; tests cannot touch production; no prototype environment asserted authoritative |
| 1. Identity/auth/consent | MNEMEX | transactional person/claim/alias/guardian/grant/audit/privacy models, MNEMEX account access, reviewed merge/split, owner-approved recipient retention rules | ambiguous links never auto-commit; staff MFA, session/recovery, guardian authorization, disclosure, redaction, and backup/restore tests pass |
| 2. Portability | MNEMEX plus participating-show adapters | portable-profile.v1, online validation/receipt endpoint, grant UX, registered client lifecycle, sandbox show adapters | at least two registered show tenants are isolated; validation rejects changed, expired, wrong-audience, ungranted, replayed, or cross-environment use; exact retry is idempotent |
| 3. Offline roster | Missoula Pro-Am Manager / first show | manifest/lock, local encryption/backups, preflight, offline rehearsal | full Missoula workflow completes with MNEMEX disconnected after lock and no roster background mutation |
| 4. Results Desk and legacy migration | MNEMEX | Railway-hosted Results Desk, spreadsheet/manual intake, deterministic validation, automatic source publication, quarantine, bulk legacy migration, provenance/correction history | duplicate uploads are idempotent; invalid rows never partially publish; identity ambiguity never auto-links; source files and published rows restore together |
| 5. Reconciliation | MNEMEX plus participating shows | show outbox committed with show finalization, MNEMEX inbox, group-capable result contract, correction history | restart/duplicate/reordered/conflicting-payload/timeout tests produce one accepted source revision and visible provenance; pair/team membership and correction cases pass |
| 6. Career/public profile | MNEMEX | reconciled career projection and competitor opt-in public pages | only consented, reconciled facts appear; revocation, dispute, minor/guardian change, and correction remove or revise projections without deleting provenance |
| 7. STRATHMARK | MNEMEX export plus STRATHMARK import contract | reviewed, explicit pseudonymous SB/UH prior-history export/import | prior-only/exclusive-cutoff tests pass; automatic archive publication alone is insufficient; no PII crosses; past receipts stay unchanged |
| 8. Pilot | MNEMEX and participating shows | consented event, PII-safe monitoring, DR rehearsal, access reviews, independent security/privacy review, product-validation study | reconciled event ledger, no race-day network dependency, auditable consent, residual-risk acceptance, and a predeclared comparison against the manual baseline for profile-link completion, consent completion, manual fallback, staff reconciliation burden, and correction resolution |

Pilot career history begins with the pilot event's reconciled outcomes. Legacy records
remain absent or visibly quarantined until each record clears its migration gate.
After the first pilot, a second independently implemented show adapter or neutral
reference verifier must accept the published package without an MNEMEX schema or
contract change before MNEMEX is represented as cross-show portable.

## Non-goals

- Replacing Missoula's operation model or reanimating a generic STRATHEX SaaS platform.
- A live MNEMEX scoring/race-day service.
- Porting payments, waivers, medical data, or unrestricted staff notes.
- Automatic identity merges from fuzzy names/federation ID alone.
- Default-public competitor career pages.
- W3C wallet/credential interoperability before the online validation and consent model is proven.
- Changes to STRATHMARK V2's prior-only calculation contract.

## Approved direction and execution inputs

The owner decisions are final in
`2026-08-14-mnemex-approved-build-decisions.md`. Phase 1 proceeds with synthetic,
isolated data. Jurisdiction rules, guardian workflow text, field catalogue values,
RPO/RTO, partner contacts, and credential settings are ordinary implementation and
production-readiness inputs under those decisions. They do not reopen D0-1 through
D0-12 or require another option round.
