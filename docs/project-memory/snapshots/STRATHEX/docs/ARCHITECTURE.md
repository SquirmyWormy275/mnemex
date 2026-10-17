# STRATHEX 7 Architecture

## Available runtime profiles

STRATHEX 7.4.3 preserves V2 production operation and adds a complete separate Linux V3 competition profile. The [Linux competition runbook](https://github.com/SquirmyWormy275/STRATHEX/blob/main/docs/V3_LINUX_COMPETITION.md) covers real Formula + trained ML, signed local authority, mark-free seeding, exact handicap/championship receipts, deliberate approval and separate issue confirmation, complete outcomes, settlement, restart, official corrections, verified recovery and later-round learning. The LLM council is unavailable; degraded or individual review is required. Existing numeric previews and authenticated V7 rehearsal scopes retain their original contracts. Windows CNG production qualification remains separate.

The authenticated V7 profile uses signed lifecycle receipts and requires full backend composition and installation qualification. Its lifecycle behavior described below applies only when that full runtime is configured and ready. The checked-in transport rehearsal uses fixtures and does not prove a real numeric lifecycle. A judge deliberately selects V2 or an available V3 profile once per competition root; failures stop the selected workflow.

## System boundary

```text
Judge
  |
  v
STRATHEX terminal application
  |-- roster, wood, tournament state, brackets, schedules
  |-- Excel canonical results
  |-- atomic JSON state + backup recovery
  |-- best-effort local ResultStore history
  |
  +-- competition-scoped engine router -----------------+
      |                                                 |
      +-- V2 direct Python or POST /calculate            |
      +-- V3 authenticated loopback lifecycle API        |
                                                        v
                                              STRATHMARK
                                              V2 baseline or V3 ensemble
                                              signed forecasts/receipts
                                              complete-field optimizer
                                              provenance/warnings
```

STRATHMARK imports nothing from STRATHEX. STRATHEX translates DataFrames and operator state into STRATHMARK value objects or the equivalent REST schema.

## Live modules

| Area | Authority |
|---|---|
| `MainProgramV5_2.py` | terminal orchestration and single-event state |
| `woodchopping/handicaps/calculator.py` | history merge, roster enrichment, fixed cutoff, live field call |
| `woodchopping/strathmark_adapter.py` | typed boundary, transport selection, v2 metadata mapping, ResultStore and simulation facades |
| `woodchopping/engine_selection.py` | immutable execution context and no-fallback V2/V3 router |
| `woodchopping/ui/prediction_context.py` | canonical SQLite competition selection, lock, inheritance, and save reference |
| `woodchopping/strathmark_v3_client.py` | authenticated loopback lifecycle, exact contract/source pins, receipt validation, and recovery |
| `woodchopping/v3_authority_store.py` | durable outbound V3 command and acknowledgment ledger |
| `woodchopping/prediction_context.py` | persisted exclusive evidence cutoff |
| `woodchopping/ui/prediction_display.py` | judge-facing v2 evidence and explanation |
| `woodchopping/ui/tournament_ui.py` | heat progression and advancing-field recalculation |
| `woodchopping/ui/bracket_ui.py` | v2 bracket seeding and bracket state |
| `woodchopping/ui/championship_simulator.py` | grouped v2 raw-time forecasts, all marks fixed at 3, memory-bounded simulation |
| `woodchopping/ui/multi_event_ui.py` | per-event state, fixed cutoff, schedules, sequential results |
| `woodchopping/ui/state_persistence.py` | schema validation, atomic replace, backup recovery |
| `woodchopping/data/excel_io.py` | canonical result write followed by best-effort ResultStore write |

## V3 two-stage evidence flow

1. STRATHEX records one root engine selection and locks it at the first numeric boundary.
2. With the full V7 profile, before a field exists V3 synchronizes the tournament and round, opens the scope, freezes the evidence epoch, and returns signed mark-free forecasts for seeding.
3. STRATHEX creates exact heats and stand assignments locally.
4. Each field snapshot crosses the minimized API boundary with pseudonymous competitor IDs only.
5. V3 prepares the five component jobs per competitor and assembles one complete field-relative receipt; partial fields are rejected.
6. The approval queue supports ordinary batch review, a separate degraded batch, and individual flagged review.

## V2 evidence flow

1. Excel and local ResultStore history are merged and de-duplicated.
2. Shared validation normalizes usable fields.
3. Roster data supplies stable competitor IDs and gender.
4. The event state supplies one exclusive cutoff.
5. The adapter creates STRATHMARK records.
6. One handicap field calculation runs under one model snapshot. Championship competitors are grouped by target wood; distinct wood or curated peak-history windows require separate calculations. STRATHEX fixes one cutoff and aborts if the returned model bundle changes between groups.
7. STRATHEX persists and displays the returned prediction and optimization evidence.

Dated observations before the cutoff are usable. Undated, same-day, future, and invalid observations are excluded by v2. Same-day round times can be displayed to a judge but cannot feed the event's prediction.

## Persistence boundaries

Excel and ResultStore are deliberately not described as synchronized or cross-store atomic. Excel succeeds first; ResultStore follows best-effort. JSON state persistence is atomic within its own file boundary.

ResultStore stores historical results. PredictionLedger stores immutable prediction receipts and settlements. Public `/calculate` is stateless. These concepts must remain separate in code and documentation.

## Failure behavior

- Direct mode has no calculation network dependency.
- HTTP mode fails visibly for missing/credential-bearing/path-bearing URL, remote plaintext, redirect, oversized response, request failure, malformed OpenAPI/response shape, version mismatch, or missing v2 audit metadata.
- Both transports apply the API's 64-competitor and numeric/string bounds before calculation.
- A failed field or championship competitor aborts the whole operation; partial mark sheets are not accepted.
- Multi-event recalculation is prohibited after results entry begins. Recalculating a scheduled event invalidates its generated heats. A failed recalculation clears both old marks and pending rounds, sets `recalculation_failed`, and blocks results entry and schedule export until the event is calculated and scheduled again.
- Championship Monte Carlo uses an adaptive competitor-cell cap and omits unused per-race spread arrays so desktop memory remains bounded.
- There is no silent transport fallback.
- There is no silent engine fallback. A V3 timeout enters durable recovery and requires a deliberate exact retry.
- Degraded engine results and optimizer fallbacks remain visible in returned metadata.
- A malformed save is rejected and may recover from its valid `.bak`.
- A derived-store failure never rewrites or rolls back the canonical Excel workbook.
- The one-time pre-v2 SQLite backup uses SQLite's snapshot API, includes committed WAL rows, is validated, and is atomically published before migration.
