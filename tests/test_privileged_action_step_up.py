from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import Client, override_settings
from django.urls import reverse

from mnemex.accounts.action_assurance import claim_action_ticket, issue_action_ticket
from mnemex.accounts.allauth_bridge import replace_session_mfa_authentication
from mnemex.accounts.assurance import SESSION_SECURITY_VERSION_KEY
from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from tests.mfa_helpers import SYNTHETIC_TOTP_SECRET, force_login_with_fresh_mfa

SECURITY_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "security": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "action-assurance-tests",
    },
}


def _request(client: Client, path: str = "/health/live", *, method: str = "get"):
    response = getattr(client, method)(path)
    return response.wsgi_request


def _privileged_account(email: str) -> Account:
    account = Account.objects.create_user(email=email, password="synthetic")
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        assigned_by=account,
    )
    return account


def _make_session_stale(client: Client, account: Account, authenticator_id: int) -> None:
    session = client.session
    session[SESSION_SECURITY_VERSION_KEY] = account.security_version
    authenticator = Authenticator.objects.get(user=account, pk=authenticator_id)
    replace_session_mfa_authentication(
        session,
        authenticator,
        verified_at=time.time() - settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS - 5,
    )
    session.save()


def _current_totp() -> str:
    counter = int(time.time()) // 30
    return format_hotp_value(hotp_value(SYNTHETIC_TOTP_SECRET, counter))


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE)
def test_action_ticket_is_bound_and_single_use() -> None:
    account = Account.objects.create_user(email="action@example.invalid", password="synthetic")
    client = Client()
    force_login_with_fresh_mfa(client, account)
    issuing_request = _request(client)

    token = issue_action_ticket(
        issuing_request,
        target_path="/results/manual/",
        target_method="POST",
    )

    submission = _request(client, "/results/manual/", method="post")
    claim = claim_action_ticket(submission, token=token)
    assert claim.account_id == account.pk
    assert claim.target_path == "/results/manual/"
    assert claim.target_method == "POST"

    with pytest.raises(PermissionDenied, match="action assurance is unavailable"):
        claim_action_ticket(submission, token=token)


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE)
def test_same_route_tickets_issued_in_one_second_remain_independently_claimable() -> None:
    account = Account.objects.create_user(email="nonce@example.invalid", password="synthetic")
    client = Client()
    force_login_with_fresh_mfa(client, account)
    issuing_request = _request(client)
    first = issue_action_ticket(
        issuing_request,
        target_path="/accounts/security/operations/",
        target_method="POST",
    )
    second = issue_action_ticket(
        issuing_request,
        target_path="/accounts/security/operations/",
        target_method="POST",
    )

    assert first != second
    submission = _request(client, "/accounts/security/operations/", method="post")
    assert claim_action_ticket(submission, token=first).account_id == account.pk
    assert claim_action_ticket(submission, token=second).account_id == account.pk


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE)
def test_action_ticket_rejects_cross_session_route_method_and_security_version() -> None:
    account = Account.objects.create_user(email="bound@example.invalid", password="synthetic")
    first = Client()
    force_login_with_fresh_mfa(first, account)
    token = issue_action_ticket(
        _request(first),
        target_path="/results/upload/",
        target_method="POST",
    )

    second = Client()
    force_login_with_fresh_mfa(second, account)
    with pytest.raises(PermissionDenied, match="action assurance is unavailable"):
        claim_action_ticket(_request(second, "/results/upload/", method="post"), token=token)

    with pytest.raises(PermissionDenied, match="action assurance is unavailable"):
        claim_action_ticket(_request(first, "/results/manual/", method="post"), token=token)

    with pytest.raises(PermissionDenied, match="action assurance is unavailable"):
        claim_action_ticket(_request(first, "/results/upload/"), token=token)

    account.security_version += 1
    account.save(update_fields=["security_version"])
    with pytest.raises(PermissionDenied, match="action assurance is unavailable"):
        claim_action_ticket(_request(first, "/results/upload/", method="post"), token=token)


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE)
def test_stale_or_password_only_session_cannot_issue_ticket() -> None:
    account = Account.objects.create_user(email="stale@example.invalid", password="synthetic")
    client = Client()
    client.force_login(account)

    with pytest.raises(PermissionDenied, match="fresh MFA is required"):
        issue_action_ticket(
            _request(client),
            target_path="/results/manual/",
            target_method="POST",
        )


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE)
def test_cache_outage_denies_claim_without_local_fallback() -> None:
    account = Account.objects.create_user(email="cache@example.invalid", password="synthetic")
    client = Client()
    force_login_with_fresh_mfa(client, account)
    token = issue_action_ticket(
        _request(client),
        target_path="/results/manual/",
        target_method="POST",
    )
    broken_cache = Mock()
    broken_cache.add.side_effect = OSError("synthetic cache outage")

    with (
        patch("mnemex.accounts.action_assurance._security_cache", return_value=broken_cache),
        pytest.raises(PermissionDenied, match="action assurance is unavailable"),
    ):
        claim_action_ticket(_request(client, "/results/manual/", method="post"), token=token)


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE, MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_action_step_up_issues_ticket_without_navigation_and_preserves_target() -> None:
    account = _privileged_account("step-up@example.invalid")
    client = Client()
    authenticator = force_login_with_fresh_mfa(client, account)
    _make_session_stale(client, account, authenticator.pk)
    endpoint = reverse("accounts:action-step-up")

    needs_code = client.post(
        endpoint,
        {"target_path": "/results/manual/", "target_method": "POST"},
        HTTP_ACCEPT="application/json",
    )
    assert needs_code.status_code == 428
    assert needs_code.json() == {"code": "mfa_required"}

    verified = client.post(
        endpoint,
        {
            "target_path": "/results/manual/",
            "target_method": "POST",
            "code": _current_totp(),
        },
        HTTP_ACCEPT="application/json",
    )
    assert verified.status_code == 200
    payload = verified.json()
    assert payload["code"] == "action_ready"
    assert isinstance(payload["ticket"], str)

    submission = _request(client, "/results/manual/", method="post")
    claim = claim_action_ticket(submission, token=payload["ticket"])
    assert claim.target_path == "/results/manual/"


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE, MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_action_step_up_rejects_invalid_code_generically() -> None:
    account = _privileged_account("bad-step-up@example.invalid")
    client = Client()
    authenticator = force_login_with_fresh_mfa(client, account)
    _make_session_stale(client, account, authenticator.pk)

    response = client.post(
        reverse("accounts:action-step-up"),
        {
            "target_path": "/results/upload/",
            "target_method": "POST",
            "code": "000000",
        },
        HTTP_ACCEPT="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {"code": "verification_failed"}
    assert "000000" not in response.content.decode()


@pytest.mark.django_db
def test_results_shell_contains_accessible_step_up_dialog_and_local_script(client: Client) -> None:
    account = _privileged_account("dialog@example.invalid")
    force_login_with_fresh_mfa(client, account)

    response = client.get(reverse("results:dashboard"))

    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="privileged-action-step-up"' in html
    assert 'aria-labelledby="privileged-action-step-up-title"' in html
    assert 'aria-live="polite"' in html
    assert "privileged-submit.js" in html
    assert "https://" not in html

    script = (
        Path(__file__).resolve().parents[1]
        / "mnemex"
        / "results"
        / "static"
        / "results"
        / "privileged-submit.js"
    ).read_text(encoding="utf-8")
    assert "new FormData(form)" in script
    assert "data-step-up-confirm" in script
    assert "new WeakSet()" in script
    assert "inFlightForms.has(form)" in script
    assert "setFormPending(form, true)" in script
    assert "form.submit(" not in script
    assert "form.action" not in script
    assert 'form.getAttribute("action")' in script
    assert "window.location.assign(response.url)" in script


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE, MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_privileged_post_claims_ticket_before_entering_portal_view() -> None:
    account = _privileged_account("claim-before-view@example.invalid")
    client = Client()
    force_login_with_fresh_mfa(client, account)
    target = reverse("results:mapping-create")

    denied = client.post(target, {"name": "untrusted body"})
    assert denied.status_code == 403

    ticket_response = client.post(
        reverse("accounts:action-step-up"),
        {"target_path": target, "target_method": "POST"},
        HTTP_ACCEPT="application/json",
    )
    assert ticket_response.status_code == 200
    accepted = client.post(
        target,
        {"name": ""},
        HTTP_X_MNEMEX_ACTION_TICKET=ticket_response.json()["ticket"],
    )
    assert accepted.status_code == 200
    assert "This field is required" in accepted.content.decode()

    replay = client.post(
        target,
        {"name": ""},
        HTTP_X_MNEMEX_ACTION_TICKET=ticket_response.json()["ticket"],
    )
    assert replay.status_code == 403


@pytest.mark.django_db
@override_settings(CACHES=SECURITY_CACHE, MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED=True)
def test_claimed_action_ticket_survives_mfa_freshness_boundary() -> None:
    account = _privileged_account("boundary-step-up@example.invalid")
    client = Client()
    authenticator = force_login_with_fresh_mfa(client, account)
    target = reverse("results:mapping-create")
    ticket_response = client.post(
        reverse("accounts:action-step-up"),
        {"target_path": target, "target_method": "POST"},
        HTTP_ACCEPT="application/json",
    )
    assert ticket_response.status_code == 200

    _make_session_stale(client, account, authenticator.pk)
    response = client.post(
        target,
        {"name": ""},
        HTTP_X_MNEMEX_ACTION_TICKET=ticket_response.json()["ticket"],
    )

    assert response.status_code == 200
    assert "This field is required" in response.content.decode()
