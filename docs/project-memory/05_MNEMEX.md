# MNEMEX: person, provenance, Results Desk and long-term delivery

Sources: [S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29),
[S30](SOURCE_INDEX.md#s30), [S31](SOURCE_INDEX.md#s31), [S32](SOURCE_INDEX.md#s32),
[S33](SOURCE_INDEX.md#s33), [S34](SOURCE_INDEX.md#s34), [S35](SOURCE_INDEX.md#s35),
[S36](SOURCE_INDEX.md#s36). The approved D0 selections govern even where an
earlier architecture paragraph still calls a selected provider a proposal.

## Mission and authority

MNEMEX is a universal competitor identity, portable-profile, career-history and
provenance service with an integrated Results Desk. It owns the person and
reconciled cross-show record. It never decides a show's winner, waiver, payment
or event-local eligibility. A delegated event's operational owner is STRATHMARK;
calculation-only hosts retain their event workflow. Host source records remain
authoritative when MNEMEX reconciles a career copy.

A person ID is opaque, immutable and not derived from email/name/federation ID.
Account authentication, legal-claim verification and competitive identity
resolution are different. Staff or guardians can have accounts without being
competitors. Aliases/federation evidence can propose matches, not silently commit
consequential links. Merge/split/redaction preserves tombstones and provenance;
IDs are never reassigned.

Internal person ID, pairwise `show_person_ref`, local show participant ID and
pseudonymous numerical identity remain different namespaces. A show's reference
must not become a public cross-show correlation key or its database primary key.
The numerical evidence envelope excludes contact/legal identity, waivers,
payments, medical data and private notes.

## The approved D0 choices, all twelve

| ID | Owner selection | Consequence |
| --- | --- | --- |
| D0-1 | C: minors in first pilot | Guardian, age-aware consent/revocation/retention and adulthood transition are required |
| D0-2 | B: expanded legal-identity profile | Encrypted claims separated from display identity, logs, public pages and show projections |
| D0-3 | B: opt-in public pages in pilot | Private by default; explicit per-person opt-in |
| D0-4 | C: MNEMEX authentication | Own account/UX boundary, maintained framework crypto/auth/session primitives |
| D0-5 | B: multiple shows from start | Tenant/client registration, revocation and pairwise references exist from first schema |
| D0-6 | B: online validation only | Validate before import/lock, then pin local roster; no live race-day MNEMEX call |
| D0-7 | A: server-side transaction | Inbox, provenance, career/reconciliation, receipt and outbox effects commit atomically |
| D0-8 | A: recovery/retention before PII | Approved RPO/RTO, DB/object/key restore and deletion/hold evidence first |
| D0-9 | B: legacy bulk migration first | Immutable staging/quarantine/reconciliation before pilot legacy career activation |
| D0-10 | A: integrated Results Desk | One Railway-hosted Django modular monolith; Supabase PostgreSQL and private objects |
| D0-11 | A: broad capture, reviewed SB/UH export | Broad archive does not widen STRATHMARK 2.x reviewed prior-only evidence |
| D0-12 | C: automatic publish after upload | Deterministic-valid private source rows publish; trust/consent/reconciliation remain separate |

Approved means development can proceed under isolated synthetic conditions.
Jurisdiction rules, field catalogues, retention values, partner custodians and
production evidence are implementation/activation inputs, not a new option round.

## Portable profiles: intended contract, still incomplete

A grant names recipient client/show, purpose, permitted field groups, verification
threshold, event/registration context, expiry/revocation, retention acknowledgment
and the approving action/policy version. It is not a universal share toggle.
Legal-identity values and guardian authority remain encrypted/private.

The intended `mnemex.portable-profile.v1` package contains scoped display claims,
allowed preferences/eligibility evidence and provenance. It binds package/digest,
issuer/audience, environment, purpose, event/context, recipient, grant, immutable
profile version and validity. It is a projection, not a database replica or a
bearer credential.

A show validates online at import and immediately before roster lock, recording
the exact bytes/digest, validation receipt, participant mapping and its own roster
digest. After lock it uses the pinned local snapshot. Expiry during an already
authorized multi-day locked event is not permission for a new registration or
silent refresh. Revocation prevents future disclosure/import/new lock; lawful
existing source/audit records follow their approved retention/dispute policy.

Manual registration remains supported. A later profile link needs consent and
must not merge distinct local people automatically. MNEMEX outage before lock
can require manual/local registration; outage after lock has no race-day effect.

Full grants/projections/validation/show adapters and opt-in public career pages
remain planned. Do not mistake existing foundation models or the sandbox result
receiver for completion. At least two show tenants and an independent adapter or
neutral reference verifier are needed before cross-show portability is claimed.

## Results Desk and migration

The integrated Desk lets authorized staff, including the named owner-facing
Results Desk workflow, upload CSV/explicitly selected XLSX worksheets or enter
results manually. It preserves original artifacts, source organization and digest,
sheet/row/cell, mapping/parser version, operator/reviewer/time, validation states,
corrections and supersession. Multi-sheet XLSX fails closed until a sheet is named.

Deterministic-valid source rows automatically publish to the **private archive**.
Invalid/conflicting rows quarantine. Neither publication nor successful extraction
confers confident person identity, verified career fact, public visibility or
STRATHMARK eligibility. Those have separate review/consent transitions. LLM-assisted
extraction responses and files are untrusted source inputs and cannot invent data.

Bulk legacy migration preserves an immutable inventory, explicit table plans,
five-way dry run, exact-digest rationale-bearing approval, durable APPLY queue,
250-row checkpoints, reconciliation export and logical withdrawal. It never
copies ambiguous names directly into Person/Career or deletes the source corpus.
Legacy-derived assertions remain gated until their record passes migration review;
a new consented profile without legacy linkage is a different case.

The reviewed STRATHMARK 2.x evidence export is explicit, immutable, pseudonymous,
prior-only and limited to eligible SB/UH rows. A broad archive does not broaden
that contract. MNEMEX never writes directly into STRATHMARK or a show database.

## Current narrow source-result receiver

The October implementation adds a closed sandbox machine API for source-attributed
`mnemex.show-result.v1` delivery/status. Registered source/client ownership,
expiring/revocable hashed credentials and endpoint/TLS-or-loopback gates are
enforced. Immutable source attempts and corrections remain unlinked.

Exact source revision/digest retries return receipts. Changed payloads conflict
even under a new idempotency key. Reordered revisions wait for contiguous verified
predecessors. Entry and issued-field bindings are checked before authoritative
admission, so a rejected envelope cannot poison a stream. Rejected valid conflict
evidence and the authenticating credential provenance remain retained. Legacy
unknown attribution stays null rather than invented. New idempotency is
source-scoped while exact older receipts remain recoverable.

The actual installed Django HTTP receiver was exercised with Missoula's real
source adapter for downtime, committed-response loss, corrections and voids.
This establishes synthetic local interface evidence, not a live provider/pilot.
There is no automatic name linking, consent promotion or public career assertion.

## Application/security foundation already implemented

Django 5.2 LTS is a modular monolith, with accounts, people, consent, partners,
results, legacy migration, career, export, foundation/audit, recovery, activation,
web and bounded worker/supervisor modules. Web and workers share domain code and
migrations. Do not introduce independent microservices to recreate these boundaries.

Implemented local foundations include invite-only authentication, verified email,
Argon2id, privileged TOTP/recovery, encrypted authenticator material, session
rotation/revocation, atomic claims and eight-hour privileged freshness with
five-minute privileged-POST freshness. Sensitive-action tickets bind route,
origin, session, method, account and security version; the in-page step-up retains
forms/files and requires deliberate confirmation rather than automatic replay.

Dependency note: allauth 65.20 requires explicit reauthentication even after a
recent initial password login for protected enrollment views. The existing
password-confirmation route supports this; do not bypass that gate to recover
an older test expectation. See the delivery ledger for the reproduced compatibility
failure and tests on both supported versions.

Security administrators have scoped staff invitations, two-person lost-factor
recovery, suspension, factor/session revocation, re-enrollment and explicit
restoration. Authentication does not itself verify legal identity or guardian
authority. Public opt-in does not widen a partner projection.

The owner approved the queue-only security-mail cutover on August 18 after the
availability risk was disclosed. Security notices create encrypted durable intents;
the request path does not fall back to SMTP. Event-time verified recipients,
deterministic identity, fenced leases, bounded retry and uncertain-handoff review
remain important. Local approval did not close hosted SMTP/recovery evidence.

Versioned MFA/notification keys, historical-key restore, resumable re-encryption,
retirement blockers, private-artifact write leases/orphan reconciliation and a
bounded server-only Supabase adapter are implemented locally. Browser URLs never
carry service credentials. Provider private-object recovery remains unproven.

## Production activation ledger

Production privileged authorization remains hard-disabled. The closed activation
registry can report blocked and verify offline signatures; it cannot enable
privilege. Passing CI or setting an environment variable is not activation.

| Gate | Remaining objective evidence |
| --- | --- |
| G01 hosted configuration | Observe exact staging/production configuration, redact values |
| G02 shared auth | True multi-process suite against disposable TLS Redis |
| G03 key rotation | Staging rotation/restore with required historical versions |
| G04 notifications | Authenticated SMTP, retries, uncertain handoff and recovery ceremony |
| G05 invitations | Independent approved staff/operator rehearsal |
| G06 staff recovery | Independent factor re-enrollment and explicit privilege restoration |
| G07 private objects | Hosted bucket policy, integrity lifecycle and provider recovery |
| G08 runtime | Built image and observed separate staging web/worker services |
| G09 monitoring | Selected hosted alerts and observed redacted signals |
| G10 recovery | Pristine provider DB restore plus reconciled object/key inventory |
| G11 activation integrity | Owner-controlled signing key, signed evidence and independent verification |
| G12 authority boundary | Final review confirms pinned/offline race-day operation |
| G13 step-up | Fresh hosted browser evidence after staging |
| G14 first operator | Independent operator and approver complete the ceremony |

No real PII, provider credential, hosted object bucket, deployed image, public
profile or full pilot is implied by the local code. Database backups alone do
not restore private objects or encryption keys. Use the actual runbooks and
approved operators for provider/key work; this technical-memory request does not
authorize it.

## Project-memory storage boundary

This documentation library is the new owner-requested technical memory use.
Its Markdown/JSON can be indexed by another harness without importing Django.
It does not insert design decisions into Person, source-result, consent or
career tables and introduces no project-memory application endpoint. Existing
application authority, tenant, disclosure and activation rules remain unchanged.
