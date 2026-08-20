from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.utils.crypto import salted_hmac

from mnemex.accounts.assurance import current_request_account, has_fresh_mfa_session
from mnemex.accounts.models import Account

_TICKET_SALT = "mnemex.accounts.privileged-action.v1"
_SESSION_SALT = "mnemex.accounts.privileged-action.session.v1"
_GENERIC_DENIAL = "action assurance is unavailable"


@dataclass(frozen=True)
class ClaimedActionTicket:
    account_id: UUID
    target_path: str
    target_method: str


def _security_cache() -> BaseCache:
    try:
        return caches["security"]
    except Exception as error:
        raise PermissionDenied(_GENERIC_DENIAL) from error


def _ticket_ttl() -> int:
    value = getattr(settings, "MNEMEX_ACTION_TICKET_TTL_SECONDS", 90)
    if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 300:
        raise PermissionDenied(_GENERIC_DENIAL)
    return value


def _target_path(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 500:
        raise PermissionDenied(_GENERIC_DENIAL)
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise PermissionDenied(_GENERIC_DENIAL)
    if any(ord(character) < 32 for character in value):
        raise PermissionDenied(_GENERIC_DENIAL)
    return parsed.path


def _target_method(value: str) -> str:
    normalized = value.upper() if isinstance(value, str) else ""
    if normalized not in {"POST", "PUT", "PATCH", "DELETE"}:
        raise PermissionDenied(_GENERIC_DENIAL)
    return normalized


def _origin(request: HttpRequest) -> str:
    host = request.get_host().strip().lower()
    scheme = request.scheme.lower() if isinstance(request.scheme, str) else ""
    if (
        scheme not in {"http", "https"}
        or not host
        or any(character in host for character in "\r\n/")
    ):
        raise PermissionDenied(_GENERIC_DENIAL)
    return f"{scheme}://{host}"


def _session_fingerprint(request: HttpRequest) -> str:
    session_key = request.session.session_key
    if not isinstance(session_key, str) or not session_key:
        raise PermissionDenied(_GENERIC_DENIAL)
    return salted_hmac(_SESSION_SALT, session_key, algorithm="sha256").hexdigest()


def issue_action_ticket(
    request: HttpRequest,
    *,
    target_path: str,
    target_method: str,
) -> str:
    """Issue a short-lived route-bound ticket after current MFA assurance."""

    account = current_request_account(request)
    if account is None or not has_fresh_mfa_session(
        request,
        account,
        max_age_seconds=getattr(settings, "MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS", 300),
    ):
        raise PermissionDenied("fresh MFA is required")
    payload = {
        "account_id": str(account.pk),
        "security_version": account.security_version,
        "session": _session_fingerprint(request),
        "origin": _origin(request),
        "target_path": _target_path(target_path),
        "target_method": _target_method(target_method),
        "nonce": secrets.token_urlsafe(18),
    }
    return signing.dumps(payload, salt=_TICKET_SALT, compress=False)


def claim_action_ticket(request: HttpRequest, *, token: str) -> ClaimedActionTicket:
    """Validate and atomically consume one privileged-action ticket."""

    if not isinstance(token, str) or not token or len(token) > 4096:
        raise PermissionDenied(_GENERIC_DENIAL)
    try:
        payload = signing.loads(token, salt=_TICKET_SALT, max_age=_ticket_ttl())
        if not isinstance(payload, dict):
            raise ValueError
        account_id = UUID(str(payload["account_id"]))
        account = Account.objects.get(pk=account_id, is_active=True)
        request_account = current_request_account(request)
        if request_account is None or request_account.pk != account.pk:
            raise ValueError
        if payload.get("security_version") != account.security_version:
            raise ValueError
        if payload.get("session") != _session_fingerprint(request):
            raise ValueError
        if payload.get("origin") != _origin(request):
            raise ValueError
        target_path = _target_path(str(payload["target_path"]))
        target_method = _target_method(str(payload["target_method"]))
        request_method = request.method.upper() if isinstance(request.method, str) else ""
        if request.path != target_path or request_method != target_method:
            raise ValueError
        claim_key = f"mnemex:action-ticket:claimed:{hashlib.sha256(token.encode()).hexdigest()}"
        if _security_cache().add(claim_key, "claimed", timeout=_ticket_ttl()) is not True:
            raise ValueError
    except (KeyError, TypeError, ValueError, signing.BadSignature, Account.DoesNotExist) as error:
        raise PermissionDenied(_GENERIC_DENIAL) from error
    except PermissionDenied:
        raise
    except Exception as error:
        raise PermissionDenied(_GENERIC_DENIAL) from error
    return ClaimedActionTicket(
        account_id=account_id,
        target_path=target_path,
        target_method=target_method,
    )
