"""Supabase direct-write adapter — DEFERRED to v1.1+.

Same rationale as http.py: v1 ships JSONL only.
"""

from __future__ import annotations


def write(rows, schema="strathmark_staging", dry_run=False):  # type: ignore[no-untyped-def]
    raise NotImplementedError(
        "Supabase STRATHMARK adapter is v1.1+. v1 ships JSONL only. "
        "See design doc 'Deferred to v1.1+: HTTP POST and Supabase direct write'."
    )
