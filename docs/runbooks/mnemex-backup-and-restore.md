# MNEMEX backup and recovery rehearsal

## Purpose and authority boundary

This runbook proves that a synthetic MNEMEX environment can be reconstructed from
three separate recovery dependencies:

1. a PostgreSQL snapshot;
2. a private-object export plus its MNEMEX object inventory; and
3. every MFA and security-notification encryption-key version required by the
   snapshot.

A Supabase database backup is not a backup of Supabase Storage objects. Database and
Storage export, retention, restore, and deletion are separate operations. Provider
console status alone is not recovery evidence; MNEMEX must reconcile the restored
schema, object digests and sizes, key-version inventory, and expired queue leases.

This procedure never enables `MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED`. It does not
authorize real PII, real credentials, production access, public profiles, or a live
race-day dependency. Shows continue to operate race day from a pinned local roster
and profile snapshot.

## Owners

- The system owner approves the backup-retention policy and the rehearsal window.
- The recovery operator creates and restores only the exact disposable targets.
- A distinct evidence reviewer checks the manifest, redacted result, cleanup receipt,
  and activation-report status.
- The credential custodian confirms key-version availability without copying keys into
  the report or application logs.

The runbook deliberately names roles instead of personal contacts. The system owner
must attach the current owner-provided contact and escalation route before hosted use.

## Preconditions

- Use synthetic identities and invalid-domain email addresses only.
- Use a unique suffix of at least eight lowercase letters, digits, or hyphens. All
  resources must derive from the same suffix:

  - target: `mnemex-rehearsal-<suffix>`
  - database: `mnemex_rehearsal_<suffix_with_underscores>`
  - object namespace: `mnemex-rehearsal/<suffix>`

- The database and object namespace must be newly created and empty. If either existed
  before the run, stop. Do not reuse, empty, overwrite, or repair it.
- The recovery environment fingerprint must be produced from the same non-secret
  configuration contract as the source manifest.
- The source recovery manifest must contain the database snapshot identity, canonical
  object-inventory digest and count, required MFA and notification key versions,
  application schema version, environment fingerprint, and its self-checking digest.
- Keep the offline activation-signing key outside the web and worker environments. It
  is not a recovery-rehearsal input.

## Capture the backup inventory

Before a backup can be considered rehearsable:

1. Record the provider's immutable PostgreSQL snapshot identity.
2. Export private Storage objects separately. For each object, record only its opaque
   digest-addressed reference, SHA-256 digest, and byte size. Do not record tenant
   names, uploaded filenames, signed URLs, or credentials.
3. Canonically sort the object inventory and record its digest and count in an
   immutable `RecoveryManifest`.
4. Record the required historical MFA and security-notification key-version numbers.
   Record version numbers only, never key bytes or secret-manager paths.
5. Record the application schema version and environment fingerprint.
6. Have the evidence reviewer compare the manifest to the database/object/key backup
   receipts before approving the backup set for a rehearsal.

An incomplete object export or unavailable historical key makes the backup set
unrehearsable. Do not retire a historical encryption key while any retained snapshot
or ciphertext requires it.

## Disposable rehearsal workflow

1. Create a new local or staging PostgreSQL target and private-object namespace with
   the exact shared suffix. Inventory both resources before restoration. Stop if
   either is not new and empty.
2. Restore the synthetic PostgreSQL snapshot using the provider-native restore tool.
   Do not restore over an existing project or database.
3. Restore the private-object export into the matching private namespace. Do not make
   the bucket public and do not expose browser credentials or signed URLs.
4. Make the required historical key versions available to the isolated rehearsal
   process through the approved secret-custody path. Do not print, export, or persist
   key material in the evidence bundle.
5. Build a restored-state inventory from the restored database, object bytes, and key
   version numbers. Object inventory must be computed from the restored bytes, not
   copied from the source manifest.
6. Run MNEMEX reconciliation. It must detect:

   - a different database snapshot or application schema;
   - an omitted, altered, or extra object;
   - a missing required MFA or notification key version;
   - application reconciliation failures; and
   - a lease-normalization count that differs from the expired running leases found.

7. Normalize only expired `running` notification or migration-job leases. Clear their
   claim ownership and return them to their existing retry path. Never change a live
   lease, replay a completed job, alter a terminal notification, or delete terminal
   evidence.
8. Capture the deterministic redacted evidence JSON. It may contain only fixed result
   and issue codes, digests, counts, and the environment fingerprint. It must not
   contain object references, snapshot identity, contact data, tokens, key bytes,
   secret paths, message bodies, or exception text.
9. Remove only the exact database and object namespace inventoried for this run. Then
   independently verify both are gone. If cleanup cannot be proven, open an operator
   incident and do not manually broaden the deletion target.
10. Repeat the rehearsal with a second newly named target and the same pinned
    observation time. Equivalent inputs must produce the same redacted evidence.

## Credential-free contract harness

`rehearse_restore` is the local, credential-free harness for the recovery contract.
It accepts only the exact disposable naming scheme, checks the manifest and supplied
restored-state inventories, normalizes only expired synthetic leases, emits redacted
JSON, and refuses to disable exact cleanup. It validates the target before reading a
fixture or constructing a backend.

The three JSON inputs are:

- `--manifest`: the immutable recovery manifest payload;
- `--object-inventory`: the expected source object inventory; and
- `--restored-state`: the independently collected restored database, object, key, and
  lease inventories plus fixed application issue codes.

Example using synthetic local files only:

```powershell
python manage.py rehearse_restore `
  --settings=mnemex.web.settings.test `
  --target-id=mnemex-rehearsal-run-00000001 `
  --environment-kind=disposable `
  --database-name=mnemex_rehearsal_run_00000001 `
  --object-namespace=mnemex-rehearsal/run-00000001 `
  --environment-fingerprint=<64-character-non-secret-fingerprint> `
  --manifest=<synthetic-manifest.json> `
  --object-inventory=<synthetic-object-inventory.json> `
  --restored-state=<synthetic-restored-state.json> `
  --observed-at=2026-08-18T12:00:00Z
```

This harness output proves deterministic application logic only. It is not evidence
that PostgreSQL, Supabase Storage, hosted key custody, or provider cleanup succeeded.
A disposable PostgreSQL/private-object rehearsal and its cleanup receipt remain
pending until actually observed in the target environment.

## Observable pass result

A rehearsal passes only when all of the following are true:

- database snapshot, schema, and environment fingerprint match the manifest;
- restored object count and canonical digest match exactly;
- all required MFA and notification key versions are available;
- all expired running leases, and only those leases, were normalized;
- application reconciliation returns no issue code;
- redacted evidence is deterministic for equivalent inputs; and
- both exact disposable resources are confirmed removed.

Any missing, mismatched, stale, unsigned, environment-mismatched, or cleanup-incomplete
evidence keeps hosted activation closed.

## Failure, rollback, and escalation

- **Unsafe or pre-existing target:** stop before any connection or mutation. Choose a
  new suffix; never empty the existing target.
- **Database restore failure:** preserve the provider error outside public logs,
  remove only the inventoried disposable resources, and record a fixed failure code.
- **Object mismatch:** do not import or parse the bytes. Preserve the manifest and
  redacted mismatch code, then remove the disposable namespace.
- **Missing historical key:** stop reconciliation. Restore access through the
  credential custodian; never substitute the active key or discard unreadable
  ciphertext.
- **Lease drift:** do not mass-update the queue. Review the exact expired-running set
  and the queue-specific transition rules.
- **Cleanup uncertainty:** do not retry with a broader path, wildcard, project, or
  database selector. Escalate with the exact target IDs and provider operation receipt.
- **Suspected real data or credential exposure:** stop the rehearsal, isolate its exact
  resources, follow the owner-approved security incident route, and keep the incident
  record out of the redacted activation report.

No step in this runbook automatically deploys MNEMEX, changes a production setting,
or authorizes privileged Results Desk access.
