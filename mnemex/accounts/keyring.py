from __future__ import annotations

import base64
import binascii
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MFA_AUTHENTICATOR_AAD = b"mnemex.mfa.authenticator.v1"
_CIPHERTEXT_RE = re.compile(r"^v(?P<version>[1-9][0-9]*)\.(?P<payload>[A-Za-z0-9_-]+=*)$")


class KeyRingError(ValueError):
    """A versioned ciphertext failed closed without exposing secret material."""


@dataclass(frozen=True)
class DecryptedText:
    plaintext: str
    key_version: int


@dataclass(frozen=True)
class VersionedKeyRing:
    keys: Mapping[int, bytes]
    active_version: int
    label: str
    aad: bytes = MFA_AUTHENTICATOR_AAD

    @classmethod
    def from_keys(
        cls,
        keys: Mapping[int, bytes],
        *,
        active_version: int,
        label: str,
        aad: bytes = MFA_AUTHENTICATOR_AAD,
        required_versions: Iterable[int] = (),
        reject_placeholders: bool = True,
    ) -> VersionedKeyRing:
        normalized: dict[int, bytes] = {}
        for version, key in keys.items():
            _validate_version(version, label=label)
            if not isinstance(key, bytes) or len(key) != 32:
                raise ImproperlyConfigured(
                    f"{label} encryption keys must be versioned 32-byte values"
                )
            if reject_placeholders and _looks_like_placeholder(key):
                raise ImproperlyConfigured(
                    f"{label} encryption keys must not contain placeholder material"
                )
            if key in normalized.values():
                raise ImproperlyConfigured(
                    f"{label} encryption key material must be unique by version"
                )
            normalized[version] = key
        _validate_version(active_version, label=label)
        if active_version not in normalized:
            raise ImproperlyConfigured(f"active {label} encryption key is unavailable")
        required = {_validate_version(version, label=label) for version in required_versions}
        if not required.issubset(normalized):
            raise ImproperlyConfigured(f"required {label} encryption key is unavailable")
        if not isinstance(aad, bytes) or not aad:
            raise ImproperlyConfigured(f"{label} encryption context is invalid")
        return cls(
            keys=normalized,
            active_version=active_version,
            label=label,
            aad=aad,
        )

    def encrypt_text(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise KeyRingError("ciphertext could not be encrypted")
        nonce = os.urandom(12)
        sealed = AESGCM(self.keys[self.active_version]).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self.aad,
        )
        payload = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
        return f"v{self.active_version}.{payload}"

    def decrypt_text(self, ciphertext: str) -> DecryptedText:
        match = _CIPHERTEXT_RE.fullmatch(ciphertext) if isinstance(ciphertext, str) else None
        if match is None:
            raise KeyRingError("ciphertext could not be decrypted")
        version = int(match.group("version"))
        key = self.keys.get(version)
        if key is None:
            raise KeyRingError("ciphertext could not be decrypted")
        try:
            sealed = base64.urlsafe_b64decode(match.group("payload").encode("ascii"))
            if len(sealed) < 29:
                raise ValueError
            plaintext = AESGCM(key).decrypt(sealed[:12], sealed[12:], self.aad)
            return DecryptedText(
                plaintext=plaintext.decode("utf-8"),
                key_version=version,
            )
        except (InvalidTag, UnicodeDecodeError, ValueError, binascii.Error) as error:
            raise KeyRingError("ciphertext could not be decrypted") from error

    def ciphertext_version(self, ciphertext: str) -> int:
        match = _CIPHERTEXT_RE.fullmatch(ciphertext) if isinstance(ciphertext, str) else None
        if match is None:
            raise KeyRingError("ciphertext version is invalid")
        return int(match.group("version"))


def parse_key_ring_entries(
    entries: Iterable[tuple[object, object]],
    *,
    active_version: int,
    label: str,
    required_versions: Iterable[int] = (),
    aad: bytes = MFA_AUTHENTICATOR_AAD,
) -> VersionedKeyRing:
    """Parse ordered configuration entries so duplicate versions cannot be hidden."""

    decoded: dict[int, bytes] = {}
    for raw_version, encoded in entries:
        version = _validate_version(raw_version, label=label)
        if version in decoded:
            raise ImproperlyConfigured(f"duplicate key version in {label} encryption key ring")
        if not isinstance(encoded, str):
            raise ImproperlyConfigured(f"{label} encryption key values must be base64 strings")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ImproperlyConfigured(
                f"{label} encryption key values must be valid base64"
            ) from error
        if len(key) != 32:
            raise ImproperlyConfigured(f"{label} encryption key values must decode to 32 bytes")
        decoded[version] = key
    return VersionedKeyRing.from_keys(
        decoded,
        active_version=active_version,
        label=label,
        aad=aad,
        required_versions=required_versions,
        reject_placeholders=True,
    )


def parse_key_ring_json(
    raw: str,
    *,
    active_version: int,
    label: str,
    required_versions: Iterable[int] = (),
    aad: bytes = MFA_AUTHENTICATOR_AAD,
) -> VersionedKeyRing:
    """Parse a JSON object without allowing duplicate version keys to collapse."""

    if not isinstance(raw, str):
        raise ImproperlyConfigured(f"{label} encryption key ring must be a JSON object")
    try:
        pairs = json.loads(raw, object_pairs_hook=lambda items: items)
    except json.JSONDecodeError as error:
        raise ImproperlyConfigured(f"{label} encryption key ring must be a JSON object") from error
    if (
        not pairs
        or not isinstance(pairs, list)
        or not all(isinstance(item, tuple) and len(item) == 2 for item in pairs)
    ):
        raise ImproperlyConfigured(f"{label} encryption key ring must be a JSON object")
    entries: list[tuple[int, object]] = []
    for raw_version, encoded in pairs:
        if not isinstance(raw_version, str):
            raise ImproperlyConfigured(
                f"{label} encryption key versions must be canonical positive integers"
            )
        try:
            version = int(raw_version)
        except ValueError as error:
            raise ImproperlyConfigured(
                f"{label} encryption key versions must be canonical positive integers"
            ) from error
        if version < 1 or str(version) != raw_version:
            raise ImproperlyConfigured(
                f"{label} encryption key versions must be canonical positive integers"
            )
        entries.append((version, encoded))
    return parse_key_ring_entries(
        entries,
        active_version=active_version,
        label=label,
        required_versions=required_versions,
        aad=aad,
    )


def mfa_key_ring(*, required_versions: Iterable[int] = ()) -> VersionedKeyRing:
    keys = getattr(settings, "MNEMEX_MFA_ENCRYPTION_KEYS", {})
    active_version = getattr(settings, "MNEMEX_MFA_ACTIVE_KEY_VERSION", None)
    if not isinstance(keys, Mapping) or not isinstance(active_version, int):
        raise ImproperlyConfigured("MFA encryption is not configured")
    return VersionedKeyRing.from_keys(
        keys,
        active_version=active_version,
        label="MFA",
        required_versions=required_versions,
        reject_placeholders=bool(getattr(settings, "MNEMEX_HOSTED_CONFIGURATION", False)),
    )


def _validate_version(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImproperlyConfigured(f"{label} encryption key versions must be positive integers")
    return value


def _looks_like_placeholder(key: bytes) -> bool:
    return len(set(key)) < 8
