from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.utils import timezone

from mnemex.accounts.models import Account, SecurityNotification
from mnemex.accounts.notifications import (
    NotificationClaimLost,
    claim_next_notification,
    enqueue_security_notification,
    expire_notification_recipients,
    mark_notification_handoff,
    notification_queue_metrics,
    run_security_notifications_once,
    settle_notification_delivered,
)
from mnemex.foundation.models import AuditEvent

pytestmark = pytest.mark.django_db


class SyntheticPreAcceptanceFailure(OSError):
    pass


class FakeTransport:
    def __init__(
        self,
        *,
        open_error: Exception | None = None,
        send_error: Exception | None = None,
    ) -> None:
        self.open_error = open_error
        self.send_error = send_error
        self.messages = []
        self.closed = False

    def open(self) -> None:
        if self.open_error is not None:
            raise self.open_error

    def send(self, message) -> bool:
        self.messages.append(message)
        if self.send_error is not None:
            raise self.send_error
        return True

    def close(self) -> None:
        self.closed = True


def _queued(
    label: str = "worker",
    *,
    now: datetime | None = None,
) -> SecurityNotification:
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
    return enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key=f"{label}-idempotency",
        now=now,
    )


def test_worker_delivers_once_with_deterministic_message_id() -> None:
    notification = _queued("delivered")
    transport = FakeTransport()

    outcome = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        transport_factory=lambda: transport,
    )

    notification.refresh_from_db()
    assert outcome.claimed == 1
    assert outcome.delivered == 1
    assert notification.status == SecurityNotification.Status.DELIVERED
    assert notification.delivered_at is not None
    assert len(transport.messages) == 1
    assert transport.messages[0].extra_headers["Message-ID"] == notification.message_id
    assert transport.closed
    assert claim_next_notification(owner="synthetic-worker-b") is None


def test_worker_delivers_to_the_event_time_recipient_after_address_removal() -> None:
    notification = _queued("event-time-recipient")
    original_recipient = notification.account.email
    EmailAddress.objects.filter(user=notification.account).delete()
    Account.objects.filter(pk=notification.account_id).update(
        email="later-address@mnemex.example.invalid"
    )
    transport = FakeTransport()

    outcome = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        transport_factory=lambda: transport,
    )

    assert outcome.delivered == 1
    assert len(transport.messages) == 1
    assert transport.messages[0].to == [original_recipient]


def test_preaccept_failure_retries_with_same_message_id_and_one_audit_intent() -> None:
    notification = _queued("safe-retry")
    first_transport = FakeTransport(open_error=SyntheticPreAcceptanceFailure("private"))

    first = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        transport_factory=lambda: first_transport,
    )

    notification.refresh_from_db()
    assert first.retry_scheduled == 1
    assert notification.status == SecurityNotification.Status.RETRY_WAIT
    assert notification.last_error_code == "transport_unavailable"
    assert "private" not in notification.last_error_code
    assert AuditEvent.objects.filter(action="account.security_notification.queued").count() == 1

    notification.available_at = timezone.now() - timedelta(seconds=1)
    notification.save(update_fields=["available_at", "updated_at"])
    second_transport = FakeTransport()
    second = run_security_notifications_once(
        owner="synthetic-worker-b",
        limit=1,
        transport_factory=lambda: second_transport,
    )

    notification.refresh_from_db()
    assert second.delivered == 1
    assert notification.status == SecurityNotification.Status.DELIVERED
    assert second_transport.messages[0].extra_headers["Message-ID"] == notification.message_id
    assert AuditEvent.objects.filter(action="account.security_notification.queued").count() == 1


def test_transport_factory_failure_uses_the_preaccept_retry_path() -> None:
    notification = _queued("factory-failure")

    def unavailable_transport() -> FakeTransport:
        raise SyntheticPreAcceptanceFailure("private provider configuration")

    outcome = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        transport_factory=unavailable_transport,
    )

    notification.refresh_from_db()
    assert outcome.claimed == 1
    assert outcome.retry_scheduled == 1
    assert notification.status == SecurityNotification.Status.RETRY_WAIT
    assert notification.last_error_code == "transport_unavailable"
    assert "private provider configuration" not in notification.last_error_code


def test_ambiguous_error_after_handoff_requires_review_without_redelivery() -> None:
    notification = _queued("ambiguous")
    transport = FakeTransport(send_error=TimeoutError("recipient was private@example.invalid"))

    outcome = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        transport_factory=lambda: transport,
    )

    notification.refresh_from_db()
    assert outcome.delivery_uncertain == 1
    assert notification.status == SecurityNotification.Status.DELIVERY_UNCERTAIN
    assert notification.last_error_code == "smtp_outcome_ambiguous"
    assert "private@example.invalid" not in notification.last_error_code
    assert (
        claim_next_notification(
            owner="synthetic-worker-b",
            now=timezone.now() + timedelta(hours=1),
        )
        is None
    )
    audit_dump = str(list(AuditEvent.objects.values("action", "metadata")))
    assert "private@example.invalid" not in audit_dump


def test_expired_pre_handoff_lease_is_reclaimed_and_stale_claim_is_fenced() -> None:
    notification = _queued("lease-retry")
    start = timezone.now()
    first = claim_next_notification(
        owner="synthetic-worker-a",
        now=start,
        lease_duration=timedelta(seconds=5),
    )
    assert first is not None

    second = claim_next_notification(
        owner="synthetic-worker-b",
        now=start + timedelta(seconds=6),
        lease_duration=timedelta(seconds=5),
    )

    assert second is not None
    assert second.notification_id == first.notification_id
    assert second.generation == first.generation + 1
    with pytest.raises(NotificationClaimLost):
        settle_notification_delivered(first, now=start + timedelta(seconds=7))
    notification.refresh_from_db()
    assert notification.status == SecurityNotification.Status.RUNNING
    assert notification.failure_count == 1


def test_expired_post_handoff_lease_becomes_delivery_uncertain() -> None:
    notification = _queued("lease-uncertain")
    start = timezone.now()
    claim = claim_next_notification(
        owner="synthetic-worker-a",
        now=start,
        lease_duration=timedelta(seconds=5),
    )
    assert claim is not None
    mark_notification_handoff(claim, now=start + timedelta(seconds=1))

    replacement = claim_next_notification(
        owner="synthetic-worker-b",
        now=start + timedelta(seconds=6),
    )

    notification.refresh_from_db()
    assert replacement is None
    assert notification.status == SecurityNotification.Status.DELIVERY_UNCERTAIN
    assert notification.last_error_code == "worker_lost_after_handoff"


def test_worker_limit_bounds_expired_handoff_terminalization() -> None:
    claimed_at = timezone.now() + timedelta(seconds=1)
    notification_ids = []
    for index in range(5):
        notification = _queued(f"expired-handoff-{index}")
        claim = claim_next_notification(
            owner=f"synthetic-worker-{index}",
            now=claimed_at,
            lease_duration=timedelta(minutes=1),
        )
        assert claim is not None
        assert claim.notification_id == notification.pk
        mark_notification_handoff(claim, now=claimed_at + timedelta(seconds=1))
        notification_ids.append(notification.pk)

    replacement = claim_next_notification(
        owner="synthetic-bounded-worker",
        now=claimed_at + timedelta(minutes=2),
    )

    statuses = list(
        SecurityNotification.objects.filter(pk__in=notification_ids).values_list(
            "status", flat=True
        )
    )
    assert replacement is None
    assert statuses.count(SecurityNotification.Status.DELIVERY_UNCERTAIN) == 1
    assert statuses.count(SecurityNotification.Status.RUNNING) == 4


def test_worker_uses_remaining_batch_slots_after_stale_terminalizations() -> None:
    claimed_at = timezone.now() - timedelta(minutes=10)
    stale_ids = []
    for index in range(4):
        notification = _queued(f"stale-before-fresh-{index}", now=claimed_at)
        claim = claim_next_notification(
            owner=f"synthetic-stale-worker-{index}",
            now=claimed_at,
            lease_duration=timedelta(minutes=1),
        )
        assert claim is not None
        mark_notification_handoff(claim, now=claimed_at + timedelta(seconds=1))
        stale_ids.append(notification.pk)
    fresh = _queued("fresh-after-stale")
    transport = FakeTransport()

    outcome = run_security_notifications_once(
        owner="synthetic-bounded-worker",
        limit=5,
        transport_factory=lambda: transport,
    )

    fresh.refresh_from_db()
    assert outcome.claimed == 1
    assert outcome.delivered == 1
    assert fresh.status == SecurityNotification.Status.DELIVERED
    assert len(transport.messages) == 1
    assert (
        SecurityNotification.objects.filter(
            pk__in=stale_ids,
            status=SecurityNotification.Status.DELIVERY_UNCERTAIN,
        ).count()
        == 4
    )


def test_worker_honors_graceful_stop_before_claim_and_metrics_are_redacted() -> None:
    notification = _queued("stop")

    outcome = run_security_notifications_once(
        owner="synthetic-worker-a",
        limit=1,
        should_stop=lambda: True,
        transport_factory=FakeTransport,
    )
    metrics = notification_queue_metrics(now=timezone.now() + timedelta(seconds=1))

    notification.refresh_from_db()
    assert outcome.claimed == 0
    assert notification.status == SecurityNotification.Status.PENDING
    assert metrics.ready_depth == 1
    assert metrics.oldest_ready_age_seconds >= 0
    assert notification.account.email not in str(metrics)


def test_worker_limit_is_bounded() -> None:
    _queued("bounded")

    with pytest.raises(ValidationError, match="between 1 and"):
        run_security_notifications_once(
            owner="synthetic-worker-a",
            limit=0,
            transport_factory=FakeTransport,
        )


def test_recipient_expiry_waits_for_active_handoff_then_marks_uncertain() -> None:
    queued_at = timezone.now()
    notification = _queued("retention-handoff")
    notification.recipient_retention_deadline = queued_at + timedelta(hours=1)
    notification.save(update_fields=["recipient_retention_deadline", "updated_at"])
    claim = claim_next_notification(
        owner="synthetic-retention-worker",
        now=queued_at + timedelta(minutes=30),
        lease_duration=timedelta(hours=1),
    )
    assert claim is not None
    mark_notification_handoff(claim, now=queued_at + timedelta(minutes=31))

    active = expire_notification_recipients(now=queued_at + timedelta(hours=1, seconds=1))
    notification.refresh_from_db()
    assert active.expired == 0
    assert notification.status == SecurityNotification.Status.RUNNING
    assert notification.recipient_ciphertext

    expired = expire_notification_recipients(now=queued_at + timedelta(hours=2))
    notification.refresh_from_db()
    assert expired.expired == 1
    assert notification.status == SecurityNotification.Status.DELIVERY_UNCERTAIN
    assert notification.last_error_code == "recipient_retention_expired_during_handoff"
    assert notification.recipient_ciphertext == ""


@pytest.mark.django_db(transaction=True)
def test_postgresql_competing_claimers_deliver_one_notification() -> None:
    # The authoritative PostgreSQL gate runs this contract against the disposable
    # MNEMEX_TEST_DATABASE_URL database. SQLite is intentionally not credited as
    # row-lock evidence.
    if connection.vendor != "postgresql":
        pytest.skip("row-lock concurrency evidence requires disposable PostgreSQL")
    notification = _queued("postgres-race")
    now = timezone.now()

    def claim(owner: str):
        connections.close_all()
        return claim_next_notification(owner=owner, now=now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("synthetic-worker-a", "synthetic-worker-b")))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].notification_id == notification.pk
