from __future__ import annotations

import hashlib
import hmac
import json
import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"mnemex.legal-identity.v1"


@dataclass(frozen=True)
class SealedIdentityPayload:
    ciphertext: bytes
    key_version: int


class IdentityCipher:
    """Versioned authenticated encryption for private identity claim payloads."""

    def __init__(
        self,
        *,
        encryption_keys: Mapping[int, bytes],
        active_version: int,
        lookup_key: bytes,
    ) -> None:
        if active_version not in encryption_keys:
            raise ValueError("active identity encryption key is unavailable")
        if any(len(key) != 32 for key in encryption_keys.values()):
            raise ValueError("identity encryption keys must be 32 bytes")
        if len(lookup_key) < 32:
            raise ValueError("identity lookup key must be at least 32 bytes")
        self._encryption_keys = dict(encryption_keys)
        self._active_version = active_version
        self._lookup_key = lookup_key

    def encrypt(self, payload: Mapping[str, Any]) -> SealedIdentityPayload:
        plaintext = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._encryption_keys[self._active_version]).encrypt(
            nonce, plaintext, _AAD
        )
        return SealedIdentityPayload(
            ciphertext=nonce + ciphertext,
            key_version=self._active_version,
        )

    def decrypt(self, sealed: bytes, *, key_version: int) -> dict[str, Any]:
        if key_version not in self._encryption_keys:
            raise ValueError("identity encryption key version is unavailable")
        if len(sealed) < 13:
            raise ValueError("sealed identity payload is malformed")
        plaintext = AESGCM(self._encryption_keys[key_version]).decrypt(
            sealed[:12], sealed[12:], _AAD
        )
        decoded = json.loads(plaintext.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("identity payload must decode to an object")
        return decoded

    def lookup_token(self, value: str) -> str:
        normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        return hmac.new(self._lookup_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
