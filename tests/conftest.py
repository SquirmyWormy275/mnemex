"""Shared pytest fixtures and gating helpers."""

from __future__ import annotations

import os

import pytest

# ----------------------------------------------------------------------------
# Supabase integration test gating
# ----------------------------------------------------------------------------
#
# Integration tests in tests/test_supabase_schema.py and
# tests/test_store_supabase.py run against the staging Supabase project.
# They require:
#
#   MNEMEX_TEST_SUPABASE=1                       (the gate)
#   MNEMEX_TEST_SUPABASE_URL                     (staging project URL)
#   MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY        (staging service-role key)
#
# When the gate is unset (the default), the requires_supabase fixture
# emits pytest.skip() so the entire test file is skipped without errors.
# This keeps the default `pytest` invocation green for contributors who
# haven't set up Supabase credentials yet.
# ----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def supabase_credentials() -> dict[str, str]:
    """Return staging Supabase credentials from env, or skip if unset.

    Used by all integration tests that need a real Supabase client.
    Sets the production env vars to the staging values for the duration
    of the test session; tests run against staging exclusively.
    """
    if os.environ.get("MNEMEX_TEST_SUPABASE") != "1":
        pytest.skip(
            "MNEMEX_TEST_SUPABASE is not set to 1; skipping Supabase integration tests. "
            "See docs/supabase-setup.md for credential setup."
        )

    url = os.environ.get("MNEMEX_TEST_SUPABASE_URL")
    key = os.environ.get("MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        pytest.skip(
            "MNEMEX_TEST_SUPABASE_URL and MNEMEX_TEST_SUPABASE_SERVICE_ROLE_KEY "
            "must both be set when MNEMEX_TEST_SUPABASE=1."
        )

    # Wire the staging credentials into the env vars the production
    # store reads. The store's _CLIENT memoization is reset before/after
    # the session so we don't leak between test runs.
    os.environ["MNEMEX_SUPABASE_URL"] = url
    os.environ["MNEMEX_SUPABASE_SERVICE_ROLE_KEY"] = key

    from mnemex import store

    store._reset_client_for_tests()
    yield {"url": url, "key": key}
    store._reset_client_for_tests()


@pytest.fixture(scope="function")
def supabase_client(supabase_credentials):
    """Yield a fresh supabase-py client connected to the staging project.

    Function-scoped so per-test cleanup doesn't leak; session-scoped
    credentials.
    """
    from mnemex.store import _get_client

    return _get_client()
