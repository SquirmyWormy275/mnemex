from __future__ import annotations

import json
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from mnemex.accounts.models import Account, SecurityNotification
from mnemex.accounts.notifications import (
    decrypt_notification_recipient,
    enqueue_security_notification,
    enqueue_verified_contact_change,
    expire_notification_recipients,
)
from mnemex.foundation.models import AuditEvent

pytestmark = pytest.mark.django_db


def _verified_account(label: str = "security-outbox") -> Account:
    account = Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password-only",
        email_verified_at=timezone.now(),
    )
    EmailAddress.objects.create(
        user=account,
        email=account.email,
        primary=True,
        verified=True,
    )
    return account


def test_enqueue_encrypts_event_time_recipient_and_is_idempotent() -> None:
    account = _verified_account()
    recipient = account.email
    queued_at = timezone.now()

    first = enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=recipient,
        context_code="account-security-v1",
        idempotency_key="totp-activated-security-version-1",
        now=queued_at,
    )
    duplicate = enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=recipient,
        context_code="account-security-v1",
        idempotency_key="totp-activated-security-version-1",
        now=queued_at + timedelta(seconds=1),
    )

    assert duplicate.pk == first.pk
    assert SecurityNotification.objects.count() == 1
    assert recipient not in first.recipient_ciphertext
    assert recipient not in first.recipient_hmac
    assert decrypt_notification_recipient(first) == recipient
    assert first.message_id.startswith("<mnemex.security.")
    assert first.message_id.endswith("@notifications.mnemex.invalid>")
    assert AuditEvent.objects.filter(action="account.security_notification.queued").count() == 1

    serialized = json.dumps(
        list(AuditEvent.objects.values("action", "target_id", "metadata")),
        sort_keys=True,
        default=str,
    )
    assert recipient not in serialized
    field_names = {field.name for field in SecurityNotification._meta.fields}
    assert "subject" not in field_names
    assert "body" not in field_names
    assert "recipient" not in field_names


def test_contact_change_snapshots_both_verified_destinations() -> None:
    account = _verified_account("contact-before")
    old_address = EmailAddress.objects.get(user=account, primary=True)
    new_address = EmailAddress.objects.create(
        user=account,
        email="contact-after@mnemex.example.invalid",
        primary=False,
        verified=True,
    )
    with transaction.atomic():
        account.security_version += 1
        account.email = new_address.email
        account.save(update_fields=["security_version", "email"])
        enqueue_verified_contact_change(
            account=account,
            previous_recipient=old_address.email,
            new_recipient=new_address.email,
            event_key=(f"account-security:account/email/email_changed:{account.security_version}"),
        )

    account.refresh_from_db()
    notifications = list(
        SecurityNotification.objects.filter(
            template_identifier="account/email/email_changed"
        ).order_by("notification_id")
    )
    assert account.email == new_address.email
    assert len(notifications) == 2
    assert {decrypt_notification_recipient(item) for item in notifications} == {
        old_address.email,
        new_address.email,
    }
    audit_dump = json.dumps(
        list(AuditEvent.objects.values("action", "metadata")),
        sort_keys=True,
        default=str,
    )
    assert old_address.email not in audit_dump
    assert new_address.email not in audit_dump


def test_contact_change_skips_unverified_destination() -> None:
    account = _verified_account("contact-verified")
    old_address = EmailAddress.objects.get(user=account, primary=True)
    unverified = EmailAddress.objects.create(
        user=account,
        email="unverified@mnemex.example.invalid",
        primary=False,
        verified=False,
    )
    with transaction.atomic():
        enqueue_verified_contact_change(
            account=account,
            previous_recipient=old_address.email,
            new_recipient=unverified.email,
            event_key="account-security:account/email/email_changed:2",
        )

    notifications = list(
        SecurityNotification.objects.filter(template_identifier="account/email/email_changed")
    )
    assert len(notifications) == 1
    assert decrypt_notification_recipient(notifications[0]) == old_address.email


def test_retention_expiry_removes_ciphertext_but_preserves_nonreversible_outcome() -> None:
    account = _verified_account("retention")
    queued_at = timezone.now()
    notification = enqueue_security_notification(
        account=account,
        template_identifier="account/email/password_changed",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key="password-change-security-version-1",
        now=queued_at,
        recipient_retention=timedelta(hours=1),
    )
    retained_hmac = notification.recipient_hmac

    outcome = expire_notification_recipients(now=queued_at + timedelta(hours=2))

    notification.refresh_from_db()
    assert outcome.expired == 1
    assert notification.status == SecurityNotification.Status.EXPIRED
    assert notification.recipient_ciphertext == ""
    assert notification.recipient_hmac == retained_hmac
    assert notification.recipient_purged_at is not None
    assert AuditEvent.objects.filter(action="account.security_notification.expired").count() == 1


@override_settings(
    MNEMEX_NOTIFICATION_ENCRYPTION_KEYS={},
    MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION=None,
)
def test_missing_notification_key_fails_closed_without_persisting_intent() -> None:
    account = _verified_account("missing-key")

    with pytest.raises(ImproperlyConfigured, match="notification encryption"):
        enqueue_security_notification(
            account=account,
            template_identifier="account/email/password_changed",
            recipient=account.email,
            context_code="account-security-v1",
            idempotency_key="missing-key-notification",
        )

    assert not SecurityNotification.objects.exists()
    assert not AuditEvent.objects.filter(action="account.security_notification.queued").exists()


@override_settings(
    MNEMEX_NOTIFICATION_ENCRYPTION_KEYS={1: b"a" * 32, 2: b"b" * 32},
    MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION=1,
)
def test_exact_enqueue_replay_survives_active_encryption_key_rotation(settings) -> None:
    account = _verified_account("rotation-replay")
    first = enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key="stable-event-id",
    )
    first_message_id = first.message_id

    settings.MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION = 2
    replay = enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key="stable-event-id",
    )

    assert replay.pk == first.pk
    assert replay.message_id == first_message_id
    assert SecurityNotification.objects.count() == 1


def test_idempotency_key_rejects_a_different_recipient_without_disclosure() -> None:
    account = _verified_account("recipient-conflict")
    enqueue_security_notification(
        account=account,
        template_identifier="account/email/password_changed",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key="one-security-event",
    )

    with pytest.raises(ValidationError, match="idempotency key conflicts") as caught:
        enqueue_security_notification(
            account=account,
            template_identifier="account/email/password_changed",
            recipient="different@mnemex.example.invalid",
            context_code="account-security-v1",
            idempotency_key="one-security-event",
        )

    assert account.email not in str(caught.value)
    assert "different@mnemex.example.invalid" not in str(caught.value)
    assert SecurityNotification.objects.count() == 1
