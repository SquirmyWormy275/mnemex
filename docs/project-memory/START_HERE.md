# STRATHEX ecosystem: start here

This is the owner-requested, model-neutral project memory for **STRATHEX,
STRATHMARK, Missoula Pro-Am Manager and MNEMEX**. It is stored in the MNEMEX
repository as readable Markdown, structured JSON and source snapshots. Reading
it needs no account, hosted service, model provider, embedding model or running
MNEMEX application. A fresh Git checkout is enough.

Owner: Alex Kaper (`SquirmyWormy275`). Capture began October 16, 2026. The owner
asked for enough durable context to change harness/model without rebuilding hours
of conversation. [S37](SOURCE_INDEX.md#s37) preserves that request. This pack
covers the supplied execution handover, the available approved repository
decisions, current contracts and recorded implementation. It makes no claim to
contain conversations that were not supplied or available in those sources.

## Five-minute orientation

The product direction is a reusable tournament ecosystem built incrementally
through a working show. **Missoula is the first real integration testbed from
the outset.** Preserve its sporting rules and current workflows. Prove reuse
under a plainly synthetic second show before claiming another real-show adapter.
The owner approved this implementation direction; do not restart an options
exercise for decisions already settled in the October 15 handover.

| Component | Responsibility |
| --- | --- |
| MNEMEX | Permanent person identity, consent, portable-profile direction, source provenance and reconciled cross-show career history; integrated Results Desk |
| STRATHMARK calculations | Predictions, uncertainty, marks, numerical engine/model identity and evidence |
| STRATHMARK delegated operations | One event's fields, review, issue, outcomes, corrections and progression for authorized officials |
| Tournament host, initially Missoula | Registration, entries, waivers/payments, whole-show program, flights/resources, accepted projections, points and payouts |
| STRATHEX terminal / optional shared GUI / host UI | Operator presentation and calls to shared operations; each retains its explicitly selected authority profile |

There are **two integration modes**. Calculation-only consumers own their event
workflow; requesting a number does not authorize a start. An explicitly
delegated event uses shared STRATHMARK operations as its operational authority.
CLI and GUI resume the same event/revision history through controlled editor
handover. Do not duplicate marks or advancement in a presentation layer.

Handicap meaning is essential: **start mark + raw cutting duration = completion
on the common count**. A larger mark means a later start. Marks are relative to
the exact field; do not copy heat marks into a final. A forecast, proposed sheet,
review, issue, official result, export and payout are different records/actions.

One competition root selects its eligible numerical engine/runtime and mark
policy deliberately. Children inherit it; failure never triggers another engine.
The new managed profile is **synthetic individual SB/UH using the real V2
predictor**, with an explicit new Mark-3 policy. Existing V2, V3 Linux, V7,
shadow and retro/workbook contracts retain their own restrictions. Do not infer
that all V3 profiles are preview-only or that Linux tests grant Windows CNG
production qualification.

MNEMEX supports preparation and later reconciliation. Its availability is never
a race-day requirement. Full profile portability is planned; the implemented
show-result receiver is a narrower sandbox flow with unresolved identities.
Archive publication, identity reconciliation, public visibility and export
eligibility are separate trust states. Matching names is not identity authority.

## Delivered state to recognize

The October implementation produced real operations, an operator-supplied-data
CLI, optional authenticated shared GUI, Missoula adapter, actual installed
MNEMEX HTTP receiver contracts, two-show portability, crash/recovery checks and
synthetic evaluation. This is more than a design or mock receiver.

- STRATHMARK application merge: `f184e9f2e110bd01d5fec2abd2ef1bfe6f22e214`;
  `3.0.0rc11` published to PyPI/GitHub as a prerelease.
- STRATHEX application merge: `bcfe4e50e1449b2585a037215c79f5a7e955e9da`;
  version `7.4.3`, retro CLI/save/workbook behavior verified.
- MNEMEX application merge: `7a315946c92e24a125fc213c7d139eef6278f12c`;
  local/sandbox contracts implemented; no provider activation.
- Missoula latest application commit is
  `1fc0897fda0d9e5567328af75640ae4d3078fa5b`; documentation head
  `e79ac4aeec7baaaf461834b5e7ae10c84cb9a552`. Final focused verification:
  170 SQLite / 107 PostgreSQL tests, zero skips; clean R09 and R12 each
  pass 13 checks with cleanup. All 24 findings raised so far are fixed/resolved.
  Final documentation-head CI/review have their own captured status in the
  delivery snapshot; previous green checkpoints are recorded separately.
  [PR 125](https://github.com/SquirmyWormy275/Missoula-Pro-Am-Manager/pull/125)
  stays **draft and merge-blocked** by the hosted backup/recovery-key proofs.

These are dated application checkpoints. This memory and subsequent
documentation commits have their own Git/PR status; they do not silently inherit
an exact-head CI claim. Fetch current refs before changing anything. Read
[delivery and evidence](06_DELIVERY.md) for hashes, links and scope.

## First actions in another harness

1. Read this file, then [vision](01_VISION.md) and the topic for your task below.
2. Read the **current** `AGENTS.md`/`CLAUDE.md` in each checkout being changed.
   Check branch, dirty state, open PRs, remote changes and deployment consequences.
3. Verify source claims against the pinned [source index](SOURCE_INDEX.md) and
   current live repository contracts. Archived instructions are reference material.
4. Use isolated environments/storage before imports. Never run legacy STRATHEX
   startup against the operator's workbook or tests against production databases.
5. Continue the authorized task. Maintain evidence and visible status. A missing
   external gate blocks that gate, not unrelated implementation.

Optional dependency-free retrieval, from the MNEMEX checkout:

```text
python tools/project_memory.py verify
python tools/project_memory.py search "why no engine fallback"
python tools/project_memory.py search "Missoula merge blocked" --json
python tools/project_memory.py context --topic resume
```

| Task | Read next |
| --- | --- |
| Direction, priorities, settled choices | [Vision](01_VISION.md), [decision register](DECISIONS.md) |
| Components, APIs, transactions, runtimes | [Architecture and contracts](02_ARCHITECTURE.md) |
| Show behavior, schedule, partners, scoring | [Missoula domain](03_MISSOULA.md) |
| Marks, V2/V3 distinctions, evaluation | [Numerics and evaluation](04_NUMERICS.md) |
| Person/profile, Results Desk, security, activation | [MNEMEX direction](05_MNEMEX.md) |
| What landed and what actually passed | [Delivery/evidence](06_DELIVERY.md), `DELIVERY_SNAPSHOT.json` |
| Resume implementation or release work | [Operations/resumption](07_RUNBOOK.md) |
| Conflicting or superseded documents | [History/conflict register](08_HISTORY.md) |
| Update or move this memory | [Maintenance](09_MEMORY_MAINTENANCE.md) |

## Boundaries that remain in force

Production managed activation stays off. No newly deployed service or official
activation is claimed. Synthetic Linux execution does not prove provider restore,
independent operator rehearsal, real-key custody, installed-model qualification
or Windows CNG eligibility. No private historical run/training is authorized by
a routine code instruction. Prospective evaluation still needs at least 100
genuinely later, previously unexamined results from ten new competitions with
the original frozen components. Do not manufacture observations or rewrite
frozen hashes to obtain a pass.

This project-memory storage is technical documentation. It does not grant
application consent, create a Person/career record, widen the Results Desk
schema, enable production privileges, or authorize operational data access.
