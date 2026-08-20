from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticDataFactory:
    """Generate recognizable, non-deliverable values for isolated tests."""

    namespace: str = "mnemex.example.invalid"

    def email(self, label: str) -> str:
        return f"{label}@{self.namespace}"

    def digest(self, label: str) -> str:
        value = f"MNEMEX synthetic test data:{label}".encode()
        return hashlib.sha256(value).hexdigest()
