"""Structured error registry for MNEMEX.

Per the design doc's "Structured errors" section: when MNEMEX is invoked
in a programmatic context (--json-errors flag, or library use), errors
are emitted as structured JSON for downstream consumers. This module is
the single source of truth for error codes.

Every MNEMEX error class has:
  - code        : stable identifier for programmatic handling
  - message     : human-readable
  - fix         : text the user reads
  - fix_command : command they run (when one exists)
  - doc_url     : link to docs/errors/<code>.md

Tests assert that every code has a matching docs/errors/<code>.md file.
Concrete error subclasses land in M2-M6 as ingest paths come online.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MnemexError(Exception):
    """Base class for all structured MNEMEX errors.

    Subclasses set `code` as a class attribute. Instances populate
    `message`, `fix`, and optionally `fix_command`.
    """

    code: str = "MNEMEX_GENERIC"
    message: str = ""
    fix: Optional[str] = None
    fix_command: Optional[str] = None
    platform: Optional[str] = None  # win32 / darwin / linux when relevant
    doc_url: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "platform": self.platform,
                "fix": self.fix,
                "fix_command": self.fix_command,
                "doc_url": self.doc_url,
            }
        }
