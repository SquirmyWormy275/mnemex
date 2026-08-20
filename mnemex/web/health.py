from __future__ import annotations

import secrets

from django.conf import settings
from django.core.cache import caches
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


def _check_database() -> None:
    """Raise when the primary database cannot serve a trivial query."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_cache() -> None:
    """Raise when the shared security cache cannot round-trip an opaque value."""
    cache = caches[settings.MNEMEX_SECURITY_CACHE_ALIAS]
    nonce = secrets.token_urlsafe(18)
    key = f"readiness:{nonce}"
    try:
        stored = cache.add(key, nonce, timeout=10)
        if stored is not True or cache.get(key) != nonce:
            raise RuntimeError("shared cache round trip failed")
    finally:
        # Deletion is best effort: the short TTL bounds residue if the backend
        # became unavailable after the read.
        try:
            cache.delete(key)
        except Exception:
            pass


def _check_key_versions() -> None:
    """Reject readiness when durable ciphertext needs an unavailable key."""

    from mnemex.accounts.key_rotation import assert_configured_key_versions_available

    assert_configured_key_versions_available(purpose="mfa")
    assert_configured_key_versions_available(purpose="notification")


@require_GET
def live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request: HttpRequest) -> JsonResponse:
    try:
        _check_database()
        _check_cache()
        _check_key_versions()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok", "cache": "ok"})
