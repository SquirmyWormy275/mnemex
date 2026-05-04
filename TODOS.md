# MNEMEX TODOs

This file is the working backlog for MNEMEX implementation. It consolidates:

- **22 Reviewer Concerns** from the 3-iteration spec review during /office-hours
- **3 Eng Review additions** from /plan-eng-review (test paths, idempotent re-ingest, SQLite reconciliation)
- **2 Design decisions surfaced** during /plan-design-review (picker filter, strict-mode default — both already resolved in the design doc)
- **2 DX additions** from /plan-devex-review (mnemex tour deferred, GitHub Discussions deferred)
- **2 CEO scope additions** from /autoplan (data-rights doc, ecosystem sequencing rule — both resolved in the design doc)
- **3 Codex strategic findings** from the Outside Voice (data rights, trust moat, ecosystem sequencing — partially addressed)

Items marked `[v1]` block v1 ship. Items marked `[v1.1]` defer cleanly. Items marked
`[never]` are explicitly out of scope forever.

Each TODO has: **what / why / pros / cons / context / depends-on**.
Read this before starting any milestone.

---

## Open clarifications (resolve during M0-M1)

### TODO-001: Serverless deployment topology vs CLI-first v1 [v1]

- **What:** Decide whether ingest serverless functions (Cloudflare Workers / Vercel)
  ship in v1 or whether v1 is fully CLI-only with web archive deployment via GitHub Actions.
- **Why:** The Distribution Plan section mentions Cloudflare Workers / Vercel but the
  milestones describe CLI-only flows. New contributors get confused.
- **Pros (CLI-only):** simpler v1, no auth surface, no token rotation.
- **Cons (CLI-only):** federation `mnemex publish` web form (M4.5) needs a serverless
  endpoint OR a static-form-to-issue-PR flow.
- **Context:** Reviewer Concern #1 from the spec-review iter-3 wrap-up. Recommend
  CLI-only for v1; defer all serverless work to v2.
- **Depends on:** M4.5 design choice for the publish-form.

### TODO-002: Cost-ledger crash recovery [v1]

- **What:** Define TTL or PID-based reclaim for `RESERVED` rows in cost_ledger.jsonl.
- **Why:** If a process crashes between `reserve()` and `finalize()/cancel()`, the
  reservation persists and silently consumes budget.
- **Pros:** prevents silent budget leak.
- **Cons:** adds complexity to the ledger module.
- **Context:** Reviewer Concern #2. Recommend 1-hour TTL OR PID check (reclaim if dead).
- **Depends on:** M3 (when cost_ledger first runs).

### TODO-003: Imputed-quality write semantics [v1]

- **What:** Decide where wood-quality imputation happens — at ingest time (writes 5 +
  flag=True to the store) or only at projection time (store stays NULL).
- **Why:** Premise 7 says imputation happens with provenance flag; the projection
  code does default-to-5 imputation without writing back.
- **Recommend:** projection-time only. Store stays NULL; STRATHMARK adapter substitutes
  5 with `quality_imputed=True` in the projected HistoricalResult.
- **Context:** Reviewer Concern #3. Decide before M2 (STIHL refactor).

### TODO-004: Concurrent-ingest serialization on Windows [v1]

- **What:** Confirm that `msvcrt.locking` semantics on Windows match the `fcntl.flock`
  semantics on POSIX for the JSONL append path.
- **Why:** O_APPEND is not atomic on Windows. The cross-platform store layer needs
  test coverage on both OSes.
- **Context:** Reviewer Concern #4. tests/test_store.py runs on the dual-CI matrix.
- **Depends on:** M1 (store implementation).

### TODO-005: Secrets recovery documentation [v1]

- **What:** Add a one-line note to docs about losing the `.env` and re-issuing keys
  vs trying to recover.
- **Why:** Reviewer Concern #5. Provider keys are revocable but not recoverable.
- **Effort:** ~5 minutes.

### TODO-006: Redaction scope for cost-ledger and extraction_notes [v1]

- **What:** When `mnemex identity redact` runs, also tombstone the `extraction_notes`
  field on affected canonical rows. The cost ledger doesn't reference athlete identity,
  so it doesn't need redaction handling.
- **Why:** `extraction_notes` may contain raw LLM output including the athlete's name.
- **Context:** Reviewer Concern #6.
- **Depends on:** M1 (identity service).

### TODO-007: identity_resolution_required semantics [v1]

- **What:** Specify in code that rows with `identity_resolution_required=true` cannot
  reach the canonical store. The review queue holds them until manually resolved.
- **Why:** The constraint "no unverified row reaches the handicap engine" requires
  this. Currently documented; needs implementation enforcement.
- **Context:** Reviewer Concern #7.
- **Depends on:** M1 (review queue).

### TODO-008: ExtractionStatus.NEEDS_INPUT vs identity_resolution_required overlap [v1]

- **What:** Differentiate or consolidate. Recommend keeping both — `NEEDS_INPUT` means
  "needs source operator to clarify the original sheet" (photo too blurry); `identity_resolution_required`
  means "names are ambiguous within MNEMEX's existing canonical athletes."
- **Context:** Reviewer Concern #8. Document the distinction inline in schema.py.

### TODO-009: PLACE_ONLY analytics safety [v1]

- **What:** Either add a derived `lower_is_better: bool` field to CanonicalRow OR never
  set `final_score` for PLACE_ONLY rows (use `place` only).
- **Why:** Mixing place values into `final_score` can confuse downstream analytics that
  assume "lower score = better."
- **Context:** Reviewer Concern #9. Recommend NOT setting `final_score` for PLACE_ONLY;
  the `place` field carries the data.
- **Depends on:** M1 (schema invariant tests).

### TODO-010: Image source format collision on re-extraction [v1]

- **What:** Use `image:<sha256>:v<prompt_version>` so re-extracting the same image after
  a prompt change creates a new pending row instead of duplicating.
- **Why:** Without prompt-version in the source ID, idempotent ingest treats them as
  duplicates and skips the re-extraction.
- **Context:** Reviewer Concern #10. Already documented in schema.py.
- **Depends on:** M4 (image ingest).

### TODO-011: CLI subcommand naming consistency [v1]

- **What:** Pick `mnemex strathmark-export` OR `mnemex export strathmark` and use one form.
- **Why:** Distribution Plan and integration-mechanisms sections use different forms.
- **Recommend:** `mnemex export strathmark --format jsonl` (composable with other formats).
- **Context:** Reviewer Concern #11.

### TODO-012: Versioned prompt templates format [v1]

- **What:** Lock the format of `mnemex/ingest/prompts/college_excel/v1.json`.
  Recommend: { "system": "...", "user_template": "...", "response_schema": {...} }
  with the response_schema as an inline JSON Schema.
- **Why:** Reviewer Concern #12. Implementer otherwise has to invent the format at M3.
- **Depends on:** M3 (first prompt-engineering iteration informs final format).

### TODO-013: Division enum mixing gender and skill levels [v1]

- **What:** Either split `Division` into a pure-skill enum (using existing `gender` field)
  or document explicitly that `Division.MEN`/`WOMEN` are gender-segregated open divisions.
- **Why:** Reviewer Concern #13. Currently mixes axes.
- **Recommend:** keep as-is for v1 (matches what real-world sources use), document the
  redundancy with `gender` field, revisit in v1.1.

### TODO-014: tier3.py shipping decision [v1]

- **What:** Confirm `tier3.py` ships in v1 with `NotImplementedError("Tier 3 never exports")`.
- **Why:** Repo tree includes it; M6 milestone implicitly covers it.
- **Status:** Already implemented as a NotImplementedError stub at M0. Done.

### TODO-015: Tier 2 feature-flag mechanism [v1]

- **What:** Confirm env-var gating `MNEMEX_ENABLE_TIER2=1` AND auto-detect via
  `strathmark.__version__` >= 0.5.
- **Why:** Reviewer Concern #15.
- **Status:** Implemented as `mnemex/strathmark_adapter/tier2.py:is_enabled()` at M0. Done.

---

## Feasibility caveats (price into expectations)

### TODO-016: Vision-LLM accuracy targets [v1]

- **What:** Document that ≥95% calibration / ≥90% ship gate applies to NUMERIC fields only.
  Athlete-name canonicalization is a separate human-loop metric.
- **Why:** Reviewer Concern #16.
- **Status:** Captured in design doc M3/M3.5 milestone descriptions. Re-document in
  CONTRIBUTING.md at M7.

### TODO-017: Calendar timeline at solo weekend pace [v1]

- **What:** Acknowledge that 47-70 focused-work-days = ~5-7 calendar months at solo
  weekend pace. Don't plan downstream milestones (e.g. STRATHEX integration) on the
  optimistic end.
- **Status:** Captured in design doc total estimate. No further action.

### TODO-018: First-name-only entries always need human review [v1]

- **What:** Implement the rule that first-name-only / initials-only rows ALWAYS enter
  the review queue with no automatic proposal, regardless of any fuzzy score.
- **Status:** Documented in design doc. Implementation lands at M1 (identity.match()).

### TODO-019: Calibration-mode flag for Vision-LLM ceiling [v1]

- **What:** Add a `--calibration-mode` flag that raises the daily ceiling to USD 100
  with explicit operator opt-in + audit-log entry.
- **Why:** Reviewer Concern #19. USD 20/day default ceiling may trip during M3 prompt iteration.
- **Depends on:** M3 (cost ledger first runs).

### TODO-020: STRATHMARK-side dependencies (--merge-corrections, --split-corrections) [v1.1]

- **What:** Coordinate a STRATHMARK 0.4.2 release that adds `--merge-corrections` and
  `--split-corrections` flags to `import_legacy.py`. Required for MNEMEX identity-correction
  propagation.
- **Why:** Reviewer Concern #20. v1 ships without merge-propagation; v1.1 lights it up
  once STRATHMARK 0.4.2 lands.
- **Depends on:** STRATHMARK release (out of MNEMEX's control).

### TODO-021: STRATHMARK token-vocabulary expansion [v1.1]

- **What:** Submit a STRATHMARK PR adding the expanded token vocabulary (STB, SBUCK,
  DBUCK, JJ, OP, PSAW, HSAW, SSAW, SPR1, SPR2, HS, VS) to STRATHMARK's discipline registry.
- **Why:** STRATHMARK 0.4.1 only knows "SB" and "UH". MNEMEX v1 ships against legacy
  vocabulary by restricting Tier 1 export to {UNDERHAND, STANDING_BLOCK} until the
  expanded vocab lands in STRATHMARK 0.4.2.
- **Recommend:** Submit the STRATHMARK PR concurrently with MNEMEX M6 work.
- **Context:** Reviewer Concern #21. The expanded `STRATHMARK_DISCIPLINE_MAP` in
  `mnemex/schema.py` is the source of truth for the new tokens.

### TODO-022: LibreOffice on Windows [v1]

- **What:** Document Windows install path and OS detection in
  `mnemex/ingest/college_excel.py`.
- **Why:** Reviewer Concern #22. CI Linux runner uses apt; local Windows users use MSI.
  Subprocess invocation differs.
- **Depends on:** M3 (college Excel parser).

---

## Eng Review additions (from /plan-eng-review)

### TODO-023: pending.db crash recovery test [v1] CRITICAL

- **What:** `tests/test_store_crash_recovery.py` — kill process during SQLite-tx +
  JSONL-append window; restart; assert deterministic rollforward/rollback.
- **Why:** The SQLite-tx-wrapping-JSONL-append crash window is the only critical gap
  flagged by Eng Review. Without this test, silent data loss is possible.
- **Depends on:** M1 (store + pending.db schema).

### TODO-024: Idempotent re-ingest test [v1]

- **What:** `tests/test_stihl_idempotent.py` — `mnemex stihl --season 2024` run twice;
  second run dedups on `source + source_native_id`.
- **Why:** Otherwise re-running the scraper after a partial failure double-counts.
- **Depends on:** M2 (STIHL ingest).

### TODO-025: Critical E2E STRATHMARK round-trip [v1]

- **What:** `tests/test_e2e_strathmark_roundtrip.py` — ingest 10 STIHL events → review/commit
  → export Tier 1 JSONL → STRATHMARK `import_legacy.py --commit` → run STRATHMARK
  `HandicapCalculator.calculate()` → assert mark output matches hand-computed expected.
- **Why:** Without this, every unit test could pass and the integration could still be
  wrong. Load-bearing for v1 ship.
- **Depends on:** M2 + M5 + M6.

---

## Design Review decisions (resolved at /plan-design-review, here for traceability)

- **TODO-026: Identity-picker text filter** — RESOLVED: prefix match first; fall back
  to fuzzy after no prefix match in 3+ chars. Implemented at M5 (`mnemex review`).
- **TODO-027: Strict-mode default for STRATHMARK export** — RESOLVED: permissive default;
  warn on imputed-quality rows; `--strict` flag refuses. Implemented at M6.

---

## DX Review additions

- **TODO-028: `mnemex tour` interactive walkthrough** — DEFERRED to v1.1.
  Demo command (locked at M0) is enough for v1.
- **TODO-029: GitHub Discussions** — DEFERRED to v1.1. Issues + issue templates only for v1.

---

## CEO Review additions (from /autoplan)

- **TODO-030: Three-leg ecosystem framing** — RESOLVED in design doc Problem Statement.
- **TODO-031: Scope discipline section** — RESOLVED in design doc.
- **TODO-032: `mnemex publish` federation backfill** — Milestone M4.5 added.
- **TODO-033: Web archive moved M8 → M2.5** — RESOLVED.

---

## Outside Voice (Codex CEO challenge) findings

### TODO-034: Data Rights and Governance documentation [v1]

- **What:** Write `docs/data-rights.md` covering attribution, takedown, ToS stance per
  source, and visible governance.
- **Status:** Section exists in design doc. Full `docs/data-rights.md` page lands at M7.
- **Depends on:** M7 (docs polish).

### TODO-035: Federation takedown CLI [v1]

- **What:** `mnemex takedown --federation <slug> --reason "<text>"` drops all rows from
  a federation source. Audit-logged. Reversible only via explicit re-ingest.
- **Why:** Codex finding "trust moat / governance" requires visible takedown semantics.
- **Depends on:** M5 (review + identity service).

### TODO-036: Ecosystem sequencing table [v1]

- **What:** Table tagging every v1 feature as INDEPENDENT / GATED-ON / DEFERRED / NEVER.
- **Status:** Section exists in design doc. Pull a copy into README.md at M7.

### TODO-037: Curator visibility (README + CONTRIBUTING) [v1]

- **What:** README states who runs MNEMEX (the operator, by name) and how to contact them.
  CONTRIBUTING.md governance section explains how disputes are handled.
- **Why:** "Canonical record" status is institutional, not engineering. Visible governance
  is the moat.
- **Depends on:** M7 (docs).

### TODO-038: Kill-condition / stop-loss for solo dev pace [Reviewer Concerns]

- **What:** Define a v0.1 ship date with minimum viable scope. If milestones slip past
  that date, ship the minimum and reassess.
- **Why:** Subagent-only finding. Solo open-source projects at weekend pace have high
  mortality rate.
- **Recommend:** Anchor v0.1 ship at "M0 + M1 + M2 + M2.5 + M7 minimum docs" — gets
  the static archive live with STIHL data only. Later milestones enrich incrementally.
- **Status:** Discussed in /autoplan; deferred to early-implementation when scope reality
  becomes clearer.

---

## Tracking

When a TODO is resolved, mark with `[RESOLVED]` and reference the commit hash. Don't delete
entries; the file is the institutional memory of design-phase decisions.
