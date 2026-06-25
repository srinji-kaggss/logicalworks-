---
type: Reference
title: U8 — Concurrent Stress Bot
description: Status: spec
tags: [bot-fabric, reference]
timestamp: 2026-06-06T13:13:23-04:00
---

# U8 — Concurrent Stress Bot

Status: spec

## Purpose

Surface real race conditions, artifact corruption, lock failures, and recovery gaps
by running multiple bot workers concurrently against a shared store.

Reckless by design. Emits everything it observes. The reducer filters.

## L budget

0. No LLM calls. All observations are deterministic given the run seed.

## Trigger

Manual CLI invocation or explicit CI gate. Not wired to the git hook —
this is a deliberate stress run, not a passive background watcher.

## Inputs

- repo path
- store path (the shared artifact store being stressed)
- worker count N (default 4)
- run seed (for reproducibility of injection timing)
- scenario list (subset of defined scenarios, or all)

## What it does

Spawns N real subprocesses — each running a bot or CLI verb — against
the same shared store simultaneously. Observes and records what breaks.

This is not simulation. The subprocesses actually run, write, and collide.

## Scenario families

### C1 — Concurrent write collision

Spawn N workers all writing to the same artifact path simultaneously.
Observe: last-write-wins, partial writes, truncation, silent data loss.

Kinds emitted: `write_collision`, `partial_write`, `silent_data_loss`

### C2 — Read-during-write inconsistency

One worker writes a JSONL artifact while N-1 workers read it.
Observe: partial reads, schema-invalid mid-write snapshots, empty reads.

Kinds emitted: `read_during_write`, `schema_violation_under_load`

### C3 — Lock failure / missing lock

Two workers attempt to acquire the same resource with no lock mechanism.
Observe: both succeed (missing lock), one hangs indefinitely (deadlock),
or one silently overwrites the other.

Kinds emitted: `missing_lock`, `deadlock_risk`, `silent_overwrite`

### C4 — Degraded dependency

Kill one subprocess mid-write. Observe recovery behavior of remaining workers.
Does the store end up in a consistent state? Does any worker detect the failure?
Does replay reproduce the correct final state?

Kinds emitted: `no_retry_path`, `recovery_gap`, `replay_violation`

### C5 — Cascading failure

One worker emits a schema-invalid record. Observe whether downstream workers
(reducer, package builder) propagate the invalid record or catch it.

Kinds emitted: `cascade_failure`, `invalid_record_propagation`

## Evidence structure

Each finding carries:
- worker IDs involved
- scenario name
- observed artifact state (diff or hash)
- expected state
- reproduction command (the exact subprocess invocations + seed)

## Severity mapping

- `critical`: silent data loss, cascade propagation of invalid records
- `high`: missing lock, recovery gap, replay violation
- `medium`: read-during-write inconsistency
- `low`: partial write caught and recoverable

## Design constraints

1. run seed makes the timing reproducible within a tolerance window
2. all subprocess invocations are logged — reproduction command in every finding
3. the store is restored to a clean state after the run (or the finding records the dirty state)
4. the bot itself must not corrupt the store permanently — use a temp copy unless --live is passed
5. emit recklessly — record every anomaly observed, not just the worst one

## Likely file targets

- `lgwks_bot_stress.py`
- `tests/test_bot_stress.py`

## Acceptance

1. Write collision detected from seeded concurrent write fixture.
2. Missing lock detected when two workers write without coordination.
3. Recovery gap detected when a worker is killed mid-write.
4. Cascade failure detected when an invalid record reaches the reducer.
5. Every finding includes a reproduction command.
6. All records validate as `lgwks.bot.record.v1`.
7. Store is restored to clean state after non-live run.
