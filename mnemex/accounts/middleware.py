from __future__ import annotations

from collections.abc import Callable
from typing import Any

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.http import urlencode

from mnemex.accounts.assurance import has_fresh_mfa_session
from mnemex.accounts.models import Account

_MFA_PROTECTED_MUTATIONS = {
    "account_change_password",
    "account_set_password",
    "account_email",
    "mfa_deactivate_totp",
    "mfa_generate_recovery_codes",
    "mfa_view_recovery_codes",
    "mfa_download_recovery_codes",
}


class PrivilegedAccountSecurityMiddleware:
    """Require the existing factor before any enrolled account changes security."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        _view_func: Callable[..., HttpResponse],
        _view_args: list[Any],
        _view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        match = request.resolver_match
        if match is None or match.url_name not in _MFA_PROTECTED_MUTATIONS:
            return None
        if match.url_name == "account_email" and request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        user = request.user
        if not isinstance(user, Account) or not user.is_authenticated:
            return None
        if not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
            return None
        if not has_fresh_mfa_session(
            request,
            user,
            max_age_seconds=settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS,
        ):
            target = reverse("mfa_reauthenticate")
            return HttpResponseRedirect(f"{target}?{urlencode({'next': request.get_full_path()})}")
        return None
