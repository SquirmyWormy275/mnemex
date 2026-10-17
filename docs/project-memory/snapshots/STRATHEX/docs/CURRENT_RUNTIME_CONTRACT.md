# Current Runtime Contract

**Applies to:** STRATHEX 7.4.3
**Prediction authority:** the competition-root selection persisted by STRATHEX; V2 remains the production baseline and V3 remains opt-in under exact readiness evidence

## Competition authority

New scopes have no default. A single event selects once at setup. A tournament selects once at creation and all child events, heats, and later rounds inherit that choice. The persisted SQLite authority records the engine, mode, actor assertion, time, reason, exact contract/source identity, and lock. JSON saves carry only its immutable reference.

The choice locks before the first numeric operation. Neither engine may call the other after timeout, incompatibility, partial response, or outage. An ambiguous V3 command is shown with its durable identity and requires an exact judge-directed retry. A locked scope never changes engine in place.

## Ownership

The following ownership describes retained retro/workbook competitions.
[New delegated sessions](MANAGED_EVENTS.md) instead use STRATHMARK's shared event
operations for fields, issue, outcomes and advancement. STRATHEX is a thin
launcher/client in that explicit mode. Existing saves are never converted.

STRATHEX owns operator interaction, tournament state, schedules, advancement, judge approval, result entry, Excel output, and local recovery.

STRATHMARK owns numeric time prediction, forecast uncertainty, race-performance spread, prediction provenance, engine health metadata, and joint handicap-mark optimization.

## Calculation

Each field has one persisted exclusive `prediction_as_of` date. STRATHEX sends stable competitor IDs, dated historical observations, target wood, and event code under that cutoff.
When an operator has not supplied an event date, STRATHEX anchors the cutoff to the operator computer's local calendar date so same-event results recorded locally cannot enter a later-round recalculation after UTC midnight.

When V2 is selected, STRATHMARK v2 uses its prior-only hierarchical core unchanged. Manual overrides remain authoritative. The optional residual is inactive unless STRATHMARK promotes it. Numeric LLM and the former local XGBoost/expected-error cascade are retired from V2.

When the authenticated V7 profile is selected, pre-field seeding and exact field marks are separate artifacts. The signed pre-field receipt contains p50 raw-time forecasts and explicitly says `issued_mark=false`; it cannot be printed or approved as a mark sheet. Exact heat membership and stand assignment must exist before V3 prepares cards and jointly assembles field-relative marks. The judge then batch-reviews ordinary green/amber fields and individually reviews flagged fields.

Same-day and future observations are excluded. Undated observations are not v2 evidence. Wood quality, division, heat, field-strength compatibility fields, and same-tournament results do not change v2 numeric output. The UI must not claim otherwise.

V2 and the full V7 field contract include predicted time, legal mark, method, confidence, explanation, forecast interval, performance standard deviation, engine/model/calibration versions, evidence cutoff, optimizer and metadata, warnings, degraded state, provenance, ignored factors, competitor ID, and optional ledger fields.

## Transport

The full Linux local competition profile is `strathmark.v3-linux-competition.v1`, frozen contract `162a5317adce4c2efd037d50e9d0239a49dc849dfaa365d935356a6240bc455e`. The reviewed Linux producer source is `e5c3f2de6a316dc4a38aed05e4fc4092893a7c84`, implementation digest `29ef522ac52409055f5353682528a8005fe0df8087ce94adbcdcf6ebf235f7d7`. It binds the code, Formula, ML, and persistent installation key into the source identity, validates signed exact-command responses, and records an acknowledged/recovery outbox. See [complete Linux workflow](V3_LINUX_COMPETITION.md). The preview restrictions below apply only to the retained numeric-preview profile.

The explicit Linux V3 numeric profile runs a separate Python 3.13 subprocess with
verified trained ML, Formula, distribution pooling, and the V3 optimizer. Its
`strathmark.v3-linux-numeric-candidate.v1` contract is separate from V7. Selection
binds the installed implementation and model digests. Per-root workbook snapshots
and preview evidence persist across restart, with an exclusive historical cutoff. Exact-field evidence binds its upstream revision and stand IDs.
Both numeric assessors must execute. Pre-field forecasts have no marks; exact-field
proposed marks remain unissued. This profile cannot authorize approval, issue,
official result entry, official schedule export, settlement, or next-round learning. Saved root authority controls these restrictions even for championship fields without preview row labels. LLM council availability, bootstrap
weights, and bootstrap dependence are disclosed; no accuracy qualification is claimed.

- `python` is the default: direct in-process `HandicapCalculator.calculate()`, offline-capable.
- `http` is explicit: one stateless `POST /calculate` per common-wood field after validating the audited `/openapi.json` 2.0.0 request/response shape.
- The V3 V7 profile uses a separate authenticated loopback-only HTTP client pinned to one reviewed V3 consumer-contract digest and source commit. Its credentials are referenced through an environment-variable name or OS keyring and are never persisted.
- Credential rotation and revocation are installation-administration operations, not judge or competition-root actions. The judge client deliberately does not persist the one-time credential returned by `/v3/credentials/rotate`; it resolves its configured environment/keyring reference for every request, so an administrator can rotate the service credential out of band without rewriting tournament state. The authenticated deployment procedure must store the replacement before revoking the prior digest.
- HTTP mode never falls back to Python.
- Loopback HTTP is allowed. Remote API URLs require HTTPS. Redirects and URLs containing credentials, paths, queries, or fragments are rejected. OpenAPI and calculation response bodies are bounded to 4 MiB.
- The HTTP calculation endpoint does not read ResultStore and does not write PredictionLedger.

Both V2 transports enforce the public API's 64-competitor field-size and value bounds before calculation. A malformed or incomplete result aborts the complete field. Championship scenarios group competitors that share target wood and history context; distinct target wood or curated peak windows require separate calls. The simulator fixes the cutoff, requires one consistent engine/model/calibration bundle, and aborts rather than mixing snapshots or producing a partial field.

STRATHEX prohibits multi-event recalculation after results entry begins. Recalculating a scheduled event invalidates its generated heats. If recalculation fails, STRATHEX clears that event's prior marks and pending rounds, sets `status=recalculation_failed`, saves the failure state, and blocks results entry, schedule generation, and schedule export until a successful recalculation and fresh schedule generation. It never leaves stale v6 or earlier v7 marks available to judges.

Simulation remains local. Championship simulation uses at most 250,000 races and an adaptive two-million competitor-cell cap, and it does not retain an unused per-race finish-spread list.

## Persistence

Excel is judge-canonical. ResultStore is a derived, best-effort second write. The two stores are not one atomic transaction and a ResultStore failure does not undo Excel.

Tournament JSON saves are schema-validated, written to a same-directory temporary file, flushed, verified, atomically replaced, and backed up. Load can recover a valid backup when the primary is malformed.

A one-time `.pre-v2.bak` SQLite snapshot protects an existing ResultStore before v2 schema migration. It includes committed WAL rows, passes SQLite integrity validation, and is atomically published. New result writes include `competition_id` and the event date.

ResultStore history and V2 PredictionLedger receipts remain separate. A full V7 scope uses the supported V3 lifecycle and signed field receipts through its authenticated boundary; this does not change the V2 public route.

## Release gates

A STRATHEX release is acceptable only when:

1. direct and HTTP transports match on a fixed-cutoff field;
2. stable identity and v2 metadata survive save/reload;
3. all tournament replay, bracket-bye, atomic-state, and result-write tests pass against isolated storage;
4. Ruff, wheel build, and clean-wheel import smoke pass;
5. maintained docs, dated solution labels, and versioned wiki source describe this contract;
6. published wikis are synced and verified separately;
7. no test touches the production workbook or ResultStore.
