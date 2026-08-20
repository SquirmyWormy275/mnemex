from __future__ import annotations

import base64
import importlib
import json
from types import ModuleType

import pytest
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings

_PRODUCTION_ENVIRONMENT = {
    "DJANGO_SECRET_KEY": "synthetic-production-settings-secret",
    "DJANGO_ALLOWED_HOSTS": "mnemex.example.invalid",
    "DATABASE_URL": "postgresql://mnemex:synthetic@db.example.invalid:5432/mnemex?sslmode=require",
    "MNEMEX_CACHE_URL": "rediss://default:synthetic-cache-password@cache.example.invalid:6380/0",
    "ALLAUTH_TRUSTED_PROXY_COUNT": "0",
    "EMAIL_HOST": "smtp.example.invalid",
    "EMAIL_PORT": "587",
    "EMAIL_HOST_USER": "synthetic-mail-user",
    "EMAIL_HOST_PASSWORD": "synthetic-mail-password-with-32-chars",
    "DEFAULT_FROM_EMAIL": "MNEMEX Security <security@mnemex.example.invalid>",
    "MNEMEX_MFA_ENCRYPTION_KEYS": json.dumps(
        {"1": base64.b64encode(bytes(range(32))).decode("ascii")}
    ),
    "MNEMEX_MFA_ACTIVE_KEY_VERSION": "1",
    "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS": json.dumps(
        {"1": base64.b64encode(bytes(range(32, 64))).decode("ascii")}
    ),
    "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION": "1",
    "MNEMEX_SUPABASE_URL": "https://synthetic-project.supabase.co",
    "MNEMEX_SUPABASE_SERVICE_ROLE_KEY": "synthetic-service-role-key-with-32-chars",
    "MNEMEX_PRIVATE_ARTIFACT_BUCKET": "mnemex-private-artifacts",
}


def _reload_production(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str | None] | None = None
) -> ModuleType:
    for name, value in _PRODUCTION_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ALLAUTH_TRUSTED_CLIENT_IP_HEADER", raising=False)
    for name, value in (overrides or {}).items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    from mnemex.web.settings import production

    return importlib.reload(production)


@pytest.mark.parametrize(
    "name",
    [
        "MNEMEX_CACHE_URL",
        "ALLAUTH_TRUSTED_PROXY_COUNT",
        "EMAIL_HOST",
        "EMAIL_HOST_PASSWORD",
        "DEFAULT_FROM_EMAIL",
        "MNEMEX_MFA_ENCRYPTION_KEYS",
        "MNEMEX_MFA_ACTIVE_KEY_VERSION",
        "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS",
        "MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION",
        "MNEMEX_SUPABASE_URL",
        "MNEMEX_SUPABASE_SERVICE_ROLE_KEY",
        "MNEMEX_PRIVATE_ARTIFACT_BUCKET",
    ],
)
def test_production_rejects_missing_hosted_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    with pytest.raises(ImproperlyConfigured, match=name):
        _reload_production(monkeypatch, {name: None})


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MNEMEX_CACHE_URL", "redis://cache.example.invalid:6379/0", "TLS"),
        ("MNEMEX_CACHE_URL", "rediss://cache.example.invalid:6380/0", "password"),
        ("MNEMEX_CACHE_URL", "rediss://default:changeme@cache.example.invalid:6380/0", "password"),
        (
            "MNEMEX_CACHE_URL",
            "rediss://default:synthetic-cache-password@cache.example.invalid:6380/0?ssl_cert_reqs=none",
            "query",
        ),
        ("MNEMEX_SUPABASE_URL", "http://project.supabase.co", "HTTPS"),
        ("EMAIL_PORT", "not-a-port", "EMAIL_PORT"),
        ("ALLAUTH_TRUSTED_PROXY_COUNT", "-1", "ALLAUTH_TRUSTED_PROXY_COUNT"),
        ("DJANGO_SECRET_KEY", "changeme", "DJANGO_SECRET_KEY"),
        (
            "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS",
            json.dumps({"1": base64.b64encode(b"n" * 32).decode("ascii")}),
            "placeholder",
        ),
    ],
)
def test_production_rejects_malformed_or_placeholder_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    with pytest.raises(ImproperlyConfigured, match=message):
        _reload_production(monkeypatch, {name: value})


def test_production_rejects_unknown_active_mfa_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ImproperlyConfigured, match="active MFA encryption key"):
        _reload_production(monkeypatch, {"MNEMEX_MFA_ACTIVE_KEY_VERSION": "2"})


def test_production_rejects_unknown_active_notification_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ImproperlyConfigured, match="active notification encryption key"):
        _reload_production(
            monkeypatch,
            {"MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION": "2"},
        )


def test_production_rejects_duplicate_raw_key_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded_first = base64.b64encode(bytes(range(32))).decode("ascii")
    encoded_second = base64.b64encode(bytes(range(64, 96))).decode("ascii")
    duplicate_json = f'{{"1":"{encoded_first}","1":"{encoded_second}"}}'

    with pytest.raises(ImproperlyConfigured, match="duplicate key version"):
        _reload_production(
            monkeypatch,
            {"MNEMEX_MFA_ENCRYPTION_KEYS": duplicate_json},
        )


def test_production_rejects_direct_client_ip_header_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ImproperlyConfigured, match="ALLAUTH_TRUSTED_CLIENT_IP_HEADER"):
        _reload_production(
            monkeypatch,
            {"ALLAUTH_TRUSTED_CLIENT_IP_HEADER": "X-Forwarded-For"},
        )


def test_production_configures_separate_shared_cache_namespaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = _reload_production(monkeypatch)

    assert production.CACHES["default"]["BACKEND"] == (
        "django.core.cache.backends.redis.RedisCache"
    )
    assert production.CACHES["security"]["BACKEND"] == (
        "django.core.cache.backends.redis.RedisCache"
    )
    assert production.CACHES["default"]["LOCATION"] == production.CACHES["security"]["LOCATION"]
    assert production.CACHES["default"]["KEY_PREFIX"] != production.CACHES["security"]["KEY_PREFIX"]
    assert production.MNEMEX_SECURITY_CACHE_ALIAS == "security"
    assert production.CACHES["security"]["OPTIONS"]["ssl_cert_reqs"] == "required"
    assert production.DATABASES["default"]["OPTIONS"]["connect_timeout"] == 5
    assert production.ALLAUTH_TRUSTED_PROXY_COUNT == 0
    assert production.ALLAUTH_TRUSTED_CLIENT_IP_HEADER is None
    assert production.MNEMEX_MFA_ENCRYPTION_KEYS == {1: bytes(range(32))}
    assert production.MNEMEX_MFA_ACTIVE_KEY_VERSION == 1
    assert production.MNEMEX_NOTIFICATION_ENCRYPTION_KEYS == {1: bytes(range(32, 64))}
    assert production.MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION == 1
    assert production.MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC is False
    assert production.MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED is False
    assert production.MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED is True
    assert production.MIDDLEWARE[1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert production.STORAGES["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )


def test_hosted_configuration_checks_use_stable_non_secret_diagnostics() -> None:
    from mnemex.web.checks import check_hosted_configuration

    secret = "must-not-appear-in-diagnostics"
    with override_settings(
        MNEMEX_HOSTED_CONFIGURATION=True,
        MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=True,
        CACHES={"default": {}, "security": {}},
        EMAIL_HOST_PASSWORD=secret,
    ):
        diagnostics = check_hosted_configuration(None)

    assert diagnostics
    assert all(isinstance(item, Error) for item in diagnostics)
    assert all(item.id.startswith("mnemex.E") for item in diagnostics)
    assert secret not in " ".join(str(item) for item in diagnostics)


def test_readiness_hides_cache_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_cache_check() -> None:
        raise RuntimeError("rediss://user:password@secret-cache.example.invalid")

    monkeypatch.setattr("mnemex.web.health._check_cache", fail_cache_check)

    response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"password" not in response.content


def test_readiness_hides_missing_historical_key_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_key_check() -> None:
        raise ImproperlyConfigured("required key for secret account data is missing")

    monkeypatch.setattr("mnemex.web.health._check_key_versions", fail_key_check)

    response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"secret" not in response.content
