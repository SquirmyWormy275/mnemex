from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from mnemex.accounts.action_assurance import claim_action_ticket
from mnemex.accounts.assurance import current_request_account, mfa_session_age_seconds

View = TypeVar("View", bound=Callable[..., HttpResponse])


def _next_url(url_name: str, request: HttpRequest) -> str:
    return f"{reverse(url_name)}?{urlencode({'next': request.get_full_path()})}"


def privileged_session_required(view: View) -> View:
    @login_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not getattr(settings, "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED", False):
            raise PermissionDenied("privileged authorization is disabled")
        account = current_request_account(request)
        if account is None or not account.is_active:
            raise PermissionDenied("an active account is required")
        if not account.privileged_roles.filter(revoked_at__isnull=True).exists():
            raise PermissionDenied("an active privileged role is required")
        if account.email_verified_at is None:
            return redirect(_next_url("account_email_verification_sent", request))
        has_totp = Authenticator.objects.filter(user=account, type=Authenticator.Type.TOTP).exists()
        if not has_totp:
            return redirect(_next_url("mfa_activate_totp", request))
        action_assured = False
        if request.method not in {"GET", "HEAD", "OPTIONS"} and getattr(
            settings, "MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED", False
        ):
            claim_action_ticket(
                request,
                token=request.headers.get("X-MNEMEX-Action-Ticket", ""),
            )
            action_assured = True
        if not action_assured:
            proof_age = mfa_session_age_seconds(request, account)
            if proof_age is None or proof_age >= int(
                settings.MNEMEX_PRIVILEGED_MFA_MAX_AGE_SECONDS
            ):
                return redirect(_next_url("mfa_reauthenticate", request))
            if request.method not in {"GET", "HEAD", "OPTIONS"} and proof_age >= int(
                settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS
            ):
                return redirect(_next_url("mfa_reauthenticate", request))
        return view(request, *args, **kwargs)

    return cast(View, wrapped)
