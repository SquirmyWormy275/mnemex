# STRATHEX onboarding

STRATHEX 7.4.3 preserves V2 production operation and adds a complete separate Linux V3 competition profile. The [Linux competition runbook](https://github.com/SquirmyWormy275/STRATHEX/blob/main/docs/V3_LINUX_COMPETITION.md) covers real Formula + trained ML, signed local authority, mark-free seeding, exact handicap/championship receipts, deliberate approval and separate issue confirmation, complete outcomes, settlement, restart, official corrections, verified recovery and later-round learning. The LLM council is unavailable; degraded or individual review is required. Existing numeric previews and authenticated V7 rehearsal scopes retain their original contracts. Windows CNG production qualification remains separate.

Read the [handicap foundations](https://github.com/SquirmyWormy275/STRATHMARK/blob/main/docs/wiki/Handicap-Mark-Math.md), [README](README.md), [current runtime contract](docs/CURRENT_RUNTIME_CONTRACT.md), [architecture](docs/ARCHITECTURE.md), and [V3 rehearsal setup](docs/V3_REHEARSAL.md).

Install Python 3.13, then `python -m pip install -e ".[dev,api-test]"`. Linux and Windows share the same source and command: `strathex --workbook /absolute/path/to/workbook.xlsx --data-dir /absolute/path/to/operator-data`. On Windows, use Windows absolute paths. The workbook must exist and include Competitor, Wood, and Results sheets. Data-directory defaults can be overridden by the explicit STRATHMARK/STRATHEX environment variables documented in the runbook.

The legacy `python MainProgramV5_2.py` entry remains supported. It opens the configured workbook at import time, initializes ResultStore, and starts its interactive loop. Use the new launcher to select paths before those imports. Keep workbook and data backups together.

For tests, use a fresh temporary directory, export `STRATHMARK_TEST_DB=1`, and assign unique `STRATHMARK_DB_PATH`, `STRATHMARK_V3_DB_PATH`, `STRATHEX_PREDICTION_AUTHORITY_DB`, and `STRATHEX_V3_COMMAND_DB` paths. Run pytest with an explicit `--basetemp` and `-p no:cacheprovider`. Existing tests use synthetic data; historical benchmark scripts are excluded from release collection.

Run `ruff check .`, `ruff format --check .`, `python scripts/check_docs.py`, `python -m build`, then `python scripts/smoke_installed_app.py --wheel dist/strathex-7.4.3-py3-none-any.whl`. The installed smoke starts and exits the actual terminal app with a generated workbook outside the checkout. It opens no live competition data.
