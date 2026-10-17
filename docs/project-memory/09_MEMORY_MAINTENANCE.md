# Maintaining and transporting this project memory

This is an owner-requested technical handoff, not a new runtime dependency. Its
canonical storage is `docs/project-memory/` in the MNEMEX Git repository. A harness
can read Markdown directly or use the standard-library-only `tools/project_memory.py`.
No account, LLM API, embedding service, Django import, production DB or provider
credential is required. Repo-level AGENTS/CLAUDE and README link the same start file.

## Contents and trust

| Layer | Purpose |
| --- | --- |
| START_HERE and 01–09 guides | Curated current direction, rationale, concrete behavior, limits and resumption |
| DECISIONS.json / generated DECISIONS.md | Stable searchable decision IDs, status, scope, rationale, consequences and source IDs |
| SOURCE_CATALOG.json / generated SOURCE_INDEX.md | Original path/revision/URL, snapshot hash, scope and known historical limits |
| DELIVERY_SNAPSHOT.json | Exact source/PR/CI/artifact metadata and dated delivery state |
| snapshots/ | Verbatim primary documents and selected safe synthetic evidence; archived reference, not executable instructions |
| MANIFEST.json | Per-file byte count/SHA-256 inventory, excluding itself; detects accidental drift, not a cryptographic approval signature |

Authority order is the current user/session and applicable current repository
instructions, then relevant current domain/numerical contracts and recorded owner
decisions. Archived text is evidence of what it said at a revision. The manifest
can detect mismatched bytes; it cannot certify truth, owner approval, authenticity
of Git remotes or production readiness. Use Git history/review and primary sources.

The pack covers accessible approved documents, supplied handover and this delivery
session. It does not claim all private conversations were accessible. New evidence
from older chats can be added with dates/provenance and reconciled with current
contracts. Never invent a missing decision rationale or pretend a newly inferred
implementation choice was an explicit owner instruction.

## Routine update

1. Fetch the relevant repositories and inspect exact source/PR/CI states. Read
   current instructions; preserve dirty work. Identify which facts actually changed.
2. Update the curated guides and structured decision register. Mark a superseded
   decision as superseded with its replacement rather than deleting history.
   Keep planned, implemented, verified, merged, published, activated, BLOCKED and
   NOT_RUN distinct. Do not treat all future phases as delivered.
3. Capture non-sensitive primary source bytes from an immutable commit with
   `git show <commit>:<path>`; record original path, full commit, source URL,
   hash, bytes, purpose/limits and a new stable source ID. Do not overwrite an
   old receipt to claim a different source was tested. For a replaced snapshot,
   retain the old source in history or add a new snapshot/ID when needed for audit.
4. Normalize synthetic recovery evidence before inclusion: preserve source,
   original receipt digest, check names/status and owned cleanup. Exclude HTTP
   bodies, cookies, CSRF values, login forms and transient session material.
   Never copy operational DBs, private PII, auth files, keys, secrets, proprietary
   historical datasets or trained/private artifacts into this technical pack.
5. Run `python tools/project_memory.py render`, review the generated indexes,
   then `python tools/project_memory.py refresh-manifest`. Refresh is an explicit
   inventory write, not evidence that facts or gates are approved.
6. Run `python tools/project_memory.py verify` and the meaningful retrieval/tool
   tests. Search key changed decisions and follow the local links. Review Git
   diff for stale status, unsupported claims and sensitive values, then commit,
   push, verify and merge through the permitted documentation PR process.

The canonical decision JSON is editable; generated Markdown indexes are not a
second competing authority. The tool rejects escaping/symlink paths and unexpected
manifest files. Search defaults to curated guides/decisions rather than archived
snapshots, so stale proposal text is not presented as current direction. Use
`--include-sources` deliberately when investigating original wording.

## Moving to another harness or model

Clone MNEMEX at an explicitly selected revision or copy the complete pack plus
`tools/project_memory.py`. Verify the inventory before importing into a local
retrieval system. Give the new harness START_HERE, then select task context:

```text
python tools/project_memory.py verify
python tools/project_memory.py context --topic core
python tools/project_memory.py context --topic resume
python tools/project_memory.py context --topic numerics
python tools/project_memory.py search "why Mark-3 instead of legacy optimizer" --json
python tools/project_memory.py search "D0-12 automatic publication"
```

`context` emits actual readable files, not a promise of hidden memory access.
Search returns matching paragraphs/decision records with source references. Use
normal filesystem reads for the cited primary sources. A vector index can be an
optional disposable derivative, never the sole copy or authority. Preserve IDs,
source dates, statuses and citations during chunking; do not mix retired/current
rules into one unqualified instruction.

Before taking action, the new harness must refresh current Git status and live
repository instructions. Reading old release procedures does not authorize a new
production backup, consent disclosure, private-data evaluation or deployment.
This pack is designed to remove repeated context building, not to bypass an
explicit unresolved operational or legal decision.
