from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.internal.flows.manage_email import emit_email_changed
from allauth.account.models import EmailAddress
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from mnemex.accounts.adapters import MnemexAccountAdapter
from mnemex.accounts.models import Account, SecurityNotification
from mnemex.accounts.notifications import (
    ALLAUTH_SECURITY_NOTIFICATION_TEMPLATES,
    decrypt_notification_recipient,
    run_security_notifications_once,
)
from mnemex.foundation.models import AuditEvent
from tests.mfa_helpers import verify_account_email

pytestmark = pytest.mark.django_db

EXPECTED_ALLAUTH_SECURITY_TEMPLATES = frozenset(
    {
        "account/email/email_changed",
        "account/email/email_deleted",
        "account/email/password_changed",
        "account/email/password_reset",
        "account/email/password_set",
        "mfa/email/recovery_codes_generated",
        "mfa/email/totp_activated",
        "mfa/email/totp_deactivated",
    }
)


def _verified_account(label: str = "allauth-cutover") -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password-only",
        email_verified_at=timezone.now(),
    )
    verify_account_email(account)
    return account


def _adapter() -> MnemexAccountAdapter:
    adapter = get_account_adapter(RequestFactory().get("/synthetic-security-change"))
    assert isinstance(adapter, MnemexAccountAdapter)
    return adapter


def test_allauth_security_mail_is_queue_only_and_idempotent() -> None:
    account = _verified_account()
    adapter = _adapter()

    adapter.send_notification_mail("account/email/password_changed", account)
    adapter.send_notification_mail("account/email/password_changed", account)

    notification = SecurityNotification.objects.get()
    assert notification.account == account
    assert notification.template_identifier == "account/email/password_changed"
    assert notification.context_code == "allauth-security-v1"
    assert decrypt_notification_recipient(notification) == account.email
    assert len(mail.outbox) == 0
    assert AuditEvent.objects.filter(action="account.security_notification.queued").count() == 1


def test_approved_template_policy_is_explicit() -> None:
    assert ALLAUTH_SECURITY_NOTIFICATION_TEMPLATES == EXPECTED_ALLAUTH_SECURITY_TEMPLATES


@pytest.mark.parametrize(
    "template_identifier",
    sorted(EXPECTED_ALLAUTH_SECURITY_TEMPLATES - {"account/email/email_changed"}),
)
def test_worker_delivers_each_approved_allauth_queue_intent(
    template_identifier: str,
) -> None:
    label = template_identifier.replace("/", "-").replace("_", "-")
    account = _verified_account(label)
    _adapter().send_notification_mail(template_identifier, account)
    notification = SecurityNotification.objects.get()
    assert len(mail.outbox) == 0

    outcome = run_security_notifications_once(owner="synthetic-cutover-worker", limit=1)

    notification.refresh_from_db()
    assert outcome.delivered == 1
    assert notification.status == SecurityNotification.Status.DELIVERED
    assert len(mail.outbox) == 1
    assert mail.outbox[0].extra_headers["Message-ID"] == notification.message_id


def test_a_later_password_state_creates_a_new_intent_before_signal_version_bump() -> None:
    account = _verified_account("later-password-state")
    adapter = _adapter()
    adapter.send_notification_mail("account/email/password_changed", account)
    first = SecurityNotification.objects.get()

    account.set_password("different synthetic password state")
    account.save(update_fields=["password"])
    adapter.send_notification_mail("account/email/password_changed", account)

    notifications = list(SecurityNotification.objects.order_by("created_at"))
    assert len(notifications) == 2
    assert notifications[0].pk == first.pk
    assert notifications[0].message_id != notifications[1].message_id
    assert len(mail.outbox) == 0


def test_real_allauth_contact_change_queues_both_verified_destinations() -> None:
    account = _verified_account("contact-change")
    previous = EmailAddress.objects.get(user=account, primary=True)
    current = EmailAddress.objects.create(
        user=account,
        email="new-contact@mnemex.example.invalid",
        primary=False,
        verified=True,
    )
    current.set_as_primary()
    request = RequestFactory().post("/synthetic-contact-change")
    SessionMiddleware(lambda _request: HttpResponse()).process_request(request)
    request.session.save()
    request.user = account

    emit_email_changed(request, previous, current)

    notifications = list(SecurityNotification.objects.order_by("created_at"))
    assert len(notifications) == 2
    assert {decrypt_notification_recipient(item) for item in notifications} == {
        previous.email,
        current.email,
    }
    assert len(mail.outbox) == 0

    outcome = run_security_notifications_once(owner="synthetic-contact-worker", limit=2)

    assert outcome.delivered == 2
    assert len(mail.outbox) == 2


def test_allauth_security_mail_uses_only_a_verified_account_destination() -> None:
    account = _verified_account("verified-destination")
    EmailAddress.objects.create(
        user=account,
        email="unverified-destination@mnemex.example.invalid",
        primary=False,
        verified=False,
    )

    with pytest.raises(ValidationError, match="verified notification destination"):
        _adapter().send_notification_mail(
            "account/email/password_changed",
            account,
            email="unverified-destination@mnemex.example.invalid",
        )

    assert not SecurityNotification.objects.exists()
    assert len(mail.outbox) == 0


def test_allauth_security_mail_rejects_an_unrecognized_template() -> None:
    account = _verified_account("template-policy")

    with pytest.raises(ValidationError, match="security notification template"):
        _adapter().send_notification_mail("account/email/email_confirmation", account)

    assert not SecurityNotification.objects.exists()
    assert len(mail.outbox) == 0


def test_queue_failure_is_audited_without_immediate_mail_fallback() -> None:
    account = _verified_account("queue-failure")

    with patch(
        "mnemex.accounts.adapters.enqueue_allauth_security_notification",
        side_effect=RuntimeError("synthetic queue outage with private detail"),
    ):
        _adapter().send_notification_mail("mfa/email/totp_activated", account)

    assert not SecurityNotification.objects.exists()
    assert len(mail.outbox) == 0
    failure = AuditEvent.objects.get(action="account.security_notification.failed")
    assert failure.metadata == {
        "template": "mfa/email/totp_activated",
        "error_type": "RuntimeError",
    }
    assert "private detail" not in str(failure.metadata)


def test_queue_and_audit_failure_still_preserve_the_security_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    account = _verified_account("queue-and-audit-failure")

    with (
        patch(
            "mnemex.accounts.adapters.enqueue_allauth_security_notification",
            side_effect=RuntimeError("private queue detail"),
        ),
        patch(
            "mnemex.accounts.adapters.record_audit_event",
            side_effect=RuntimeError("private audit detail"),
        ),
        caplog.at_level(logging.ERROR, logger="mnemex.accounts.adapters"),
    ):
        _adapter().send_notification_mail("mfa/email/totp_activated", account)

    assert not SecurityNotification.objects.exists()
    assert len(mail.outbox) == 0
    assert "account.security_notification.audit_unavailable" in caplog.text
    assert "private queue detail" not in caplog.text
    assert "private audit detail" not in caplog.text


@override_settings(ACCOUNT_EMAIL_NOTIFICATIONS=False)
def test_disabled_allauth_notifications_create_no_delivery_intent() -> None:
    account = _verified_account("notifications-disabled")

    _adapter().send_notification_mail("account/email/password_changed", account)

    assert not SecurityNotification.objects.exists()
    assert len(mail.outbox) == 0
