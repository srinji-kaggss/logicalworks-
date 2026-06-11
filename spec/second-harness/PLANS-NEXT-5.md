# Implementation plan — I8 multi-tenant concurrency + isolation (two-DB) · 2026-06-11 (session 6)

Self-contained work packet hardening issue [#72 / I8](https://github.com/srinji-kaggss/logicalworks-/issues/72)
to its **actual hardest surface**: the §1-INV tenant-isolation invariant **holding under concurrent
multi-tenant load**, across the two-DB topology. Director directive (session 6): concurrency is within one
tenant *and* across tenants; the complexity is the **shared world DB ("the Google") + the private per-pair
DB**; *that* is the security load (think Figma / Google Workspace daemons). Gap analysis + topology:
[ARCH-two-db-multitenant.md](ARCH-two-db-multitenant.md). Genuinely-future surfaces (cross-workspace
sharing, network/MCP transport): [SCOPE-DEFERRED.md](SCOPE-DEFERRED.md). AI-for-AI; receipts.

## The idea of this part (north star)
Two databases the engine must serve concurrently and keep separate:
- **World DB ("the Google")** — `store/substrate-global/`: shared, append-only, content-addressed world
  knowledge everyone reads; written **only by audited promotion**, never direct tenant write (§1).
- **Tenant DB (the private human+AI pair)** — `store/projects/<tenant>/`: isolated workspace; **the security
  load** — tenant A must never read tenant B (§1-INV, T0).
A query/agent touches **both at once** (reads its private workspace ⊕ the shared world). The hard problem is
making that safe under concurrency: queue + load-balance + never drop, **and** never leak across the seam.

## Authority ladder (on conflict)
`/CLAUDE.md` → `INGESTION-LAYER.md §1` (the two-tier store + §1-INV) **+** `§6` + `INGESTION-PLAN.md §I8` →
`ARCH-two-db-multitenant.md` → issue #72. Build-state truth = `BUILDLOG.md`. Out-of-scope = SCOPE-DEFERRED.md.

## Constraints inherited (do not relitigate)
1. **Model layer OUT OF SCOPE.** Routing/admission/isolation/queue only — no compute, no scoring, no model.
2. **Verify before assert.** `python3 -m pytest tests/test_admission.py tests/test_capability.py` + new
   concurrency/isolation tests; registry gate `python3 scripts/check_schema_registry.py` from repo root.
3. **No silent failure, no gate weakening.** A cross-tenant read, a lost job, a double-commit, or a
   fail-OPEN limiter is a bug — never a tolerance. The §1-INV is cryptographic, never `if tenant == ...`.
4. **Local ops assumed, multi-tenant real.** Network/MCP → SCOPE-DEFERRED. But isolation is NOT deferred:
   the two-DB seam is the security load and is in scope now.

## Honest delta from the boilerplate (PR #76)
- `lgwks_admission.py` is **in-memory, single-process, drop-on-full** (`deque` `:143`, `Rejected429` on full
  `:154`). Wrong for the surface: it drops internal work and cannot coordinate the separate crawler process
  (`crawler/src/main.rs`) or multiple tenant daemons. → durable cross-process queue, backpressure not drop.
- `lgwks_capability.py` (`guard`/`make_tenant_filter`) exists and is tested **but binds to nothing** —
  `lgwks_vector.get_record`/`query_by_source` (`:248,260`) never filter on `tenant`. § 1-INV is asserted,
  not enforced. → wire the boundary into a tier-aware access layer.
- Admission is one **global** bucket; per-tenant limiting is **fail-OPEN** (RECONCILE.md:318,360, limiter
  before auth context). → per-tenant buckets, ordered **after** capability resolution.
`TokenBucket` (`:75`) and the cid-dedup idea (`_seen` `:144`) are kept, moved behind a per-tenant durable
queue. `Rejected429` is retained but reserved for the future external/MCP adapter (SCOPE-DEFERRED D1).

---

## Build order inside I8 (the invariant first, then concurrency around it)

### Step 1 — enforce §1-INV: tier-routing access layer + tenant-scoped private reads  (closes L1, L2)
Every store op is **tier-tagged** and routed:
- `read_world(cid)` → world DB, no tenant filter (shared by design).
- `read_tenant(cid|source, token, key)` → **capability-guarded**, tenant-filtered at the store.
- `promote(cid, token, key)` → tenant → world, audited (Step 4). The **only** cross-tier write path.
Implementation: add tenant-scoped reads to `lgwks_vector.py` (`get_record_for_tenant(conn, cid, tenant)`,
`query_by_source_for_tenant(conn, src, tenant, *, space_id=None)` — `WHERE ... AND tenant = ?`, index-backed
by `vr_space_tenant` `:49`). Route the private path through `lgwks_capability.guard(token, fn, key)` so a
read **cannot** execute without a verified cap; apply `make_tenant_filter(token)` as defense-in-depth on the
result. Keep the unfiltered `get_record`/`query_by_source` for world reads only; the tenant path uses **only**
the `_for_tenant` variants. No `if tenant == ...` branch in business logic — the cap+SQL filter is the gate.

**Acceptance (L1/L2):** against a **live two-tier SQLite store** seeded with ≥2 tenants, a guarded tenant
read returns only the token's rows (assert both directions, A↮B); a world read returns shared rows to any
valid cap; an uncapped tenant read raises `CapabilityError` before SQL; a direct tenant→world write is
refused (promotion is the only path).

### Step 2 — tier-scoped capability  (closes L7)
Extend `lgwks_capability.py` so a token carries **scopes**, not a flat tenant: `tenant:rw`, `world:r`,
`world:promote` (gated). `guard()` checks the op's required scope against the token. Backward-compatible:
a bare tenant token = `{tenant:rw, world:r}` by default. Keep the key REQUIRED (no keyless path, D3).
**Acceptance:** a token without `world:promote` cannot promote; with it, can; signature still hmac-verified.

### Step 3 — per-tenant durable no-drop fair queue  (closes L3, L4; fixes fail-open)
The concurrency core. Reuse the hardened store — do not invent one:
- `lgwks_sqlite.connect(...)` (`:59`) — WAL + BUSY retry → cross-process safe (the world+tenant daemons and
  the crawler all coordinate through WAL). `ConnectionPool.acquire` (`:162`, `block=True, timeout`) is the
  **backpressure precedent** to mirror — block, don't drop.
- New durable table `admission_queue(cid PK, tenant, source, tier, state, lease_until, enqueued_at, attempts)`
  in the substrate db. `cid` PK ⇒ durable cross-process idempotency (ask twice → one row, the "mini Google"
  property). `state ∈ {pending, leased, done}`.
- **Per-tenant admission, ordered AFTER capability resolution** (fixes the fail-OPEN): a token-bucket **per
  tenant** (rate `c·μ`, burst B) so one tenant cannot starve others or flood the world DB.
- **No-drop:** at `Q_max`, durable-spill (crawler path — persist regardless, throttle the *pull* not the
  *accept*) or block-with-timeout returning a retryable `Backpressure` (agent path) — **never** a drop on the
  internal path.
- **Bounded fair leasing:** ≤ `c = compute_worker_cap(role_count)["computed_cap"]` (`lgwks_workercap.py:96`)
  concurrent leases; lease the next job **fairly across tenant then source** (no tenant/source starvation).
- **Crash-durable (at-least-once + idempotent = effectively-once):** lease sets `leased`+`lease_until`; a dead
  worker's lease expires → `reap()` returns it to `pending`; cid-idempotency means re-processing never
  double-commits. Clock injected (deterministic replay).

**Acceptance (L3/L4):** (a) **no-drop** — P concurrent producers across T tenants submit K jobs with capacity
< K → all K processed exactly once (`lost==0`, `dup_commit==0`); (b) **per-tenant fairness** — a flooding
tenant does not starve a quiet tenant beyond a pre-registered staleness bound; (c) **crash-durable** — kill a
worker mid-lease → job re-leased and completes; (d) **backpressure** — at `Q_max` an internal submit
blocks/persists, never drops; (e) **worker-cap** — max concurrent leases ≤ c; (f) **deterministic replay**.

### Step 4 — promotion audit/provenance  (closes L5, minimal)
The only tenant→world write path records **who promoted which cid, when, under what cap** to the
`lgwks_cognition` chain (`:65`, reuse — do not mint a second log). Lets the world DB attribute contributions
and a tenant retract from its private view without removing the shared node.
**Acceptance:** every promotion writes one audited cognition record; an unaudited tenant→world write is
impossible (Step 1 refuses it).

---

## Verified inputs (file:line — read, do not rebuild)
- `INGESTION-LAYER.md §1` (`:30-49`) — the two-tier store + **§1-INV (T0)** + promotion-only write model.
- `lgwks_vector.py` — `tenant` col (`:45`, `NOT NULL DEFAULT ''`), `vr_space_tenant` index (`:49`),
  `get_record` (`:248`), `query_by_source` (`:260`) — the reads to make tier/tenant-aware.
- `lgwks_capability.py` — `CapabilityToken` (`:48`), `guard(token, fn, key)` (`:103`, key REQUIRED),
  `make_tenant_filter` (`:130`) — the boundary to wire + extend with scopes.
- `lgwks_admission.py` — `TokenBucket` (`:75`, keep as smoother), `AdmissionQueue` (`:126`, replace with
  durable per-tenant table), `admission_decision` (`:199`), `make_admission_gate` (`:227`).
- `lgwks_sqlite.py` — `connect` (`:59`, WAL/cross-process), `ConnectionPool.acquire` (`:162`, backpressure).
- `lgwks_workercap.py` — `compute_worker_cap(...)["computed_cap"]` (`:64,96`) = `c`.
- `lgwks_cognition.py` — `CognitionLog.append` (`:65`) — the audit chain for promotion (L5).
- `lgwks_substrate_config.py` — `GLOBAL_ROOT = store/substrate-global` (`:18`); tenant tier = `store/projects/`.
- `crawler/src/main.rs` — crawler is a **separate process**; the queue must coordinate it (cross-process).

## Contract / schema
Durable job row + tier-scoped token cross process boundaries. **Check REGISTRY.md §4 first:** extend
`lgwks.admission.v1` for the queue row and `lgwks.capability.v1` for scopes; mint `lgwks.queue.job.v1` only if
the shape diverges (repurpose > extend > mint). Any new literal in code needs a REGISTRY row + a
`docs/schemas/*.json` in the same change or the gate fails. Run the gate from repo root.

## Acceptance (the load-bearing proof)
**§1-INV under concurrency:** 10⁴ randomized A/B cross-tenant queries against the **live two-tier store**,
run **concurrently** (genuine threads/processes, not an in-memory fake) → **zero B-cid in any A result**;
every uncapped cross-read rejected. This is §1-INV's own verify, hardened from the fake-fixture T2 to the
live concurrent store. Plus all Step 1–4 acceptances above (no-drop, per-tenant fairness, crash-durable,
backpressure, worker-cap, promotion audit, deterministic replay).

## Scope fence (this packet)
Tier-routing / capability-scoping / per-tenant admission / durable concurrent queue / promotion audit ONLY.
**No new compute, no scoring, no model, no CRDT deployment (that is I9/#73), no network/MCP, no
cross-workspace sharing.** Changes whether/when/in-what-order/for-which-tenant work runs and *that none
leaks or is lost* — never what a worker computes.

## Done =
Green §1-INV-under-concurrency (zero cross-tenant leak, live two-tier store) + no-drop + per-tenant fairness
+ crash-durable + backpressure + worker-cap + promotion-audit + deterministic-replay tests + registry gate
green + leak=0/lost=0/dup=0/fairness numbers in BUILDLOG + §8 G-07/G-09 reframed + SCOPE-DEFERRED filed +
issue #72 closed (multi-tenant-concurrency-first). After I8: **#73 (I9 — deploy CRDT on both tiers, L6)** →
#74 (I10 vector-store join) → #75 (I11 daemon wiring).
