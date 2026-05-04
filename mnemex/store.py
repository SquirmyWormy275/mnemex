"""Canonical store + pending queue.

Storage architecture (locked at /plan-eng-review):
  - data/canonical.jsonl  : COMMITTED rows. Append-only. Git-tracked.
  - data/pending.db       : SQLite, mutable working state. NOT git-tracked.
  - data/rejected.jsonl   : REJECTED rows. Append-only audit. Git-tracked.

Cross-platform locking:
  - POSIX  : fcntl.flock (exclusive, blocking)
  - Windows: msvcrt.locking (exclusive)

Implementation lands in Milestone 1. This module is a placeholder.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from mnemex.schema import CanonicalRow

DEFAULT_DATA_DIR = Path("data")
CANONICAL_PATH = DEFAULT_DATA_DIR / "canonical.jsonl"
PENDING_DB_PATH = DEFAULT_DATA_DIR / "pending.db"
REJECTED_PATH = DEFAULT_DATA_DIR / "rejected.jsonl"
REVIEW_LOCK_PATH = DEFAULT_DATA_DIR / ".review.lock"


def read_canonical(path: Path = CANONICAL_PATH) -> Iterator[CanonicalRow]:
    """Iterate over committed CanonicalRow records from data/canonical.jsonl.

    Lazy iterator: opens the file, yields one row per line, closes on
    completion. Safe to call concurrently with appends (the file is
    append-only).

    Implementation in Milestone 1.
    """
    raise NotImplementedError("read_canonical lands in Milestone 1")


def read_pending(state: str = "pending") -> Iterator[CanonicalRow]:
    """Iterate over rows in pending.db filtered by review_state.

    state must be one of: "pending", "verified", or "all".
    Implementation in Milestone 1.
    """
    raise NotImplementedError("read_pending lands in Milestone 1")


def commit_pending(row_id: str, verified_by: str) -> None:
    """Promote a verified row from pending.db to canonical.jsonl.

    Atomic: SQLite transaction wrapping the JSONL append, with cross-platform
    locking on the JSONL file. On crash mid-commit, mnemex doctor reconciles.

    Implementation in Milestone 1.
    """
    raise NotImplementedError("commit_pending lands in Milestone 1")
