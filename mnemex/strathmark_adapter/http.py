"""HTTP adapter to STRATHMARK FastAPI — DEFERRED to v1.1+.

Per the design doc: v1 ships JSONL only. HTTP and Supabase paths are
designed and stubbed but not implemented in v1. They serve a single use
case (live tournament ingest into a running STRATHMARK instance) which
is STRATHEX-driven and post-v1.
"""

from __future__ import annotations


def post(rows, endpoint, token=None, dry_run=False):  # type: ignore[no-untyped-def]
    raise NotImplementedError(
        "HTTP STRATHMARK adapter is v1.1+. v1 ships JSONL only. "
        "See design doc 'Deferred to v1.1+: HTTP POST and Supabase direct write'."
    )
