from __future__ import annotations

import os
from multiprocessing import get_context
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value
from django.conf import settings
from django.test import RequestFactory, override_settings

from mnemex.accounts.forms import _claim_totp_once
from mnemex.accounts.models import Account

_SECRET = "JBSWY3DPEHPK3PXP"


def _redis_add_worker(redis_url: str, key: str, barrier: Any, results: Any) -> None:
    import redis

    client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
    barrier.wait(timeout=5)
    results.put(client.set(key, "claimed", nx=True, ex=30) is True)


def _account(suffix: str) -> Account:
    return Account.objects.create_user(
        email=f"shared-cache-{suffix}@mnemex.example.invalid",
        password="synthetic-password-123",
    )


def _totp_authenticator(account: Account) -> Authenticator:
    from allauth.mfa.adapter import get_adapter

    return Authenticator.objects.create(
        user=account,
        type=Authenticator.Type.TOTP,
        data={"secret": get_adapter().encrypt(_SECRET)},
    )


def _current_code(now: float = 1_800_000_000.0) -> str:
    counter = int(now) // settings.MFA_TOTP_PERIOD
    return format_hotp_value(hotp_value(_SECRET, counter))


@pytest.mark.django_db
def test_totp_claim_uses_only_the_named_security_cache() -> None:
    account = _account("named-alias")
    authenticator = _totp_authenticator(account)

    class CacheRegistry:
        requested: list[str] = []

        def __getitem__(self, alias: str):
            self.requested.append(alias)

            class AtomicCache:
                def add(self, key: str, value: str, timeout: int) -> bool:
                    return True

            return AtomicCache()

    registry = CacheRegistry()
    with (
        patch("mnemex.accounts.forms.caches", registry),
        patch("mnemex.accounts.forms.time.time", return_value=1_800_000_000.0),
    ):
        assert _claim_totp_once(authenticator, _current_code())

    assert registry.requested == [settings.MNEMEX_SECURITY_CACHE_ALIAS]


@pytest.mark.django_db
def test_totp_claim_fails_closed_when_shared_cache_is_unavailable() -> None:
    account = _account("outage")
    authenticator = _totp_authenticator(account)

    class FailedCache:
        def add(self, key: str, value: str, timeout: int) -> bool:
            raise TimeoutError("synthetic cache outage")

    class CacheRegistry:
        def __getitem__(self, alias: str) -> FailedCache:
            return FailedCache()

    with (
        patch("mnemex.accounts.forms.caches", CacheRegistry()),
        patch("mnemex.accounts.forms.time.time", return_value=1_800_000_000.0),
    ):
        assert not _claim_totp_once(authenticator, _current_code())


@pytest.mark.django_db
def test_totp_claim_rejects_corrupt_cache_result() -> None:
    account = _account("corruption")
    authenticator = _totp_authenticator(account)

    class CorruptCache:
        def add(self, key: str, value: str, timeout: int) -> str:
            return "accepted-but-not-a-boolean"

    class CacheRegistry:
        def __getitem__(self, alias: str) -> CorruptCache:
            return CorruptCache()

    with (
        patch("mnemex.accounts.forms.caches", CacheRegistry()),
        patch("mnemex.accounts.forms.time.time", return_value=1_800_000_000.0),
    ):
        assert not _claim_totp_once(authenticator, _current_code())


def test_untrusted_forwarded_header_does_not_select_rate_limit_identity() -> None:
    from allauth.core.internal.ratelimit import Rate, get_cache_key

    request = RequestFactory().post(
        "/accounts/login/",
        HTTP_X_FORWARDED_FOR="198.51.100.77",
        REMOTE_ADDR="192.0.2.10",
    )
    with override_settings(
        ALLAUTH_TRUSTED_PROXY_COUNT=0,
        ALLAUTH_TRUSTED_CLIENT_IP_HEADER=None,
    ):
        key = get_cache_key(
            request,
            action="login",
            rate=Rate(amount=5, duration=60, per="ip"),
        )

    assert key.endswith(":ip:192.0.2.10")
    assert "198.51.100.77" not in key


@pytest.mark.skipif(
    not os.environ.get("MNEMEX_TEST_REDIS_URL"),
    reason="disposable loopback Redis was not configured",
)
def test_two_processes_have_exactly_one_disposable_redis_claim_winner() -> None:
    redis_url = os.environ["MNEMEX_TEST_REDIS_URL"]
    parsed = urlsplit(redis_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("MNEMEX_TEST_REDIS_URL must target loopback")

    import redis

    client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
    key = f"mnemex:test:synthetic-process-claim:{uuid4().hex}"
    context = get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(target=_redis_add_worker, args=(redis_url, key, barrier, results))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
        assert all(process.exitcode == 0 for process in processes)
        assert sorted([results.get(timeout=2), results.get(timeout=2)]) == [False, True]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        client.delete(key)
