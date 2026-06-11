# Implementation plan — I8 "basically working" (simplest tenant + concurrency) · 2026-06-11 (session 6)

Self-contained packet for issue [#72 / I8](https://github.com/srinji-kaggss/logicalworks-/issues/72).
Director directive (session 6, final): *"it's all 1 conceptual db. World data is shared cuz it's world.
Standard data is called in during query from the other db. I don't know the simplest way — log the
complexity as future, for now get the thing working basically."* So this packet is the **minimal,
honestly-simple** version. The full multi-tenant/two-DB hardening (capability crypto, durable per-tenant
queue, CRDT, promotion audit) is **logged as future** in [ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md)
and [SCOPE-DEFERRED.md](SCOPE-DEFERRED.md) — **do not build it now.**

## North star (framing, not a build target)
lgwks is shaping into *"the daemon you code on"* — an AI-first, Unix-style CLI: small composable `lgwks_*`
modules behind one dispatcher, one content-addressed store. Keep that spirit — **small, composable, simple**.
Do not mint a framework. (Director: "I'm blurring frameworks, speaking from vibes" — treat as direction, not
spec.)

## The simplest model that works now (one conceptual DB)
It is **one logical store** (the existing `vector_records` table, `lgwks_vector.py`). Two kinds of rows:
- **World rows** — shared, because they're world. (A reserved tenant sentinel, e.g. `tenant = 'world'`.)
- **Tenant ("standard") rows** — a tenant's own data, `tenant = '<T>'`.

A query for tenant `T` **calls in both**: its standard data ⊕ the world data. In SQL that is one WHERE clause:
```
SELECT ... FROM vector_records WHERE tenant = :T OR tenant = 'world'
```
That is the entire isolation story for "basically working." No second physical DB, no promotion pipeline, no
crypto. **Tenant = each db** conceptually, but physically it's the `tenant` column on one table (it already
exists: `lgwks_vector.py:45`, `NOT NULL DEFAULT ''`, indexed `vr_space_tenant` `:49`).

## The simplest concurrency that works now (no new queue)
Multiple crawls + several agents at once → use what already exists: `lgwks_sqlite.connect(...)`
(`lgwks_sqlite.py:59`) opens **WAL mode + BUSY/LOCKED retry**. WAL gives concurrent readers + serialized
writers across processes; BUSY-retry absorbs contention. That is "queue + don't corrupt + don't drop" for the
basic case **for free** — no durable queue, no token bucket needed yet. Ensure the store path goes through
`lgwks_sqlite.connect` (not a bare `sqlite3.connect`) and you have basic concurrency safety.

## Ordered steps (minimal)
1. **World/tenant read** in `lgwks_vector.py`: add `query_for_tenant(conn, tenant, ...)` returning
   `WHERE tenant = ? OR tenant = 'world'` (index-backed). This gives `lgwks_capability` its first real home
   (the token's `tenant` feeds this WHERE) without requiring crypto enforcement yet.
2. **Concurrency**: confirm the ingestion store opens via `lgwks_sqlite.connect` (WAL). If any path uses a
   bare connection, route it through `connect`. No new module.
3. **Tests**: a tenant read returns own ⊕ world rows and **not** another tenant's standard rows; two
   concurrent writers via WAL don't corrupt/lose (BUSY-retry). Real SQLite, not a fake.
4. **Record**: BUILDLOG row; note in #72 that the basic version is the WHERE-clause + WAL, and the
   cryptographic-capability / durable-queue / per-tenant-fairness hardening is deferred (ARCH + SCOPE-DEFERRED).

## What is explicitly deferred (the complexity — logged, not built)
Cryptographic §1-INV enforcement via capability tokens, per-tenant durable no-drop fair queue, backpressure,
CRDT deployment, promotion audit, network/MCP, cross-workspace sharing. All in
[ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md) (gaps L1–L9) + [SCOPE-DEFERRED.md](SCOPE-DEFERRED.md).
The `lgwks_admission.py` / `lgwks_capability.py` boilerplate is the **seed** of that future work; the basic
version above gives `capability` a minimal home and leaves `admission` parked for the durable-queue future
(see the boilerplate audit in HANDOFF.md).

## Scope fence
One WHERE clause + WAL. No crypto, no queue, no model, no network. Get the basic shared-world / tenant-data
query working; nothing more.

## Done =
Green tenant-read (own ⊕ world, not other-tenant) + concurrent-WAL-write tests + BUILDLOG row + #72 noted.
After I8-basic: continue the canonical tail — #73 (I9 CRDT), #74 (I10 viz join), #75 (I11 waste wiring).
