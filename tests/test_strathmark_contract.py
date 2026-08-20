"""Installed STRATHMARK 2.x evidence-snapshot contract smoke tests."""

from __future__ import annotations

import pytest


@pytest.mark.strathmark_contract
def test_strathmark_is_importable() -> None:
    """The optional consumer dependency is installed for contract CI."""
    try:
        import strathmark
    except ImportError:
        pytest.skip(
            'strathmark not installed. Install with `pip install -e ".[dev]"` '
            "from the MNEMEX repo root."
        )
    assert hasattr(strathmark, "__version__"), "strathmark must expose __version__"


@pytest.mark.strathmark_contract
def test_strathmark_version_in_pinned_range() -> None:
    """MNEMEX targets the STRATHMARK 2.x evidence-snapshot source protocol."""
    strathmark = pytest.importorskip("strathmark")
    version = getattr(strathmark, "__version__", None)
    assert version is not None, "strathmark must expose __version__"
    parts = version.split(".")
    major, minor = int(parts[0]), int(parts[1])
    assert major >= 2, f"strathmark too old: {version}"
    assert major < 3, (
        f"strathmark too new for current MNEMEX pin: {version}. "
        f"Run the STRATHMARK upgrade protocol from the design doc."
    )


@pytest.mark.strathmark_contract
def test_evidence_snapshot_types_are_importable() -> None:
    """The source adapter targets the durable offline snapshot protocol."""
    pytest.importorskip("strathmark")
    from strathmark.store import EvidenceSnapshotPayload, ResultStore  # noqa: F401


def test_legacy_direct_export_paths_fail_closed(monkeypatch, tmp_path) -> None:
    from mnemex.strathmark_adapter import http, jsonl, supabase, tier1, tier2

    monkeypatch.setenv("MNEMEX_ENABLE_TIER2", "1")
    assert tier2.is_enabled() is False
    for operation in (
        lambda: tier1.to_strathmark_results([]),
        lambda: tier2.to_strathmark_results([]),
        lambda: jsonl.write([], tmp_path / "legacy.jsonl"),
        lambda: http.post([], "https://example.invalid"),
        lambda: supabase.write([]),
    ):
        with pytest.raises(PermissionError):
            operation()
