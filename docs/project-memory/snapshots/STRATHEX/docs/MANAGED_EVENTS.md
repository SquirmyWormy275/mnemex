# Shared managed events

STRATHEX 7.4.3 preserves the retro terminal application and its existing V2/V3,
workbook, result and recovery contracts. New delegated sessions are explicit:
their state belongs to the shared component. No existing save or workbook is
automatically converted. The first managed profile is synthetic individual
SB/UH with real V2 predictions; official use is disabled.

Install `requirements-managed-runtime.txt` in a **separate** Python 3.10–3.13
environment. Keep STRATHEX's existing reviewed V2 dependency and any saved V3
runtime unchanged. From the normal STRATHEX environment:

```bash
strathex --managed-cli-python /path/to/managed/bin/python --managed capabilities
strathex --managed-cli-python /path/to/managed/bin/python --managed event status \
  --database /private/events.sqlite3 --show synthetic:missoula \
  --event-id synthetic:missoula:underhand
strathex --managed-workspace-url http://127.0.0.1:8789 \
  --managed-event-id synthetic:missoula:underhand
```

The first two commands run the same installed STRATHMARK application operations
used by Missoula and the shared GUI. They do not enter legacy startup or open an
operator workbook. Runtime failure is visible and never triggers another engine.
The workspace link carries an event identity, never a service token. Sign in
there with the configured scoped operator account. Remote origins require HTTPS;
credential-bearing, path-bearing or token-bearing launch origins are refused.
Switch mutating interfaces only through deliberate editor handover. Read-only
views can coexist and stale writes conflict.

Use the [STRATHMARK operations guide](https://github.com/SquirmyWormy275/STRATHMARK/blob/main/docs/MANAGED_EVENTS.md)
for supplied-data creation, fields, review, issue, outcomes, advancement,
correction, export, private accounts and fenced recovery. The
[shared agreement](https://github.com/SquirmyWormy275/STRATHMARK/blob/main/docs/MODULAR_ECOSYSTEM.md)
defines host scheduling, accepted projections and MNEMEX publishing ownership.
