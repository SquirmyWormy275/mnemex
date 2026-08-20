# MNEMEX Phase A implementation status

Date: 2026-08-14

## Outcome

The local Phase A code foundation is implemented. It establishes the hosted
Django modular monolith without enabling production PII, credentials, public
profiles, partner access, or deployment.

Implemented:

- Django 5.2 LTS project with separate base, test, and production settings;
- MNEMEX-owned email account model and initial migrations;
- PostgreSQL `DATABASE_URL` parsing for production;
- isolated SQLite tests plus an optional guarded local-PostgreSQL test URL;
- hard rejection of remote or non-test PostgreSQL targets in test settings;
- Argon2-first password hashing configuration;
- append-only application-level audit primitives with PII-key rejection;
- idempotency records with uniqueness-race savepoint handling;
- a server-owned transaction wrapper and injected-crash rollback test;
- liveness and database-aware readiness endpoints;
- WSGI, ASGI, management, and Phase A worker-check entry points;
- synthetic-only reusable test-data factories;
- strict targeted typing and lint coverage for the new foundation.

## Verification evidence

| Check | Result |
| --- | --- |
| Phase A tests, default isolated SQLite | 20 passed, 1 PostgreSQL-only test skipped |
| Phase A tests, disposable PostgreSQL 18 | 21 passed |
| Repository suite excluding the versioned STRATHMARK contract | 101 passed, 42 skipped, 3 deselected |
| Full repository suite | 103 passed, 42 skipped, 1 failed |
| Known full-suite failure | `test_strathmark_version_in_pinned_range`: installed STRATHMARK 2.0.0 is outside the legacy MNEMEX `<0.6` pin |
| Migration drift | `No changes detected` |
| Django system checks | 0 issues |
| Ruff | all Phase A checks passed |
| Mypy | 16 Phase A source files passed with Django stubs |
| Django deployment check | no errors; two deliberate HSTS subdomain/preload warnings remain pending the production-domain decision |

Pytest cache writing was disabled for these runs because the agent sandbox cannot
create `.pytest_cache` in this checkout. This does not alter test behavior.

## Gate assessment

- PASS: test settings ignore configured production `DATABASE_URL` and Supabase
  credentials and reject remote PostgreSQL before connection.
- PASS: injected failure rolls back both audit and idempotency writes as one
  service transaction on SQLite and PostgreSQL.
- PASS: two concurrent PostgreSQL requests using the same idempotency key commit
  exactly one record and return one created/one replay outcome.
- PASS: PostgreSQL verification ran on an isolated temporary PostgreSQL 18 cluster
  under the system temp directory using trust authentication on localhost only.
  The server was stopped and the verified cluster directory was removed after the
  run. No production or shared staging credential was used.

Phase A's local acceptance gate is closed. This status does not authorize
deployment or real PII.
