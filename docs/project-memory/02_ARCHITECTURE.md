# Architecture, authority and contracts

Sources: [S02](SOURCE_INDEX.md#s02), [S06](SOURCE_INDEX.md#s06),
[S17](SOURCE_INDEX.md#s17), [S24](SOURCE_INDEX.md#s24), [S28](SOURCE_INDEX.md#s28),
[S30](SOURCE_INDEX.md#s30), [S31](SOURCE_INDEX.md#s31).

## Responsibility map

| Responsibility | Authority | Consumer behavior |
| --- | --- | --- |
| Permanent person, aliases, grants, reconciled career history | MNEMEX | Shows retain scoped references and authorized snapshots |
| Predictions, uncertainty, marks and calculation provenance | STRATHMARK calculation layer | Plain clients can request calculations without opening an operational event |
| Delegated fields, review, issue, outcomes, advancement, correction | STRATHMARK event operations acting for officials | CLI/shared GUI/host controls call one application boundary |
| Registration, entries, program, flights, cross-event resources/rest | Host | Supplies actual roster/configuration/physical constraints and chooses schedule placement |
| Accepted source projection, tournament points, payouts | Host | Accepts immutable revisions and applies awards explicitly |
| Operator prompts, forms, navigation and printing | Client presentation | Does not implement alternative numeric or progression authority |

An event has one operational authority. MNEMEX's permanent career record does
not prohibit local event databases, caches, ledgers, accepted projections or
archives. It establishes one cross-show person/history authority with provenance
back to the original official event. A reconciled copy never silently replaces
the source result.

## Integration modes and interfaces

**Calculation-only:** the host controls its event workflow. A calculation receipt
is evidence about numbers, not permission to issue a start sheet. Existing V2
direct Python and explicitly selected HTTP paths retain their contracts.

**Delegated:** a host deliberately creates/links a supported event in
`strathmark.events`. The same operations support CLI, local trusted-process RPC,
the optional authenticated Flask workspace and host controls. The shared layer
does not import Missoula's ORM or request objects and does not assume a particular UI.

The first profile is local OS-private synthetic SB/UH, using the real V2
predictor. A hosted direction is approved, but a loopback development server is
not hosted deployment qualification. Broad V3 service credentials are not browser
credentials; actor strings alone do not authenticate a person over a public API.

## Runtime separation

Missoula keeps its supported Python 3.10 and retained STRATHMARK 2.x pin. It
selects an explicit separate managed interpreter/database; the verified delivery
used Python 3.13.15 and indexed `strathmark==3.0.0rc11`. It never imports an
incompatible V3 runtime into the host or uses the old library after process failure.

The installed core calculation/event CLI works without Flask, STRATHEX, Missoula
or MNEMEX. `strathmark[workspace]` adds the optional shared UI. STRATHEX's explicit
managed launcher branches before legacy startup and delegates to that interpreter.
Its retained retro/V2/V3 profile pins remain distinct. Package version, numerical
engine version, model/calibration identity, consumer contract and OS qualification
are separate facts.

## Event contract and lifecycle

`strathmark.managed-event.v1` binds show/tournament/event, configured discipline
and format, source-show publisher, dated pseudonymous evidence, roster entries,
host references, physical stands, gear groups, timer policy, round capacity,
qualification/tie rules, selected numerical root and operational revision.
Unsupported combinations fail rather than borrowing another profile.

The functional lifecycle includes:

```text
configure/roster -> forecast for seeding -> exact fields -> calculate
-> whole-sheet review -> separate confirmed issue -> complete outcomes
-> explicit result acceptance -> advancement/tie decision -> later fields
-> complete accepted final -> finalization -> export/host acceptance
-> explicit host awards -> supervised career delivery
```

Forecasts contain no issued mark. Exact heat membership and stands precede
field-relative calculation. Round/heat IDs remain stable; heat identities cannot
collide with earlier rounds. A sheet digest and issue identity bind subsequent
outcomes. Raw timers, derived raw duration, start count and common-count completion
remain separately labeled. Every attempted heat/result revision is distinct from
the final participant summary.

The root fixes engine, numerical runtime and mark policy. Child events/rounds
inherit them. New fields rebase from underlying predictions/evidence, not the
displayed marks of independently rebased earlier heats.

## Commands, retries and concurrency

Each mutation carries a stable request ID, actor/principal, editor, canonical
payload and expected revision. An exact accepted retry returns its original
receipt before stale-revision checks. A changed payload under the same identity
conflicts. New stale edits cannot overwrite later corrections.

CLI/GUI handover changes event revision and mutation ownership; it does not change
physical field identity or invalidate issued marks. Read-only views can coexist.
The first implementation uses controlled ownership rather than competing copies.

Corrections append revisions. They invalidate unissued dependent preparation.
Already issued/completed descendants remain frozen and require explicit director
review, including a retained reason, actor/time/revision and exact issue/result
bindings. Finalization requires every latest result used by the summary to be
accepted, including corrected earlier rounds.

## Missoula adapter and host transaction

Binding is allowed only for a fresh supported individual handicap event. It
validates complete active host entries, divisions, configured wood, gear and
canonical physical stands. A 275 mm synthetic example does not override show
WoodConfig. Existing host heats prevent binding. A pending creation keeps legacy
scoring fenced until its source outcome is recovered; it is not deleted to guess
that a remote create failed.

The host commits durable command intent before RPC. Insert-only source creation
and source actor/request/config provenance identify the accepted initial mapping.
A refused configuration can receive a new durable corrected request; an earlier
ambiguous source success cannot be overwritten. Pending original retries first
consult verified source audit, so later host registration edits cannot hide a
command that already committed.

The adapter projects module fields into host `HeatAssignment` rows for scheduling.
It does not autonomously reorder the entire show. Projection advances monotonically
under tournament/event locks; delayed responses keep their own valid receipts
without regressing the latest host state. Preparation and new acceptance reload
host registration facts. Unchanged source configuration cannot conceal added or
removed active entries.

Host acceptance atomically stores source attempt revisions, career-delivery
intents, current summary and acceptance receipt. Exact retries are immutable;
stale source exports are refused. Accepted positions drive separate points/payout
actions, with college individual/team totals and the existing pro tie purse rules.
A non-finalized correction acceptance reopens host finalization and clears summary
award eligibility. Earlier award/settlement facts remain for explicit reconciliation.
Re-finalized source results require fresh acceptance and an explicit host award
action. Finalized metadata-only revisions preserve award finalization.

Legacy mark/scoring/progression writers refuse managed events. Global scratch
cascades and college competitor/team deletion protect retained managed mappings,
including pending/unissued events. Registration gear synchronization skips pending
and issued managed fields, explains that action, and can still repair independent
host fields. Scheduled unissued field replacement requires digest-bound explicit
unscheduling from a still-pending flight; issued or started history stays protected.

## Source fence through host commit

The selected rc11 component verifies an export under its SQLite writer mutex and
returns opaque state digests through a private helper protocol. The host takes
its own existing-file SQLite mutex and compares the verified bytes again. An
intervening source write fails the handoff. That host-owned mutex survives helper
exit through actual host DBAPI commit/rollback/close. Savepoints do not release
the outer fence. Bulk award operations acquire all selected source events before
host schedule/event locks.

The Python 3.10 host interprets no numerical or progression rules here; it compares
opaque bytes under a schema/runtime adapter pinned to exact rc11. This is a local
coordination contract, not a claim of distributed/hosted two-phase commit. A new
runtime/schema requires revalidation. Synthetic process-kill and competing-writer
tests established the supported local behavior.

## MNEMEX result path

The host is the default outward publisher after accepting a source revision.
Standalone sessions declare their own source-show/export identity. Do not send
two unrelated authoritative versions from host and component.

`strathmark.source-result.v1` carries source/revision/predecessor, event date and
wood, round/heat/entry/issue/field identity, explicit clocks, status, position and
correction evidence. The host wraps it in the narrow `mnemex.show-result.v1`
envelope using scoped references. A bounded supervised batch records pending,
conflicting or acknowledged delivery and verifies receiver receipt bindings.
MNEMEX downtime never undoes accepted event results.

The implemented registered-source sandbox HTTP receiver preserves immutable
source revisions and rejected valid conflict envelopes, authenticating credential
provenance, predecessor continuity and entry/issue binding. Out-of-order messages
remain pending until the contiguous chain is valid. All received identities
remain unlinked. This does not implement consented full profile portability or
public career publication. Shadow prediction settlement is a different outbox.

## Storage and recovery ownership

STRATHMARK owns its event SQLite authority and sibling independent head reference.
Missoula owns additive managed mapping/command/field/attempt/acceptance/delivery
tables. MNEMEX owns its transactional Django/PostgreSQL inbox/provenance/receipt
boundary. Clients call supported operations; no component writes directly into
another component's authoritative business tables.

A backup is a candidate, not permission for a second active authority. Local
transfer uses deliberate fencing and original receipts; stale/corrupt/incompatible
candidates fail closed. Retain an independently accessible issued sheet before
racing. Manual outcomes can reference that exact issue during outage; unissued
fields pause. Traditional/manual authority requires a separately recorded director
decision, with no fabricated engine-issued receipt or automatic cloud/local failover.
