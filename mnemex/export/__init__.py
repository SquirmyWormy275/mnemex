"""Export hub — produces output formats from canonical.jsonl.

v1 formats:
  csv.py        -- standard CSV
  json.py       -- pretty-printed JSON with full schema
  excel.py      -- legacy 9-column XLSX + richer multi-sheet variant

v1.1+ deferred:
  parquet.py    -- pyarrow-based Parquet
  sqlite.py     -- SQLite database export

Implementations land in Milestone 6.
"""

from __future__ import annotations
