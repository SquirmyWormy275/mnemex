from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from allauth.account.models import EmailAddress
from allauth.account.signals import (
    email_added,
    email_changed,
    email_confirmed,
    email_removed,
    password_changed,
    password_reset,
    password_set,
    user_logged_in,
)
from allauth.mfa.models import Authenticator
from allauth.mfa.signals import (
    authentication_failed,
    authenticator_added,
    authenticator_removed,
    authenticator_reset,
    authenticator_used,
)
from django.contrib.auth import update_session_auth_hash
from django.db.models import F
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils import timezone

from mnemex.accounts.adapters import ensure_primary_email
from mnemex.accounts.allauth_bridge import (
    clear_session_mfa_authentication,
    record_mfa_authentication,
)
from mnemex.accounts.assurance import bind_security_version_to_session
from mnemex.accounts.models import Account
from mnemex.foundation.services import record_audit_event


def _digest(action: str, account: Account, target_id: str) -> str:
    payload = f"{action}:{account.pk}:{target_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _audit(
    *,
    action: str,
    account: Account,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_audit_event(
        action=action,
        target_type="account_authenticator",
        target_id=target_id,
        payload_digest=_digest(action, account, target_id),
        metadata=metadata or {},
        actor_id=account.pk,
    )


def _bump_security_version(
    request: HttpRequest,
    account: Account,
    *,
    update_mfa_enrolled_at: bool = False,
    mfa_enrolled_at: datetime | None = None,
    preserve_current_session: bool = True,
    clear_mfa_proof: bool = False,
) -> Account:
    updates: dict[str, Any] = {"security_version": F("security_version") + 1}
    if update_mfa_enrolled_at:
        updates["mfa_enrolled_at"] = mfa_enrolled_at
    Account.objects.filter(pk=account.pk).update(**updates)
    account.refresh_from_db(fields=["password", "security_version", "mfa_enrolled_at"])
    if clear_mfa_proof:
        clear_session_mfa_authentication(request.session)
    if preserve_current_session and getattr(request.user, "pk", None) == account.pk:
        update_session_auth_hash(request, account)
        bind_security_version_to_session(request, account)
    return account


@receiver(user_logged_in)
def on_user_logged_in(request: HttpRequest, user: Account, **_kwargs: Any) -> None:
    if not isinstance(user, Account):
        return
    ensure_primary_email(user)
    bind_security_version_to_session(request, user)


@receiver(email_confirmed)
def on_email_confirmed(
    request: HttpRequest,
    email_address: EmailAddress,
    **_kwargs: Any,
) -> None:
    account = email_address.user
    if not isinstance(account, Account):
        return
    if email_address.email.lower() != account.email.lower():
        return
    Account.objects.filter(pk=account.pk).update(email_verified_at=timezone.now())
    account.refresh_from_db(fields=["email_verified_at"])
    _audit(
        action="account.email.verified",
        account=account,
        target_id=str(email_address.pk),
        metadata={"method": "verified_email"},
    )


def _record_email_security_change(
    request: HttpRequest,
    account: Account,
    *,
    action: str,
    target_id: str,
) -> None:
    _bump_security_version(request, account, clear_mfa_proof=True)
    _audit(
        action=action,
        account=account,
        target_id=target_id,
        metadata={"method": "verified_email"},
    )


@receiver(email_added)
def on_email_added(
    request: HttpRequest,
    user: Account,
    email_address: EmailAddress,
    **_kwargs: Any,
) -> None:
    if isinstance(user, Account):
        _record_email_security_change(
            request,
            user,
            action="account.email.added",
            target_id=str(email_address.pk),
        )


@receiver(email_changed)
def on_email_changed(
    request: HttpRequest,
    user: Account,
    to_email_address: EmailAddress,
    **_kwargs: Any,
) -> None:
    if not isinstance(user, Account):
        return
    Account.objects.filter(pk=user.pk).update(
        email=to_email_address.email.strip().lower(),
        email_verified_at=timezone.now() if to_email_address.verified else None,
    )
    user.refresh_from_db(fields=["email", "email_verified_at"])
    _record_email_security_change(
        request,
        user,
        action="account.email.changed",
        target_id=str(to_email_address.pk),
    )


@receiver(email_removed)
def on_email_removed(
    request: HttpRequest,
    user: Account,
    email_address: EmailAddress,
    **_kwargs: Any,
) -> None:
    if isinstance(user, Account):
        _record_email_security_change(
            request,
            user,
            action="account.email.removed",
            target_id=str(email_address.pk),
        )


@receiver(authenticator_added)
def on_authenticator_added(
    request: HttpRequest,
    user: Account,
    authenticator: Authenticator,
    **_kwargs: Any,
) -> None:
    if not isinstance(user, Account):
        return
    if authenticator.type == Authenticator.Type.TOTP:
        record_mfa_authentication(
            request,
            user,
            authenticator,
            reauthenticated=True,
        )
        _bump_security_version(
            request,
            user,
            update_mfa_enrolled_at=True,
            mfa_enrolled_at=timezone.now(),
        )
    _audit(
        action="account.mfa.authenticator_added",
        account=user,
        target_id=str(authenticator.pk),
        metadata={"authenticator_type": authenticator.type},
    )


@receiver(authenticator_removed)
def on_authenticator_removed(
    request: HttpRequest,
    user: Account,
    authenticator: Authenticator,
    **_kwargs: Any,
) -> None:
    if not isinstance(user, Account):
        return
    if authenticator.type == Authenticator.Type.TOTP:
        has_primary = Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()
        _bump_security_version(
            request,
            user,
            update_mfa_enrolled_at=True,
            mfa_enrolled_at=user.mfa_enrolled_at if has_primary else None,
            clear_mfa_proof=True,
        )
    else:
        _bump_security_version(request, user, clear_mfa_proof=True)
    _audit(
        action="account.mfa.authenticator_removed",
        account=user,
        target_id=str(authenticator.pk),
        metadata={"authenticator_type": authenticator.type},
    )


@receiver(authenticator_reset)
def on_authenticator_reset(
    request: HttpRequest,
    user: Account,
    authenticator: Authenticator,
    **_kwargs: Any,
) -> None:
    if not isinstance(user, Account):
        return
    _bump_security_version(request, user, clear_mfa_proof=True)
    _audit(
        action="account.mfa.authenticator_reset",
        account=user,
        target_id=str(authenticator.pk),
        metadata={"authenticator_type": authenticator.type},
    )


@receiver(authenticator_used)
def on_authenticator_used(
    request: HttpRequest,
    user: Account,
    authenticator: Authenticator,
    reauthenticated: bool,
    passwordless: bool,
    **_kwargs: Any,
) -> None:
    if not isinstance(user, Account):
        return
    request.session.cycle_key()
    _audit(
        action="account.mfa.authenticator_used",
        account=user,
        target_id=str(authenticator.pk),
        metadata={
            "authenticator_type": authenticator.type,
            "reauthenticated": bool(reauthenticated),
            "passwordless": bool(passwordless),
        },
    )


@receiver(authentication_failed)
def on_authentication_failed(
    request: HttpRequest,
    user: Account,
    authenticator: Authenticator,
    **_kwargs: Any,
) -> None:
    if isinstance(user, Account):
        _audit(
            action="account.mfa.authentication_failed",
            account=user,
            target_id=str(authenticator.pk),
            metadata={"authenticator_type": authenticator.type},
        )


def _password_security_change(request: HttpRequest, user: Account, action: str) -> None:
    if not isinstance(user, Account):
        return
    _bump_security_version(
        request,
        user,
        preserve_current_session=False,
        clear_mfa_proof=True,
    )
    _audit(action=action, account=user, target_id=str(user.pk), metadata={"method": "password"})


@receiver(password_changed)
def on_password_changed(request: HttpRequest, user: Account, **_kwargs: Any) -> None:
    _password_security_change(request, user, "account.password.changed")


@receiver(password_reset)
def on_password_reset(request: HttpRequest, user: Account, **_kwargs: Any) -> None:
    _password_security_change(request, user, "account.password.reset")


@receiver(password_set)
def on_password_set(request: HttpRequest, user: Account, **_kwargs: Any) -> None:
    _password_security_change(request, user, "account.password.set")
