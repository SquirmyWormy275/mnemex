from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from allauth.account.internal.flows.login import (
    AUTHENTICATION_METHODS_SESSION_KEY,
    record_authentication,
)
from allauth.mfa.models import Authenticator
from django.http import HttpRequest

from mnemex.accounts.models import Account


def record_mfa_authentication(
    request: HttpRequest,
    account: Account,
    authenticator: Authenticator,
    *,
    reauthenticated: bool,
) -> None:
    """Keep MNEMEX's dependency on allauth's staged-login internals isolated."""

    record_authentication(
        request,
        account,
        method="mfa",
        id=authenticator.pk,
        type=authenticator.type,
        reauthenticated=reauthenticated,
    )


def replace_session_mfa_authentication(
    session: MutableMapping[str, Any],
    authenticator: Authenticator,
    *,
    verified_at: float,
) -> None:
    """Install one synthetic MFA record for isolated contract tests."""

    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {
            "method": "mfa",
            "at": verified_at,
            "id": authenticator.pk,
            "type": authenticator.type,
        }
    ]


def clear_session_mfa_authentication(session: MutableMapping[str, Any]) -> None:
    """Invalidate every staged authentication record in this browser session."""

    session.pop(AUTHENTICATION_METHODS_SESSION_KEY, None)
