# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MNEMEX** is the third leg of the STRATHEX ecosystem alongside:
- **STRATHEX** — live tournament management platform (captures current-era results during events)
- **STRATHMARK** — handicap and prediction engine (computes marks from historical results)
- **MNEMEX** (this repo) — historical archive (scrapes the past + accepts federation backfill)

MNEMEX's job is to be the **historical memory** of Timbersports: a continuously growing
archive of competition results from federations, events, and scorebooks across decades.
It feeds STRATHMARK's training data and gives the platform deep historical context that
no live scoring system can produce on its own.

The full design rationale is in [docs/MNEMEX-design-2026-05-04.md](docs/MNEMEX-design-2026-05-04.md).
That doc has been through 5 plan-phase reviews (CEO, Eng, Design, DX, Outside Voice via Codex)
and is the canonical source of truth for v1 scope.

## Scope Discipline (load-bearing)

MNEMEX is **historical-only**. Discipline: **scrape first, accept federation historical backfill second, and stop.**

### What MNEMEX is

- **Primary function: scraping.** Collects old results from public sources — federation
  websites, archived event pages, PDF scorebooks (ALA, CANLOG newsletters), photographed
  scoresheets, news coverage. Most of the value is data that exists somewhere online but
  is unstructured, scattered, or buried in formats nobody has parsed.
- **Secondary function: federation backfill.** Some federations have decades of internal
  records that were never published. MNEMEX accepts batched uploads from federation admins
  (CSV, Excel, structured upload form). One-way intake for historical data only.

### What MNEMEX is NOT

- **NOT a portal for federations to enter live or current match results.** That is STRATHEX's job.
- **NOT a scoring system.** MNEMEX never decides who won an event.
- **NOT a competitor to STRATHEX's tournament management.**
- **NOT a real-time data source.**

A parallel live-entry portal in MNEMEX would duplicate STRATHEX's core function, fragment
the data pipeline, and create two sources of truth for current-era results. It is forbidden
by design. The `mnemex publish` historical-backfill flow refuses to ingest events with dates
within the federation's STRATHEX-active window.

## v1 Scope (per design doc)

Five ingest paths: STIHL HTML scraper, college Excel via Vision LLM, ALA / CANLOG newsletter
PDF via Vision LLM, photographed scoresheet via Vision LLM, manual CSV / federation backfill.

Plus: identity dedup service with cross-source matching, pending review queue with audit-comment
threads, JSONL+git canonical store, SQLite pending queue, export hub (CSV / JSON / 9-col XLSX),
STRATHMARK Tier 1 adapter (JSONL → import_legacy.py), static web archive (Astro/Next.js,
deployed to GitHub Pages), `mnemex demo` magical-moment command.

v1 estimate: ~47-70 focused work-days, 5-7 calendar months solo.

## Tier classification (which disciplines export to STRATHMARK)

- **Tier 1** — time-scored speed events. Ship cleanly against STRATHMARK 0.4.1.
  UH, STB, SB, DB, JJ, OP, Power Saw, Hot Saw, Stock Saw, Springboard 1bd/2bd, HS, VS.
- **Tier 2** — hits-based axe events (HHH, VHH). Need STRATHMARK ≥ 0.5 with `score_type` field.
  v1 implements but feature-flag-disables.
- **Tier 3** — distance / knowledge / place-only events. Captured in MNEMEX archive **forever**;
  **never** exported to STRATHMARK. STRATHMARK is a handicap engine, period.

## Code Patterns

### When adding a new ingest source

1. Subclass `mnemex.ingest.IngestSource`.
2. Output `CanonicalRow` records with full provenance (`source` field uses
   `<source_type>:<instance_id>` format).
3. Use the shared `mnemex.ingest.llm_client` for any Vision-LLM call. Don't roll your own.
4. Vision-LLM rows enter the pending queue with `extraction_status` populated; the review
   queue handles state transitions.
5. Never write directly to `data/canonical.jsonl` — go through `mnemex.store.commit_pending`.

### When changing the schema

- **Enums are append-only.** Adding a value is fine; renaming or removing requires a major version bump + migration script.
- **New fields must have defaults.** Existing JSONL rows must remain valid.
- **Tier classification matters.** A new Discipline must be added to TIER1, TIER2, or TIER3
  in `mnemex/schema.py`. The `test_every_discipline_classified` test catches misses.

### CLI output style (CI-enforced)

- Plain text. No emojis. No ANSI color. No banner art.
- Utility language ("scrape the STIHL official site"), not marketing voice.
- Errors name the file/path/value involved AND propose the next action.
- The single `✓` glyph is allowed for success indicators; no other unicode glyphs.

A regex-based test (`tests/test_cli_output_style.py`, lands at M7) asserts every CLI
command's output matches these rules.

## Score accuracy is non-negotiable

This rule is inherited verbatim from STRATHMARK. Wrong ingest data corrupts handicap math,
which makes races unfair. **No row reaches the STRATHMARK adapter unverified.** The review
queue is the recheck protocol for image-extracted and parser-extracted rows. The contract
test gates every release.

## Development Commands

```bash
# Install with dev dependencies (note: the repo will be renamed to mnemex)
pip install -e ".[dev]"

# Run the schema tests (the only thing that passes at end-of-Milestone-0)
pytest tests/test_schema.py -v

# Run the full test suite (most tests are placeholders until M1+)
pytest -v

# Type-check the public API
mypy mnemex/

# Lint
ruff check mnemex/ tests/
ruff format mnemex/ tests/
```

## Workflow

This project uses gstack + Superpowers. The design doc and all 5 plan-phase reviews
are tracked in `~/.gstack/projects/$SLUG/`.

### Decision & Review Layer (gstack)
- /plan-ceo-review — product-level thinking, strategic direction
- /plan-eng-review — architecture review, tech debt assessment
- /plan-design-review — UI/UX critique
- /plan-devex-review — developer experience review
- /autoplan — bundles CEO + dual-voice (Claude subagent + Codex) into one pass
- /review — structural code review, pattern compliance
- /qa — browser-based QA testing
- /ship — branch finishing, PR creation
- /retro — engineering retrospective

### Build Layer (Superpowers — for multi-file features)
- /brainstorming → /writing-plans → /executing-plans (TDD enforcement)
- For quick fixes / single-file changes: skip Superpowers, use gstack directly

### Override Rules
- CLAUDE.md instructions > Superpowers skills > default behavior
- Codex QA reviewer is the independent QA layer — runs AFTER /review
- For multi-file features, refactors, and new modules: full Superpowers TDD workflow

## Inherited project rules

From the user's global CLAUDE.md:

- **Test isolation** — Tests MUST NEVER write to or pollute production data. Use separate
  test databases, fixtures, or transactions that roll back. Vision-LLM tests use cached
  fixture responses, not live API calls.
- **Stale cache** — When debugging Python import errors or unexpected behaviour where
  source code looks correct, check for stale `__pycache__/.pyc` files first.
- **Git workflow** — Always check the current branch before running release/deploy
  workflows. Feature branches are required for PRs. Never assume we're on a feature branch.
- **Context retention** — When the user references a business name or prior decision,
  search the codebase and docs for context before claiming ignorance. Read DESIGN.md,
  README, and recent git history.

## Important Context

- **The repo's GitHub name is currently `stihl-timbersports-aggregator`** but the package
  is `mnemex`. The repo will be renamed in a future Milestone 0 task (requires the user's
  explicit authorization since renaming a published repo is a coordination-required action).
- **No live API calls in tests by default.** Vision-LLM tests are gated behind the
  `requires_vision_llm` pytest marker and skipped when `MNEMEX_VISION_PROVIDER_KEY` is unset.
- **The 22+ Reviewer Concerns** from the design-phase reviews are tracked in `TODOS.md`
  for early-implementation triage. Read it before starting any milestone.
