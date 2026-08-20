from __future__ import annotations

import base64

import pytest
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from mnemex.accounts.keyring import KeyRingError, VersionedKeyRing, parse_key_ring_entries


def _key(seed: int) -> bytes:
    return bytes((seed + offset) % 256 for offset in range(32))


def test_strict_key_ring_rejects_duplicate_versions() -> None:
    with pytest.raises(ImproperlyConfigured, match="duplicate key version"):
        parse_key_ring_entries(
            ((1, base64.b64encode(_key(1)).decode()), (1, base64.b64encode(_key(2)).decode())),
            active_version=1,
            label="MFA",
        )


@pytest.mark.parametrize(
    ("entries", "active_version", "message"),
    [
        (((1, base64.b64encode(b"short").decode()),), 1, "decode to 32 bytes"),
        (((1, base64.b64encode(b"x" * 32).decode()),), 1, "placeholder"),
        (((1, base64.b64encode(_key(1)).decode()),), 2, "active MFA encryption key"),
    ],
)
def test_strict_key_ring_rejects_invalid_or_incomplete_material(
    entries: tuple[tuple[int, str], ...],
    active_version: int,
    message: str,
) -> None:
    with pytest.raises(ImproperlyConfigured, match=message):
        parse_key_ring_entries(
            entries,
            active_version=active_version,
            label="MFA",
        )


def test_strict_key_ring_rejects_removal_of_required_historical_version() -> None:
    with pytest.raises(ImproperlyConfigured, match="required MFA encryption key"):
        parse_key_ring_entries(
            ((2, base64.b64encode(_key(2)).decode()),),
            active_version=2,
            required_versions={1, 2},
            label="MFA",
        )


def test_versioned_ring_reads_old_and_new_ciphertext_during_overlap() -> None:
    old_ring = VersionedKeyRing.from_keys(
        {1: _key(1), 2: _key(2)},
        active_version=1,
        label="MFA",
    )
    old_ciphertext = old_ring.encrypt_text("synthetic-old-secret")
    new_ring = VersionedKeyRing.from_keys(
        {1: _key(1), 2: _key(2)},
        active_version=2,
        label="MFA",
    )
    new_ciphertext = new_ring.encrypt_text("synthetic-new-secret")

    assert old_ciphertext.startswith("v1.")
    assert new_ciphertext.startswith("v2.")
    assert new_ring.decrypt_text(old_ciphertext).plaintext == "synthetic-old-secret"
    assert new_ring.decrypt_text(new_ciphertext).plaintext == "synthetic-new-secret"


def test_versioned_ring_rejects_tampering_and_unknown_versions_generically() -> None:
    ring = VersionedKeyRing.from_keys(
        {1: _key(1)},
        active_version=1,
        label="MFA",
    )
    ciphertext = ring.encrypt_text("synthetic-secret")
    prefix, payload = ciphertext.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(payload))
    raw[-1] ^= 1
    tampered = f"{prefix}.{base64.urlsafe_b64encode(bytes(raw)).decode()}"

    for invalid in (tampered, ciphertext.replace("v1.", "v9.", 1)):
        with pytest.raises(KeyRingError, match="ciphertext could not be decrypted") as error:
            ring.decrypt_text(invalid)
        assert "synthetic-secret" not in str(error.value)


@override_settings(
    MNEMEX_MFA_ENCRYPTION_KEYS={1: _key(1), 2: _key(2)},
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
def test_mfa_adapter_uses_shared_versioned_ring_contract() -> None:
    adapter = get_mfa_adapter()
    encrypted = adapter.encrypt("synthetic-adapter-secret")

    assert encrypted.startswith("v2.")
    assert adapter.decrypt(encrypted) == "synthetic-adapter-secret"
