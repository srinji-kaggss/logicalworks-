# Implementation plan — I8 P3→P0 hardening · 2026-06-11 (session 6)

Self-contained work packet for the agent after the I8–I11 boilerplate landing (PR #76, merged to main).
This doc specs the **hardening** of issue [#72 / I8](https://github.com/srinji-kaggss/logicalworks-/issues/72) —
the work between "boilerplate green" and the issue's own `Done =` line. The four I-series tail issues
(#72–#75) are filed and open; their modules + tests are merged. I8 is the next to **fully close** because it
is the security/isolation gate that escalates **P3 → P0 before any multi-tenant or network exposure**
(gaps G-07 high/T0, G-09 high). AI-for-AI; receipts, not essays.

**Lineage:** I8 was specced in [PLANS-NEXT-3.md](PLANS-NEXT-3.md) §PACKET I8 and refreshed in
[PLANS-NEXT-4.md](PLANS-NEXT-4.md) §PACKET I8 (the boilerplate contract). Those landed the *structure*:
`lgwks_admission.py`, `lgwks_capability.py`, schemas, 26 tests. **This doc is the hardening contract** — what
remains is real proof against a live store and under sustained load, plus the escalation wiring. Do not
re-spec the module API; it exists and is tested. Spec the proofs.

## Authority ladder (on conflict)
`/CLAUDE.md` → `spec/second-harness/INGESTION-LAYER.md` §6 + `INGESTION-PLAN.md` §I8 → `docs/ARCHITECTURE.md`
→ issue #72. Build-state truth = `spec/second-harness/BUILDLOG.md`, not spec prose.

## Constraints inherited (do not relitigate)
1. **Model layer is OUT OF SCOPE.** Admission/isolation only — no compute, no scoring, no model call.
2. **Verify before assert.** `python3 -m pytest tests/test_admission.py tests/test_capability.py` is the
   verifier; the registry gate is `python3 scripts/check_schema_registry.py` (run from repo root).
3. **No silent failure, no gate weakening.** A rejection is a *typed* 429; an invalid token *raises*; a
   non-deterministic decision sequence is a bug, not a tolerance. Surface degeneracy loudly.
4. **On a real fork in intent, ask (AskUserQuestion).** The exposure-timeline fork (below) is the Director's.

---

## Why now / the exposure split (read before sequencing the work)

I8 is the only packet with a conditional priority: **P3 while single-operator local; P0 before exposure.**
"Exposure" = any of: (1) a second operator gets store access; (2) any network surface opens (HTTP/MCP
beyond localhost, sync peer, webhook that writes the store); (3) client data lands in shared substrate
(`cl-ideas` overlay carries business/client material); (4) concurrent writers touch one store (I9's case).

The boundary is cheap to build before data commingles / a socket opens, and expensive to retrofit after.
So this packet splits its acceptance:

- **NOW-safe (build regardless of exposure timeline):** wire the tenant filter into the live store reads
  (it is currently *unenforced* — see Gap A), deterministic-replay proof, idempotent-shed proof. These
  harden correctness for one operator and are prerequisites for the gated proofs.
- **EXPOSURE-GATED (must land before the first trigger event):** sustained-load λ-sweep with zero-5xx,
  10⁴ cross-tenant isolation against the live store, and P3→P0 process-manager escalation wiring.

Confirm the exposure timeline with the Director before treating the gated half as urgent.

---

## Verified inputs (file:line — read, do not rebuild)

- `lgwks_admission.py` — **complete + tested.** `TokenBucket(rate, burst, clock=time.monotonic)` (`:85`,
  injectable clock D1); `AdmissionQueue(q_max, *, rng=None)` (`:126`, `deque` FIFO, idempotent cid dedup via
  `_seen` `:144`); `admission_decision(*, cid, item, bucket, queue, rng=None)` (`:199`); `make_admission_gate(
  role_count, *, mu, burst, q_max, clock, rng)` (`:227`) wires `compute_worker_cap` → bucket + queue.
  Pre-registered knobs `DEFAULT_MU=1.0`, `DEFAULT_BURST=4.0`, `DEFAULT_Q_MAX=32` (`:43`). CLI `lgwks
  admission info` carries the prose P3→P0 trigger (`:290`).
- `lgwks_capability.py` — **module complete + tested, but NOT wired into the store.** `CapabilityToken(
  tenant, nonce, sig)` (`:48`); `issue_token(tenant, *, key=None)` (`:67`); `validate(token, key)` (`:84`);
  `guard(token, query_fn, key)` (`:103`, key REQUIRED — no keyless path, D3); `make_tenant_filter(token)`
  (`:130`, defense-in-depth). `CapabilityError(PermissionError)` (`:99`).
- `lgwks_workercap.py` — `compute_worker_cap(role_count, *, host, reserves)` (`:64`) → dict; **`c` =
  `["computed_cap"]`** (`:96`). Host probe is env-pinnable (`LGWKS_HOST_RAM_GIB`/`LGWKS_HOST_CPU`), fail-closed.
- `lgwks_vector.py` — **the isolation gap is here.** `get_record(conn, cid)` (`:248`) and
  `query_by_source(conn, source_cid, *, space_id=None)` (`:260`) read records but take **no tenant argument
  and filter on none** — `query_by_source` filters `source_cid` (+ optional `space_id`) only. The
  `vr_space_tenant` index `ON (space_id, tenant)` (`:49`) and `VectorRecord.tenant` (`:75`,
  `NOT NULL DEFAULT ''`) exist and are unused by the read path. **This is what the capability boundary must
  bind to.**
- `tests/test_capability.py` — T2 already runs a 10⁴ cross-tenant loop but against `_FakeRecord` fixtures,
  not a live SQLite store. `tests/test_admission.py` — T1 stability is a step-clock replay, not sustained load.

---

## The three hardening gaps (each falsifiable, each closes a `Done =` clause)

### Gap A — capability boundary is not wired into the live store reads  ·  NOW-safe  ·  the load-bearing fix

**Problem:** `lgwks_capability.guard()`/`make_tenant_filter()` exist, but `lgwks_vector.get_record` and
`query_by_source` never filter on tenant. A query today is isolated only by which `conn`/path it was handed
(G-07 path separation). The boundary is a fiction until a read path *cannot* return another tenant's cid.

**Fix (implement exactly):** add a tenant-scoped read path in `lgwks_vector.py` and route capability-guarded
queries through it. Two acceptable shapes — pick the first unless a caller needs the second:

```
# Preferred: tenant is a required arg on the read, enforced in SQL (uses vr_space_tenant index).
def query_by_source_for_tenant(conn, source_cid, tenant, *, space_id=None) -> list[VectorRecord]:
    # WHERE source_cid = ? AND tenant = ?  [AND space_id = ?]   — index-backed, O(log n)
def get_record_for_tenant(conn, cid, tenant) -> Optional[VectorRecord]:
    # WHERE cid = ? AND tenant = ?   — returns None (not another tenant's row) on mismatch

# Boundary call site (capability is the only door):
guard(token, lambda t: query_by_source_for_tenant(conn, src, t), key=signing_key)
```

`make_tenant_filter(token)` stays as **defense-in-depth** applied to the result, so even a future caller that
forgets the WHERE clause cannot leak. Do not delete the unfiltered `get_record`/`query_by_source` (other
call sites depend on them) — add the `_for_tenant` variants and make the capability path use *only* them.

**Acceptance (NOW):**
- A `guard`-wrapped read against a real SQLite store seeded with ≥2 tenants returns **only** the token's
  tenant's rows — assert on cids, both directions (A cannot see B, B cannot see A).
- `get_record_for_tenant(conn, cid_of_other_tenant, my_tenant)` returns `None` (not the row).
- A read attempted without a valid token raises `CapabilityError` before any SQL executes.

### Gap B — sustained-load λ-sweep with zero 5xx  ·  EXPOSURE-GATED

**Problem:** T1 proves the rate-limiter property under a synthetic step-clock; it does not prove behaviour
under *sustained arrival* at the three regimes the §6 acceptance names.

**Fix:** a load harness (test, not prod code) that drives `make_admission_gate(...)` with an injectable
clock advancing at a fixed Δt and an arrival process at rate λ, draining the queue at `c·μ`. Run
λ ∈ {0.5·cμ, cμ, 2·cμ}. Keep μ/B/Q_max pinned (D3); inject clock + seeded rng for replay.

```
ρ = λ / (c·μ)
0.5×:  ρ = 0.5  → queue occupancy bounded, steady-state admit ≈ arrival, no growth
1.0×:  ρ = 1.0  → bounded (occupancy does not grow without limit; Q_max never exceeded)
2.0×:  ρ = 2.0  → EVERY rejection is Rejected429 (rate_limited|queue_full) with Retry-After; ZERO 5xx,
                  zero unbounded growth, zero untyped exception escaping admission_decision
```

**Acceptance (GATED):** the three regimes behave as above; at 2× count rejections by type and assert
`5xx == 0` (no exception type other than a returned `Rejected429`); Retry-After values fall in
`[base, 1.25·base]` with the seeded rng (deterministic bound).

### Gap C — P3→P0 escalation is documented prose, not a wired guard  ·  EXPOSURE-GATED

**Problem:** `lgwks admission info` and `lgwks capability info` print the trigger string
(`"escalates to P0 before any multi-tenant or network exposure"`) but nothing *enforces* it. Exposure could
happen with the gate inactive.

**Fix:** a single fail-closed checkpoint at the exposure boundary — the place that would open a network
socket or admit a second tenant must refuse to proceed unless (1) the admission gate is constructed and
(2) every store read is capability-guarded. Implement as an explicit assertion/guard function (e.g.
`require_admission_active(...)` / `require_capability_enforced(...)`) called from the daemon/server
entrypoint, **not** as a comment. The exact entrypoint depends on which exposure mechanism lands first —
**confirm with the Director which surface opens first (network endpoint vs second operator) before wiring**,
because that decides where the checkpoint lives.

**Acceptance (GATED):** with the gate inactive, the exposure entrypoint raises/refuses (fail-closed); with
it active, it proceeds; a test asserts the refusal path (no silent bypass).

---

## Determinism / replay (NOW-safe, spans A–C)

Pinned host env (`LGWKS_HOST_*`) + injected clock + seeded rng → **byte-identical decision sequence** across
runs. Assert the full admit/reject transcript is reproducible (mirrors the I5/I6 replay discipline). No
wall-clock read on any decision path (TokenBucket already injects; verify no new `time.*`/`random.*` global
leaks land in the harness or the store wiring).

---

## Ordered steps

1. **Gap A first** (NOW, unblocks the isolation proof): add `*_for_tenant` reads in `lgwks_vector.py`; route
   the capability path through them; keep `make_tenant_filter` as defense-in-depth. No new schema (reuses
   `lgwks.capability.v1`, `lgwks.vector.record.v1`). Run the registry gate from root anyway.
2. **Isolation proof:** move T2's 10⁴ cross-tenant loop onto a real SQLite store (seed ≥2 tenants); assert
   zero cross-tenant cids both directions. Keep the `_FakeRecord` unit test too (fast path).
3. **Gap B harness:** `tests/test_admission.py` sustained-load sweep at the three λ regimes; zero-5xx assert.
4. **Gap C checkpoint:** `require_*` fail-closed guard + its test. Confirm the exposure surface with the
   Director before choosing the entrypoint.
5. **Records:** BUILDLOG row (zero-5xx + zero-leak numbers, not adjectives); flip INGESTION-LAYER §8 G-07
   and G-09 from "not implemented" to "boundary wired + proven (I8)"; update HANDOFF "Suggested next step";
   note in issue #72 which acceptance clauses are NOW-closed vs exposure-gated. Close #72 only when the
   gated proofs land **or** the Director accepts the NOW-safe half as the close with the gated half tracked.

## Integration traps (this repo's CI/dispatcher enforce — verified)
- **REGISTRY gate.** No new `lgwks.*.vN` literal is introduced by this packet (admission/capability schemas
  exist). If you add one, add the `REGISTRY.md` row in the same change. Run `python3
  scripts/check_schema_registry.py` from repo root (it skips `.claude/` worktrees).
- **No new CLI verb expected.** `admission`/`capability` are already wired in the `lgwks` dispatcher and
  `lgwks_home._DOMAINS`. If you add a verb, wire both places or `test_home` L0 fails.
- **Subagent green ≠ correct.** The isolation proof must hit a *live* store; a green `_FakeRecord` test is
  exactly the hollow signal this repo keeps catching. Assert on real SQLite rows.
- **Root convention.** Any new module stays at repo root; do not create a package.

## Done =
Gap A wired + live-store isolation proof (zero cross-tenant cids) + sustained-load zero-5xx sweep +
fail-closed exposure checkpoint + deterministic replay transcript + registry gate green + zero-5xx/zero-leak
numbers recorded in BUILDLOG + §8 G-07/G-09 updated + issue #72 closed (or NOW-half accepted with gated half
tracked). After I8 closes, the I-series tail is #73 (I9, nearest to done) → #74 (I10 vector-store join) →
#75 (I11 daemon wiring); after #75 the ingestion plan is fully landed.
