"""STRATHMARK contract test — placeholder.

The full contract test (type shape + JSONL round-trip + no-silent-loss)
lands in Milestone 6 alongside the Tier 1 adapter implementation.

For Milestone 0, this file just confirms strathmark is importable.
"""

from __future__ import annotations

import pytest


@pytest.mark.strathmark_contract
def test_strathmark_is_importable() -> None:
    """Confirms the pinned STRATHMARK version is installed and importable.

    The contract test in M6 will:
      1. Build a fixture set of CanonicalRow records.
      2. Project Tier 1 via mnemex.strathmark_adapter.tier1.to_strathmark_results.
      3. Serialize via mnemex.strathmark_adapter.jsonl.write.
      4. Subprocess-invoke STRATHMARK's import_legacy.py --dry-run.
      5. Assert exit code 0 AND no Tier 1 row was silently dropped.
    """
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
    """The pyproject pin is `strathmark>=0.4.1,<0.6`. Contract test runs
    against the installed version. M6 will tighten this to an exact pin
    (`==0.4.1`) for the contract-test job specifically."""
    strathmark = pytest.importorskip("strathmark")
    version = getattr(strathmark, "__version__", None)
    assert version is not None, "strathmark must expose __version__"
    parts = version.split(".")
    major, minor = int(parts[0]), int(parts[1])
    # Allow 0.4.x through 0.5.x; reject 0.6+ until MNEMEX is updated.
    assert (major, minor) >= (0, 4), f"strathmark too old: {version}"
    assert (major, minor) < (0, 6), (
        f"strathmark too new for current MNEMEX pin: {version}. "
        f"Run the STRATHMARK upgrade protocol from the design doc."
    )


@pytest.mark.strathmark_contract
def test_historical_result_is_importable() -> None:
    """The Tier 1 adapter projects to strathmark.predictor.HistoricalResult."""
    pytest.importorskip("strathmark")
    from strathmark.predictor import HistoricalResult  # noqa: F401
