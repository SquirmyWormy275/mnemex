"""STIHL HTML scraper — refactor of the existing TimbersportsScraper.py.

Implementation lands in Milestone 2:
  - Refactor TimbersportsScraper.py into this module
  - Output CanonicalRow instances (not 9-col Excel as primary)
  - Preserve the 1-second rate limit (constant + test, see Operational Concerns)

The 1.0s minimum delay is non-negotiable per CLAUDE.md and STRATHMARK ethos.
"""

from __future__ import annotations

# Non-negotiable rate-limit floor. Tests in tests/test_stihl_rate_limit.py
# assert that the scraper observes at least this delay between requests.
# Configuration cannot reduce below the constant; attempts raise ValueError.
MIN_REQUEST_DELAY_SEC: float = 1.0

# The base URL is currently configurable per the legacy scraper. Hardcoded
# for the typical case; can be overridden for testing against fixtures.
DEFAULT_BASE_URL = "https://data.stihl-timbersports.com"
