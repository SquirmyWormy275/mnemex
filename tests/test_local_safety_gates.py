from __future__ import annotations

import base64
import importlib
import json
import os
from pathlib import Path
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from mnemex.accounts.authorization import has_effective_role
from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.results.artifacts import ArtifactCollisionError, LocalPrivateArtifactStore
from mnemex.web.settings import test as test_settings
from tests.conftest import (
    _assert_local_supabase_url,
    _supabase_credentials_from_environment,
)


def test_artifact_write_failure_leaves_no_partial_file_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalPrivateArtifactStore(tmp_path)
    content = b"synthetic result artifact"

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("injected final-install failure")

    monkeypatch.setattr("mnemex.results.artifacts.os.link", fail_link)

    with pytest.raises(OSError, match="injected final-install failure"):
        store.put(content=content, filename="results.csv")

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_artifact_fsync_failure_is_observed_and_cleaned_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalPrivateArtifactStore(tmp_path)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr("mnemex.results.artifacts.os.fsync", fail_fsync)

    with pytest.raises(OSError, match="injected fsync failure"):
        store.put(content=b"synthetic fsync artifact", filename="results.csv")

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_artifact_exact_retry_recovers_after_post_install_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalPrivateArtifactStore(tmp_path)
    content = b"synthetic retry artifact"
    real_link = os.link

    def install_then_fail(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        real_link(source, target)
        raise OSError("injected acknowledgement failure")

    with monkeypatch.context() as patch:
        patch.setattr("mnemex.results.artifacts.os.link", install_then_fail)
        with pytest.raises(OSError, match="injected acknowledgement failure"):
            store.put(content=content, filename="results.csv")

    reference = store.put(content=content, filename="results.csv")

    assert (tmp_path / reference).read_bytes() == content
    assert not list(tmp_path.rglob("*.tmp"))


def test_artifact_store_never_overwrites_an_existing_digest_object(tmp_path: Path) -> None:
    store = LocalPrivateArtifactStore(tmp_path)
    content = b"synthetic immutable artifact"
    reference = store.put(content=content, filename="results.csv")
    target = tmp_path / reference
    target.write_bytes(b"tampered bytes")

    with pytest.raises(ArtifactCollisionError, match="different bytes"):
        store.put(content=content, filename="results.csv")

    assert target.read_bytes() == b"tampered bytes"


def test_artifact_cleanup_rejects_a_reference_outside_its_root(tmp_path: Path) -> None:
    store = LocalPrivateArtifactStore(tmp_path / "private")
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"synthetic outside bytes")

    with pytest.raises(ValueError, match="below the private artifact root"):
        store.remove_if_exact(reference="../outside.csv", content=outside.read_bytes())

    assert outside.read_bytes() == b"synthetic outside bytes"


def test_test_settings_use_a_fast_synthetic_only_password_hasher() -> None:
    assert test_settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:54321",
        "http://127.0.0.1:54321",
        "http://[::1]:54321",
    ],
)
def test_supabase_guard_accepts_only_explicit_local_targets(url: str) -> None:
    _assert_local_supabase_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://synthetic-project.supabase.co",
        "https://db.example.invalid",
        "file:///tmp/supabase",
    ],
)
def test_supabase_guard_rejects_hosted_or_non_http_targets(url: str) -> None:
    with pytest.raises(RuntimeError, match="refusing non-local Supabase"):
        _assert_local_supabase_url(url)


def test_supabase_fixture_rejects_hosted_target_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE", "1")
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY", "synthetic-local-key")
    fixture_generator = _supabase_credentials_from_environment()

    with pytest.raises(RuntimeError, match="refusing non-local Supabase"):
        next(fixture_generator)


def test_supabase_fixture_restores_store_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE", "1")
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY", "synthetic-local-key")
    monkeypatch.setenv("MNEMEX_SUPABASE_URL", "original-url")
    monkeypatch.delenv("MNEMEX_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    fixture_generator = _supabase_credentials_from_environment()

    credentials = next(fixture_generator)
    assert credentials["url"] == "http://127.0.0.1:54321"
    assert os.environ["MNEMEX_SUPABASE_URL"] == "http://127.0.0.1:54321"
    fixture_generator.close()

    assert os.environ["MNEMEX_SUPABASE_URL"] == "original-url"
    assert "MNEMEX_SUPABASE_SERVICE_ROLE_KEY" not in os.environ


@pytest.mark.django_db
def test_privileged_authorization_fails_closed_when_session_mfa_gate_is_disabled() -> None:
    actor = Account.objects.create_user(
        email="synthetic-production-gate@mnemex.example.invalid",
        password="synthetic-password-123",
        mfa_enrolled_at=timezone.now(),
    )
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
    )

    with override_settings(MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=False):
        assert not has_effective_role(actor, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)


def _reload_production_settings(monkeypatch: pytest.MonkeyPatch, database_url: str) -> ModuleType:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "synthetic-production-settings-secret")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "mnemex.example.invalid")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv(
        "MNEMEX_CACHE_URL",
        "rediss://default:synthetic-cache-password@cache.example.invalid:6380/0",
    )
    monkeypatch.setenv("ALLAUTH_TRUSTED_PROXY_COUNT", "0")
    monkeypatch.delenv("ALLAUTH_TRUSTED_CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.invalid")
    monkeypatch.setenv("EMAIL_PORT", "587")
    monkeypatch.setenv("EMAIL_HOST_USER", "synthetic-mail-user")
    monkeypatch.setenv("EMAIL_HOST_PASSWORD", "synthetic-mail-password-with-32-chars")
    monkeypatch.setenv(
        "DEFAULT_FROM_EMAIL",
        "MNEMEX Security <security@mnemex.example.invalid>",
    )
    monkeypatch.setenv(
        "MNEMEX_MFA_ENCRYPTION_KEYS",
        json.dumps({"1": base64.b64encode(bytes(range(32))).decode("ascii")}),
    )
    monkeypatch.setenv("MNEMEX_MFA_ACTIVE_KEY_VERSION", "1")
    monkeypatch.setenv(
        "MNEMEX_NOTIFICATION_ENCRYPTION_KEYS",
        json.dumps({"1": base64.b64encode(bytes(range(32, 64))).decode("ascii")}),
    )
    monkeypatch.setenv("MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION", "1")
    monkeypatch.setenv("MNEMEX_SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv(
        "MNEMEX_SUPABASE_SERVICE_ROLE_KEY",
        "synthetic-service-role-key-with-32-chars",
    )
    monkeypatch.setenv("MNEMEX_PRIVATE_ARTIFACT_BUCKET", "mnemex-private-artifacts")
    from mnemex.web.settings import production

    return importlib.reload(production)


@pytest.mark.parametrize("sslmode", [None, "disable", "allow", "prefer"])
def test_production_settings_reject_missing_or_weak_database_tls(
    monkeypatch: pytest.MonkeyPatch, sslmode: str | None
) -> None:
    suffix = "" if sslmode is None else f"?sslmode={sslmode}"

    with pytest.raises(ImproperlyConfigured, match="sslmode"):
        _reload_production_settings(
            monkeypatch,
            f"postgresql://mnemex:synthetic@db.example.invalid:5432/mnemex{suffix}",
        )


@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_production_settings_accept_strong_database_tls_without_connecting(
    monkeypatch: pytest.MonkeyPatch, sslmode: str
) -> None:
    production = _reload_production_settings(
        monkeypatch,
        f"postgresql://mnemex:synthetic@db.example.invalid:5432/mnemex?sslmode={sslmode}",
    )

    assert production.DATABASES["default"]["OPTIONS"]["sslmode"] == sslmode
    assert production.MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED is False


def test_legacy_jsonl_export_has_no_schedule_and_is_prominently_disabled() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/jsonl-export.yml").read_text(
        encoding="utf-8"
    )

    assert "schedule:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "LEGACY" in workflow
    assert "PRODUCTION DISABLED" in workflow
