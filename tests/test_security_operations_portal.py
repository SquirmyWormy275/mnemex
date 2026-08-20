from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from mnemex.accounts.allauth_bridge import replace_session_mfa_authentication
from mnemex.accounts.authorization import has_effective_role
from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.accounts.services import (
    create_privileged_invitation,
    create_privileged_recovery,
)
from mnemex.partners.models import PartnerOrganization
from tests.mfa_helpers import force_login_with_fresh_mfa

pytestmark = pytest.mark.django_db


def _account(label: str) -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password",
    )
    from tests.mfa_helpers import enroll_account_mfa

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


def _target(label: str) -> Account:
    account = _account(label)
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=account,
    )
    return account


def _action_ticket(client: Client, target_path: str) -> str:
    response = client.post(
        reverse("accounts:action-step-up"),
        {"target_path": target_path, "target_method": "POST"},
    )
    assert response.status_code == 200
    return response.json()["ticket"]


def test_invitation_acceptance_url_never_contains_the_secret() -> None:
    admin = _admin("admin")
    subject = _account("subject")
    invitation, secret = create_privileged_invitation(
        requested_by=admin,
        subject=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        external_evidence_reference="HR-TEST-501",
    )
    url = reverse("accounts:invitation-accept", args=[invitation.request_id])
    assert secret not in url
    client = Client()
    force_login_with_fresh_mfa(client, subject)

    page = client.get(url)
    assert page.status_code == 200
    assert secret not in page.content.decode()
    assert 'name="secret"' in page.content.decode()
    invalid = client.post(url, {"secret": "not-the-code"})
    assert invalid.status_code == 400
    assert "not-the-code" not in invalid.content.decode()
    accepted = client.post(url, {"secret": secret})
    assert accepted.status_code == 302
    assert secret not in accepted.url


def test_absent_and_unauthorized_operation_ids_return_identical_not_found_pages() -> None:
    admin = _admin("platform-admin")
    other = _account("ordinary-user")
    target = _target("target")
    recovery = create_privileged_recovery(
        requested_by=admin,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-502",
        reason_code="lost_factor",
    )
    client = Client()
    client.force_login(other)

    unauthorized = client.get(
        reverse("accounts:security-operation-detail", args=[recovery.request_id])
    )
    absent = client.get(
        reverse(
            "accounts:security-operation-detail",
            args=["00000000-0000-0000-0000-000000000000"],
        )
    )
    assert unauthorized.status_code == absent.status_code == 404
    assert unauthorized.content == absent.content


def test_security_queue_is_pii_free_and_distinguishes_same_scope_requests() -> None:
    admin = _admin("queue-admin")
    target_one = _target("target-one")
    target_two = _target("target-two")
    first = create_privileged_recovery(
        requested_by=admin,
        subject=target_one,
        external_evidence_reference="CALLBACK-TEST-503-A",
        reason_code="lost_factor",
    )
    second = create_privileged_recovery(
        requested_by=admin,
        subject=target_two,
        external_evidence_reference="CALLBACK-TEST-503-B",
        reason_code="lost_factor",
    )
    client = Client()
    force_login_with_fresh_mfa(client, admin)
    response = client.get(reverse("accounts:security-operations"))
    body = response.content.decode()

    assert response.status_code == 200
    assert str(first.request_id) in body
    assert str(second.request_id) in body
    assert first.external_evidence_reference in body
    assert second.external_evidence_reference in body
    assert target_one.email not in body
    assert target_two.email not in body
    assert "Next action" in body
    assert "No contact details are shown" in body
    assert body.count('id="id_invitation_subject_account_id"') == 1
    assert body.count('id="id_recovery_subject_account_id"') == 1
    assert 'for="id_invitation_subject_account_id"' in body
    assert 'for="id_recovery_subject_account_id"' in body


@override_settings(MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_recovery_approval_requires_a_route_bound_one_use_action_ticket() -> None:
    requestor = _admin("ticket-requestor")
    approver = _admin("ticket-approver")
    target = _target("ticket-target")
    recovery = create_privileged_recovery(
        requested_by=requestor,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-504",
        reason_code="lost_factor",
    )
    detail_url = reverse("accounts:security-operation-detail", args=[recovery.pk])
    client = Client()
    force_login_with_fresh_mfa(client, approver)
    payload = {
        "action": "approve",
        "external_evidence_reference": recovery.external_evidence_reference,
    }

    assert client.post(detail_url, payload).status_code == 403
    ticket_response = client.post(
        reverse("accounts:action-step-up"),
        {"target_path": detail_url, "target_method": "POST"},
    )
    ticket = ticket_response.json()["ticket"]
    accepted = client.post(
        detail_url,
        payload,
        HTTP_X_MNEMEX_ACTION_TICKET=ticket,
    )
    assert accepted.status_code == 302
    assert (
        client.post(
            detail_url,
            payload,
            HTTP_X_MNEMEX_ACTION_TICKET=ticket,
        ).status_code
        == 403
    )


def test_wrong_tenant_recovery_identifier_is_indistinguishable_from_absent() -> None:
    organization_a = PartnerOrganization.objects.create(name="Synthetic Tenant A")
    organization_b = PartnerOrganization.objects.create(name="Synthetic Tenant B")
    platform_admin = _admin("scope-requestor")
    tenant_admin = _account("scope-approver")
    PrivilegedRoleAssignment.objects.create(
        account=tenant_admin,
        role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
        assigned_by=tenant_admin,
    )
    target = _account("scope-target")
    PrivilegedRoleAssignment.objects.create(
        account=target,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_b,
        assigned_by=target,
    )
    recovery = create_privileged_recovery(
        requested_by=platform_admin,
        subject=target,
        external_evidence_reference="CALLBACK-TEST-505",
        reason_code="lost_factor",
    )
    client = Client()
    force_login_with_fresh_mfa(client, tenant_admin)

    wrong_scope = client.get(reverse("accounts:security-operation-detail", args=[recovery.pk]))
    absent = client.get(
        reverse(
            "accounts:security-operation-detail",
            args=["00000000-0000-0000-0000-000000000000"],
        )
    )
    assert wrong_scope.status_code == absent.status_code == 404
    assert wrong_scope.content == absent.content


@override_settings(MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_security_admin_creates_and_subject_accepts_invitation_entirely_through_ui() -> None:
    admin = _admin("ui-invitation-admin")
    subject = _account("ui-invitation-subject")
    admin_client = Client()
    force_login_with_fresh_mfa(admin_client, admin)
    queue_url = reverse("accounts:security-operations")
    ticket = _action_ticket(admin_client, queue_url)

    created = admin_client.post(
        queue_url,
        {
            "action": "create_invitation",
            "subject_account_id": str(subject.pk),
            "role": PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            "scope": PrivilegedRoleAssignment.Scope.PLATFORM,
            "organization": "",
            "external_evidence_reference": "HR-TEST-UI-801",
        },
        HTTP_X_MNEMEX_ACTION_TICKET=ticket,
    )

    body = created.content.decode()
    assert created.status_code == 200
    assert created.headers["Cache-Control"] == "no-store, private"
    assert created.headers["Referrer-Policy"] == "no-referrer"
    assert created.headers["X-MNEMEX-One-Time-Result"] == "invitation-secret-v1"
    match = re.search(r'id="one-time-invitation-code">([A-Za-z0-9_-]+)</code>', body)
    assert match is not None
    secret = match.group(1)
    assert secret not in created.request["PATH_INFO"]
    assert subject.email not in body
    invitation = subject.privileged_invitations.get()

    subject_client = Client()
    force_login_with_fresh_mfa(subject_client, subject)
    accepted = subject_client.post(
        reverse("accounts:invitation-accept", args=[invitation.pk]),
        {"secret": secret},
    )
    assert accepted.status_code == 302
    assert PrivilegedRoleAssignment.objects.filter(
        account=subject,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        revoked_at__isnull=True,
    ).exists()


@override_settings(MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_security_operation_claimed_ticket_survives_mfa_freshness_boundary() -> None:
    admin = _admin("ui-boundary-admin")
    subject = _account("ui-boundary-subject")
    client = Client()
    authenticator = force_login_with_fresh_mfa(client, admin)
    queue_url = reverse("accounts:security-operations")
    ticket = _action_ticket(client, queue_url)
    session = client.session
    replace_session_mfa_authentication(
        session,
        authenticator,
        verified_at=time.time() - 10_000,
    )
    session.save()

    response = client.post(
        queue_url,
        {
            "action": "create_invitation",
            "subject_account_id": str(subject.pk),
            "role": PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            "scope": PrivilegedRoleAssignment.Scope.PLATFORM,
            "organization": "",
            "external_evidence_reference": "HR-TEST-UI-BOUNDARY",
        },
        HTTP_X_MNEMEX_ACTION_TICKET=ticket,
    )

    assert response.status_code == 200
    assert response.headers["X-MNEMEX-One-Time-Result"] == "invitation-secret-v1"
    assert subject.privileged_invitations.count() == 1


@override_settings(MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_staff_complete_recovery_ceremony_from_portal_initiation_to_restore() -> None:
    requestor = _admin("ui-recovery-requestor")
    approver = _admin("ui-recovery-approver")
    target = _target("ui-recovery-target")
    requestor_client = Client()
    force_login_with_fresh_mfa(requestor_client, requestor)
    queue_url = reverse("accounts:security-operations")

    created = requestor_client.post(
        queue_url,
        {
            "action": "create_recovery",
            "subject_account_id": str(target.pk),
            "external_evidence_reference": "CALLBACK-TEST-UI-802",
            "reason_code": "lost_factor",
        },
        HTTP_X_MNEMEX_ACTION_TICKET=_action_ticket(requestor_client, queue_url),
    )
    recovery = target.privileged_recovery_requests.get()
    detail_url = reverse("accounts:security-operation-detail", args=[recovery.pk])
    assert created.status_code == 302
    assert created.url == detail_url

    approver_client = Client()
    force_login_with_fresh_mfa(approver_client, approver)
    approved = approver_client.post(
        detail_url,
        {
            "action": "approve",
            "external_evidence_reference": "CALLBACK-TEST-UI-802",
        },
        HTTP_X_MNEMEX_ACTION_TICKET=_action_ticket(approver_client, detail_url),
    )
    assert approved.status_code == 302
    target.refresh_from_db()
    from tests.mfa_helpers import enroll_account_mfa

    enroll_account_mfa(target)
    restored = approver_client.post(
        detail_url,
        {"action": "restore", "confirm_reenrollment": "on"},
        HTTP_X_MNEMEX_ACTION_TICKET=_action_ticket(approver_client, detail_url),
    )
    assert restored.status_code == 302
    assert has_effective_role(
        target,
        PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    )


@override_settings(MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_recovery_initiation_does_not_distinguish_unknown_from_wrong_scope_subject() -> None:
    organization_a = PartnerOrganization.objects.create(name="Initiation Tenant A")
    organization_b = PartnerOrganization.objects.create(name="Initiation Tenant B")
    tenant_admin = _account("initiation-tenant-admin")
    PrivilegedRoleAssignment.objects.create(
        account=tenant_admin,
        role=PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
        assigned_by=tenant_admin,
    )
    wrong_scope_target = _account("initiation-wrong-scope")
    PrivilegedRoleAssignment.objects.create(
        account=wrong_scope_target,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_b,
        assigned_by=wrong_scope_target,
    )
    client = Client()
    force_login_with_fresh_mfa(client, tenant_admin)
    queue_url = reverse("accounts:security-operations")
    common = {
        "action": "create_recovery",
        "external_evidence_reference": "CALLBACK-TEST-UI-803",
        "reason_code": "lost_factor",
    }
    unknown = client.post(
        queue_url,
        {**common, "subject_account_id": "00000000-0000-0000-0000-000000000000"},
        HTTP_X_MNEMEX_ACTION_TICKET=_action_ticket(client, queue_url),
    )
    wrong_scope = client.post(
        queue_url,
        {**common, "subject_account_id": str(wrong_scope_target.pk)},
        HTTP_X_MNEMEX_ACTION_TICKET=_action_ticket(client, queue_url),
    )
    assert unknown.status_code == wrong_scope.status_code == 400
    assert b"Security operation could not be started." in unknown.content
    assert b"Security operation could not be started." in wrong_scope.content
    assert str(wrong_scope_target.pk).encode() not in wrong_scope.content
    assert wrong_scope_target.email.encode() not in wrong_scope.content


def test_one_time_invitation_result_has_an_explicit_browser_replacement_contract() -> None:
    admin = _admin("js-contract-admin")
    client = Client()
    force_login_with_fresh_mfa(client, admin)
    page = client.get(reverse("accounts:security-operations")).content.decode()
    script_path = (
        Path(__file__).parents[1]
        / "mnemex"
        / "results"
        / "static"
        / "results"
        / "privileged-submit.js"
    )
    source = script_path.read_text(encoding="utf-8")

    assert "privileged-submit.js" in page
    assert 'id="privileged-action-step-up"' in page
    assert 'response.headers.get("X-MNEMEX-One-Time-Result")' in source
    assert '=== "invitation-secret-v1"' in source
    assert "document.write(oneTimeDocument)" in source
    assert source.index('=== "invitation-secret-v1"') < source.index(
        "document.write(oneTimeDocument)"
    )
