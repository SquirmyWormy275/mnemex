"""Phase A contract tests for the hosted MNEMEX service foundation.

These tests deliberately use only the isolated Django test settings. They must
never inherit ``DATABASE_URL`` or Supabase credentials from the environment.
"""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import Client

from mnemex.accounts.models import Account
from mnemex.foundation.models import AuditEvent, IdempotencyRecord
from mnemex.foundation.services import (
    IdempotencyConflict,
    claim_idempotency,
    record_audit_event,
)
from mnemex.foundation.transactions import run_in_transaction
from mnemex.web.database import assert_safe_test_database, database_config_from_url
from mnemex.web.settings import test as test_settings
from mnemex.worker import main as worker_main
from tests.factories import SyntheticDataFactory


def test_test_settings_ignore_production_database_url(monkeypatch) -> None:
    monkeypatch.delenv("MNEMEX_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://service:secret@db.production.supabase.co:5432/postgres",
    )
    monkeypatch.setenv("MNEMEX_SUPABASE_URL", "https://production.supabase.co")
    monkeypatch.setenv("MNEMEX_SUPABASE_SERVICE_ROLE_KEY", "production-secret")

    database = importlib.reload(test_settings).DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.sqlite3"
    assert "production.supabase.co" not in str(database["NAME"])


def test_test_database_guard_rejects_remote_postgres() -> None:
    with pytest.raises(RuntimeError, match="refusing non-local test database"):
        assert_safe_test_database(
            {
                "ENGINE": "django.db.backends.postgresql",
                "HOST": "db.production.supabase.co",
                "NAME": "postgres",
            }
        )


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_test_database_guard_allows_local_postgres(host: str) -> None:
    assert_safe_test_database(
        {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": host,
            "NAME": "mnemex_test",
        }
    )


def test_postgres_database_url_is_parsed_without_leaking_credentials() -> None:
    config = database_config_from_url(
        "postgresql://mnemex:encoded%20password@db.internal:5433/mnemex?sslmode=require"
    )

    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "mnemex",
        "USER": "mnemex",
        "PASSWORD": "encoded password",
        "HOST": "db.internal",
        "PORT": "5433",
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5, "sslmode": "require"},
    }


def test_database_url_rejects_non_postgres_scheme() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        database_config_from_url("mysql://mnemex:secret@db.internal/mnemex")


@pytest.mark.django_db
def test_custom_account_uses_email_and_hashes_password() -> None:
    factory = SyntheticDataFactory()
    account = Account.objects.create_user(
        email=factory.email("Competitor"),
        password="correct horse battery staple",
    )

    assert account.email == factory.email("Competitor").lower()
    assert account.check_password("correct horse battery staple")
    assert account.password != "correct horse battery staple"
    assert account.security_version == 1


@pytest.mark.django_db
def test_audit_event_is_append_only() -> None:
    event = record_audit_event(
        action="account.created",
        target_type="account",
        target_id="acct-123",
        payload_digest="a" * 64,
        metadata={"source": "synthetic-test"},
    )

    assert isinstance(event.event_id, UUID)
    event.action = "account.changed"

    with pytest.raises(PermissionDenied, match="append-only"):
        event.save()

    with pytest.raises(PermissionDenied, match="append-only"):
        event.delete()

    with pytest.raises(PermissionDenied, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).update(action="account.changed")


@pytest.mark.parametrize(
    "metadata",
    [
        {"email": "person@example.com"},
        {"nested": {"legal_name": "Private Person"}},
        {"token": "secret-value"},
    ],
)
def test_audit_service_rejects_sensitive_metadata(metadata: dict) -> None:
    with pytest.raises(ValueError, match="sensitive audit metadata"):
        record_audit_event(
            action="unsafe.event",
            target_type="test",
            target_id="test-1",
            payload_digest="b" * 64,
            metadata=metadata,
        )


@pytest.mark.django_db
def test_idempotency_exact_retry_returns_existing_record() -> None:
    first, first_created = claim_idempotency(
        scope="portable-profile.validate",
        key="request-123",
        request_digest="c" * 64,
    )
    second, second_created = claim_idempotency(
        scope="portable-profile.validate",
        key="request-123",
        request_digest="c" * 64,
    )

    assert first_created is True
    assert second_created is False
    assert second.record_id == first.record_id


@pytest.mark.django_db
def test_idempotency_rejects_changed_payload_for_same_key() -> None:
    claim_idempotency(
        scope="results.upload",
        key="upload-123",
        request_digest="d" * 64,
    )

    with pytest.raises(IdempotencyConflict, match="different payload"):
        claim_idempotency(
            scope="results.upload",
            key="upload-123",
            request_digest="e" * 64,
        )


@pytest.mark.django_db(transaction=True)
def test_postgres_idempotency_race_commits_one_record() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency semantics require the disposable PostgreSQL gate")

    factory = SyntheticDataFactory()
    barrier = Barrier(2)

    def concurrent_claim() -> tuple[UUID, bool]:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            record, created = claim_idempotency(
                scope="synthetic.concurrent-test",
                key="same-request",
                request_digest=factory.digest("concurrent-idempotency"),
            )
            return record.record_id, created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: concurrent_claim(), range(2)))

    assert {record_id for record_id, _created in outcomes} == {
        IdempotencyRecord.objects.get(key="same-request").record_id
    }
    assert sorted(created for _record_id, created in outcomes) == [False, True]


@pytest.mark.django_db
def test_service_transaction_rolls_back_every_write_after_injected_crash() -> None:
    factory = SyntheticDataFactory()

    def crashing_operation() -> None:
        claim_idempotency(
            scope="synthetic.crash-test",
            key="transaction-rollback",
            request_digest=factory.digest("idempotency"),
        )
        record_audit_event(
            action="synthetic.before-crash",
            target_type="synthetic",
            target_id="transaction-rollback",
            payload_digest=factory.digest("audit"),
            metadata={"source": "synthetic-test"},
        )
        raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        run_in_transaction(crashing_operation)

    assert not IdempotencyRecord.objects.filter(key="transaction-rollback").exists()
    assert not AuditEvent.objects.filter(target_id="transaction-rollback").exists()


def test_liveness_endpoint_has_no_dependency_detail() -> None:
    response = Client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_endpoint_checks_isolated_database() -> None:
    response = Client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "cache": "ok"}


def test_readiness_endpoint_hides_database_failure(monkeypatch) -> None:
    def fail_database_check():
        raise RuntimeError("database hostname and password must not leak")

    monkeypatch.setattr("mnemex.web.health._check_database", fail_database_check)

    response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"hostname" not in response.content


def test_worker_check_entrypoint_uses_django_system_checks() -> None:
    assert worker_main(["--check"]) == 0


def test_audit_model_has_no_update_or_delete_default_permissions() -> None:
    permissions = AuditEvent._meta.default_permissions

    assert permissions == ("add", "view")
