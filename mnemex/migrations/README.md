# MNEMEX Migrations

This directory holds the SQL migration history for MNEMEX's Supabase
schema. The migrations are checked into git as the canonical source of
truth for the database structure.

## File naming

`YYYYMMDD_NNN_short_name.sql`

- `YYYYMMDD` is the date the migration was authored (UTC). Sortable.
- `NNN` is a zero-padded sequence within that date. Reset daily.
- `short_name` is a snake_case description.

Example: `20260504_001_initial_schema.sql`

## Apply

The Supabase CLI is the standard tool. From the repo root:

```bash
supabase link --project-ref <mnemex-prod-ref>
supabase db push
```

Or apply via the dashboard: open the project's SQL editor and paste
the contents of the migration file.

For the staging project (used by the integration test suite), substitute
the staging project ref. See `docs/supabase-setup.md` for the project
refs and credential storage rules.

## Idempotency

Every migration in this directory uses `CREATE TABLE IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE VIEW`, and `INSERT ...
ON CONFLICT DO NOTHING` so that re-running a migration on a database
where it already applied is a no-op for the structural pieces.

Re-running a migration that `ALTER`s an existing table is NOT idempotent
in general. Future migrations that mutate live tables MUST use
conditional logic (`DO $$ ... IF NOT EXISTS $$`) or land as separate
add-only migrations.

## Rollback

Migrations are forward-only. To revert a structural change:

1. Author a new migration that reverses it.
2. Apply the new migration via `supabase db push`.
3. Do NOT delete or edit the original migration file. The audit trail
   is the file history.

For an emergency rollback before a migration has been deployed beyond
staging, drop the migration file from the branch via `git revert` and
recreate the staging project from the previous migration set.

## Related docs

- `docs/supabase-setup.md` - project refs, env vars, credential rules
- `docs/supabase-rls-policies.md` - the three roles (service_role,
  strathmark_read, strathex_write) and what each can do
