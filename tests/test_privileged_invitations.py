from __future__ import annotations

from datetime import timedelta

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from mnemex.accounts.models import (
    Account,
    PrivilegedInvitation,
    PrivilegedRoleAssignment,
)
from mnemex.accounts.notifications import run_security_notifications_once
from mnemex.accounts.services import (
    accept_privileged_invitation,
    cancel_privileged_invitation,
    create_privileged_invitation,
)
from mnemex.partners.models import PartnerOrganization
from tests.mfa_helpers import enroll_account_mfa, verify_account_email

pytestmark = pytest.mark.django_db


def _account(label: str, *, ready: bool = True) -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password",
    )
    if ready:
        enroll_account_mfa(account)
    return account


def _security_admin(label: str = "security-admin") -> Account:
    account = _account(label)
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        assigned_by=account,
    )
    return account


def test_invitation_secret_is_hashed_purpose_bound_and_accepted_once() -> None:
    admin = _security_admin()
    subject = _account("invite-subject")

    invitation, secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-1042",
    )

    assert secret not in invitation.secret_digest
    assert secret not in str(invitation.request_id)
    accepted = accept_privileged_invitation(
        subject=subject,
        request_id=invitation.request_id,
        secret=secret,
    )
    assert accepted.status == accepted.Status.ACCEPTED
    assert PrivilegedRoleAssignment.objects.filter(
        account=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        revoked_at__isnull=True,
    ).exists()

    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=invitation.request_id,
            secret=secret,
        )


def test_invitation_rejects_wrong_subject_expiry_cancellation_and_stale_security_version() -> None:
    admin = _security_admin()
    subject = _account("subject")
    wrong_subject = _account("wrong-subject")

    wrong, wrong_secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-2001",
    )
    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=wrong_subject,
            request_id=wrong.request_id,
            secret=wrong_secret,
        )

    expired, expired_secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-2002",
        expires_at=timezone.now() + timedelta(seconds=1),
    )
    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=expired.request_id,
            secret=expired_secret,
            now=timezone.now() + timedelta(seconds=2),
        )

    cancelled, cancelled_secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-2003",
    )
    cancel_privileged_invitation(invitation=cancelled, cancelled_by=admin)
    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=cancelled.request_id,
            secret=cancelled_secret,
        )

    stale, stale_secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.PRIVACY_OFFICER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-2004",
    )
    subject.security_version += 1
    subject.save(update_fields=["security_version"])
    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=stale.request_id,
            secret=stale_secret,
        )


def test_invitation_requires_verified_email_mfa_and_authorized_scope() -> None:
    admin = _security_admin()
    subject = _account("not-ready", ready=False)
    verify_account_email(subject)
    invitation, secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-3001",
    )
    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=invitation.request_id,
            secret=secret,
        )
    assert not Authenticator.objects.filter(user=subject).exists()

    unauthorized = _account("ordinary-requestor")
    with pytest.raises(PermissionDenied):
        create_privileged_invitation(
            requested_by=unauthorized,
            subject=subject,
            role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            scope=PrivilegedRoleAssignment.Scope.PLATFORM,
            external_evidence_reference="HR-TEST-3002",
        )


def test_security_administrator_role_is_platform_or_tenant_scoped() -> None:
    assert PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR.value == "security_administrator"
    assert PrivilegedRoleAssignment.Scope.PLATFORM.value == "platform"
    assert PrivilegedRoleAssignment.Scope.ORGANIZATION.value == "organization"


def test_invitation_evidence_cannot_be_changed_or_deleted() -> None:
    admin = _security_admin()
    subject = _account("immutable-subject")
    invitation, _secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-4001",
    )
    invitation.external_evidence_reference = "CHANGED"
    with pytest.raises(PermissionDenied, match="immutable"):
        invitation.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        PrivilegedInvitation.objects.filter(pk=invitation.pk).delete()


def test_invitation_rejects_role_policy_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = _security_admin()
    subject = _account("policy-subject")
    invitation, secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-5001",
    )
    monkeypatch.setattr("mnemex.accounts.services.PRIVILEGED_ROLE_POLICY_VERSION", 2)

    with pytest.raises(ValidationError, match="could not be accepted"):
        accept_privileged_invitation(
            subject=subject,
            request_id=invitation.pk,
            secret=secret,
        )


def test_organization_security_admin_cannot_invite_outside_tenant_scope() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Partner A")
    other_organization = PartnerOrganization.objects.create(name="Synthetic Partner B")
    admin = _account("tenant-admin")
    subject = _account("tenant-subject")
    PrivilegedRoleAssignment.objects.create(
        account=admin,
        role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization,
        assigned_by=admin,
    )

    invitation, _secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization,
        external_evidence_reference="HR-TEST-6001",
    )
    assert invitation.organization == organization

    with pytest.raises(PermissionDenied):
        create_privileged_invitation(
            requested_by=admin,
            subject=subject,
            role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization=other_organization,
            external_evidence_reference="HR-TEST-6002",
        )
    with pytest.raises(PermissionDenied):
        create_privileged_invitation(
            requested_by=admin,
            subject=subject,
            role=PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
            scope=PrivilegedRoleAssignment.Scope.PLATFORM,
            external_evidence_reference="HR-TEST-6003",
        )


def test_invitation_transition_notification_renders_and_delivers() -> None:
    admin = _security_admin()
    subject = _account("notification-subject")
    create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-7001",
    )

    outcome = run_security_notifications_once(owner="u4-focused-test", limit=1)

    assert outcome.claimed == outcome.delivered == 1
    assert outcome.failed_review == outcome.delivery_uncertain == 0
