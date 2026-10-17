# MNEMEX security operations runbook

## Status and purpose

This runbook describes the future hosted workflow for privileged staff invitations,
lost-authenticator recovery, security notifications, and encryption-key rotation. It
is also the script for the required synthetic first-operator rehearsal.

The repository does not authorize a deployment. Production privileged access remains
hard-disabled, and this procedure must use synthetic accounts until a separate owner
decision approves hosted activation. Do not put contact details, invitation codes,
authenticator secrets, recovery codes, encryption keys, object references, or message
bodies in tickets, screenshots, logs, or activation evidence.

## Roles and separation of duties

- **Security administrator:** creates scope-bound invitations and recovery requests.
- **Independent approver:** verifies a recovery using an owner-approved record and
  must be a different person from the requester.
- **Invited operator:** verifies their email, enrolls MFA, and accepts their own
  invitation.
- **Recovery subject:** re-enrolls MFA after existing sessions and factors are
  revoked; they cannot restore their own privilege.
- **Key custodian:** controls versioned key material outside the repository and
  application logs.
- **Incident owner:** chooses rollback or containment using the current private
  escalation route. This repository deliberately does not invent a contact or SLA.

A tenant-scoped security administrator may act only inside that tenant. A platform
security administrator may act across tenants. A request identifier from another
scope must behave like an unknown identifier.

## Before any ceremony

1. Confirm the intended environment, immutable release, and organization scope.
2. Confirm the operator is using the MNEMEX HTTPS origin, not a copied or redirected
   form.
3. Confirm the security administrator has a fresh MFA session. Sensitive forms use an
   in-page challenge and a one-use ticket bound to that browser session, route, method,
   account security version, and origin.
4. Obtain the subject's opaque MNEMEX account ID from the independently verified staff
   record. The portal does not list staff email addresses.
5. Create a non-secret evidence reference in the approved private record. The
   reference may identify that record but must not contain contact data, credentials,
   authenticator material, or incident narrative.
6. Stop if shared cache, database, mail, or private-object readiness is unavailable.
   Security decisions fail closed.

## Invite a privileged operator

1. Sign in as a security administrator and open **Security operations**.
2. Under **Start a role invitation**, enter the opaque account ID, role, platform or
   organization scope, and non-secret evidence reference.
3. Submit the form. If MFA freshness has expired, complete the in-page challenge,
   review the still-visible form, and choose **Submit now** once.
4. Copy the displayed one-time invitation code immediately into the approved secure
   out-of-band channel. The response is marked private and non-cacheable. The code is
   never placed in a URL, audit event, notification, or database column; only its
   purpose-bound hash is stored.
5. Leave or refresh the page after transfer. The displayed code cannot be recovered.
   Cancel the invitation and issue a new one if transfer is uncertain.
6. The invited operator signs in to their own verified account, enrolls TOTP and saves
   recovery codes outside the device, opens the invitation acceptance page, and enters
   the one-time code.
7. Confirm the queue reports the invitation as accepted and the exact intended role
   and scope became effective. A replay, wrong account, expiry, cancellation, security
   version change, or policy-version change must fail with a generic response.

Do not send a raw invitation code in ordinary application email. The durable mail
queue records transition notices, not reusable invitation authority.

## Recover a lost authenticator

1. The first security administrator independently verifies the subject and opens
   **Security operations**.
2. Under **Start lost-authenticator recovery**, enter the subject's opaque account ID,
   the typed reason, and the non-secret evidence reference. This creates a request; it
   does not restore access.
3. A different authorized security administrator repeats the independent check,
   opens the request by its opaque identifier, matches the evidence reference, and
   approves it.
4. Approval revokes every existing browser session and MFA factor, increments the
   account security version, and suspends the subject's privileged roles. Access stays
   suspended.
5. The subject signs in through the approved account-recovery path, verifies the
   primary address as policy permits, enrolls a new TOTP authenticator, and stores new
   one-use recovery codes separately.
6. An authorized security administrator reopens the request, confirms the new factor
   exists, and deliberately restores the suspended roles. The approval must still be
   current; any intervening security-version change requires a new recovery request.
7. Confirm the operation is completed, old sessions remain invalid, old factors and
   recovery codes do not work, and only the intended roles were restored.

For suspected compromise, use this same two-person path. The affected mailbox,
password, requester, or subject alone is never sufficient authority.

## Security notifications

Security-state transitions enqueue PII-minimized notification intents in the same
database transaction as their audit boundary. The worker holds only a versioned
encrypted event-time recipient snapshot plus a keyed identity until the approved
retention deadline. It never stores a rendered message body.

Operators monitor these states:

- `pending` or `retry_wait`: delivery has not been accepted; bounded retry is allowed.
- `running`: one worker holds a live fenced lease. Retention cleanup must not purge it.
- `delivered`: the transport accepted the message.
- `delivery_uncertain`: transport handoff may have occurred but settlement was not
  provable. Do not automatically redeliver; review the provider event.
- `failed_review`: retry budget or a permanent safe failure requires human review.
- `expired`: a pre-handoff intent exceeded retention and no active lease exists.

The worker output may report counts, oldest-ready age, fixed state names, and fixed
error codes. It must not report recipient values, ciphertext, message content, tokens,
or provider exception text.

Generic allauth account-security notices now use this queue exclusively. The web
request never falls back to immediate SMTP. It accepts only the configured password,
verified-contact, TOTP, and recovery-code security templates, snapshots only an
address that allauth currently marks verified for that account, and makes exact
replays idempotent within the account security revision. Rendering and transport occur
only in the worker.

If queue creation fails, the security mutation is allowed to finish so a mail outage
cannot strand a password or factor change. MNEMEX records a PII-free
`account.security_notification.failed` audit event and does not attempt immediate
delivery. Treat that audit action, `failed_review`, `delivery_uncertain`, nonzero ready
depth without worker progress, or an increasing oldest-ready age as an operator alert.
The hosted activation gate remains pending until staging proves authenticated SMTP
handoff, retry, ambiguous-handoff review, and a complete recovery-notice ceremony.

## Rotate encryption keys

1. Back up the complete historical key ring through the owner-approved custody path.
   Record version numbers only in application evidence.
2. Add a new positive integer version and its 32-byte high-entropy key. Keep the old
   version present and select the new version as active.
3. Restart web and worker processes only after strict configuration validation passes.
4. Enqueue or resume the bounded MFA key-rotation job. Monitor scanned, rotated,
   ready, oldest-ready, retry, claim-loss, and failed-review counts.
5. Interrupt and resume a synthetic rotation before hosted use. A stale worker must be
   unable to settle a newer claim.
6. Verify every rewritten authenticator decrypts under the new version before the
   batch commits.
7. Run the recovery inventory and activation report. Retirement is blocked while any
   authenticator, notification, retained recovery manifest, or active rotation job
   still requires the old version.
8. Remove an old key only after a separate reviewed retirement decision and a current
   restorable backup prove that no durable ciphertext needs it.

Unknown versions and authentication failures are generic permanent security failures.
Never substitute the active key for missing historical material.

## Synthetic first-operator rehearsal

Use two security administrators and one operator, all synthetic invalid-domain
accounts. No participant or staff PII is permitted.

1. Administrator A creates an invitation in the portal and transfers its one-time
   code through the rehearsal's approved out-of-band channel.
2. The operator verifies email, enrolls MFA, accepts the invitation, and enters the
   intended workspace.
3. Force the operator's sensitive-action freshness to expire. Populate a form,
   including a synthetic file where applicable, complete the in-page MFA challenge,
   confirm the form is still intact, and submit deliberately once. A rapid second
   submit must not create a second action.
4. Administrator A creates a lost-authenticator recovery.
5. Administrator B, who did not create it, approves it. Confirm the operator's old
   sessions, old factors, and privilege are unusable.
6. The operator enrolls a new authenticator. An authorized administrator explicitly
   restores the suspended role.
7. Confirm notification, audit, invitation, approval, suspension, restoration, and
   action-ticket evidence contain no contact value or secret.
8. Record a redacted pass or fail observation for the first-operator activation gate.
   The observer must not be the person who prepared the release.

## Incident cues and containment

Keep production privilege disabled and stop the affected ceremony when any of these
occurs:

- a code, factor, recipient, or private payload appears in a URL, log, report, or audit;
- the same invitation or action ticket succeeds twice;
- the requester can approve their own recovery;
- privilege returns before new MFA enrollment and explicit restoration;
- a notification remains `delivery_uncertain` or `failed_review`;
- a required historical key is missing or ciphertext authentication fails;
- queue age grows without bounded progress;
- an unauthorized scope produces a distinguishable existence response; or
- the browser loses a populated form or submits it without deliberate confirmation.

Preserve fixed error codes, timestamps, request identifiers, and environment/release
digests in the private incident record. Do not repair append-only evidence directly in
the database. Attach the current owner-provided contact and escalation route outside
this repository.

## Completion evidence

A ceremony is complete only when the expected immutable state transitions, session
revocation, factor state, role scope, notification intent, and PII-free audit records
are independently verified. Local automated tests prove application behavior only.
Hosted SMTP delivery, shared Redis atomicity, edge throttling, provider monitoring,
and human rehearsal evidence remain separate activation gates.
