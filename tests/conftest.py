"""Shared pytest fixtures and gating helpers."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from urllib.parse import urlsplit

import pytest

# ----------------------------------------------------------------------------
# Supabase integration test gating
# ----------------------------------------------------------------------------
#
# Integration tests in tests/test_supabase_schema.py and
# tests/test_store_supabase.py may run only against a local disposable
# Supabase stack. Hosted projects are rejected even when credentials exist.
# They require:
#
#   MNEMEX_TEST_SUPABASE=1                       (the gate)
#   MNEMEX_TEST_SUPABASE_URL                     (localhost URL)
#   MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY        (local service-role key)
#
# When the gate is unset (the default), the supabase_credentials fixture
# emits pytest.skip() so the entire test file is skipped without errors.
# This keeps the default `pytest` invocation green for contributors who
# haven't set up a disposable local Supabase stack yet.
# ----------------------------------------------------------------------------

_LOCAL_SUPABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}
_STORE_ENV_NAMES = ("MNEMEX_SUPABASE_URL", "MNEMEX_SUPABASE_SERVICE_ROLE_KEY")


def _assert_local_supabase_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_SUPABASE_HOSTS:
        raise RuntimeError("refusing non-local Supabase integration test target")


def _supabase_credentials_from_environment() -> Generator[dict[str, str], None, None]:
    """Return disposable local Supabase credentials, or skip if unset.

    Used by all integration tests that need a real Supabase client.
    Sets the store env vars to local values only for the duration of the test
    session and restores their exact prior state afterward.
    """
    if os.environ.get("MNEMEX_TEST_SUPABASE") != "1":
        pytest.skip(
            "MNEMEX_TEST_SUPABASE is not set to 1; skipping Supabase integration tests. "
            "See docs/supabase-setup.md for credential setup."
        )

    url = os.environ.get("MNEMEX_TEST_SUPABASE_URL")
    key = os.environ.get("MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "MNEMEX_TEST_SUPABASE_URL and MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY "
            "must both be set when MNEMEX_TEST_SUPABASE=1."
        )
    _assert_local_supabase_url(url)

    previous = {name: os.environ.get(name) for name in _STORE_ENV_NAMES}
    store = None
    try:
        os.environ["MNEMEX_SUPABASE_URL"] = url
        os.environ["MNEMEX_SUPABASE_SERVICE_ROLE_KEY"] = key

        from mnemex import store as mnemex_store

        store = mnemex_store
        store._reset_client_for_tests()
        yield {"url": url, "key": key}
    finally:
        if store is not None:
            store._reset_client_for_tests()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(scope="session")
def supabase_credentials() -> Generator[dict[str, str], None, None]:
    yield from _supabase_credentials_from_environment()


@pytest.fixture(scope="function")
def supabase_client(supabase_credentials: dict[str, str]) -> Any:
    """Yield a fresh supabase-py client connected to the local test project.

    Function-scoped so per-test cleanup doesn't leak; session-scoped
    credentials.
    """
    from mnemex.store import _get_client

    return _get_client()
