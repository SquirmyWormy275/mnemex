from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Protocol
from uuid import UUID, uuid4

from allauth.account.models import EmailAddress
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core import mail
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail.message import EmailMessage, EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import IntegrityError, connection, models, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from mnemex.accounts.models import Account, SecurityNotification
from mnemex.foundation.services import record_audit_event

DEFAULT_NOTIFICATION_LEASE = timedelta(minutes=5)
DEFAULT_RECIPIENT_RETENTION = timedelta(days=30)
INITIAL_RETRY_DELAY_SECONDS = 30
MAX_RETRY_DELAY_SECONDS = 15 * 60
MAX_NOTIFICATION_ATTEMPTS = 5
MAX_NOTIFICATIONS_PER_RUN = 25
MAX_RETENTION_BATCH = 500

_AAD_PREFIX = "mnemex.security.notification.recipient.v1"
_CIPHERTEXT_RE = re.compile(r"^v(?P<version>[1-9][0-9]*)\.(?P<payload>[A-Za-z0-9_-]+=*)$")
_TEMPLATE_RE = re.compile(r"^(?:account|mfa)/email/[a-z0-9_/-]{1,140}$")
_CONTEXT_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,79}$")

ALLAUTH_SECURITY_NOTIFICATION_TEMPLATES = frozenset(
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
ALLAUTH_SECURITY_CONTEXT_CODE = "allauth-security-v1"


class NotificationClaimLost(RuntimeError):
    """A stale or mismatched worker attempted to mutate a notification."""


class NotificationTransport(Protocol):
    """SMTP boundary that makes the pre/post-acceptance split explicit."""

    def open(self) -> None: ...

    def send(self, message: EmailMessage) -> bool: ...

    def close(self) -> None: ...


class DjangoNotificationTransport:
    """Django mail transport with a separately observable connection-open step."""

    def __init__(self) -> None:
        self._connection = mail.get_connection()

    def open(self) -> None:
        self._connection.open()

    def send(self, message: EmailMessage) -> bool:
        return self._connection.send_messages([message]) == 1

    def close(self) -> None:
        self._connection.close()


@dataclass(frozen=True)
class ClaimedSecurityNotification:
    notification_id: UUID
    token: str
    generation: int
    owner: str


@dataclass(frozen=True)
class _NotificationClaimAttempt:
    claim: ClaimedSecurityNotification | None = None
    terminalized: bool = False


@dataclass(frozen=True)
class SecurityNotificationOutcome:
    notification_id: UUID
    status: str
    attempt_count: int
    failure_count: int
    error_code: str
    available_at: datetime


@dataclass(frozen=True)
class NotificationWorkerBatchOutcome:
    claimed: int = 0
    delivered: int = 0
    retry_scheduled: int = 0
    failed_review: int = 0
    delivery_uncertain: int = 0
    expired: int = 0
    claim_lost: int = 0


@dataclass(frozen=True)
class RecipientExpiryOutcome:
    expired: int = 0
    pending_terminalized: int = 0


@dataclass(frozen=True)
class NotificationQueueMetrics:
    ready_depth: int
    oldest_ready_age_seconds: int | None
    running_depth: int
    retry_wait_depth: int
    failed_review_depth: int
    delivery_uncertain_depth: int


def _checked_now(now: datetime | None) -> datetime:
    value = now if now is not None else timezone.now()
    if timezone.is_naive(value):
        raise ValidationError("notification worker time must be timezone-aware")
    return value


def _checked_owner(owner: str) -> str:
    if not isinstance(owner, str):
        raise ValidationError("notification claim owner is invalid")
    normalized = owner.strip()
    if not normalized or len(normalized) > 120 or any(ord(char) < 32 for char in normalized):
        raise ValidationError("notification claim owner is invalid")
    return normalized


def _checked_lease(lease_duration: timedelta) -> timedelta:
    if not isinstance(lease_duration, timedelta) or not (
        timedelta(seconds=1) <= lease_duration <= timedelta(hours=1)
    ):
        raise ValidationError("notification lease must be between 1 second and 1 hour")
    return lease_duration


def _checked_limit(limit: int, *, maximum: int, field: str) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValidationError(f"{field} must be between 1 and {maximum}")
    return limit


def _checked_retention(value: timedelta | None) -> timedelta:
    retention = value if value is not None else DEFAULT_RECIPIENT_RETENTION
    if not isinstance(retention, timedelta) or not (
        timedelta(hours=1) <= retention <= timedelta(days=90)
    ):
        raise ValidationError("recipient retention must be between 1 hour and 90 days")
    return retention


def _notification_keys() -> tuple[dict[int, bytes], int]:
    keys = getattr(settings, "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS", {})
    active_version = getattr(settings, "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION", None)
    if not isinstance(keys, Mapping) or not isinstance(active_version, int):
        raise ImproperlyConfigured("notification encryption is not configured")
    normalized: dict[int, bytes] = {}
    for version, key in keys.items():
        if (
            not isinstance(version, int)
            or version < 1
            or not isinstance(key, bytes)
            or len(key) != 32
        ):
            raise ImproperlyConfigured(
                "notification encryption keys must be versioned 32-byte values"
            )
        normalized[version] = key
    if active_version not in normalized:
        raise ImproperlyConfigured("active notification encryption key is unavailable")
    return normalized, active_version


def _canonical_recipient(recipient: str) -> str:
    if not isinstance(recipient, str):
        raise ValidationError("verified notification destination is invalid")
    canonical = recipient.strip().lower()
    validate_email(canonical)
    if len(canonical) > 254:
        raise ValidationError("verified notification destination is invalid")
    return canonical


def _checked_template(template_identifier: str) -> str:
    if not isinstance(template_identifier, str) or not _TEMPLATE_RE.fullmatch(template_identifier):
        raise ValidationError("notification template identifier is invalid")
    return template_identifier


def _checked_context(context_code: str) -> str:
    if not isinstance(context_code, str) or not _CONTEXT_RE.fullmatch(context_code):
        raise ValidationError("notification context code is invalid")
    return context_code


def _checked_idempotency_seed(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("notification idempotency key is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 500 or any(ord(char) < 32 for char in normalized):
        raise ValidationError("notification idempotency key is invalid")
    return normalized


def _recipient_aad(*, notification_id: UUID, account_id: UUID, template_identifier: str) -> bytes:
    return (f"{_AAD_PREFIX}:{notification_id}:{account_id}:{template_identifier}").encode("utf-8")


def _encrypt_recipient(
    *,
    notification_id: UUID,
    account_id: UUID,
    template_identifier: str,
    recipient: str,
    key: bytes,
    key_version: int,
) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        recipient.encode("utf-8"),
        _recipient_aad(
            notification_id=notification_id,
            account_id=account_id,
            template_identifier=template_identifier,
        ),
    )
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"v{key_version}.{encoded}"


def decrypt_notification_recipient(notification: SecurityNotification) -> str:
    if notification.recipient_purged_at is not None or not notification.recipient_ciphertext:
        raise ValueError("notification recipient is unavailable")
    match = _CIPHERTEXT_RE.fullmatch(notification.recipient_ciphertext)
    if match is None:
        raise ValueError("notification recipient could not be decrypted")
    version = int(match.group("version"))
    if version != notification.encryption_key_version:
        raise ValueError("notification recipient could not be decrypted")
    keys, _active_version = _notification_keys()
    key = keys.get(version)
    if key is None:
        raise ValueError("notification recipient could not be decrypted")
    try:
        sealed = base64.urlsafe_b64decode(match.group("payload").encode("ascii"))
        if len(sealed) < 29:
            raise ValueError
        plaintext = AESGCM(key).decrypt(
            sealed[:12],
            sealed[12:],
            _recipient_aad(
                notification_id=notification.pk,
                account_id=notification.account_id,
                template_identifier=notification.template_identifier,
            ),
        )
        return _canonical_recipient(plaintext.decode("utf-8"))
    except (InvalidTag, UnicodeDecodeError, ValueError, binascii.Error) as error:
        raise ValueError("notification recipient could not be decrypted") from error


def _audit_digest(action: str, notification: SecurityNotification) -> str:
    return hashlib.sha256(
        f"{action}:{notification.pk}:{notification.idempotency_key}".encode("utf-8")
    ).hexdigest()


def _audit_notification(
    *,
    action: str,
    notification: SecurityNotification,
    metadata: dict[str, str | int] | None = None,
) -> None:
    record_audit_event(
        action=action,
        target_type="security_notification",
        target_id=str(notification.pk),
        payload_digest=_audit_digest(action, notification),
        metadata=metadata or {},
        actor_id=notification.account_id,
        correlation_id=notification.pk,
    )


def _message_id(idempotency_digest: str) -> str:
    return f"<mnemex.security.{idempotency_digest}@notifications.mnemex.invalid>"


@transaction.atomic
def enqueue_security_notification(
    *,
    account: Account,
    template_identifier: str,
    recipient: str,
    context_code: str,
    idempotency_key: str,
    now: datetime | None = None,
    recipient_retention: timedelta | None = None,
) -> SecurityNotification:
    queued_at = _checked_now(now)
    template = _checked_template(template_identifier)
    context = _checked_context(context_code)
    seed = _checked_idempotency_seed(idempotency_key)
    canonical_recipient = _canonical_recipient(recipient)
    retention = _checked_retention(recipient_retention)
    keys, active_version = _notification_keys()
    recipient_hmac = hmac.new(
        keys[active_version],
        canonical_recipient.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    idempotency_digest = hashlib.sha256(
        f"mnemex.security.notification.idempotency.v1:{account.pk}:{template}:{context}:{seed}".encode(
            "utf-8"
        )
    ).hexdigest()
    expected = {
        "account_id": account.pk,
        "template_identifier": template,
        "context_code": context,
    }
    existing = (
        SecurityNotification.objects.select_for_update()
        .filter(idempotency_key=idempotency_digest)
        .first()
    )
    if existing is not None:
        if any(getattr(existing, field) != value for field, value in expected.items()):
            raise ValidationError("notification idempotency key conflicts with existing intent")
        if existing.recipient_ciphertext:
            try:
                existing_recipient = decrypt_notification_recipient(existing)
            except (ImproperlyConfigured, ValueError) as error:
                raise ValidationError(
                    "notification idempotency key conflicts with existing intent"
                ) from error
            if not hmac.compare_digest(existing_recipient, canonical_recipient):
                raise ValidationError("notification idempotency key conflicts with existing intent")
        return existing

    notification_id = uuid4()
    ciphertext = _encrypt_recipient(
        notification_id=notification_id,
        account_id=account.pk,
        template_identifier=template,
        recipient=canonical_recipient,
        key=keys[active_version],
        key_version=active_version,
    )
    try:
        with transaction.atomic():
            notification = SecurityNotification.objects.create(
                notification_id=notification_id,
                account=account,
                template_identifier=template,
                context_code=context,
                idempotency_key=idempotency_digest,
                message_id=_message_id(idempotency_digest),
                recipient_ciphertext=ciphertext,
                recipient_hmac=recipient_hmac,
                encryption_key_version=active_version,
                max_attempts=MAX_NOTIFICATION_ATTEMPTS,
                available_at=queued_at,
                recipient_retention_deadline=queued_at + retention,
            )
    except IntegrityError:
        notification = SecurityNotification.objects.select_for_update().get(
            idempotency_key=idempotency_digest
        )
        if any(getattr(notification, field) != value for field, value in expected.items()):
            raise ValidationError(
                "notification idempotency key conflicts with existing intent"
            ) from None
        if notification.recipient_ciphertext:
            try:
                existing_recipient = decrypt_notification_recipient(notification)
            except (ImproperlyConfigured, ValueError) as error:
                raise ValidationError(
                    "notification idempotency key conflicts with existing intent"
                ) from error
            if not hmac.compare_digest(existing_recipient, canonical_recipient):
                raise ValidationError("notification idempotency key conflicts with existing intent")
        return notification
    _audit_notification(
        action="account.security_notification.queued",
        notification=notification,
        metadata={
            "template_identifier": template,
            "context_code": context,
            "key_version": active_version,
        },
    )
    return notification


@transaction.atomic
def enqueue_allauth_security_notification(
    *,
    account: Account,
    template_identifier: str,
    requested_recipient: str | None = None,
    notification_context: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> tuple[SecurityNotification, ...]:
    """Snapshot a verified allauth security-mail recipient into the durable queue."""

    if not isinstance(account, Account):
        raise ValidationError("security notification account is invalid")
    template = _checked_template(template_identifier)
    if template not in ALLAUTH_SECURITY_NOTIFICATION_TEMPLATES:
        raise ValidationError("security notification template is not approved")

    locked_account = Account.objects.select_for_update().get(pk=account.pk)
    credential_fingerprint = hashlib.sha256(locked_account.password.encode("utf-8")).hexdigest()
    event_key = (
        f"{ALLAUTH_SECURITY_CONTEXT_CODE}:"
        f"security-version:{locked_account.security_version}:"
        f"credential:{credential_fingerprint}"
    )
    if template == "account/email/email_changed":
        if not isinstance(notification_context, Mapping):
            raise ValidationError("verified contact-change context is invalid")
        previous_recipient = requested_recipient or notification_context.get("from_email")
        new_recipient = notification_context.get("to_email")
        if not isinstance(previous_recipient, str) or not isinstance(new_recipient, str):
            raise ValidationError("verified contact-change context is invalid")
        queued = _enqueue_verified_contact_change_locked(
            account=locked_account,
            previous_recipient=previous_recipient,
            new_recipient=new_recipient,
            event_key=event_key,
            now=now,
        )
        if not queued:
            raise ValidationError("verified notification destination is unavailable")
        return queued

    addresses = EmailAddress.objects.select_for_update().filter(
        user=locked_account,
        verified=True,
    )
    if requested_recipient is None:
        address = addresses.filter(primary=True).first()
    else:
        canonical_recipient = _canonical_recipient(requested_recipient)
        address = addresses.filter(email__iexact=canonical_recipient).first()
    if address is None:
        raise ValidationError("verified notification destination is unavailable")

    return (
        enqueue_security_notification(
            account=locked_account,
            template_identifier=template,
            recipient=address.email,
            context_code=ALLAUTH_SECURITY_CONTEXT_CODE,
            idempotency_key=event_key,
            now=now,
        ),
    )


def _enqueue_verified_contact_change_locked(
    *,
    account: Account,
    previous_recipient: str | None,
    new_recipient: str | None,
    event_key: str,
    now: datetime | None,
) -> tuple[SecurityNotification, ...]:
    verified_addresses = {
        address.email.strip().lower(): address
        for address in EmailAddress.objects.select_for_update().filter(
            user=account,
            verified=True,
        )
    }
    queued: list[SecurityNotification] = []
    seen: set[str] = set()
    for side, recipient in (
        ("previous", previous_recipient),
        ("new", new_recipient),
    ):
        if not recipient:
            continue
        canonical = _canonical_recipient(recipient)
        if canonical in seen:
            continue
        seen.add(canonical)
        address = verified_addresses.get(canonical)
        if address is None:
            continue
        queued.append(
            enqueue_security_notification(
                account=account,
                template_identifier="account/email/email_changed",
                recipient=address.email,
                context_code="verified-contact-change-v1",
                idempotency_key=f"{event_key}:{side}",
                now=now,
            )
        )
    return tuple(queued)


@transaction.atomic
def enqueue_verified_contact_change(
    *,
    account: Account,
    previous_recipient: str | None,
    new_recipient: str | None,
    event_key: str,
    now: datetime | None = None,
) -> tuple[SecurityNotification, ...]:
    """Snapshot both verified contact destinations inside the caller transaction."""

    locked_account = Account.objects.select_for_update().get(pk=account.pk)
    return _enqueue_verified_contact_change_locked(
        account=locked_account,
        previous_recipient=previous_recipient,
        new_recipient=new_recipient,
        event_key=event_key,
        now=now,
    )


def _outcome(notification: SecurityNotification) -> SecurityNotificationOutcome:
    return SecurityNotificationOutcome(
        notification_id=notification.pk,
        status=notification.status,
        attempt_count=notification.attempt_count,
        failure_count=notification.failure_count,
        error_code=notification.last_error_code,
        available_at=notification.available_at,
    )


def _clear_claim(notification: SecurityNotification) -> None:
    notification.claim_token = ""
    notification.claim_owner = ""
    notification.heartbeat_at = None
    notification.lease_expires_at = None


def _assert_claim(
    notification: SecurityNotification,
    claim: ClaimedSecurityNotification,
    *,
    now: datetime,
) -> None:
    if (
        notification.status != SecurityNotification.Status.RUNNING
        or notification.claim_token != claim.token
        or notification.claim_generation != claim.generation
        or notification.claim_owner != claim.owner
        or notification.lease_expires_at is None
        or notification.lease_expires_at < now
    ):
        raise NotificationClaimLost("security notification claim is no longer active")


def _locked_notification(notification_id: UUID) -> SecurityNotification:
    notification = (
        SecurityNotification.objects.select_for_update()
        .select_related("account")
        .filter(pk=notification_id)
        .first()
    )
    if notification is None:
        raise NotificationClaimLost("security notification claim no longer exists")
    return notification


def _terminalize_review(
    notification: SecurityNotification,
    *,
    now: datetime,
    error_code: str,
    action: str = "account.security_notification.failed_review",
) -> None:
    notification.status = SecurityNotification.Status.FAILED_REVIEW
    notification.completed_at = now
    notification.review_required_at = now
    notification.last_error_code = error_code
    _clear_claim(notification)
    notification.save(
        update_fields=[
            "status",
            "completed_at",
            "review_required_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit_notification(
        action=action,
        notification=notification,
        metadata={"error_code": error_code},
    )


def _terminalize_uncertain(
    notification: SecurityNotification,
    *,
    now: datetime,
    error_code: str,
) -> None:
    notification.status = SecurityNotification.Status.DELIVERY_UNCERTAIN
    notification.completed_at = now
    notification.review_required_at = now
    notification.last_error_code = error_code
    _clear_claim(notification)
    notification.save(
        update_fields=[
            "status",
            "completed_at",
            "review_required_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit_notification(
        action="account.security_notification.delivery_uncertain",
        notification=notification,
        metadata={"error_code": error_code},
    )


def _purge_recipient(notification: SecurityNotification, *, now: datetime) -> bool:
    if notification.recipient_purged_at is not None:
        return False
    previous_status = notification.status
    uncertain_handoff = (
        previous_status == SecurityNotification.Status.RUNNING
        and notification.delivery_phase == SecurityNotification.DeliveryPhase.HANDOFF
    )
    terminalized = previous_status in {
        SecurityNotification.Status.PENDING,
        SecurityNotification.Status.RUNNING,
        SecurityNotification.Status.RETRY_WAIT,
    }
    notification.recipient_ciphertext = ""
    notification.recipient_purged_at = now
    if uncertain_handoff:
        notification.status = SecurityNotification.Status.DELIVERY_UNCERTAIN
        notification.completed_at = now
        notification.review_required_at = now
        notification.last_error_code = "recipient_retention_expired_during_handoff"
        _clear_claim(notification)
    elif terminalized:
        notification.status = SecurityNotification.Status.EXPIRED
        notification.completed_at = now
        notification.last_error_code = "recipient_retention_expired"
        _clear_claim(notification)
    notification.save(
        update_fields=[
            "recipient_ciphertext",
            "recipient_purged_at",
            "status",
            "completed_at",
            "review_required_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit_notification(
        action="account.security_notification.expired",
        notification=notification,
        metadata={"previous_status": previous_status},
    )
    return terminalized


@transaction.atomic
def expire_notification_recipients(
    *, now: datetime | None = None, limit: int = 100
) -> RecipientExpiryOutcome:
    expired_at = _checked_now(now)
    checked_limit = _checked_limit(limit, maximum=MAX_RETENTION_BATCH, field="expiry limit")
    queryset = (
        SecurityNotification.objects.filter(
            recipient_purged_at__isnull=True,
            recipient_retention_deadline__lte=expired_at,
        )
        .exclude(
            status=SecurityNotification.Status.RUNNING,
            lease_expires_at__gt=expired_at,
        )
        .order_by("recipient_retention_deadline", "created_at", "notification_id")
    )
    queryset = queryset.select_for_update(
        skip_locked=connection.features.has_select_for_update_skip_locked
    )
    notifications = list(queryset[:checked_limit])
    terminalized = sum(
        1 for notification in notifications if _purge_recipient(notification, now=expired_at)
    )
    return RecipientExpiryOutcome(
        expired=len(notifications),
        pending_terminalized=terminalized,
    )


def _claimable(now: datetime) -> models.QuerySet[SecurityNotification]:
    due = models.Q(
        status__in=(
            SecurityNotification.Status.PENDING,
            SecurityNotification.Status.RETRY_WAIT,
        ),
        available_at__lte=now,
    )
    expired_lease = models.Q(
        status=SecurityNotification.Status.RUNNING,
        lease_expires_at__lte=now,
    )
    return (
        SecurityNotification.objects.filter(
            due | expired_lease,
            recipient_purged_at__isnull=True,
            recipient_retention_deadline__gt=now,
        )
        .annotate(
            claim_ready_at=models.Case(
                models.When(
                    status=SecurityNotification.Status.RUNNING,
                    then=models.F("lease_expires_at"),
                ),
                default=models.F("available_at"),
                output_field=models.DateTimeField(),
            )
        )
        .order_by("claim_ready_at", "created_at", "notification_id")
    )


@transaction.atomic
def _claim_next_notification_attempt(
    *,
    owner: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_NOTIFICATION_LEASE,
) -> _NotificationClaimAttempt:
    claimed_at = _checked_now(now)
    checked_owner = _checked_owner(owner)
    checked_lease = _checked_lease(lease_duration)
    expire_notification_recipients(now=claimed_at)
    queryset = _claimable(claimed_at).select_for_update(
        skip_locked=connection.features.has_select_for_update_skip_locked
    )
    notification = queryset.first()
    if notification is None:
        return _NotificationClaimAttempt()
    expired_takeover = notification.status == SecurityNotification.Status.RUNNING
    if (
        expired_takeover
        and notification.delivery_phase == SecurityNotification.DeliveryPhase.HANDOFF
    ):
        _terminalize_uncertain(
            notification,
            now=claimed_at,
            error_code="worker_lost_after_handoff",
        )
        return _NotificationClaimAttempt(terminalized=True)
    if expired_takeover:
        notification.failure_count += 1
        if notification.failure_count >= notification.max_attempts:
            _terminalize_review(
                notification,
                now=claimed_at,
                error_code="attempts_exhausted",
            )
            return _NotificationClaimAttempt(terminalized=True)
    token = secrets.token_hex(32)
    notification.status = SecurityNotification.Status.RUNNING
    notification.delivery_phase = SecurityNotification.DeliveryPhase.PRE_HANDOFF
    notification.attempt_count += 1
    notification.claim_generation += 1
    notification.claim_token = token
    notification.claim_owner = checked_owner
    notification.heartbeat_at = claimed_at
    notification.lease_expires_at = claimed_at + checked_lease
    notification.started_at = notification.started_at or claimed_at
    notification.completed_at = None
    notification.review_required_at = None
    notification.handoff_at = None
    notification.last_error_code = ""
    notification.save(
        update_fields=[
            "status",
            "delivery_phase",
            "attempt_count",
            "failure_count",
            "claim_generation",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "started_at",
            "completed_at",
            "review_required_at",
            "handoff_at",
            "last_error_code",
            "updated_at",
        ]
    )
    return _NotificationClaimAttempt(
        claim=ClaimedSecurityNotification(
            notification_id=notification.pk,
            token=token,
            generation=notification.claim_generation,
            owner=checked_owner,
        )
    )


def claim_next_notification(
    *,
    owner: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_NOTIFICATION_LEASE,
) -> ClaimedSecurityNotification | None:
    return _claim_next_notification_attempt(
        owner=owner,
        now=now,
        lease_duration=lease_duration,
    ).claim


@transaction.atomic
def heartbeat_notification(
    claim: ClaimedSecurityNotification,
    *,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_NOTIFICATION_LEASE,
) -> SecurityNotificationOutcome:
    heartbeat_at = _checked_now(now)
    checked_lease = _checked_lease(lease_duration)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=heartbeat_at)
    assert notification.heartbeat_at is not None
    assert notification.lease_expires_at is not None
    notification.heartbeat_at = max(notification.heartbeat_at, heartbeat_at)
    notification.lease_expires_at = max(
        notification.lease_expires_at,
        heartbeat_at + checked_lease,
    )
    notification.save(update_fields=["heartbeat_at", "lease_expires_at", "updated_at"])
    return _outcome(notification)


@transaction.atomic
def mark_notification_handoff(
    claim: ClaimedSecurityNotification, *, now: datetime | None = None
) -> SecurityNotificationOutcome:
    handoff_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=handoff_at)
    if notification.delivery_phase == SecurityNotification.DeliveryPhase.HANDOFF:
        return _outcome(notification)
    notification.delivery_phase = SecurityNotification.DeliveryPhase.HANDOFF
    notification.handoff_at = handoff_at
    notification.save(update_fields=["delivery_phase", "handoff_at", "updated_at"])
    return _outcome(notification)


@transaction.atomic
def settle_notification_delivered(
    claim: ClaimedSecurityNotification, *, now: datetime | None = None
) -> SecurityNotificationOutcome:
    delivered_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=delivered_at)
    if notification.delivery_phase != SecurityNotification.DeliveryPhase.HANDOFF:
        raise NotificationClaimLost("notification was not handed to SMTP")
    notification.status = SecurityNotification.Status.DELIVERED
    notification.delivered_at = delivered_at
    notification.completed_at = delivered_at
    notification.last_error_code = ""
    _clear_claim(notification)
    notification.save(
        update_fields=[
            "status",
            "delivered_at",
            "completed_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    _audit_notification(
        action="account.security_notification.delivered",
        notification=notification,
        metadata={"attempt_count": notification.attempt_count},
    )
    return _outcome(notification)


@transaction.atomic
def settle_notification_preaccept_failure(
    claim: ClaimedSecurityNotification,
    *,
    error_code: str = "transport_unavailable",
    now: datetime | None = None,
    immediate_retry: bool = False,
) -> SecurityNotificationOutcome:
    settled_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=settled_at)
    if notification.delivery_phase != SecurityNotification.DeliveryPhase.PRE_HANDOFF:
        raise NotificationClaimLost("notification has crossed the SMTP handoff boundary")
    notification.failure_count += 1
    if notification.failure_count >= notification.max_attempts:
        _terminalize_review(
            notification,
            now=settled_at,
            error_code="attempts_exhausted",
        )
        return _outcome(notification)
    delay = (
        0
        if immediate_retry
        else min(
            INITIAL_RETRY_DELAY_SECONDS * (2 ** max(notification.failure_count - 1, 0)),
            MAX_RETRY_DELAY_SECONDS,
        )
    )
    notification.status = SecurityNotification.Status.RETRY_WAIT
    notification.available_at = settled_at + timedelta(seconds=delay)
    notification.completed_at = None
    notification.last_error_code = error_code
    _clear_claim(notification)
    notification.save(
        update_fields=[
            "status",
            "failure_count",
            "available_at",
            "completed_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return _outcome(notification)


@transaction.atomic
def settle_notification_delivery_uncertain(
    claim: ClaimedSecurityNotification,
    *,
    error_code: str = "smtp_outcome_ambiguous",
    now: datetime | None = None,
) -> SecurityNotificationOutcome:
    settled_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=settled_at)
    if notification.delivery_phase != SecurityNotification.DeliveryPhase.HANDOFF:
        raise NotificationClaimLost("notification did not cross the SMTP handoff boundary")
    _terminalize_uncertain(notification, now=settled_at, error_code=error_code)
    return _outcome(notification)


@transaction.atomic
def settle_notification_terminal_failure(
    claim: ClaimedSecurityNotification,
    *,
    error_code: str,
    now: datetime | None = None,
) -> SecurityNotificationOutcome:
    settled_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=settled_at)
    notification.failure_count += 1
    _terminalize_review(notification, now=settled_at, error_code=error_code)
    return _outcome(notification)


@transaction.atomic
def release_notification_claim(
    claim: ClaimedSecurityNotification, *, now: datetime | None = None
) -> SecurityNotificationOutcome:
    released_at = _checked_now(now)
    notification = _locked_notification(claim.notification_id)
    _assert_claim(notification, claim, now=released_at)
    if notification.delivery_phase != SecurityNotification.DeliveryPhase.PRE_HANDOFF:
        _terminalize_uncertain(
            notification,
            now=released_at,
            error_code="shutdown_after_handoff",
        )
        return _outcome(notification)
    notification.status = SecurityNotification.Status.RETRY_WAIT
    notification.available_at = released_at
    notification.last_error_code = "graceful_shutdown"
    _clear_claim(notification)
    notification.save(
        update_fields=[
            "status",
            "available_at",
            "last_error_code",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return _outcome(notification)


def _safe_render_context(notification: SecurityNotification, recipient: str) -> dict[str, object]:
    return {
        "user": notification.account,
        "timestamp": notification.created_at,
        "ip": "not retained",
        "user_agent": "not retained",
        "email": recipient,
        "from_email": "your previous verified address",
        "to_email": "your new verified address",
        "deleted_email": "a verified address",
        "current_site": SimpleNamespace(name="MNEMEX", domain="mnemex.invalid"),
    }


def render_security_notification(
    notification: SecurityNotification, *, recipient: str
) -> EmailMessage:
    from allauth.account import app_settings as account_app_settings
    from allauth.account.adapter import get_adapter

    adapter = get_adapter()
    context = _safe_render_context(notification, recipient)
    rendered_subject = render_to_string(
        f"{notification.template_identifier}_subject.txt",
        context,
    )
    subject = " ".join(rendered_subject.splitlines()).strip()
    subject_prefix = account_app_settings.EMAIL_SUBJECT_PREFIX
    subject = f"{subject_prefix if subject_prefix is not None else '[MNEMEX] '}{subject}"
    body = str(
        render_to_string(
            f"{notification.template_identifier}_message.txt",
            context,
        ).strip()
    )
    return EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=adapter.get_from_email(),
        to=[recipient],
        headers={"Message-ID": notification.message_id},
    )


def run_security_notifications_once(
    *,
    owner: str,
    limit: int = 1,
    should_stop: Callable[[], bool] | None = None,
    transport_factory: Callable[[], NotificationTransport] = DjangoNotificationTransport,
) -> NotificationWorkerBatchOutcome:
    """Claim and deliver one bounded batch; safe for the shared worker supervisor."""

    checked_limit = _checked_limit(
        limit,
        maximum=MAX_NOTIFICATIONS_PER_RUN,
        field="notification limit",
    )
    stop_requested = should_stop or (lambda: False)
    claimed = delivered = retry_scheduled = failed_review = 0
    delivery_uncertain = expired = claim_lost = 0
    for _ in range(checked_limit):
        if stop_requested():
            break
        attempt = _claim_next_notification_attempt(owner=owner)
        claim = attempt.claim
        if claim is None:
            if attempt.terminalized:
                continue
            break
        claimed += 1
        transport: NotificationTransport | None = None
        try:
            notification = SecurityNotification.objects.select_related("account").get(
                pk=claim.notification_id
            )
            try:
                recipient = decrypt_notification_recipient(notification)
            except (ImproperlyConfigured, ValueError):
                outcome = settle_notification_terminal_failure(
                    claim,
                    error_code="recipient_decryption_failed",
                )
            else:
                try:
                    message = render_security_notification(notification, recipient=recipient)
                except Exception:
                    outcome = settle_notification_terminal_failure(
                        claim,
                        error_code="template_render_failed",
                    )
                else:
                    if stop_requested():
                        outcome = release_notification_claim(claim)
                    else:
                        try:
                            transport = transport_factory()
                            transport.open()
                        except Exception:
                            outcome = settle_notification_preaccept_failure(
                                claim,
                                error_code="transport_unavailable",
                            )
                        else:
                            if stop_requested():
                                outcome = release_notification_claim(claim)
                            else:
                                mark_notification_handoff(claim)
                                try:
                                    accepted = transport.send(message)
                                except Exception:
                                    outcome = settle_notification_delivery_uncertain(claim)
                                else:
                                    if accepted:
                                        outcome = settle_notification_delivered(claim)
                                    else:
                                        outcome = settle_notification_delivery_uncertain(
                                            claim,
                                            error_code="smtp_acceptance_not_confirmed",
                                        )
        except NotificationClaimLost:
            claim_lost += 1
            continue
        finally:
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass
        if outcome.status == SecurityNotification.Status.DELIVERED:
            delivered += 1
        elif outcome.status == SecurityNotification.Status.RETRY_WAIT:
            retry_scheduled += 1
        elif outcome.status == SecurityNotification.Status.FAILED_REVIEW:
            failed_review += 1
        elif outcome.status == SecurityNotification.Status.DELIVERY_UNCERTAIN:
            delivery_uncertain += 1
        elif outcome.status == SecurityNotification.Status.EXPIRED:
            expired += 1
    return NotificationWorkerBatchOutcome(
        claimed=claimed,
        delivered=delivered,
        retry_scheduled=retry_scheduled,
        failed_review=failed_review,
        delivery_uncertain=delivery_uncertain,
        expired=expired,
        claim_lost=claim_lost,
    )


def notification_queue_metrics(*, now: datetime | None = None) -> NotificationQueueMetrics:
    measured_at = _checked_now(now)
    ready = SecurityNotification.objects.filter(
        status__in=(
            SecurityNotification.Status.PENDING,
            SecurityNotification.Status.RETRY_WAIT,
        ),
        available_at__lte=measured_at,
        recipient_purged_at__isnull=True,
        recipient_retention_deadline__gt=measured_at,
    )
    oldest = ready.order_by("available_at").values_list("available_at", flat=True).first()
    oldest_age = None
    if oldest is not None:
        oldest_age = max(0, int((measured_at - oldest).total_seconds()))
    return NotificationQueueMetrics(
        ready_depth=ready.count(),
        oldest_ready_age_seconds=oldest_age,
        running_depth=SecurityNotification.objects.filter(
            status=SecurityNotification.Status.RUNNING
        ).count(),
        retry_wait_depth=SecurityNotification.objects.filter(
            status=SecurityNotification.Status.RETRY_WAIT
        ).count(),
        failed_review_depth=SecurityNotification.objects.filter(
            status=SecurityNotification.Status.FAILED_REVIEW
        ).count(),
        delivery_uncertain_depth=SecurityNotification.objects.filter(
            status=SecurityNotification.Status.DELIVERY_UNCERTAIN
        ).count(),
    )
