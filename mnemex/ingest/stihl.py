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

# Identifying User-Agent. Replaces the legacy TimbersportsScraper.py
# behaviour of sending a Mozilla/5.0 string that impersonates a browser.
# This UA identifies MNEMEX so server operators can:
#   - distinguish our traffic from real users in their logs
#   - reach us if our scraping is causing load problems
#   - opt us out via robots.txt with confidence
#
# All new scraper code paths in mnemex/ingest/* MUST use this UA on every
# outbound HTTP request. The legacy TimbersportsScraper.py is slated for
# deletion at M2 and is intentionally not modified.
USER_AGENT: str = (
    "MNEMEX/0.1.0 (+https://github.com/SquirmyWormy275/mnemex; "
    "admin@mnemex.example)"
)
