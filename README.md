# MNEMEX

The historical archive of competitive Timbersports. Third leg of the
STRATHEX ecosystem alongside STRATHEX (live tournament management) and
STRATHMARK (handicap and prediction engine).

MNEMEX scrapes results from federation sites, parses scorebook PDFs,
extracts data from photographed scoresheets, and accepts federation
historical-backfill uploads. Its output feeds STRATHMARK's training data
and serves as a standalone, browsable archive of timbersports competition
history across decades.

This repo is in active development. Current state: PR 1 (additive schema)
merged, PR 2 (Supabase canonical store) in progress.

## Status

| Component                   | State                                |
|-----------------------------|--------------------------------------|
| Schema (dataclasses)        | Implemented (PR 1)                   |
| Canonical store (Supabase)  | Schema and code in PR 2; provisioning is operator-action |
| STIHL ingest                | Stub; refactor at M2                 |
| College Excel ingest        | Stub; M3                             |
| ALA / CANLOG newsletter ingest | Stub; M3.5                        |
| Image (Vision LLM) ingest   | Stub; M4                             |
| Federation upload pipeline  | Not started; M4.5                    |
| STRATHMARK three-trigger sync | Not started; PR 3                  |
| STRATHEX inbound webhook    | Not started; PR 4                    |
| Reconciliation worker       | Not started; PR 5                    |
| Static web archive          | Not started; M2.5                    |
| `mnemex demo` command       | Not started; M0 follow-up            |

See `docs/MNEMEX-design-2026-05-04.md` for the locked design doc.

## Storage

Supabase is the canonical store. Two projects live under the STRATHEX
organization:

- `mnemex-prod` (production)
- `mnemex-staging` (integration test target)

Both run the same schema, defined in `mnemex/migrations/`. See
`docs/supabase-setup.md` for the operator setup steps and the rule about
credentials never appearing in chat.

JSONL snapshots are generated nightly by `.github/workflows/jsonl-export.yml`
and committed to the orphan `data` branch. JSONL is an export artifact,
not a canonical source. See `data/README.md` for the consumer-side
contract.

The legacy plan was JSONL+git as canonical with SQLite as a pending
queue; that plan is superseded by the Supabase decision in PR 2.

## Ecosystem topology

```
External sources                STRATHEX (live events)
(federation sites,              writes finalized event
archived events,                results to MNEMEX on
scorebook PDFs)                 event completion
        |                                |
        v                                v
    MNEMEX (universal archive of record - canonical)
        |
        | sync (chopping disciplines, canonical only)
        v
    STRATHMARK Supabase (chopping cache + ML state)
        |
        | reads only at prediction time
        v
    STRATHMARK prediction cascade
```

MNEMEX must remain useful as a standalone product. Without STRATHEX or
STRATHMARK running, MNEMEX still operates as a searchable archive (the
`data` branch JSONL snapshots and the `mnemex` CLI both work
standalone).

## Scope discipline

MNEMEX is **historical-only**. The discipline:

1. Scrape first.
2. Accept federation historical backfill second.
3. Stop.

Live result entry, current-event scoring, and any "tournament management"
feature belong in STRATHEX, not here. The `mnemex publish` federation
backfill flow refuses event dates within a federation's STRATHEX-active
window.

## Local development

```bash
# Clone
git clone https://github.com/SquirmyWormy275/mnemex.git
cd mnemex

# Install with dev dependencies
pip install -e ".[dev]"

# Run the test suite
pytest -v

# Without Supabase credentials, the integration tests skip cleanly.
# To run them, populate .env.staging and set MNEMEX_TEST_SUPABASE=1.
# See docs/supabase-setup.md for the credential setup.
```

## Repo layout

```
mnemex/                  Python package
  schema.py              CanonicalRow, enums, tier classification
  identity.py            CanonicalAthlete, match/merge/split (M1)
  ingestion_runs.py      IngestionRun, lifecycle helpers, ULID generator
  store.py               Supabase-backed canonical store (PR 2)
  cli.py                 mnemex CLI entrypoint
  errors.py              structured error registry
  ingest/                ingest path stubs (stihl, college, etc.)
  export/                export hub stubs (csv, json, excel)
  strathmark_adapter/    Tier 1/2/3 projection stubs
  migrations/            checked-in SQL migrations

tests/                   pytest suite
  test_schema.py
  test_identity.py
  test_ingestion_runs.py
  test_strathmark_contract.py
  test_supabase_schema.py     (gated on MNEMEX_TEST_SUPABASE=1)
  test_store_supabase.py      (gated on MNEMEX_TEST_SUPABASE=1)
  fixtures/                   sample PDFs and Excel files

docs/                    design doc + operator playbooks
  MNEMEX-design-2026-05-04.md
  supabase-setup.md
  supabase-rls-policies.md

data/                    placeholder (real data lives on the `data` branch)

.github/workflows/       CI and scheduled jobs
  jsonl-export.yml       nightly canonical -> JSONL snapshot
```

## Related repos

- STRATHEX: live tournament management platform (private)
- STRATHMARK: handicap and prediction engine (pip-installable Python
  package; v0.4.1)

## License

Proprietary, pending finalization.
