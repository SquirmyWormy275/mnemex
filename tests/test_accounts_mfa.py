from __future__ import annotations

import base64
import logging
import threading
import time
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.account.signals import email_changed
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value
from django.conf import settings
from django.core import mail
from django.db import IntegrityError, close_old_connections, connection
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from mnemex.accounts.allauth_bridge import (
    AUTHENTICATION_METHODS_SESSION_KEY,
    replace_session_mfa_authentication,
)
from mnemex.accounts.assurance import (
    SESSION_SECURITY_VERSION_KEY,
    has_fresh_mfa_session,
)
from mnemex.accounts.authorization import has_effective_role
from mnemex.accounts.forms import _claim_totp_once, _validate_recovery_code
from mnemex.accounts.models import Account, PrivilegedRoleAssignment, SecurityNotification
from mnemex.foundation.models import AuditEvent
from tests.mfa_helpers import SYNTHETIC_TOTP_SECRET

pytestmark = pytest.mark.django_db

_PASSWORD = "synthetic correct horse battery staple"
_SECRET = SYNTHETIC_TOTP_SECRET


def _account(label: str, *, verified: bool = True) -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password=_PASSWORD,
        email_verified_at=timezone.now() if verified else None,
    )
    EmailAddress.objects.create(
        user=account,
        email=account.email,
        primary=True,
        verified=verified,
    )
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=account,
    )
    return account


def _totp_authenticator(account: Account) -> Authenticator:
    authenticator = Authenticator.objects.create(
        user=account,
        type=Authenticator.Type.TOTP,
        data={"secret": get_mfa_adapter().encrypt(_SECRET)},
    )
    account.mfa_enrolled_at = timezone.now()
    account.save(update_fields=["mfa_enrolled_at"])
    return authenticator


def _current_code(secret: str = _SECRET) -> str:
    return format_hotp_value(hotp_value(secret, int(time.time()) // settings.MFA_TOTP_PERIOD))


def _password_step(client: Client, account: Account):
    return client.post(
        reverse("account_login"),
        {"login": account.email, "password": _PASSWORD},
    )


def _complete_mfa_login(
    client: Client,
    account: Account,
    code: str | None = None,
    *,
    expected_url: str | None = None,
) -> None:
    first = _password_step(client, account)
    assert first.status_code == 302
    assert first.url == reverse("mfa_authenticate")
    password_session_key = client.session.session_key

    second = client.post(reverse("mfa_authenticate"), {"code": code or _current_code()})

    assert second.status_code == 302
    assert second.url == (expected_url or reverse("results:dashboard"))
    assert client.session.session_key != password_session_key


def _bind_mfa_record(
    client: Client,
    account: Account,
    authenticator: Authenticator,
    *,
    verified_at: float,
) -> None:
    client.force_login(account)
    session = client.session
    session[SESSION_SECURITY_VERSION_KEY] = account.security_version
    replace_session_mfa_authentication(
        session,
        authenticator,
        verified_at=verified_at,
    )
    session.save()


def test_password_only_session_cannot_reach_privileged_workspace() -> None:
    account = _account("password-only")
    _totp_authenticator(account)
    client = Client()
    client.force_login(account)

    response = client.get(reverse("results:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("mfa_reauthenticate"))
    assert not has_fresh_mfa_session(response.wsgi_request, account)


def test_forged_request_local_marker_cannot_bypass_durable_authority_checks() -> None:
    account = Account.objects.create_user(
        email="forged-assurance@mnemex.example.invalid",
        password=_PASSWORD,
        email_verified_at=timezone.now(),
        mfa_enrolled_at=timezone.now(),
    )
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=account,
    )
    setattr(account, "_mnemex_session_assured", True)

    assert not has_effective_role(account, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)


def test_account_entry_pages_explain_invite_only_and_recovery_options() -> None:
    login = Client().get(reverse("account_login"))
    body = login.content.decode()

    assert login.status_code == 200
    assert "Invite-only access" in body
    assert "Forgot your password?" in body
    assert "sign up" not in body.lower()

    account = _account("entry-copy")
    _totp_authenticator(account)
    client = Client()
    challenge = _password_step(client, account)
    assert challenge.url == reverse("mfa_authenticate")
    challenge_body = client.get(reverse("mfa_authenticate")).content.decode()
    assert "authenticator app or one unused recovery code" in challenge_body


def test_security_center_and_enrollment_are_operator_facing() -> None:
    account = _account("security-center")
    client = Client()
    first = _password_step(client, account)
    assert first.url == reverse("mfa_activate_totp")

    enrollment = client.get(reverse("mfa_activate_totp"))
    enrollment_body = enrollment.content.decode()
    assert "Scan the QR code" in enrollment_body
    assert "Save this setup key" in enrollment_body
    assert "MNEMEX account security" in enrollment_body


def test_public_signup_is_closed_and_password_reset_is_enumeration_resistant() -> None:
    signup = Client().post(
        reverse("account_signup"),
        {
            "email": "uninvited@mnemex.example.invalid",
            "password1": _PASSWORD,
            "password2": _PASSWORD,
        },
    )
    assert signup.status_code == 200
    assert "Sign Up Closed" in signup.content.decode()
    assert not Account.objects.filter(email="uninvited@mnemex.example.invalid").exists()

    known = _account("reset-known")
    known_response = Client().post(reverse("account_reset_password"), {"email": known.email})
    known_email_count = len(mail.outbox)
    unknown_response = Client().post(
        reverse("account_reset_password"),
        {"email": "unknown@mnemex.example.invalid"},
    )

    assert (known_response.status_code, known_response.url) == (
        unknown_response.status_code,
        unknown_response.url,
    )
    assert len(mail.outbox) > known_email_count


@override_settings(
    ACCOUNT_RATE_LIMITS={
        "login": "20/m/ip",
        "login_failed": "2/m/key",
    }
)
def test_repeated_password_failures_are_throttled() -> None:
    account = _account("throttled-login")
    client = Client()
    payload = {"login": account.email, "password": "definitely-wrong"}

    assert client.post(reverse("account_login"), payload).status_code == 200
    assert client.post(reverse("account_login"), payload).status_code == 200
    blocked = client.post(
        reverse("account_login"),
        {"login": account.email, "password": _PASSWORD},
    )
    assert blocked.status_code == 200
    assert not blocked.has_header("Location")


def test_real_totp_login_rotates_session_and_binds_proof_to_one_browser() -> None:
    account = _account("session-bound")
    _totp_authenticator(account)
    verified_client = Client()
    other_client = Client()

    _complete_mfa_login(verified_client, account)
    other_client.force_login(account)

    assert verified_client.get(reverse("results:dashboard")).status_code == 200
    denied = other_client.get(reverse("results:dashboard"))
    assert denied.status_code == 302
    assert denied.url.startswith(reverse("mfa_reauthenticate"))


def test_mfa_proof_expires_at_configured_freshness_boundary() -> None:
    account = _account("freshness")
    authenticator = _totp_authenticator(account)
    client = Client()
    client.force_login(account)
    session = client.session
    now = time.time()
    session[SESSION_SECURITY_VERSION_KEY] = account.security_version
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {
            "method": "mfa",
            "at": now - settings.MNEMEX_PRIVILEGED_MFA_MAX_AGE_SECONDS - 1,
            "id": authenticator.pk,
            "type": authenticator.type,
        }
    ]
    session.save()

    response = client.get(reverse("results:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("mfa_reauthenticate"))


def test_sensitive_action_requires_five_minute_mfa_while_navigation_remains_available() -> None:
    account = _account("sensitive-action")
    authenticator = _totp_authenticator(account)
    client = Client()
    _bind_mfa_record(
        client,
        account,
        authenticator,
        verified_at=time.time() - settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS - 1,
    )

    assert client.get(reverse("results:dashboard")).status_code == 200
    response = client.post(reverse("results:mapping-create"), {})

    assert response.status_code == 302
    assert response.url.startswith(reverse("mfa_reauthenticate"))


def test_mfa_freshness_boundary_is_exact() -> None:
    account = _account("exact-boundary")
    authenticator = _totp_authenticator(account)
    max_age = 300
    now = time.time()
    client = Client()
    _bind_mfa_record(
        client,
        account,
        authenticator,
        verified_at=now - max_age + 0.001,
    )
    request = client.get(reverse("results:dashboard")).wsgi_request
    assert has_fresh_mfa_session(
        request,
        account,
        now=now,
        max_age_seconds=max_age,
    )

    _bind_mfa_record(
        client,
        account,
        authenticator,
        verified_at=now - max_age,
    )
    request = client.get(reverse("results:dashboard")).wsgi_request
    assert not has_fresh_mfa_session(
        request,
        account,
        now=now,
        max_age_seconds=max_age,
    )


def test_security_version_change_invalidates_existing_mfa_session() -> None:
    account = _account("security-version")
    _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    account.security_version += 1
    account.save(update_fields=["security_version"])

    response = client.get(reverse("results:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))


def test_role_revocation_and_factor_removal_take_effect_on_next_request() -> None:
    account = _account("live-revocation")
    authenticator = _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    assignment = account.privileged_roles.get()
    assignment.revoked_at = timezone.now()
    assignment.save(update_fields=["revoked_at"])
    assert client.get(reverse("results:dashboard")).status_code == 403

    assignment.revoked_at = None
    assignment.save(update_fields=["revoked_at"])
    authenticator.delete()
    response = client.get(reverse("results:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("mfa_activate_totp"))


def test_logout_clears_session_bound_mfa_proof() -> None:
    account = _account("logout")
    _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    response = client.post(reverse("account_logout"))

    assert response.status_code == 302
    assert client.session.get(AUTHENTICATION_METHODS_SESSION_KEY) is None
    assert client.get(reverse("results:dashboard")).status_code == 302


def test_unverified_email_stops_before_mfa_challenge() -> None:
    account = _account("unverified", verified=False)
    _totp_authenticator(account)
    client = Client()

    response = _password_step(client, account)

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    assert client.session.get(SESSION_SECURITY_VERSION_KEY) is None


def test_privileged_login_without_factor_is_sent_to_enrollment() -> None:
    account = _account("needs-enrollment")
    client = Client()

    response = _password_step(client, account)

    assert response.status_code == 302
    assert response.url == reverse("mfa_activate_totp")
    assert account.mfa_enrolled_at is None


def test_confirmed_enrollment_encrypts_secret_and_emits_safe_audit() -> None:
    account = _account("enrollment")
    client = Client()
    response = _password_step(client, account)
    assert response.url == reverse("mfa_activate_totp")

    enrollment = client.get(reverse("mfa_activate_totp"))
    secret = client.session["mfa.totp.secret"]
    activated = client.post(reverse("mfa_activate_totp"), {"code": _current_code(secret)})

    authenticator = Authenticator.objects.get(user=account, type=Authenticator.Type.TOTP)
    account.refresh_from_db()
    assert enrollment.status_code == 200
    assert activated.status_code == 302
    assert authenticator.data["secret"] != secret
    assert secret not in str(authenticator.data)
    assert get_mfa_adapter().decrypt(authenticator.data["secret"]) == secret
    assert account.mfa_enrolled_at is not None
    assert client.get(reverse("results:dashboard")).status_code == 200
    audits = AuditEvent.objects.filter(action="account.mfa.authenticator_added")
    assert audits.count() == 2  # TOTP plus automatically generated recovery codes.
    assert all(secret not in str(audit.metadata) for audit in audits)
    assert all(account.email not in str(audit.metadata) for audit in audits)
    notification = SecurityNotification.objects.get(
        account=account,
        template_identifier="mfa/email/totp_activated",
    )
    assert notification.status == SecurityNotification.Status.PENDING
    assert len(mail.outbox) == 0


def test_invalid_enrollment_code_creates_no_authenticator_or_audit() -> None:
    account = _account("bad-enrollment")
    client = Client()
    _password_step(client, account)
    client.get(reverse("mfa_activate_totp"))

    response = client.post(reverse("mfa_activate_totp"), {"code": "000000"})

    account.refresh_from_db()
    assert response.status_code == 200
    assert not Authenticator.objects.filter(user=account).exists()
    assert account.mfa_enrolled_at is None
    assert not AuditEvent.objects.filter(action="account.mfa.authenticator_added").exists()


def test_recovery_code_is_single_use_and_seed_is_encrypted() -> None:
    account = _account("recovery")
    _totp_authenticator(account)
    recovery = RecoveryCodes.activate(account)
    code = recovery.generate_codes()[0]
    assert recovery.instance.data["seed"] != code
    assert code not in str(recovery.instance.data)
    first_client = Client()
    second_client = Client()

    _complete_mfa_login(first_client, account, code)
    assert first_client.get(reverse("results:dashboard")).status_code == 200
    first_client.post(reverse("account_logout"))
    first = _password_step(second_client, account)
    assert first.url == reverse("mfa_authenticate")
    replay = second_client.post(reverse("mfa_authenticate"), {"code": code})

    assert replay.status_code == 200
    assert "incorrect" in replay.content.decode().lower()
    assert second_client.get(reverse("results:dashboard")).status_code == 302


def test_totp_code_cannot_be_replayed_within_its_valid_window() -> None:
    account = _account("totp-replay")
    _totp_authenticator(account)
    code = _current_code()
    first_client = Client()
    second_client = Client()

    _complete_mfa_login(first_client, account, code)
    assert _password_step(second_client, account).url == reverse("mfa_authenticate")
    replay = second_client.post(reverse("mfa_authenticate"), {"code": code})

    assert replay.status_code == 200
    assert "incorrect" in replay.content.decode().lower()
    assert second_client.get(reverse("results:dashboard")).status_code == 302


def test_ciphertext_is_versioned_and_tamper_evident() -> None:
    adapter = get_mfa_adapter()
    encrypted = adapter.encrypt(_SECRET)

    assert _SECRET not in encrypted
    assert encrypted.startswith("v1.")
    assert adapter.decrypt(encrypted) == _SECRET

    prefix, payload = encrypted.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(payload.encode("ascii")))
    raw[-1] ^= 1
    tampered = f"{prefix}.{base64.urlsafe_b64encode(bytes(raw)).decode('ascii')}"
    with pytest.raises(ValueError, match="could not be decrypted"):
        adapter.decrypt(tampered)


@override_settings(MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=False)
def test_hosted_privilege_stays_fail_closed_after_mfa_login() -> None:
    account = _account("production-gate")
    _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    assert client.get(reverse("results:dashboard")).status_code == 403


def test_password_only_reauthentication_cannot_authorize_factor_mutation() -> None:
    account = _account("password-reauth-takeover")
    authenticator = _totp_authenticator(account)
    client = Client()
    _bind_mfa_record(
        client,
        account,
        authenticator,
        verified_at=time.time() - settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS - 1,
    )

    password_reauth = client.post(
        reverse("account_reauthenticate"),
        {"password": _PASSWORD},
    )
    assert password_reauth.status_code == 302

    response = client.post(reverse("mfa_generate_recovery_codes"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("mfa_reauthenticate"))


def test_password_change_logs_out_current_session_and_invalidates_mfa_proof() -> None:
    account = _account("password-change-revocation")
    _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    response = client.post(
        reverse("account_change_password"),
        {
            "oldpassword": _PASSWORD,
            "password1": "new synthetic correct horse battery staple",
            "password2": "new synthetic correct horse battery staple",
        },
    )

    assert response.status_code == 302
    assert client.session.get(AUTHENTICATION_METHODS_SESSION_KEY) is None
    assert client.get(reverse("results:dashboard")).url.startswith(reverse("account_login"))
    notification = SecurityNotification.objects.get(
        account=account,
        template_identifier="account/email/password_changed",
    )
    assert notification.status == SecurityNotification.Status.PENDING
    assert len(mail.outbox) == 0


def test_password_change_persists_when_queue_and_audit_are_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    account = _account("password-change-queue-outage")
    _totp_authenticator(account)
    original_security_version = account.security_version
    client = Client()
    _complete_mfa_login(client, account)
    new_password = "new synthetic password after queue outage"

    with (
        patch(
            "mnemex.accounts.adapters.enqueue_allauth_security_notification",
            side_effect=RuntimeError("private queue failure"),
        ),
        patch(
            "mnemex.accounts.adapters.record_audit_event",
            side_effect=RuntimeError("private audit failure"),
        ),
        caplog.at_level(logging.ERROR, logger="mnemex.accounts.adapters"),
    ):
        response = client.post(
            reverse("account_change_password"),
            {
                "oldpassword": _PASSWORD,
                "password1": new_password,
                "password2": new_password,
            },
        )

    account.refresh_from_db()
    assert response.status_code == 302
    assert account.check_password(new_password)
    assert account.security_version == original_security_version + 1
    assert not SecurityNotification.objects.filter(account=account).exists()
    assert len(mail.outbox) == 0
    assert "account.security_notification.audit_unavailable" in caplog.text
    assert "private queue failure" not in caplog.text
    assert "private audit failure" not in caplog.text


@override_settings(MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=False)
def test_account_security_mutation_remains_available_while_workspace_gate_is_closed() -> None:
    account = _account("closed-workspace-security")
    _totp_authenticator(account)
    client = Client()
    _complete_mfa_login(client, account)

    response = client.post(
        reverse("account_change_password"),
        {
            "oldpassword": _PASSWORD,
            "password1": "new synthetic correct horse battery staple",
            "password2": "new synthetic correct horse battery staple",
        },
    )

    assert response.status_code == 302
    assert not response.url.startswith(reverse("mfa_reauthenticate"))
    assert client.session.get(AUTHENTICATION_METHODS_SESSION_KEY) is None


def test_account_email_is_canonical_and_case_insensitively_unique() -> None:
    first = Account.objects.create_user(
        email="Gillian@MNEMEX.Example.Invalid",
        password=_PASSWORD,
    )

    assert first.email == "gillian@mnemex.example.invalid"
    with pytest.raises(IntegrityError):
        Account.objects.create_user(
            email="GILLIAN@mnemex.example.invalid",
            password=_PASSWORD,
        )


def test_nonprivileged_account_lands_in_security_center() -> None:
    account = Account.objects.create_user(
        email="competitor@mnemex.example.invalid",
        password=_PASSWORD,
        email_verified_at=timezone.now(),
    )
    EmailAddress.objects.create(
        user=account,
        email=account.email,
        primary=True,
        verified=True,
    )
    _totp_authenticator(account)
    client = Client()

    _complete_mfa_login(client, account, expected_url=reverse("mfa_index"))

    assert client.get(reverse("mfa_index")).status_code == 200


def test_security_notification_failure_does_not_split_totp_enrollment() -> None:
    account = _account("notification-failure")
    client = Client()
    response = _password_step(client, account)
    assert response.url == reverse("mfa_activate_totp")
    client.get(reverse("mfa_activate_totp"))
    secret = client.session["mfa.totp.secret"]

    with patch(
        "mnemex.accounts.adapters.enqueue_allauth_security_notification",
        side_effect=RuntimeError("synthetic email outage"),
    ):
        activated = client.post(
            reverse("mfa_activate_totp"),
            {"code": _current_code(secret)},
        )

    assert activated.status_code == 302
    assert Authenticator.objects.filter(user=account, type=Authenticator.Type.TOTP).exists()
    assert Authenticator.objects.filter(
        user=account,
        type=Authenticator.Type.RECOVERY_CODES,
    ).exists()
    assert AuditEvent.objects.filter(action="account.security_notification.failed").exists()


def test_totp_claim_spans_the_complete_tolerance_window() -> None:
    account = _account("totp-tolerance-claim")
    authenticator = _totp_authenticator(account)
    base_time = 1_800_000_000.0
    counter = int(base_time) // settings.MFA_TOTP_PERIOD
    code = format_hotp_value(hotp_value(_SECRET, counter))

    with patch("mnemex.accounts.forms.time.time", return_value=base_time):
        assert _claim_totp_once(authenticator, code)
    with patch(
        "mnemex.accounts.forms.time.time",
        return_value=base_time + settings.MFA_TOTP_PERIOD,
    ):
        assert not _claim_totp_once(authenticator, code)


def test_concurrent_totp_claim_has_exactly_one_winner() -> None:
    account = _account("totp-concurrent-claim")
    authenticator = _totp_authenticator(account)
    code = _current_code()
    barrier = threading.Barrier(2)
    outcomes: list[bool] = []

    def claim() -> None:
        barrier.wait()
        outcomes.append(_claim_totp_once(authenticator, code))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(outcomes) == [False, True]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="row-lock concurrency requires PostgreSQL",
)
@pytest.mark.django_db(transaction=True)
def test_concurrent_recovery_code_consumption_has_exactly_one_winner() -> None:
    account = _account("recovery-concurrent-claim")
    _totp_authenticator(account)
    recovery = RecoveryCodes.activate(account)
    code = recovery.generate_codes()[0]
    authenticator_id = recovery.instance.pk
    barrier = threading.Barrier(2)
    outcomes: list[bool] = []

    def consume() -> None:
        close_old_connections()
        try:
            authenticator = Authenticator.objects.get(pk=authenticator_id)
            barrier.wait()
            outcomes.append(_validate_recovery_code(authenticator, code) is not None)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == [False, True]


def test_email_addition_revokes_other_sessions_and_current_mfa_proof() -> None:
    account = _account("email-change-revocation")
    authenticator = _totp_authenticator(account)
    current_client = Client()
    other_client = Client()
    _complete_mfa_login(current_client, account)
    _bind_mfa_record(other_client, account, authenticator, verified_at=time.time())

    request = current_client.get(reverse("results:dashboard")).wsgi_request
    alternate = EmailAddress.objects.create(
        user=account,
        email="alternate@mnemex.example.invalid",
        primary=False,
        verified=True,
    )
    email_changed.send(
        sender=EmailAddress,
        request=request,
        user=account,
        from_email_address=EmailAddress.objects.get(user=account, email=account.email),
        to_email_address=alternate,
    )
    request.session.save()
    current_client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key

    account.refresh_from_db()
    assert account.email == "alternate@mnemex.example.invalid"
    current = current_client.get(reverse("results:dashboard"))
    other = other_client.get(reverse("results:dashboard"))
    assert current.status_code == 302
    assert current.url.startswith(reverse("mfa_reauthenticate"))
    assert other.status_code == 302
    assert other.url.startswith(reverse("account_login"))
