from __future__ import annotations

from datetime import date
from typing import Any

from mnemex.export.models import EvidenceSnapshotManifest


class StoredEvidenceSnapshotSource:
    """Read-only STRATHMARK 2.x source adapter over one frozen MNEMEX manifest."""

    def __init__(self, snapshot: EvidenceSnapshotManifest):
        self._source_id = snapshot.source_id
        self._cutoff = snapshot.cutoff
        self._captured_at = snapshot.captured_at
        self._rows = tuple(dict(row) for row in snapshot.rows)
        self._source_digest = snapshot.source_digest

    def load_snapshot(self, *, cutoff: date) -> Any:
        if cutoff != self._cutoff:
            raise ValueError("snapshot source cutoff does not match the requested cutoff")
        try:
            from strathmark.store import EvidenceSnapshotPayload  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - minimal installs
            raise RuntimeError(
                'STRATHMARK 2.x is required; install MNEMEX with the "strathmark" extra'
            ) from exc
        return EvidenceSnapshotPayload(
            schema_version="strathmark.evidence-snapshot-source.v1",
            source_id=self._source_id,
            cutoff=self._cutoff,
            captured_at=self._captured_at,
            rows=self._rows,
            source_digest=self._source_digest,
        )
