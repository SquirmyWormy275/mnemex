from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, register


def _error(message: str, code: int) -> Error:
    return Error(message, id=f"mnemex.E{code:03d}")


@register(deploy=True)
def check_hosted_configuration(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Return stable, non-secret diagnostics for hosted security invariants."""
    if not getattr(settings, "MNEMEX_HOSTED_CONFIGURATION", False):
        return []

    errors: list[Error] = []
    cache_settings = getattr(settings, "CACHES", {})
    rate_limit = cache_settings.get("default", {})
    security = cache_settings.get("security", {})
    redis_backend = "django.core.cache.backends.redis.RedisCache"
    if rate_limit.get("BACKEND") != redis_backend:
        errors.append(_error("Hosted rate-limit cache is not shared Redis.", 1))
    if security.get("BACKEND") != redis_backend:
        errors.append(_error("Hosted security cache is not shared Redis.", 2))
    if not rate_limit.get("KEY_PREFIX") or rate_limit.get("KEY_PREFIX") == security.get(
        "KEY_PREFIX"
    ):
        errors.append(_error("Hosted cache namespaces are not distinct.", 3))
    if getattr(settings, "MNEMEX_SECURITY_CACHE_ALIAS", None) != "security":
        errors.append(_error("Security cache alias is not pinned.", 4))
    if getattr(settings, "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED", True):
        errors.append(_error("Production privileged authorization is not hard-disabled.", 5))
    if getattr(settings, "ALLAUTH_TRUSTED_CLIENT_IP_HEADER", None) is not None:
        errors.append(_error("A direct client-IP header is trusted.", 6))
    if getattr(settings, "EMAIL_BACKEND", "") != "django.core.mail.backends.smtp.EmailBackend":
        errors.append(_error("Hosted security mail is not configured for SMTP.", 7))
    for keys_name, active_name, code in (
        ("MNEMEX_MFA_ENCRYPTION_KEYS", "MNEMEX_MFA_ACTIVE_KEY_VERSION", 8),
        (
            "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS",
            "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION",
            9,
        ),
    ):
        keys = getattr(settings, keys_name, {})
        active = getattr(settings, active_name, None)
        if not isinstance(keys, dict) or active not in keys:
            errors.append(_error("A hosted encryption key ring is incomplete.", code))
    if getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BACKEND", None) != "supabase":
        errors.append(_error("Hosted private artifact storage is not selected.", 10))
    if getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC", True) is not False:
        errors.append(_error("Hosted artifact bucket is not explicitly private.", 11))
    if not getattr(settings, "MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED", False):
        errors.append(_error("Hosted privileged action tickets are not required.", 12))
    return errors
