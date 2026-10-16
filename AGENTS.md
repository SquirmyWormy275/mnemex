# Agent instructions

The October 15 approved modular effort adds a bounded
[synthetic show-result inbox](docs/SHOW_RESULT_CONTRACT.md). It preserves
unlinked source attempts and explicit receipts without enabling full profile
portability or production. Shared components are developed incrementally with
Missoula as the integration testbed; the historical warning against speculative
wholesale platform replacement does not prohibit this approved work.


Read [CLAUDE.md](CLAUDE.md), then the current README and August 14 approved
architecture/build decisions linked there. They govern all agents working here.
The earlier historical-only scraper plan is superseded.

Use synthetic data and isolated Django test settings. Preserve source provenance,
tenant and consent boundaries, the reviewed SB/UH-only STRATHMARK 2.x export
contract, and all production activation gates. Never restore the retired
scheduled production exporter or write directly to a show's scoring database.
