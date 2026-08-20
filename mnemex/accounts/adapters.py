from __future__ import annotations

import hashlib
import logging
from typing import Any

from allauth.account import app_settings as account_app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.models import Authenticator
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import HttpRequest, HttpResponse
from django.urls import reverse

from mnemex.accounts.keyring import KeyRingError, mfa_key_ring
from mnemex.accounts.models import Account
from mnemex.accounts.notifications import enqueue_allauth_security_notification
from mnemex.foundation.services import record_audit_event

logger = logging.getLogger(__name__)


def ensure_primary_email(account: Account) -> EmailAddress:
    """Synchronize the existing MNEMEX account verification timestamp."""

    verified = account.email_verified_at is not None
    canonical = account.email.strip().lower()
    address = EmailAddress.objects.filter(user=account, email__iexact=canonical).first()
    if address is None:
        address = EmailAddress.objects.create(
            user=account,
            email=canonical,
            primary=True,
            verified=verified,
        )
    else:
        address.email = canonical
        address.primary = True
        address.verified = verified
        address.save(update_fields=["email", "primary", "verified"])
    EmailAddress.objects.filter(user=account).exclude(pk=address.pk).update(primary=False)
    return address


class MnemexAccountAdapter(DefaultAccountAdapter):
    """Invite-only MNEMEX account policy layered over maintained flows."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False

    def pre_login(self, request: HttpRequest, user: Any, **kwargs: Any) -> HttpResponse | None:
        if isinstance(user, Account):
            ensure_primary_email(user)
        return super().pre_login(request, user, **kwargs)

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        user = request.user
        if (
            isinstance(user, Account)
            and user.privileged_roles.filter(revoked_at__isnull=True).exists()
        ):
            has_totp = Authenticator.objects.filter(
                user=user, type=Authenticator.Type.TOTP
            ).exists()
            if not has_totp:
                return reverse("mfa_activate_totp")
            return reverse("results:dashboard")
        if isinstance(user, Account):
            return reverse("mfa_index")
        return super().get_login_redirect_url(request)

    def get_reauthentication_methods(self, user: AbstractBaseUser) -> list[dict[str, Any]]:
        methods = super().get_reauthentication_methods(user)
        if not user.is_authenticated:
            return methods
        has_totp = Authenticator.objects.filter(
            user=user,
            type=Authenticator.Type.TOTP,
        ).exists()
        if not has_totp:
            return methods
        return [method for method in methods if method["id"] == "mfa_reauthenticate"]

    def send_notification_mail(
        self,
        template_prefix: str,
        user: AbstractBaseUser,
        context: dict[str, Any] | None = None,
        email: str | None = None,
    ) -> None:
        if not account_app_settings.EMAIL_NOTIFICATIONS:
            return
        if not isinstance(user, Account):
            raise ValidationError("security notification account is invalid")
        try:
            enqueue_allauth_security_notification(
                account=user,
                template_identifier=template_prefix,
                requested_recipient=email,
                notification_context=context,
            )
        except ValidationError:
            raise
        except Exception as error:  # Notification delivery must not split security state.
            digest = hashlib.sha256(
                f"account.security_notification.failed:{user.pk}:{template_prefix}".encode()
            ).hexdigest()
            try:
                record_audit_event(
                    action="account.security_notification.failed",
                    target_type="account",
                    target_id=str(user.pk),
                    payload_digest=digest,
                    metadata={
                        "template": template_prefix,
                        "error_type": type(error).__name__,
                    },
                    actor_id=user.pk,
                )
            except Exception as audit_error:
                logger.error(
                    "account.security_notification.audit_unavailable",
                    extra={
                        "queue_error_type": type(error).__name__,
                        "audit_error_type": type(audit_error).__name__,
                    },
                )


class MnemexMFAAdapter(DefaultMFAAdapter):
    """Encrypt allauth TOTP and recovery material with versioned AES-GCM."""

    def encrypt(self, text: str) -> str:
        return mfa_key_ring().encrypt_text(text)

    def decrypt(self, encrypted_text: str) -> str:
        try:
            return mfa_key_ring().decrypt_text(encrypted_text).plaintext
        except (ImproperlyConfigured, KeyRingError) as error:
            raise ValueError("MFA secret could not be decrypted") from error
