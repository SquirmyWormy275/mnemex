from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION = "strathmark.evidence-snapshot-source.v1"
EVIDENCE_HISTORY_ROW_SCHEMA_VERSION = "strathmark.evidence-history-row.v1"
STRATHMARK_EXPORT_DISCIPLINE_MAP = {"STANDING_BLOCK": "SB", "UNDERHAND": "UH"}
STRATHMARK_MAX_EVIDENCE_ROWS = 100_000
STRATHMARK_MAX_EVIDENCE_SOURCE_BYTES = 32 * 1024 * 1024

_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,31}:[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,94}$")
SPECIES_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def validate_namespaced_id(value: str, label: str) -> str:
    normalized = value.strip()
    if len(normalized) > 128 or not _NAMESPACED_ID.fullmatch(normalized):
        raise ValueError(f"{label} must be a bounded namespaced identifier")
    return normalized


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def canonical_source_bytes(
    *,
    source_id: str,
    cutoff: date,
    captured_at: datetime,
    rows: Sequence[Mapping[str, Any]],
) -> bytes:
    source = validate_namespaced_id(source_id, "source_id")
    if isinstance(cutoff, datetime) or not isinstance(cutoff, date):
        raise ValueError("cutoff must be a date without a time")
    material = {
        "schema_version": EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
        "source_id": source,
        "cutoff": cutoff.isoformat(),
        "cutoff_semantics": "exclusive-utc-date",
        "captured_at": utc_iso(captured_at),
        "rows": list(rows),
    }
    return json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_source_digest(
    *,
    source_id: str,
    cutoff: date,
    captured_at: datetime,
    rows: Sequence[Mapping[str, Any]],
    max_bytes: int | None = None,
) -> str:
    encoded = canonical_source_bytes(
        source_id=source_id,
        cutoff=cutoff,
        captured_at=captured_at,
        rows=rows,
    )
    if max_bytes is not None and len(encoded) > max_bytes:
        raise ValueError(f"canonical source envelope exceeds {max_bytes} bytes")
    return hashlib.sha256(encoded).hexdigest()


def pseudonymous_id(namespace: str, *components: object) -> str:
    digest = hashlib.sha256(
        "\x1f".join(str(component) for component in components).encode("utf-8")
    ).hexdigest()[:40]
    return f"mnemex:{namespace}:{digest}"
