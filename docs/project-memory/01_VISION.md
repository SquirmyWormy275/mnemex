# Vision, priorities and settled direction

Primary authority: [S01](SOURCE_INDEX.md#s01), [S02](SOURCE_INDEX.md#s02),
[S28](SOURCE_INDEX.md#s28), [S29](SOURCE_INDEX.md#s29), [S37](SOURCE_INDEX.md#s37).
The [decision register](DECISIONS.md) separates owner choices from implementation
consequences and dated implementation status.

## What the owner is building

STRATHEX is the parent ecosystem and tournament-management direction. Missoula
Pro-Am Manager is its first working real-world pilot. STRATHMARK supplies
handicap calculation and, when explicitly delegated, event operations. MNEMEX
provides the person, portable profile, provenance and career-history foundation.
The desired result is reuse without rebuilding handicap, identity, history and
event behavior for each new show.

Modularity applies to the whole design: shows select supported events and
configure rules, resources, divisions, schedules and presentation. Reusability
must be demonstrated with real working contracts and a second synthetic show.
It is not permission to replace every show application, invent a generic event
bus/plugin system, or implement every sporting discipline before one bounded
family works end to end.

The owner explicitly selected Missoula as the integration testbed from the
beginning. A separate synthetic demonstration cannot become a prerequisite that
indefinitely postpones the working show's adapter. STRATHEX's functional retro
terminal remains a product deliverable and reference client, not disposable
scaffolding. Preserve existing saved competitions and judge-canonical Excel.

MNEMEX's identity/profile ambition is larger than a historical scraper. A
competitor should maintain one consent-aware profile and take an authorized
projection to participating shows. The integrated Results Desk allows authorized
staff to turn historical spreadsheets/manual entry into source-backed history.
None of this makes a central service the live scoring authority or a mandatory
race-day dependency.

## Approved October product choices

These twelve choices follow the owner execution handover's numbering.
`DECISIONS.json` cross-references their themes with the detailed domain and
implementation decisions; its IDs are independent of this numbered list.

1. Integrate Missoula from the outset while preserving STRATHEX.
2. Make event capabilities reusable/configurable across shows.
3. Preserve independent calculation-only access and add full delegation.
4. Deliver an operational standalone STRATHMARK CLI accepting supplied data.
5. Keep the graphical handicap workspace shared and optional.
6. Keep one authoritative event state, initially with controlled editor handover.
7. Prepare MNEMEX's person/history/results boundary without blocking on full deployment.
8. Allow the approved hosted direction while preserving supported local execution.
9. Preserve Missoula's existing sporting rules during boundary changes.
10. Prove cross-show reuse, outages, retry/restart, correction and recovery.
11. Separate numerical behavior changes from architecture extraction.
12. Reconcile current repository guidance and preserve historical decisions visibly.

These are implementation instructions, not an invitation to ask the owner to
choose the same options again. Missing keys, future data, provider evidence or
release approvals are concrete inputs/gates; they do not undo the product direction.

## Longer-term MNEMEX choices

The August 14 D0 selections remain binding within their scope. They include
minors in the first pilot, an expanded profile with encrypted legal identity,
explicitly opt-in public pages, MNEMEX-owned authentication built on maintained
primitives, and multiple shows from the first schema. Portability validation is
online before lock; afterward a show uses its pinned local snapshot. Server-side
transactions own authoritative mutation. Recovery/retention proof precedes PII.
Legacy history is bulk staged before pilot career activation. The Results Desk
is integrated into one Django modular monolith; Railway plus Supabase is the
selected hosting shape, subject to provider qualification. Archive capture is
broad, while reviewed STRATHMARK history export stays SB/UH-only. Deterministically
valid source rows publish to the **private archive** automatically; identity,
career, public visibility and export trust do not follow automatically.

Some D0 selections were not the workshop's recommended options. The selected
owner option wins. Read [S29](SOURCE_INDEX.md#s29) rather than recovering a product
choice from an old recommendation table.

## Design principles that recur across the work

- One authority per responsibility, with explicit references and reconciled copies.
- Stable identities for consequential writes; display names never substitute for IDs.
- Exact request identity, canonical payload binding, expected revisions and durable receipts.
- Append corrections and provenance; do not erase prior results to make state look clean.
- Keep preparation, review, issue, official acceptance, publication and payout distinct.
- Make unavailable/unsupported capabilities visible; do not silently switch runtime or engine.
- Protect the exact field and physical stands before calculating or issuing marks.
- Use existing numerical engines, domain services, transactions and frameworks.
- Keep GUI/provider dependencies optional where the core CLI/calculation can stand alone.
- Preserve local operational storage, issued sheets, receipts and recovery context.
- Keep sensitive person data out of numerical evidence, logs and public artifacts.
- Distinguish implemented, verified, merged, published, deployed and official activation.
- Record failed runs and their causes; do not weaken a check to call delivery complete.

## Direction versus current scope

The first managed family is bounded to **synthetic individual SB/UH handicap**.
The example 275 mm underhand event proves configuration; it is not Missoula's
new default block size, a new real tournament, or a complete general-sports suite.
The new managed layer runs the real V2 predictor. Full MNEMEX profiles, public
career pages, participating-show portability and hosted activation remain larger
programs. The implemented sandbox receiver is useful now without claiming those
programs complete.

Future event families should fit the discipline/format/configuration extension
boundary and preserve authority invariants. A new family needs an explicit
capability/contract and real tests; a label in the GUI is not support. Broader
reuse should grow from working integrations rather than speculative replacement.

## What success means to the owner

A configurable event works through Missoula in normal show context, qualifying
heats progress through later rounds to a final, and terminal/shared GUI use the
same operations. It survives restart, ambiguous responses and corrections. The
same installed component runs a different synthetic show without source edits.
Career/result boundaries work with MNEMEX unavailable during racing. Existing
official/shadow events and retro saves retain their authority. Current agents
and future models can locate the decisions and implementation evidence without
reconstructing a long conversation.

Writing a design, adding tables, drawing a screen or making a fake successful
request does not meet that standard. Neither does calling a published package
production-enabled. The [delivery ledger](06_DELIVERY.md) records the actual
functional proof and the operational gates that still prevent Missoula's merge.
