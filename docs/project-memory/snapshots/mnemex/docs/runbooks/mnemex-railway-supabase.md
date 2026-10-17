# MNEMEX Railway and Supabase runbook

## Status and purpose

This is the operating procedure for a future hosted MNEMEX staging or production
environment. It is not authorization to deploy. The repository deliberately keeps
`MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = False` in production, and an activation
report is evidence for owner review rather than a switch that can change that value.

Use this runbook to create or update the web, release, worker, PostgreSQL, Redis, mail,
and private-object boundaries after the named owner has approved a deployment window.
Do not use the deprecated direct-Supabase schema or JSONL-export instructions.

## Required owners and access

Before starting, record these people in the private change record. Do not put personal
contact details or credentials in this repository.

- Change owner and rollback decision maker
- Database backup and restore operator
- Private-object storage operator
- Security-key custodian
- Mail-delivery operator
- Independent verifier who did not prepare the release

The operator needs access to Railway, the dedicated Supabase project, the shared Redis
service, the mail provider, and the offline activation-signing process. A real
credential must never be copied into a test command, ticket, screenshot, or activation
report.

## Service topology

One immutable image is used by two Railway services:

| Service | Responsibility | Must not do |
| --- | --- | --- |
| Web | Gunicorn, operator portals, `/health/live`, `/health/ready` | Run migrations in its start command or process background queues |
| Worker | Artifact reconciliation, legacy APPLY jobs, security notifications, key rotation | Listen on HTTP or own release migrations |

The web service owns one pre-deploy command. It applies forward migrations and runs
deployment checks before Railway promotes the new web process. The worker has no
pre-deploy command. Configuration lives in `deploy/railway/web.json` and
`deploy/railway/worker.json`.

Supabase PostgreSQL is the server-side transaction boundary. Supabase Storage holds
private digest-addressed source artifacts. Browser clients never receive the service
role key or a public object URL. Redis provides distinct namespaces for rate limiting
and atomic security claims.

## Configuration inventory

Configure values in the hosted secret manager, not in files. Every staging and
production environment needs its own values.

### Django and network

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS` when a trusted HTTPS origin is required
- `DJANGO_SECURE_HSTS_SECONDS`
- `DATABASE_URL` with an approved TLS `sslmode`
- `ALLAUTH_TRUSTED_PROXY_COUNT` matching the reviewed Railway proxy chain

### Shared cache and mail

- `MNEMEX_CACHE_URL` using authenticated `rediss://`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

### Versioned encryption keys

- `MNEMEX_MFA_ENCRYPTION_KEYS`
- `MNEMEX_MFA_ACTIVE_KEY_VERSION`
- `MNEMEX_NOTIFICATION_ENCRYPTION_KEYS`
- `MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION`

Key maps are JSON objects whose canonical positive integer versions point to base64
encoded 32-byte values. Store the complete restorable historical ring with the key
custodian. Adding a key and rotating data precedes retirement; never remove a version
still named by stored ciphertext, a recovery manifest, or an active rotation job.

### Private artifacts

- `MNEMEX_SUPABASE_URL`
- `MNEMEX_SUPABASE_SERVICE_ROLE_KEY`
- `MNEMEX_PRIVATE_ARTIFACT_BUCKET`

The bucket must remain private. `MNEMEX_PRIVATE_ARTIFACT_BACKEND` is pinned to
`supabase` and `MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC` is pinned false by production
settings; they are not operator-controlled activation toggles.

## Pre-deployment gates

Stop before deployment unless all items are true:

1. The intended branch and exact immutable revision are recorded.
2. The release uses only expand-and-contract migrations compatible with the running
   web and worker versions.
3. Isolated SQLite tests and the disposable PostgreSQL suite pass for that revision.
4. Shared Redis atomic-claim tests pass against a disposable service.
5. `check --deploy` passes with the intended hosted configuration while privileged
   production authorization remains hard-disabled.
6. A fresh database backup and private-object inventory are recorded.
7. The full versioned key rings required by the backup are available to the recovery
   operator.
8. A disposable restore rehearsal passes and produces redacted evidence.
9. Mail sender authentication, bounce handling, complaint handling, and recovery-abuse
   monitoring have current staging evidence.
10. The independent verifier confirms the activation report is blocked when any
    required evidence is absent, stale, failed, or bound to another environment.

## Staging deployment

1. Create separate Railway web and worker services from the same repository revision.
2. Point each service to its matching configuration file under `deploy/railway/`.
3. Supply staging-only PostgreSQL, Redis, mail, storage, and key configuration.
4. Deploy the web service. Its pre-deploy command must finish before the web process is
   promoted.
5. Confirm `/health/live` responds without checking dependencies and `/health/ready`
   reports only database/cache state with no connection details.
6. Confirm the collected CSS and JavaScript are served under fingerprinted names from
   the image.
7. Deploy one worker service. Confirm it opens no HTTP listener and rotates fairly
   through bounded queue tasks.
8. Exercise only synthetic accounts, results, workbooks, notifications, and restore
   bundles.
9. Stop and investigate any terminal migration job, blocked artifact, delivery-
   uncertain notification, failed key rotation, or readiness failure.
10. Capture redacted staging evidence. Hosted-only gates must remain pending until the
    actual observation exists.

## Production promotion

Production promotion requires a separate approval after staging evidence review.

1. Record current production database and object-inventory evidence.
2. Confirm the rollback image can run against the forward schema.
3. Promote the web image and allow the single pre-deploy owner to apply migrations.
4. Verify readiness before routing operator traffic.
5. Promote the worker image only after the web and schema are stable.
6. Observe queue depths, oldest ready ages, terminal review states, mail outcomes, and
   artifact reconciliation without logging identifiers or payloads.
7. Run the representative operator rehearsal and recovery smoke checks.
8. Build the environment-bound activation report and have the offline owner process
   verify/sign it if every gate passes.

Do not change the hard-disabled privileged-production constant during this procedure.
That is a separate reviewed code change after the full activation decision.

## Rollback

Prefer application rollback against the already-expanded forward schema.

1. Stop worker promotion or scale the worker down between claims.
2. Route web traffic to the last compatible image.
3. Do not reverse migrations unless a migration-specific, rehearsed rollback says it
   is safe. Durable queue, checkpoint, and evidence rows are append-only history.
4. If integrity is uncertain, keep privileged access disabled and restore into a new
   disposable environment before choosing a production recovery action.
5. Record the stable failure code, affected component, timestamps, and image/schema
   revisions. Do not record secrets, addresses, workbook contents, or legal identity.

## Incident cues

Treat these states as requiring human review:

- Readiness unavailable while liveness remains healthy
- Repeated worker task failure or process restart
- Artifact digest mismatch or referenced object missing
- Legacy migration unresolved terminal failure
- Notification `delivery_uncertain` after SMTP handoff
- Notification recipient decryption failure
- Key rotation claim failure or missing historical version
- Recovery inventory drift
- Activation evidence that is stale, tampered, duplicated, unknown, or bound to the
  wrong environment

Keep production privilege disabled during investigation. Follow the security and
backup runbooks for the affected domain; never repair append-only history with direct
database edits.

## Evidence and completion

A deployment is operationally complete only when:

- the exact revision and schema state are recorded;
- web and worker responsibilities remain separate;
- database, cache, private storage, mail, and queue observations are redacted;
- the recovery manifest matches database, objects, schema, and required key versions;
- the independent verifier can reproduce the activation-report decision; and
- every remaining pending gate is named rather than represented as passed.
