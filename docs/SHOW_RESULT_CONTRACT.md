# Synthetic show-result inbox

Current ownership follows the approved incremental
[modular ecosystem agreement](https://github.com/SquirmyWormy275/STRATHMARK/blob/main/docs/MODULAR_ECOSYSTEM.md).
Missoula publishes accepted STRATHMARK source attempts. Standalone sources declare
their own show identity. MNEMEX preserves and reconciles career provenance; it
never scores a heat or writes to the show database. Existing reviewed SB/UH 2.x
history exports remain unchanged.

## Implemented boundary

`POST /partners/results/ingest` accepts `mnemex.show-result.v1`: a stable
`message_id`, closed `strathmark.source-result.v1` source, canonical SHA-256
`source_digest`, and participant references (`show_person_ref`, `unresolved_ref`,
`authorization_basis_ref`, explicit nulls allowed). No names, email or legal
identity enter this contract. Source includes show/event/result/revision, heat,
field and issue digests, discipline/date/wood, raw timers, raw duration, start
count, common-count completion, official position/status and correction ancestry.
Common-count completion equals start count plus raw duration; finished durations
match the available timer mean. Voids/nonfinishes invent no duration or position.

Only synthetic SB/UH sources from active **sandbox** clients are accepted.
`MNEMEX_SHOW_RESULTS_ENABLED` defaults false in base settings and cannot be
switched on by a payload. TLS is required except a loopback rehearsal. A scoped
random bearer credential is hashed at rest, expires after one day, can be revoked,
and binds one registered source show to one client. Browser sessions grant no
machine authority. The two machine POST routes alone are CSRF-exempt; normal
browser CSRF and privileged MFA controls remain unchanged.

Local OS administration can run `manage.py register_show_source --client UUID
--source-show-id synthetic:missoula --credential-output /private/new-token.json`
against explicitly selected synthetic settings/database. The file must be new;
POSIX mode is 600. The token is never printed. Do not provision production or
put a token in URLs, browser storage, committed examples or screenshots.

The transaction commits idempotency, immutable inbox evidence, source projection
and audit together. Exact request/source retries return the original receipt,
even under a new delivery identity. Changed requests or same source revision
conflict durably. Out-of-order corrections wait for a contiguous predecessor
with its exact digest and immutable issued binding. No prior revision is erased.
`mnemex.show-result-receipt.v1` binds source ID/revision and payload digest
(excluding only message_id); states include `unlinked`, `pending_predecessor`
and `conflicting`. `POST /partners/results/status` uses the same scoped
credential and reports stream revisions/unlinked states and counts. Receipt
state is immutable; use status to inspect later predecessor reconciliation.

Every received identity remains **unlinked**, even if a scoped reference is
present. A reference is not identity or consent evidence. Existing reviewed
reconciliation, public opt-in and export eligibility remain separate services.
This inbox does not implement full portable profiles, show grants, offline roster
snapshots, public career pages or production activation. It proves the result
transport and provenance boundary without requiring live MNEMEX during racing.

## Verification and rollback

Use `mnemex.web.settings.test`, `MNEMEX_TEST_SUPABASE=0` and an empty vision key.
Run `pytest tests/test_show_result_inbox.py`, Django checks and migration drift,
then the full synthetic suite. Missoula's `tests/test_managed_events.py` can
launch the actual installed Django receiver in fresh SQLite storage and tests
real HTTP outages and committed-response loss, separately from R08's simulated
shadow peer. Migrations partners 0002–0005 are additive. Roll back application
code with this receiver disabled; retain inbox/source/credential/conflict tables
and independent backups. Do not drop received source history to roll back code.
All provider/restore/operator activation evidence stays pending unless separately
qualified under the existing 14-gate registry.

Correction identity and status scope follow-up: entry identity, issued field,
discipline, date and wood remain bound across source revisions. A direct invalid
correction receives a durable conflicting receipt before an immutable inbox slot
is allocated; a valid correction can then arrive under a new delivery identity.
Reordered conflicting evidence remains retained and blocks contiguous projection
for explicit reconciliation. Status counts are scoped to the credential's show,
including conflict counts. Additive partners migration 0004 leaves older
unattributed conflicts null and private; it never guesses their show.

Delivery identifiers are scoped to the registered source, including when one
client operates several shows. Exact retries from the older client-only
namespace keep their original receipt and changed-payload binding; a known old
source cannot reserve another source's key. Legacy ownership that cannot be
attributed remains blocked rather than guessed.

Accepted inbox and rejected conflict evidence retain the authenticating
credential ID, never its token. Overlapping key rotation does not rewrite the
original attempt's provenance. Validated rejected envelopes are immutable private
evidence outside the authoritative revision slots. Nullable migration 0005 fields
leave earlier unavailable payload/credential evidence explicitly unknown. Local
synthetic service calls remain a declared trusted-OS boundary; HTTP ingestion
always passes and revalidates its scoped credential. Both machine endpoints
require the enabled sandbox profile and reject inactive/revoked/expired scopes.
Credential output files are exclusively created with private POSIX mode in the
initial open operation, before any token bytes are written; Windows ACL and
hosted deployment qualification remain separate.
