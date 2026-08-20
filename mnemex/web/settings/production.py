from __future__ import annotations

import os
import re
from email.utils import parseaddr
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.core.validators import validate_email

from mnemex.accounts.keyring import parse_key_ring_json
from mnemex.web.database import database_config_from_url
from mnemex.web.settings import base as base_settings
from mnemex.web.settings.base import *  # noqa: F403

MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED = True
_BASE_MIDDLEWARE = base_settings.MIDDLEWARE
MIDDLEWARE = [
    _BASE_MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *_BASE_MIDDLEWARE[1:],
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

_PLACEHOLDER_SECRETS = {
    "changeme",
    "change-me",
    "password",
    "secret",
    "replace-me",
}
_BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required")
    return value


def _required_secret(name: str, *, minimum_length: int = 24) -> str:
    value = _required(name)
    if len(value) < minimum_length or value.lower() in _PLACEHOLDER_SECRETS or len(set(value)) < 8:
        raise ImproperlyConfigured(f"{name} must be a non-placeholder secret")
    return value


def _required_integer(name: str, *, minimum: int, maximum: int) -> int:
    raw = _required(name)
    try:
        value = int(raw)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ImproperlyConfigured(f"{name} is outside the supported range")
    return value


def _https_url(name: str) -> str:
    value = _required(name)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ImproperlyConfigured(f"{name} must be an HTTPS origin without credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ImproperlyConfigured(f"{name} must be an HTTPS origin without a path")
    return value.rstrip("/")


def _shared_cache_url() -> str:
    value = _required("MNEMEX_CACHE_URL")
    parsed = urlsplit(value)
    if parsed.scheme != "rediss":
        raise ImproperlyConfigured("MNEMEX_CACHE_URL must use Redis TLS (rediss)")
    if not parsed.hostname:
        raise ImproperlyConfigured("MNEMEX_CACHE_URL must include a host")
    if not parsed.password:
        raise ImproperlyConfigured("MNEMEX_CACHE_URL must include a password")
    if len(parsed.password) < 16 or parsed.password.lower() in _PLACEHOLDER_SECRETS:
        raise ImproperlyConfigured("MNEMEX_CACHE_URL must include a non-placeholder password")
    if parsed.query or parsed.fragment:
        raise ImproperlyConfigured("MNEMEX_CACHE_URL must not include a query or fragment")
    return value


def _versioned_key_ring(
    name: str,
    active_name: str,
    *,
    label: str,
) -> tuple[dict[int, bytes], int]:
    active_version = _required_integer(active_name, minimum=1, maximum=2**31 - 1)
    ring = parse_key_ring_json(
        _required(name),
        active_version=active_version,
        label=label,
    )
    return dict(ring.keys), ring.active_version


SECRET_KEY = _required_secret("DJANGO_SECRET_KEY", minimum_length=32)
DATABASES = {"default": database_config_from_url(_required("DATABASE_URL"))}
_database_sslmode = str(DATABASES["default"].get("OPTIONS", {}).get("sslmode", "")).lower()
if _database_sslmode not in {"require", "verify-ca", "verify-full"}:
    raise ImproperlyConfigured(
        "production DATABASE_URL must set sslmode=require, verify-ca, or verify-full"
    )

_cache_url = _shared_cache_url()
_cache_options = {
    "socket_connect_timeout": 3,
    "socket_timeout": 3,
    "ssl_cert_reqs": "required",
}
CACHES = {
    # django-allauth deliberately uses the default alias for its best-effort
    # application throttles. Keep that namespace distinct from atomic claims.
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _cache_url,
        "KEY_PREFIX": "mnemex:rate-limits",
        "TIMEOUT": 300,
        "OPTIONS": dict(_cache_options),
    },
    "security": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _cache_url,
        "KEY_PREFIX": "mnemex:security",
        "TIMEOUT": 300,
        "OPTIONS": dict(_cache_options),
    },
}
MNEMEX_SECURITY_CACHE_ALIAS = "security"

# A direct client-IP header bypasses proxy-chain validation in allauth. MNEMEX
# does not trust one until a future deployment-specific review adds a guarded
# policy. X-Forwarded-For is considered only through the explicit proxy count.
if os.environ.get("ALLAUTH_TRUSTED_CLIENT_IP_HEADER", "").strip():
    raise ImproperlyConfigured(
        "ALLAUTH_TRUSTED_CLIENT_IP_HEADER is not permitted without a reviewed proxy policy"
    )
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = None
ALLAUTH_TRUSTED_PROXY_COUNT = _required_integer(
    "ALLAUTH_TRUSTED_PROXY_COUNT", minimum=0, maximum=10
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = _required("EMAIL_HOST")
if "://" in EMAIL_HOST:
    raise ImproperlyConfigured("EMAIL_HOST must be a hostname, not a URL")
EMAIL_PORT = _required_integer("EMAIL_PORT", minimum=1, maximum=65535)
EMAIL_HOST_USER = _required("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = _required_secret("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = _required("DEFAULT_FROM_EMAIL")
_sender_address = parseaddr(DEFAULT_FROM_EMAIL)[1]
try:
    validate_email(_sender_address)
except Exception as error:
    raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must contain a valid email address") from error

MNEMEX_MFA_ENCRYPTION_KEYS, MNEMEX_MFA_ACTIVE_KEY_VERSION = _versioned_key_ring(
    "MNEMEX_MFA_ENCRYPTION_KEYS",
    "MNEMEX_MFA_ACTIVE_KEY_VERSION",
    label="MFA",
)
(
    MNEMEX_NOTIFICATION_ENCRYPTION_KEYS,
    MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION,
) = _versioned_key_ring(
    "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS",
    "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION",
    label="notification",
)

MNEMEX_SUPABASE_URL = _https_url("MNEMEX_SUPABASE_URL")
MNEMEX_SUPABASE_SERVICE_ROLE_KEY = _required_secret("MNEMEX_SUPABASE_SERVICE_ROLE_KEY")
MNEMEX_PRIVATE_ARTIFACT_BUCKET = _required("MNEMEX_PRIVATE_ARTIFACT_BUCKET")
if not _BUCKET_RE.fullmatch(MNEMEX_PRIVATE_ARTIFACT_BUCKET):
    raise ImproperlyConfigured(
        "MNEMEX_PRIVATE_ARTIFACT_BUCKET must be a lowercase private bucket name"
    )
MNEMEX_PRIVATE_ARTIFACT_BACKEND = "supabase"
MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC = False
MNEMEX_HOSTED_CONFIGURATION = True

# Production privileged operations remain deliberately unavailable. Nothing in
# environment configuration or an activation report can override this constant.
MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = False
ALLOWED_HOSTS = [
    host.strip() for host in _required("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()
]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit hosts")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
for origin in CSRF_TRUSTED_ORIGINS:
    parsed_origin = urlsplit(origin)
    if parsed_origin.scheme != "https" or not parsed_origin.hostname:
        raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain HTTPS origins")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = (
    _required_integer("DJANGO_SECURE_HSTS_SECONDS", minimum=3600, maximum=63072000)
    if os.environ.get("DJANGO_SECURE_HSTS_SECONDS")
    else 3600
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
