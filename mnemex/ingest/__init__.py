"""Ingest package — five paths, all funneling into the pending queue.

Per the design doc, v1 ships:
  stihl       -- existing TimbersportsScraper.py refactored
  college_excel -- Vision-LLM Excel parser (libreoffice render -> LLM)
  newsletter  -- Vision-LLM PDF parser (pypdfium2 render -> LLM)
  image       -- Vision-LLM single-image parser
  manual      -- paste-in CSV importer

All five emit CanonicalRow records with provenance and (when extraction
is uncertain) ExtractionStatus values that surface in mnemex review.

Concrete implementations land in M2-M4.5.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from mnemex.schema import CanonicalRow


class IngestSource(ABC):
    """ABC for any ingest path. Concrete classes:
    StihlIngest, CollegeExcelIngest, NewsletterIngest, ImageIngest, ManualCsvIngest.

    The contract is small on purpose: each source produces an iterable
    of CanonicalRow records. The pending-queue write happens in the
    caller (mnemex.review module), not in the source. This keeps ingest
    logic stateless and testable in isolation.
    """

    @abstractmethod
    def extract(self) -> Iterator[CanonicalRow]:
        """Yield CanonicalRow records. May yield rows with extraction_status
        != OK when the underlying extraction had problems; the review queue
        decides how to handle them."""
        ...


__all__ = ["IngestSource"]
