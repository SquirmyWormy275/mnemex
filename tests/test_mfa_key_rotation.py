from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections
from django.test import override_settings
from django.utils import timezone

from mnemex.accounts.key_rotation import (
    KeyRetirementBlocked,
    KeyRotationClaimLost,
    assert_configured_key_versions_available,
    assert_key_version_retirable,
    claim_next_key_rotation,
    enqueue_mfa_key_rotation,
    key_retirement_blockers,
    release_key_rotation_claim,
    run_mfa_key_rotation_batch,
)
from mnemex.accounts.models import Account, EncryptionKeyRotationJob, SecurityNotification
from mnemex.foundation.models import AuditEvent

pytestmark = pytest.mark.django_db


def _key(seed: int) -> bytes:
    return bytes((seed + offset) % 256 for offset in range(32))


def _account(label: str) -> Account:
    return Account.objects.create_user(
        email=f"{label}@mnemex.example.invalid",
        password="synthetic-password-only",
        email_verified_at=timezone.now(),
    )


def _authenticator(account: Account, *, kind: str, plaintext: str) -> Authenticator:
    field = "secret" if kind == Authenticator.Type.TOTP else "seed"
    return Authenticator.objects.create(
        user=account,
        type=kind,
        data={field: get_mfa_adapter().encrypt(plaintext)},
    )


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_rotation_commits_bounded_batches_and_resumes_without_rewriting_completed_rows() -> None:
    account_a = _account("rotation-a")
    account_b = _account("rotation-b")
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        first = _authenticator(
            account_a,
            kind=Authenticator.Type.TOTP,
            plaintext="synthetic-first-secret",
        )
        second = _authenticator(
            account_b,
            kind=Authenticator.Type.RECOVERY_CODES,
            plaintext="synthetic-second-seed",
        )
    job = enqueue_mfa_key_rotation(
        requested_by=account_a,
        source_version=1,
        target_version=2,
    )
    first_claim = claim_next_key_rotation(owner="rotation-worker-a")
    assert first_claim is not None

    first_batch = run_mfa_key_rotation_batch(first_claim, limit=1)
    first.refresh_from_db()
    second.refresh_from_db()
    first_ciphertext = first.data["secret"]

    assert first_batch.batch_scanned_count == first_batch.rotated_count == 1
    assert first_ciphertext.startswith("v2.")
    assert second.data["seed"].startswith("v1.")
    released = release_key_rotation_claim(first_claim)
    assert released.status == EncryptionKeyRotationJob.Status.PENDING

    resumed_claim = claim_next_key_rotation(owner="rotation-worker-b")
    assert resumed_claim is not None
    second_batch = run_mfa_key_rotation_batch(resumed_claim, limit=1)
    final_batch = run_mfa_key_rotation_batch(resumed_claim, limit=1)

    job.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert second_batch.batch_scanned_count == second_batch.rotated_count == 1
    assert final_batch.status == EncryptionKeyRotationJob.Status.COMPLETED
    assert job.processed_count == 2
    assert job.scanned_count == 2
    assert first.data["secret"] == first_ciphertext
    assert second.data["seed"].startswith("v2.")
    assert get_mfa_adapter().decrypt(first.data["secret"]) == "synthetic-first-secret"
    assert get_mfa_adapter().decrypt(second.data["seed"]) == "synthetic-second-seed"


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_rotation_verifies_new_ciphertext_before_committing_row_or_cursor() -> None:
    account = _account("rotation-verify")
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        authenticator = _authenticator(
            account,
            kind=Authenticator.Type.TOTP,
            plaintext="synthetic-verification-secret",
        )
    original = authenticator.data["secret"]
    job = enqueue_mfa_key_rotation(
        requested_by=account,
        source_version=1,
        target_version=2,
    )
    claim = claim_next_key_rotation(owner="rotation-verify-worker")
    assert claim is not None

    with (
        patch(
            "mnemex.accounts.key_rotation.VersionedKeyRing.encrypt_text",
            return_value="v2.invalid",
        ),
        pytest.raises(ValueError, match="verification failed"),
    ):
        run_mfa_key_rotation_batch(claim, limit=1)

    authenticator.refresh_from_db()
    job.refresh_from_db()
    assert authenticator.data["secret"] == original
    assert job.cursor_authenticator_id is None
    assert job.processed_count == job.scanned_count == 0


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_expired_lease_takeover_fences_the_stale_rotation_worker() -> None:
    account = _account("rotation-fence")
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        _authenticator(
            account,
            kind=Authenticator.Type.TOTP,
            plaintext="synthetic-fenced-secret",
        )
    enqueue_mfa_key_rotation(requested_by=account, source_version=1, target_version=2)
    now = timezone.now()
    stale = claim_next_key_rotation(
        owner="stale-worker",
        now=now,
        lease_duration=timedelta(seconds=1),
    )
    assert stale is not None
    replacement = claim_next_key_rotation(
        owner="replacement-worker",
        now=now + timedelta(seconds=2),
    )
    assert replacement is not None
    assert replacement.generation == stale.generation + 1

    with pytest.raises(KeyRotationClaimLost, match="claim"):
        run_mfa_key_rotation_batch(stale, limit=1, now=now + timedelta(seconds=2))


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_retirement_refuses_ciphertext_backup_evidence_and_active_jobs(monkeypatch) -> None:
    account = _account("rotation-retirement")
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        _authenticator(
            account,
            kind=Authenticator.Type.TOTP,
            plaintext="synthetic-retirement-secret",
        )
    enqueue_mfa_key_rotation(requested_by=account, source_version=1, target_version=2)
    monkeypatch.setattr(
        "mnemex.accounts.key_rotation._backup_required_versions",
        lambda purpose: frozenset({1}),
    )

    blockers = key_retirement_blockers(purpose="mfa", key_version=1)

    assert {blocker.code for blocker in blockers} == {
        "active_rotation_job",
        "authenticator_ciphertext",
        "backup_evidence",
    }
    with pytest.raises(KeyRetirementBlocked, match="cannot be retired") as error:
        assert_key_version_retirable(purpose="mfa", key_version=1)
    assert "synthetic-retirement-secret" not in str(error.value)


@override_settings(
    MNEMEX_NOTIFICATION_ENCRYPTION_KEYS={1: _key(4), 2: _key(5)},
    MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION=2,
)
def test_notification_ciphertext_and_backup_evidence_block_notification_key_retirement(
    monkeypatch,
) -> None:
    account = _account("notification-retirement")
    SecurityNotification.objects.create(
        account=account,
        template_identifier="account/email/password_changed",
        context_code="account-security-v1",
        idempotency_key="notification-retirement-event",
        message_id="<notification-retirement@notifications.mnemex.invalid>",
        recipient_ciphertext="v1.synthetic-ciphertext",
        recipient_hmac="a" * 64,
        encryption_key_version=1,
        recipient_retention_deadline=timezone.now() + timedelta(days=1),
    )
    monkeypatch.setattr(
        "mnemex.accounts.key_rotation._backup_required_versions",
        lambda purpose: frozenset({1}) if purpose == "notification" else frozenset(),
    )

    blockers = key_retirement_blockers(purpose="notification", key_version=1)

    assert {blocker.code for blocker in blockers} == {
        "backup_evidence",
        "notification_ciphertext",
    }


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_rotation_audit_and_diagnostics_do_not_persist_plaintext_or_key_bytes() -> None:
    account = _account("rotation-audit")
    plaintext = "synthetic-never-log-this-secret"
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        _authenticator(account, kind=Authenticator.Type.TOTP, plaintext=plaintext)
    enqueue_mfa_key_rotation(requested_by=account, source_version=1, target_version=2)
    claim = claim_next_key_rotation(owner="rotation-audit-worker")
    assert claim is not None
    run_mfa_key_rotation_batch(claim, limit=10)

    serialized = json.dumps(
        list(AuditEvent.objects.values("action", "target_id", "metadata")),
        sort_keys=True,
        default=str,
    )
    job_dump = json.dumps(
        list(
            EncryptionKeyRotationJob.objects.values(
                "last_error_code",
                "source_key_version",
                "target_key_version",
            )
        ),
        sort_keys=True,
        default=str,
    )
    assert plaintext not in serialized + job_dump
    assert base64_for_assertion(_key(1)) not in serialized + job_dump
    assert base64_for_assertion(_key(2)) not in serialized + job_dump


def test_configured_ring_rejects_removal_of_a_durable_authenticator_version() -> None:
    account = _account("rotation-required-version")
    with override_settings(
        MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
        MNEMEX_MFA_ACTIVE_KEY_VERSION=1,
    ):
        _authenticator(
            account,
            kind=Authenticator.Type.TOTP,
            plaintext="synthetic-required-historical-secret",
        )

    with (
        override_settings(
            MNEMEX_MFA_ENCRYPTION_KEYS={2: _key(2)},
            MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
        ),
        pytest.raises(ImproperlyConfigured, match="required MFA encryption key"),
    ):
        assert_configured_key_versions_available(purpose="mfa")


def base64_for_assertion(value: bytes) -> str:
    import base64

    return base64.b64encode(value).decode("ascii")


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
@pytest.mark.django_db(transaction=True)
def test_postgresql_competing_claimers_claim_one_rotation_once() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock coverage")
    account = _account("rotation-postgresql-race")
    job = enqueue_mfa_key_rotation(
        requested_by=account,
        source_version=1,
        target_version=2,
    )
    now = timezone.now()

    def claim(owner: str):
        connections.close_all()
        return claim_next_key_rotation(owner=owner, now=now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("rotation-racer-a", "rotation-racer-b")))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].job_id == job.pk
