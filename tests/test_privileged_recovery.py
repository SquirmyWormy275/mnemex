from __future__ import annotations

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError

from mnemex.accounts.authorization import has_effective_role
from mnemex.accounts.models import (
    Account,
    PrivilegedRecoveryApproval,
    PrivilegedRoleAssignment,
    PrivilegedRoleSuspension,
    SecurityNotification,
)
from mnemex.accounts.services import (
    approve_privileged_recovery,
    create_privileged_recovery,
    restore_recovered_privileges,
)
from tests.mfa_helpers import enroll_account_mfa, force_login_with_fresh_mfa

pytestmark = pytest.mark.django_db


def _account(label: str) -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password",
    )
    enroll_account_mfa(account)
    return account


def _admin(label: str) -> Account:
    account = _account(label)
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
        assigned_by=account,
    )
    return account


def _target() -> Account:
    account = _account("recovery-target")
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=account,
    )
    return account


def test_distinct_approver_revokes_sessions_and_factors_and_suspends_roles() -> None:
    requestor = _admin("requestor")
    approver = _admin("approver")
    target = _target()
    client_one = __import__("django.test", fromlist=["Client"]).Client()
    client_two = __import__("django.test", fromlist=["Client"]).Client()
    force_login_with_fresh_mfa(client_one, target)
    force_login_with_fresh_mfa(client_two, target)
    session_keys = {client_one.session.session_key, client_two.session.session_key}
    original_version = target.security_version

    recovery = create_privileged_recovery(
        requested_by=requestor,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-77",
        reason_code="lost_factor",
    )
    state = approve_privileged_recovery(
        recovery=recovery,
        approved_by=approver,
        external_evidence_reference="CALLBACK-TEST-77",
    )

    target.refresh_from_db()
    assert state.status == state.Status.AWAITING_REENROLLMENT
    assert target.security_version == original_version + 1
    assert target.mfa_enrolled_at is None
    assert not Authenticator.objects.filter(user=target).exists()
    assert not Session.objects.filter(session_key__in=session_keys).exists()
    assert (
        PrivilegedRoleSuspension.objects.filter(
            assignment__account=target,
            restored_at__isnull=True,
        ).count()
        == 1
    )
    assert not has_effective_role(target, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)
    assert PrivilegedRecoveryApproval.objects.filter(
        recovery=recovery,
        approved_by=approver,
    ).exists()
    assert SecurityNotification.objects.filter(account=target).count() == 2
    approval = PrivilegedRecoveryApproval.objects.get(recovery=recovery)
    approval.evidence_reference_digest = "0" * 64
    with pytest.raises(PermissionDenied, match="immutable"):
        approval.save()


def test_recovery_rejects_self_approval_reference_mismatch_and_stale_account() -> None:
    requestor = _admin("requestor")
    approver = _admin("approver")
    target = _target()
    recovery = create_privileged_recovery(
        requested_by=requestor,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-88",
        reason_code="lost_factor",
    )

    with pytest.raises(PermissionDenied, match="distinct"):
        approve_privileged_recovery(
            recovery=recovery,
            approved_by=requestor,
            external_evidence_reference="CALLBACK-TEST-88",
        )
    with pytest.raises(ValidationError, match="could not be approved"):
        approve_privileged_recovery(
            recovery=recovery,
            approved_by=approver,
            external_evidence_reference="WRONG-REFERENCE",
        )
    target.security_version += 1
    target.save(update_fields=["security_version"])
    with pytest.raises(ValidationError, match="could not be approved"):
        approve_privileged_recovery(
            recovery=recovery,
            approved_by=approver,
            external_evidence_reference="CALLBACK-TEST-88",
        )


def test_restore_is_explicit_and_requires_new_mfa_enrollment() -> None:
    requestor = _admin("requestor")
    approver = _admin("approver")
    restorer = _admin("restorer")
    target = _target()
    recovery = create_privileged_recovery(
        requested_by=requestor,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-99",
        reason_code="lost_factor",
    )
    approve_privileged_recovery(
        recovery=recovery,
        approved_by=approver,
        external_evidence_reference="CALLBACK-TEST-99",
    )

    with pytest.raises(ValidationError, match="re-enrollment"):
        restore_recovered_privileges(recovery=recovery, restored_by=restorer)

    target.refresh_from_db()
    enroll_account_mfa(target)
    state = restore_recovered_privileges(recovery=recovery, restored_by=restorer)
    assert state.status == state.Status.COMPLETED
    assert not PrivilegedRoleSuspension.objects.filter(
        assignment__account=target,
        restored_at__isnull=True,
    ).exists()
    assert has_effective_role(target, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)
    assert SecurityNotification.objects.filter(account=target).count() == 3


def test_restore_rejects_an_approval_after_another_security_revision() -> None:
    requestor = _admin("stale-requestor")
    approver = _admin("stale-approver")
    restorer = _admin("stale-restorer")
    target = _target()
    recovery = create_privileged_recovery(
        requested_by=requestor,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-100",
        reason_code="lost_factor",
    )
    approve_privileged_recovery(
        recovery=recovery,
        approved_by=approver,
        external_evidence_reference="CALLBACK-TEST-100",
    )
    target.refresh_from_db()
    enroll_account_mfa(target)
    target.security_version += 1
    target.save(update_fields=["security_version"])

    with pytest.raises(ValidationError, match="no longer current"):
        restore_recovered_privileges(recovery=recovery, restored_by=restorer)


def test_recovery_cannot_be_created_by_mailbox_only_subject_or_unprivileged_actor() -> None:
    target = _target()
    with pytest.raises(PermissionDenied):
        create_privileged_recovery(
            requested_by=target,
            subject=target,
            external_evidence_reference="CALLBACK-TEST-101",
            reason_code="lost_factor",
        )
