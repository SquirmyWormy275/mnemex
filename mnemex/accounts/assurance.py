from __future__ import annotations

import math
import time
from typing import cast

from allauth.account.authentication import get_authentication_records
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.http import HttpRequest

from mnemex.accounts.models import Account

SESSION_SECURITY_VERSION_KEY = "mnemex.security_version"
_MAX_FUTURE_SKEW_SECONDS = 60


def bind_security_version_to_session(request: HttpRequest, account: Account) -> None:
    request.session[SESSION_SECURITY_VERSION_KEY] = account.security_version


def has_fresh_mfa_session(
    request: HttpRequest,
    account: Account,
    *,
    now: float | None = None,
    max_age_seconds: int | None = None,
) -> bool:
    """Return whether this exact browser session has current MFA assurance."""

    age = mfa_session_age_seconds(request, account, now=now)
    max_age = int(
        settings.MNEMEX_PRIVILEGED_MFA_MAX_AGE_SECONDS
        if max_age_seconds is None
        else max_age_seconds
    )
    return age is not None and max_age > 0 and age < max_age


def mfa_session_age_seconds(
    request: HttpRequest,
    account: Account,
    *,
    now: float | None = None,
) -> float | None:
    """Return the age of a valid MFA proof after checking its full binding."""

    if not request.user.is_authenticated or request.user.pk != account.pk:
        return None
    current = account
    if (
        not current.is_active
        or current.email_verified_at is None
        or current.mfa_enrolled_at is None
    ):
        return None
    if request.session.get(SESSION_SECURITY_VERSION_KEY) != current.security_version:
        return None
    if not EmailAddress.objects.filter(
        user=current,
        email__iexact=current.email,
        verified=True,
    ).exists():
        return None
    authenticators = list(
        Authenticator.objects.filter(
            user=current,
            type__in=[Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES],
        ).values_list("pk", "type")
    )
    primary_ids = {pk for pk, kind in authenticators if kind == Authenticator.Type.TOTP}
    if not primary_ids:
        return None
    valid_authenticator_ids = {pk for pk, _kind in authenticators}
    current_time = time.time() if now is None else now
    for record in reversed(get_authentication_records(request)):
        if record.get("method") != "mfa" or record.get("id") not in valid_authenticator_ids:
            continue
        verified_at = record.get("at")
        if not isinstance(verified_at, (int, float)) or not math.isfinite(verified_at):
            return None
        age = current_time - float(verified_at)
        return age if age >= -_MAX_FUTURE_SKEW_SECONDS else None
    return None


def current_request_account(request: HttpRequest) -> Account | None:
    if not request.user.is_authenticated:
        return None
    return cast(Account, request.user)
