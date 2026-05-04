# Supabase Setup for MNEMEX

This document captures the operator steps for provisioning the MNEMEX
Supabase projects. The MNEMEX code requires the projects to exist; it
does NOT (and cannot) provision them itself.

## Standing rule: credentials never paste into chat

Service-role keys, anon keys, JWT secrets, database passwords, and any
URL fragments that contain a project ref MUST live only in your local
`.env` file (or in GitHub Actions secrets for the workflow). They are
NEVER pasted into Claude.ai chat, into a prompt, into a commit message,
or into any text Claude.ai sees. This rule applies to all three RLS role
keys (service_role, strathmark_read, strathex_write).

## Two projects

MNEMEX uses two Supabase projects, both under the **STRATHEX**
organization (the same org that hosts STRATHMARK's
`iordtvxryrdhqvdkfgzf`).

| Name              | Purpose                              | Credentials env file           |
|-------------------|--------------------------------------|-------------------------------|
| `mnemex-prod`     | Production canonical store           | `.env` (root)                 |
| `mnemex-staging`  | Integration test target              | `.env.staging` (root)         |

The staging project mirrors production schema-for-schema (apply the same
migration set) and is wiped + reseeded by the integration test suite. It
holds no real production data.

## Region

Both projects: `us-east-1`. Matches the rest of the STRATHEX ecosystem
(STRATHMARK is also in `us-east-1`).

## Operator steps for first-time setup

These are the steps the user (Alex) runs manually. Do them once for
production, once for staging.

### 1. Create the project in the Supabase dashboard

1. Sign in to [supabase.com](https://supabase.com) with the STRATHEX-org
   account.
2. Open the **STRATHEX** organization.
3. Click **New project**.
4. Name: `mnemex-prod` (or `mnemex-staging`).
5. Database password: generate a strong one. Store it in 1Password (or
   equivalent), NOT in any text file in this repo.
6. Region: `us-east-1`.
7. Pricing plan: Free tier is sufficient for v1 staging; production
   should track ecosystem-standard plan.
8. Wait ~2 minutes for the project to spin up.

### 2. Capture the project ref and credentials

In the dashboard, open **Project Settings > API**:

- **Project URL**: `https://<project-ref>.supabase.co` - this is the
  `MNEMEX_SUPABASE_URL`.
- **service_role secret**: copy ONCE; this is `MNEMEX_SUPABASE_SERVICE_ROLE_KEY`.

Write both into the appropriate local env file:

```bash
# .env (production; loaded by mnemex code via python-dotenv)
MNEMEX_SUPABASE_URL=https://<prod-ref>.supabase.co
MNEMEX_SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
```

```bash
# .env.staging (used by the integration test suite)
MNEMEX_TEST_SUPABASE=1
MNEMEX_TEST_SUPABASE_URL=https://<staging-ref>.supabase.co
MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY=<staging_service_role_key>
```

`.env` and `.env.staging` are both git-ignored (see `.gitignore`).

### 3. Apply the migration

Install the Supabase CLI if you don't have it:
[supabase.com/docs/guides/cli](https://supabase.com/docs/guides/cli).

Then from the repo root:

```bash
# Production
supabase link --project-ref <prod-ref>
supabase db push

# Staging
supabase link --project-ref <staging-ref>
supabase db push
```

The migration applies `mnemex/migrations/20260504_001_initial_schema.sql`
which creates all tables, indexes, the `canonical_chopping_results` view,
and the `strathmark_read` and `strathex_write` roles. Federations are
seed-loaded.

Alternative: paste the SQL into the dashboard's **SQL Editor** and run.
Same outcome.

### 4. Generate the role-specific keys

Supabase only generates `anon` and `service_role` keys by default. The
`strathmark_read` and `strathex_write` keys for the new RLS roles are
generated separately:

1. In the dashboard, open **Project Settings > API > JWT Settings**.
2. Note the JWT secret (do not copy; just confirm it exists).
3. Use a Supabase JWT generator (or the `supabase functions` CLI) to
   mint a JWT for the new role names. Each JWT is signed with the
   project's JWT secret and carries `"role": "strathmark_read"` (or
   `"strathex_write"`) as a claim.
4. Store each JWT in 1Password under labels:
   - `MNEMEX prod - strathmark_read JWT`
   - `MNEMEX prod - strathex_write JWT`
5. When STRATHMARK or STRATHEX needs to consume MNEMEX (PRs 3 and 4),
   the JWT is provided to that consumer via their own secret store -
   never via this repo.

For Supabase project-ref values: store as plaintext in env files because
the project ref alone, without a key, cannot read or write data. The
key is the secret; the ref is the address.

### 5. GitHub Actions secrets (for the JSONL export workflow)

The nightly JSONL export workflow needs production credentials. From
the repo's GitHub web UI:

**Settings > Secrets and variables > Actions > New repository secret**

Add:

- `MNEMEX_SUPABASE_URL` (the production URL)
- `MNEMEX_SUPABASE_SERVICE_ROLE_KEY` (the production service-role key)

The workflow file (`.github/workflows/jsonl-export.yml`) reads these
via `secrets.*`.

## Project refs (record once, paste here as plaintext)

Project refs are not secrets; they're effectively project addresses.
Paste them here once you've provisioned the projects, so subsequent
contributors know which project is which:

```
mnemex-prod:    <FILL IN AFTER PROVISIONING>
mnemex-staging: <FILL IN AFTER PROVISIONING>
```

## Future migrations

Each future schema change lands as a new file in `mnemex/migrations/`,
named `YYYYMMDD_NNN_short_name.sql`. See `mnemex/migrations/README.md`
for the application and rollback rules. Migrations are forward-only;
reversing a change requires authoring a new migration that undoes it.
