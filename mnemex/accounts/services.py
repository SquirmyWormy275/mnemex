from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone
from django.utils.crypto import salted_hmac

from mnemex.accounts.authorization import has_effective_role
from mnemex.accounts.models import (
    Account,
    PrivilegedInvitation,
    PrivilegedInvitationState,
    PrivilegedRecoveryApproval,
    PrivilegedRecoveryRequest,
    PrivilegedRecoveryState,
    PrivilegedRoleAssignment,
    PrivilegedRoleSuspension,
)
from mnemex.accounts.notifications import enqueue_security_notification
from mnemex.foundation.services import record_audit_event

if TYPE_CHECKING:
    from mnemex.partners.models import PartnerOrganization

PRIVILEGED_ROLE_POLICY_VERSION = 1
DEFAULT_INVITATION_LIFETIME = timedelta(days=2)
DEFAULT_RECOVERY_LIFETIME = timedelta(hours=8)
_MAX_OPERATION_LIFETIME = timedelta(days=7)
_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,119}$")
_GENERIC_INVITATION_ERROR = "invitation could not be accepted"
_GENERIC_RECOVERY_ERROR = "recovery could not be approved"


def _now(value: datetime | None) -> datetime:
    current = timezone.now() if value is None else value
    if timezone.is_naive(current):
        raise ValidationError("security operation time must be timezone-aware")
    return current


def _reference(value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not _REFERENCE_RE.fullmatch(normalized):
        raise ValidationError("external evidence reference is invalid")
    return normalized


def _expiry(*, now: datetime, expires_at: datetime | None, default: timedelta) -> datetime:
    expiry = now + default if expires_at is None else expires_at
    if timezone.is_naive(expiry) or not now < expiry <= now + _MAX_OPERATION_LIFETIME:
        raise ValidationError("security operation expiry is invalid")
    return expiry


def _digest(*parts: object) -> str:
    return hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _record_transition(
    *,
    action: str,
    target_type: str,
    request_id: UUID,
    actor: Account,
    status: str,
) -> None:
    record_audit_event(
        action=action,
        target_type=target_type,
        target_id=str(request_id),
        correlation_id=request_id,
        payload_digest=_digest(action, request_id, actor.pk, status),
        metadata={"status": status},
        actor_id=actor.pk,
    )


def _verified_destination(account: Account) -> str:
    if (
        account.email_verified_at is None
        or not EmailAddress.objects.filter(
            user=account,
            email__iexact=account.email,
            verified=True,
        ).exists()
    ):
        raise ValidationError("verified security-notification destination is unavailable")
    return account.email


def _notify_transition(
    *,
    account: Account,
    request_id: UUID,
    transition: str,
    now: datetime,
) -> None:
    enqueue_security_notification(
        account=account,
        template_identifier="account/email/security_operation",
        recipient=_verified_destination(account),
        context_code=f"security-{transition}-v1",
        idempotency_key=f"security-operation:{request_id}:{transition}",
        now=now,
    )


def _administrator_covers(
    account: Account,
    *,
    scope: str,
    organization: PartnerOrganization | None,
) -> bool:
    role = PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR
    if scope == PrivilegedRoleAssignment.Scope.PLATFORM:
        return has_effective_role(account, role)
    if scope == PrivilegedRoleAssignment.Scope.ORGANIZATION and organization is not None:
        return has_effective_role(account, role, organization=organization)
    return False


def _administrator_covers_subject(
    account: Account,
    subject: Account,
    *,
    include_recovery_suspended: bool = False,
) -> bool:
    assignments_query = subject.privileged_roles.filter(revoked_at__isnull=True)
    if not include_recovery_suspended:
        assignments_query = assignments_query.exclude(
            pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
                "assignment_id"
            )
        )
    assignments = list(assignments_query.select_related("organization"))
    return bool(assignments) and all(
        _administrator_covers(
            account,
            scope=assignment.scope,
            organization=assignment.organization,
        )
        for assignment in assignments
    )


def _invitation_secret_digest(
    *,
    request_id: UUID,
    subject_id: UUID,
    security_version: int,
    secret: str,
) -> str:
    return salted_hmac(
        "mnemex.accounts.privileged-invitation.v1",
        f"{request_id}:{subject_id}:{security_version}:{secret}",
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


@transaction.atomic
def create_privileged_invitation(
    *,
    requested_by: Account,
    subject: Account,
    role: PrivilegedRoleAssignment.Role | str,
    scope: PrivilegedRoleAssignment.Scope | str,
    external_evidence_reference: str,
    organization: PartnerOrganization | None = None,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[PrivilegedInvitation, str]:
    created_at = _now(now)
    role_value = str(role)
    scope_value = str(scope)
    if role_value not in PrivilegedRoleAssignment.Role.values:
        raise ValidationError("requested privileged role is invalid")
    if not _administrator_covers(
        requested_by,
        scope=scope_value,
        organization=organization,
    ):
        raise PermissionDenied("security administrator scope is required")
    if (scope_value == PrivilegedRoleAssignment.Scope.PLATFORM) != (organization is None):
        raise ValidationError("requested privileged scope is invalid")
    current_subject = Account.objects.select_for_update().get(pk=subject.pk)
    if not current_subject.is_active:
        raise ValidationError("invitation could not be created")
    if current_subject.privileged_roles.filter(
        role=role_value,
        scope=scope_value,
        organization=organization,
        revoked_at__isnull=True,
    ).exists():
        raise ValidationError("invitation could not be created")
    request_id = uuid4()
    secret = secrets.token_urlsafe(32)
    invitation = PrivilegedInvitation.objects.create(
        request_id=request_id,
        subject=current_subject,
        requested_by=requested_by,
        role=role_value,
        scope=scope_value,
        organization=organization,
        external_evidence_reference=_reference(external_evidence_reference),
        secret_digest=_invitation_secret_digest(
            request_id=request_id,
            subject_id=current_subject.pk,
            security_version=current_subject.security_version,
            secret=secret,
        ),
        subject_security_version=current_subject.security_version,
        role_policy_version=PRIVILEGED_ROLE_POLICY_VERSION,
        expires_at=_expiry(
            now=created_at,
            expires_at=expires_at,
            default=DEFAULT_INVITATION_LIFETIME,
        ),
        created_at=created_at,
    )
    PrivilegedInvitationState.objects.create(invitation=invitation)
    _record_transition(
        action="account.privileged_invitation.created",
        target_type="privileged_invitation",
        request_id=request_id,
        actor=requested_by,
        status=PrivilegedInvitationState.Status.PENDING,
    )
    _notify_transition(
        account=current_subject,
        request_id=request_id,
        transition="invitation-created",
        now=created_at,
    )
    return invitation, secret


def _subject_ready_for_privilege(account: Account) -> bool:
    return bool(
        account.is_active
        and account.email_verified_at is not None
        and EmailAddress.objects.filter(
            user=account,
            email__iexact=account.email,
            verified=True,
        ).exists()
        and Authenticator.objects.filter(
            user=account,
            type=Authenticator.Type.TOTP,
        ).exists()
    )


@transaction.atomic
def accept_privileged_invitation(
    *,
    subject: Account,
    request_id: UUID,
    secret: str,
    now: datetime | None = None,
) -> PrivilegedInvitationState:
    accepted_at = _now(now)
    invitation = (
        PrivilegedInvitation.objects.select_related("subject", "organization")
        .filter(pk=request_id, subject_id=subject.pk)
        .first()
    )
    if invitation is None:
        raise ValidationError(_GENERIC_INVITATION_ERROR)
    state = PrivilegedInvitationState.objects.select_for_update().get(invitation=invitation)
    current_subject = Account.objects.select_for_update().get(pk=subject.pk)
    supplied_digest = _invitation_secret_digest(
        request_id=invitation.pk,
        subject_id=current_subject.pk,
        security_version=invitation.subject_security_version,
        secret=secret if isinstance(secret, str) else "",
    )
    valid = (
        state.status == PrivilegedInvitationState.Status.PENDING
        and accepted_at < invitation.expires_at
        and invitation.subject_security_version == current_subject.security_version
        and invitation.role_policy_version == PRIVILEGED_ROLE_POLICY_VERSION
        and hmac.compare_digest(invitation.secret_digest, supplied_digest)
        and _subject_ready_for_privilege(current_subject)
        and _administrator_covers(
            invitation.requested_by,
            scope=invitation.scope,
            organization=invitation.organization,
        )
    )
    if not valid:
        raise ValidationError(_GENERIC_INVITATION_ERROR)
    try:
        PrivilegedRoleAssignment.objects.create(
            account=current_subject,
            role=invitation.role,
            scope=invitation.scope,
            organization=invitation.organization,
            assigned_by=invitation.requested_by,
        )
    except IntegrityError as error:
        raise ValidationError(_GENERIC_INVITATION_ERROR) from error
    state.status = PrivilegedInvitationState.Status.ACCEPTED
    state.accepted_at = accepted_at
    state.save(update_fields=["status", "accepted_at", "updated_at"])
    _record_transition(
        action="account.privileged_invitation.accepted",
        target_type="privileged_invitation",
        request_id=invitation.pk,
        actor=current_subject,
        status=state.status,
    )
    _notify_transition(
        account=current_subject,
        request_id=invitation.pk,
        transition="invitation-accepted",
        now=accepted_at,
    )
    return state


@transaction.atomic
def cancel_privileged_invitation(
    *,
    invitation: PrivilegedInvitation,
    cancelled_by: Account,
    now: datetime | None = None,
) -> PrivilegedInvitationState:
    cancelled_at = _now(now)
    current = PrivilegedInvitation.objects.select_related("organization", "subject").get(
        pk=invitation.pk
    )
    if not _administrator_covers(
        cancelled_by,
        scope=current.scope,
        organization=current.organization,
    ):
        raise PermissionDenied("security administrator scope is required")
    state = PrivilegedInvitationState.objects.select_for_update().get(invitation=current)
    if state.status != PrivilegedInvitationState.Status.PENDING:
        raise ValidationError("invitation could not be cancelled")
    state.status = PrivilegedInvitationState.Status.CANCELLED
    state.cancelled_at = cancelled_at
    state.cancelled_by = cancelled_by
    state.save(update_fields=["status", "cancelled_at", "cancelled_by", "updated_at"])
    _record_transition(
        action="account.privileged_invitation.cancelled",
        target_type="privileged_invitation",
        request_id=current.pk,
        actor=cancelled_by,
        status=state.status,
    )
    _notify_transition(
        account=current.subject,
        request_id=current.pk,
        transition="invitation-cancelled",
        now=cancelled_at,
    )
    return state


@transaction.atomic
def create_privileged_recovery(
    *,
    requested_by: Account,
    subject: Account,
    external_evidence_reference: str,
    reason_code: PrivilegedRecoveryRequest.Reason | str,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> PrivilegedRecoveryRequest:
    created_at = _now(now)
    current_subject = Account.objects.select_for_update().get(pk=subject.pk)
    if requested_by.pk == current_subject.pk or not _administrator_covers_subject(
        requested_by, current_subject
    ):
        raise PermissionDenied("authorized security administrator is required")
    reason = str(reason_code)
    if reason not in PrivilegedRecoveryRequest.Reason.values:
        raise ValidationError("recovery reason is invalid")
    reference = _reference(external_evidence_reference)
    recovery = PrivilegedRecoveryRequest.objects.create(
        subject=current_subject,
        requested_by=requested_by,
        external_evidence_reference=reference,
        reason_code=reason,
        subject_security_version=current_subject.security_version,
        expires_at=_expiry(
            now=created_at,
            expires_at=expires_at,
            default=DEFAULT_RECOVERY_LIFETIME,
        ),
        created_at=created_at,
    )
    PrivilegedRecoveryState.objects.create(recovery=recovery)
    _record_transition(
        action="account.privileged_recovery.created",
        target_type="privileged_recovery",
        request_id=recovery.pk,
        actor=requested_by,
        status=PrivilegedRecoveryState.Status.PENDING_APPROVAL,
    )
    _notify_transition(
        account=current_subject,
        request_id=recovery.pk,
        transition="recovery-created",
        now=created_at,
    )
    return recovery


def _delete_account_sessions(account: Account) -> None:
    sessions = Session.objects.filter(expire_date__gte=timezone.now()).iterator(chunk_size=200)
    session_keys = []
    for session in sessions:
        try:
            if session.get_decoded().get("_auth_user_id") == str(account.pk):
                session_keys.append(session.session_key)
        except Exception:
            continue
    if session_keys:
        Session.objects.filter(session_key__in=session_keys).delete()


@transaction.atomic
def approve_privileged_recovery(
    *,
    recovery: PrivilegedRecoveryRequest,
    approved_by: Account,
    external_evidence_reference: str,
    now: datetime | None = None,
) -> PrivilegedRecoveryState:
    approved_at = _now(now)
    current = PrivilegedRecoveryRequest.objects.select_related("subject", "requested_by").get(
        pk=recovery.pk
    )
    if approved_by.pk in {current.requested_by_id, current.subject_id}:
        raise PermissionDenied("a distinct security administrator must approve recovery")
    if not _administrator_covers_subject(approved_by, current.subject):
        raise PermissionDenied("authorized security administrator is required")
    state = PrivilegedRecoveryState.objects.select_for_update().get(recovery=current)
    subject = Account.objects.select_for_update().get(pk=current.subject_id)
    supplied_reference = _reference(external_evidence_reference)
    valid = (
        state.status == PrivilegedRecoveryState.Status.PENDING_APPROVAL
        and approved_at < current.expires_at
        and subject.security_version == current.subject_security_version
        and hmac.compare_digest(current.external_evidence_reference, supplied_reference)
    )
    if not valid:
        raise ValidationError(_GENERIC_RECOVERY_ERROR)
    active_assignments = list(
        PrivilegedRoleAssignment.objects.select_for_update()
        .filter(account=subject, revoked_at__isnull=True)
        .exclude(
            pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
                "assignment_id"
            )
        )
    )
    if not active_assignments:
        raise ValidationError(_GENERIC_RECOVERY_ERROR)
    PrivilegedRecoveryApproval.objects.create(
        recovery=current,
        approved_by=approved_by,
        evidence_reference_digest=_digest(
            "mnemex.accounts.recovery-evidence.v1", supplied_reference
        ),
        approved_subject_security_version=subject.security_version,
        approved_at=approved_at,
    )
    for assignment in active_assignments:
        PrivilegedRoleSuspension.objects.create(
            assignment=assignment,
            recovery=current,
            suspended_at=approved_at,
        )
    Authenticator.objects.filter(user=subject).delete()
    subject.security_version += 1
    subject.mfa_enrolled_at = None
    subject.save(update_fields=["security_version", "mfa_enrolled_at"])
    _delete_account_sessions(subject)
    state.status = PrivilegedRecoveryState.Status.AWAITING_REENROLLMENT
    state.approved_at = approved_at
    state.save(update_fields=["status", "approved_at", "updated_at"])
    _record_transition(
        action="account.privileged_recovery.approved",
        target_type="privileged_recovery",
        request_id=current.pk,
        actor=approved_by,
        status=state.status,
    )
    _notify_transition(
        account=subject,
        request_id=current.pk,
        transition="recovery-approved",
        now=approved_at,
    )
    return state


@transaction.atomic
def restore_recovered_privileges(
    *,
    recovery: PrivilegedRecoveryRequest,
    restored_by: Account,
    now: datetime | None = None,
) -> PrivilegedRecoveryState:
    restored_at = _now(now)
    current = PrivilegedRecoveryRequest.objects.select_related("subject").get(pk=recovery.pk)
    if restored_by.pk == current.subject_id or not _administrator_covers_subject(
        restored_by,
        current.subject,
        include_recovery_suspended=True,
    ):
        raise PermissionDenied("authorized security administrator is required")
    state = PrivilegedRecoveryState.objects.select_for_update().get(recovery=current)
    subject = Account.objects.select_for_update().get(pk=current.subject_id)
    if state.status != PrivilegedRecoveryState.Status.AWAITING_REENROLLMENT:
        raise ValidationError("recovery is not ready for restoration")
    approval = PrivilegedRecoveryApproval.objects.filter(recovery=current).first()
    if (
        approval is None
        or subject.security_version != approval.approved_subject_security_version + 1
    ):
        raise ValidationError("recovery approval is no longer current")
    if not _subject_ready_for_privilege(subject):
        raise ValidationError("MFA re-enrollment is required before privilege restoration")
    suspensions = list(
        PrivilegedRoleSuspension.objects.select_for_update().filter(
            recovery=current,
            restored_at__isnull=True,
        )
    )
    if not suspensions:
        raise ValidationError("recovery is not ready for restoration")
    PrivilegedRoleSuspension.objects.filter(
        pk__in=[suspension.pk for suspension in suspensions]
    ).update(restored_at=restored_at, restored_by=restored_by)
    state.status = PrivilegedRecoveryState.Status.COMPLETED
    state.restored_at = restored_at
    state.restored_by = restored_by
    state.save(update_fields=["status", "restored_at", "restored_by", "updated_at"])
    _record_transition(
        action="account.privileged_recovery.completed",
        target_type="privileged_recovery",
        request_id=current.pk,
        actor=restored_by,
        status=state.status,
    )
    _notify_transition(
        account=subject,
        request_id=current.pk,
        transition="recovery-completed",
        now=restored_at,
    )
    return state


def visible_recoveries_for(account: Account) -> QuerySet[PrivilegedRecoveryRequest]:
    """Return only operations covered by the administrator's effective scope."""

    if has_effective_role(account, PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR):
        return PrivilegedRecoveryRequest.objects.all()
    organization_ids = (
        account.privileged_roles.filter(
            role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            revoked_at__isnull=True,
        )
        .exclude(
            pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
                "assignment_id"
            )
        )
        .values_list("organization_id", flat=True)
    )
    subject_assignments = PrivilegedRoleAssignment.objects.filter(
        account_id=OuterRef("subject_id"),
        revoked_at__isnull=True,
    )
    forbidden_assignment = subject_assignments.filter(
        Q(scope=PrivilegedRoleAssignment.Scope.PLATFORM)
        | Q(
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization_id__isnull=False,
        )
        & ~Q(organization_id__in=organization_ids)
    )
    return PrivilegedRecoveryRequest.objects.annotate(
        has_subject_role=Exists(subject_assignments),
        has_forbidden_subject_role=Exists(forbidden_assignment),
    ).filter(
        has_subject_role=True,
        has_forbidden_subject_role=False,
    )


def visible_invitations_for(account: Account) -> QuerySet[PrivilegedInvitation]:
    if has_effective_role(account, PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR):
        return PrivilegedInvitation.objects.all()
    organization_ids = (
        account.privileged_roles.filter(
            role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            revoked_at__isnull=True,
        )
        .exclude(
            pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
                "assignment_id"
            )
        )
        .values_list("organization_id", flat=True)
    )
    return PrivilegedInvitation.objects.filter(
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization_id__in=organization_ids,
    )
