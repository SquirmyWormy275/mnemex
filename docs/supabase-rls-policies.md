# MNEMEX Supabase RLS Policies

Three roles operate on the MNEMEX database. Each has a precisely scoped
contract; nothing else.

| Role               | Surface                              | Can do          | Cannot do                        | Used by                                    |
|--------------------|--------------------------------------|-----------------|----------------------------------|-------------------------------------------|
| `service_role`     | Every base table + every view        | Full read/write | (nothing restricted)             | MNEMEX internal: scrapers, reconciliation worker, JSONL exporter, federation upload pipeline |
| `strathmark_read`  | `canonical_chopping_results` view    | SELECT only     | Read base tables; any write      | STRATHMARK pulling chopping data for prediction (PR 3 implements the sync triggers) |
| `strathex_write`   | `strathex_inbox` table               | INSERT only     | SELECT, UPDATE, DELETE; touch any other table | STRATHEX finalization webhook (PR 4 implements the handler) |

## Why three roles, not one shared key

The temptation is to give STRATHMARK and STRATHEX the service-role key
and call it done. Three reasons we don't:

1. **Blast radius.** If STRATHMARK's deployment leaks its key, the
   damage is bounded to "an attacker can read the canonical chopping
   view." With service_role, the attacker would be able to drop tables.
2. **STRATHMARK's surface is intentionally narrow.** The
   `canonical_chopping_results` view hides provenance, reconciliation,
   and operational columns. Giving STRATHMARK service_role would let it
   accidentally read provisional rows and corrupt its prediction
   training set. The view enforces the contract.
3. **STRATHEX is write-only.** STRATHEX should never read from MNEMEX
   (its own database is the source of truth for live events). Granting
   read access creates a bidirectional coupling we don't want.

## service_role

Supabase auto-generates this on every project. It bypasses RLS by
default. MNEMEX's own code uses this for everything that requires
write access to base tables.

The service_role key lives in:
- Local `.env` (developer machines)
- GitHub Actions secrets (the JSONL export workflow)
- The deployment environment for the reconciliation worker (PR 5)
- The deployment environment for the federation upload pipeline (M4.5)

It does NOT live in:
- STRATHMARK's deployment environment (use `strathmark_read` JWT)
- STRATHEX's deployment environment (use `strathex_write` JWT)
- Any chat with Claude.ai
- Any commit, PR description, or issue body

## strathmark_read

Created in `20260504_001_initial_schema.sql` via:

```sql
CREATE ROLE strathmark_read NOLOGIN;
GRANT SELECT ON canonical_chopping_results TO strathmark_read;
REVOKE ALL ON results, competitors, ingestion_runs, reconciliation_queue,
              strathex_inbox, federations
       FROM strathmark_read;
```

The view `canonical_chopping_results` filters to:
- chopping disciplines only (TIER1 from `mnemex.schema`)
- canonical rows only (`provisional = FALSE OR canonical_id IS NOT NULL`)
- non-superseded rows only (`canonical_id IS NULL`)
- exposes only the columns STRATHMARK needs (no source_type, source_id,
  ingestion_run_id, provisional flag, etc.)

STRATHMARK consumes this view via a JWT minted with `"role":
"strathmark_read"` as a claim, signed with the project's JWT secret.
The JWT is delivered to STRATHMARK out of band (1Password, deployment
secrets) - never via this repo.

## strathex_write

Created in `20260504_001_initial_schema.sql` via:

```sql
CREATE ROLE strathex_write NOLOGIN;

CREATE POLICY strathex_inbox_insert_only
    ON strathex_inbox
    FOR INSERT
    TO strathex_write
    WITH CHECK (true);

GRANT INSERT ON strathex_inbox TO strathex_write;

REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
       ON strathex_inbox
       FROM strathex_write;
REVOKE ALL ON results, competitors, ingestion_runs, reconciliation_queue,
              federations, canonical_chopping_results
       FROM strathex_write;
```

The webhook handler in PR 4 will:
1. Authenticate STRATHEX (HMAC-signed payload).
2. Validate the payload shape.
3. Use the `strathex_write` JWT to INSERT a single row into
   `strathex_inbox` with `strathex_event_id` set to STRATHEX's event
   UUID.
4. The UNIQUE constraint on `strathex_event_id` makes the INSERT
   idempotent: STRATHEX retries on the same event are deduplicated at
   the database layer.
5. MNEMEX's reconciliation worker (PR 5, using service_role) reads the
   inbox, processes payloads into canonical results, and updates the
   inbox row's `status` and `processed_at`.

## Verifying the policies

The integration test suite (PR 2) includes
`tests/test_supabase_schema.py` which:

- Connects with each role's JWT
- Attempts the operations the role should be able to do (and asserts
  success)
- Attempts the operations the role should NOT be able to do (and asserts
  failure)

Run with `MNEMEX_TEST_SUPABASE=1` set against the staging project to
verify the policies are wired correctly before applying the migration to
production.

## Adding a new role in a future migration

If a fourth role is needed (e.g., a public read-only API role that
exposes a smaller view to fans), it lands as a new migration file:

1. Author `mnemex/migrations/YYYYMMDD_NNN_add_role_<name>.sql`.
2. `CREATE ROLE` with `IF NOT EXISTS` semantics (the
   `DO $$ ... CREATE ROLE ... END $$` pattern from the initial migration).
3. `CREATE OR REPLACE VIEW` for the role's surface, if any.
4. `GRANT` exactly the permissions needed.
5. `REVOKE` everything else, defensively.
6. Add a test in `tests/test_supabase_schema.py`.
7. Update this document.
