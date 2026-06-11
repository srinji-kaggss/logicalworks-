# Implementation plans — remaining backlog (I8–I11) · 2026-06-11

Self-contained work packets for the agent after the `I7 → I5.1` landing (PR #70, both merged).
This doc carries the **entire remaining ingestion backlog**: I8, I9, I10, I11. I12 is done (PR #63);
I1–I7 + I5.1 are done and merged (HANDOFF.md, BUILDLOG.md 2026-06-10 session 3). Each section below is
pickup-able alone — it names verified inputs (file:line), the exact contract, the formula inline, ordered
steps, falsifiable acceptance, and the integration traps this repo's CI/dispatcher enforce. AI-for-AI;
receipts, not essays.

**Lineage:** I8 was first specced in [PLANS-NEXT-3.md](PLANS-NEXT-3.md) §PACKET I8 (still valid — depends
on I1, done). It is reproduced here, refreshed (I7/I5.1 now landed; `VectorRecord.tenant` confirmed live),
so this is the single authoritative "everything left" reference. I9/I10/I11 are newly detailed here.

**Build order:** **I8 → (I9 ∥ I10 ∥ I11).** I8 is the next packet. After I8, the three tail packets are
mutually independent given their deps (I9┄I1, I10┄I4, I11←I7 — all green). I10 is viz-only: **never let it
run ahead of the spine** (INGESTION-PLAN.md sequencing note). I11 measures whether the whole optimization
works — file it once you want the proof, not before I7 has produced packs to measure.

Authority ladder (on conflict): `/CLAUDE.md` → `spec/second-harness/INGESTION-LAYER.md` +
`INGESTION-PLAN.md` → `docs/ARCHITECTURE.md` → the GitHub issue. Build-state truth =
`spec/second-harness/BUILDLOG.md`, not spec prose.

## Constraints inherited from HANDOFF.md (do not relitigate)
1. **Model layer is OUT OF SCOPE.** Models are opaque deps. If a step needs the model layer, STOP AND ASK.
2. **Verify before assert:** `cargo test` / `.venv/bin/python -m pytest` is the verifier. Run from repo root.
3. **No silent failure, no gate weakening.** Surface non-convergence/degeneracy/divergence loudly.
4. **On a real fork in intent, ask (AskUserQuestion).** Don't ask what the code answers; read the code.

## Integration traps every packet here hits (verified this session, unchanged from NEXT-3)
- **REGISTRY gate.** `scripts/check_schema_registry.py` greps every `lgwks.<x>.v<N>` literal in
  `*.py/*.rs/*.sh` (excludes `tests/`, `.claude/`, `store/`) and fails CI unless a row exists in
  `docs/schemas/REGISTRY.md`. Mint a literal in CODE → add the row in the same PR. (Mentions in `*.md` like
  this doc do NOT trip the gate — only code files are scanned.) Run from repo root:
  `.venv/bin/python scripts/check_schema_registry.py`.
- **CLI wiring is two places.** A new verb registers in the `lgwks` dispatcher via
  `<module>.add_parser(sub)` (pattern at `lgwks:1466-1476` — `lgwks_score`/`lgwks_rank`/`lgwks_inbound`) AND
  must be added to `lgwks_home._DOMAINS` (`lgwks_home.py:410-419`) or the `test_home` L0 "no Other catch-all"
  invariant fails. Each module owns `add_parser(sub)` + `main(argv)` (see `lgwks_rank.py:456`).
- **Subagent green ≠ correct.** This session repeatedly caught hollow signals / silent non-convergence /
  dead CLI behind green subagent tests. Review/harden in the main thread; assert the math, not just exit 0.
- **Root convention.** New `lgwks_*.py` modules go at repo root (load-bearing dispatcher convention,
  CLAUDE.md "do not clean up the root"). Do not create a package.

---

## PACKET I8 — concurrency, queue, isolation · P3 (→ P0 before any multi-tenant/network exposure) · NOT YET ISSUED (file it) · depends: I1 (┄, done)

**One line:** no 5xx under load + hard tenant isolation — token-bucket admission, typed 429 + Retry-After
at saturation, idempotent shed on duplicate cid, and a capability-token isolation boundary that leaks
zero cross-tenant cids.

### Why P3 now but flagged
While ingestion is single-operator local, this is P3. It **escalates to P0 before any multi-tenant or
network exposure** (INGESTION-PLAN.md priorities; §8 gaps G-07 capability-token isolation = high/T0,
G-09 queue/admission = high). File it now so the boundary is built before exposure, not after an incident.
The P3→P0 trigger MUST be written into the issue body.

### Scope fence
Queue / admission / isolation ONLY. **No new compute, no new scoring, no model layer.** Does not change
what a worker does — only whether/when it is admitted and which tenant's data it can see.

### Verified inputs (file:line — read, do not rebuild)
- `lgwks_workercap.py` — `RESERVES` dict (`:26`), `probe_host()` (`:36`, env-pinnable via
  `LGWKS_HOST_RAM_GIB`/`LGWKS_HOST_CPU`, fail-closed), `compute_worker_cap(role_count, *, host, reserves)`
  (`:64`) → dict with `computed_cap` (`:96`), `formula_headroom`, `memory_cap`, `cpu_cap`, `cap_basis`;
  schema `lgwks-worker-cap/1`. **`c` (the concurrency cap) = `compute_worker_cap(...)["computed_cap"]`.**
- crawler politeness (jittered backoff) — `crawler/src/` (gather/engine); reuse the backoff pattern for
  Retry-After jitter, do not reinvent.
- `store/projects/` (per-tenant) + `store/substrate-global/` — the path-separation that is TODAY's only
  isolation (G-07: path separation, no capability token). I8 adds the token boundary on top.
- `lgwks_vector.py` — `VectorRecord.tenant: str` (`:75`); the SQLite `vector_records.tenant` column
  (`:45`, `NOT NULL DEFAULT ''`) + index `vr_space_tenant ON (space_id, tenant)` (`:49`). **This is the
  field isolation keys on — it is live, not hypothetical.**

### Formulas (implement exactly — INGESTION-PLAN.md I8 + INGESTION-LAYER §6)
```
c   = compute_worker_cap(role_count)["computed_cap"]          # already built; do not recompute by hand
ρ   = λ / (c·μ)                          # utilization; STABLE requires ρ < 1
admission: token bucket, refill rate c·μ, burst capacity B    # rate-limit at the cap
Q ≥ Q_max  ⇒  reject with typed 429 + Retry-After             # bounded queue, never unbounded growth
duplicate submission (same cid) ⇒ ONE row                     # idempotent shed (cid is the dedup key, I1)
```
`μ` (service rate), `B` (burst), `Q_max` are config inputs — probe or pin them like `lgwks_workercap` pins
the host (env override for replay). Pre-register the values in a `//why`; do not fiddle under test.

### Ordered steps
1. File the GitHub issue "I8 — concurrency, queue, isolation" (label `ingestion`), pasting this packet.
   **Write the P3→P0 escalation trigger (before any multi-tenant or network exposure) into the body.**
2. **New module `lgwks_admission.py`** (root convention). API:
   - `TokenBucket(rate, burst)` — `try_acquire() -> bool`; **injectable clock** (deterministic for
     replay/test, mirroring `probe_host`'s env-override discipline — never read wall-clock directly).
   - `Queue(q_max)` — `submit(item) -> Admitted | Rejected429(retry_after)`; dedup by cid (idempotent shed).
   - `admission_decision(load, *, cap, mu, ...)` → typed result.
   Reuse `compute_worker_cap` for `c`. Reuse crawler backoff for Retry-After jitter.
3. **Isolation boundary `lgwks_capability.py`** (or extend an existing tenant module — `git grep -niE
   'tenant|capability.?token|store/projects' -- '*.py'` FIRST to avoid minting a duplicate; repurpose >
   mint, REGISTRY rule 5). A capability token scopes a query to one `tenant`; a query without a valid token
   is rejected; cross-tenant cid access is impossible by construction (filter every read on
   `VectorRecord.tenant` — the `vr_space_tenant` index already exists for this).
4. **Contract:** if a payload crosses modules/process boundary, register it (`lgwks.admission.v1` /
   `lgwks.capability.v1` — check REGISTRY.md §4 harness family first; the `lgwks-worker-cap/1` artifact
   already exists and may be the right family to extend). Run the registry gate from root.
5. **CLI** (if a verb is warranted): `add_parser(sub)` + `lgwks_home._DOMAINS` entry. A `lgwks admission
   info` surface for ops is reasonable; confirm net-new operator surface with the Director if unsure.
6. Tests `tests/test_admission.py` + `tests/test_capability.py`; BUILDLOG row; HANDOFF / INGESTION-PLAN /
   INGESTION-LAYER §8 (G-07, G-09) updates.

### Acceptance (§1-INV + §6, falsifiable — all required)
- **Stability sweep:** load test at λ ∈ {0.5·cμ, cμ, 2·cμ} → ρ<1 stable at 0.5×; bounded (no unbounded
  queue growth) at 1×; at 2× **every** rejection is a typed 429 with Retry-After and **zero 5xx**.
- **Idempotent shed:** duplicate submission of the same cid ⇒ exactly one row (dedup by cid, I1).
- **Tenant isolation (§1-INV):** 10⁴ randomized A/B cross-tenant queries leak **zero** cross-tenant cids.
- **Token required:** a query without a valid capability token is rejected (not served, not partial).
- **Replayable:** injected clock + pinned host/μ/B → deterministic admission decisions across runs.

### Done = green load/isolation tests + registry gate green + zero-5xx + zero-leak proofs recorded in BUILDLOG + issue filed and closed.

---

## PACKET I9 — CRDT state · P3 · NOT YET ISSUED (file it) · depends: I1 (┄, done)

**One line:** concurrent writers converge to byte-identical state without conflict — world-nodes as a
G-Set keyed by cid (idempotent ⇒ CvRDT for free), tenant edges as an OR-Set / LWW tie-broken by the
cognition-chain head.

### Why P3 / when it matters
I9 is the merge-semantics half of multi-writer; I8 is the admission/isolation half. Single-operator local
needs neither, so P3. It becomes load-bearing the moment two writers (a second daemon, a sync, a network
peer) can touch the same store concurrently — pair it with I8 before multi-tenant/network exposure. File
now so the convergence proof exists before the first concurrent writer, not after a silent divergence.

### Scope fence
State-merge semantics ONLY. **No transport, no networking, no consensus protocol** (CRDTs are
coordination-free *by design* — that is the point). No new compute, no model layer. Defines how two
already-produced states merge; does not move bytes between machines.

### Verified inputs (file:line — read, do not rebuild)
- `lgwks_cognition.py` — `CognitionLog` (`:40`): append-only, **HMAC hash-chained** record. `append(kind,
  data)` (`:65`) chains on the previous hash; `_tail_hash()` (`:50`) "recovers the chain head from disk so a
  new process continues the same chain" — **this chain head IS the logical clock** for LWW tie-breaking.
  `verify()` (`:97`) walks the chain; `_next_seq()` (`:81`) is the monotonic seq; `_log_path` (`:32`) →
  `store/cognition/<stream>-*.cognition.jsonl`. Refuses to append to a broken chain (`:70`). **Repurpose
  this for the logical clock — do NOT mint a second clock (REGISTRY §1 "one byte-truth").**
- `lgwks_vector.py` — `VectorRecord.cid` (content address, blake2b of canonical bytes, I1). **cid is the
  G-Set element key** — identical input bytes → identical cid (I1's dedup invariant) is exactly what makes
  the G-Set a CvRDT: adding the same fact twice is a no-op by construction.
- `store/projects/` (per-tenant edges) + `store/substrate-global/` (world-nodes) — the two state surfaces.
- INGESTION-PLAN.md I9 (line 208) — the design (G-Set / OR-Set / LWW); INGESTION-LAYER §6 — the SEC
  (Strong Eventual Consistency) requirement.

### Design (implement exactly — INGESTION-PLAN.md I9)
```
world-nodes  = G-Set keyed by cid                  # grow-only; idempotent add ⇒ CvRDT for free (I1 cid dedup)
tenant edges = OR-Set (add/remove + unique tags)   # observed-remove: a remove only cancels the adds it saw
             | LWW-Register tie-broken by cognition-chain head   # last-writer-wins, head = logical clock
merge(a, b)  = commutative ∧ associative ∧ idempotent   # the CvRDT laws; SEC follows
```
- **G-Set** (world-nodes): `merge = set-union`. No removes (world facts are append-only, matching the
  cognition chain and the axiom fabric DAG).
- **OR-Set** (tenant edges) if edges can be removed: each add carries a unique tag; remove cancels only the
  tags it observed → add-wins on concurrent add/remove. Use this if removal is a real requirement.
- **LWW-Register** if last-write-wins is acceptable and simpler: tie-break by the cognition-chain head
  (`_tail_hash`) + `_next_seq`, NOT wall-clock (wall-clock is non-deterministic and breaks replay).
- Pick OR-Set vs LWW per the edge's real semantics; **if removal semantics are ambiguous, AskUserQuestion**
  (add-wins vs last-wins is a real fork with different data-loss profiles).

### Ordered steps
1. File the GitHub issue "I9 — CRDT state" (label `ingestion`), pasting this packet.
2. **New module `lgwks_crdt.py`** (root convention). API (pure functions — no I/O in the merge core, so the
   merge is trivially testable and replayable):
   - `GSet` — `add(cid)`, `merge(other) -> GSet`, `value() -> frozenset`.
   - `ORSet` — `add(elem, tag)`, `remove(elem, observed_tags)`, `merge(other)`, `value()`.
   - `LWWRegister` — `set(value, head, seq)`, `merge(other)` (tie-break: higher seq, then head bytes).
   - `merge_state(a, b)` → merged state; the laws below are the contract.
   Read the logical clock from `lgwks_cognition.CognitionLog` (`_tail_hash`/`_next_seq`) at the I/O edge;
   keep the merge core clock-free (clock is an argument, not a global read).
3. **Contract:** the merged-state payload crosses the store boundary → register `lgwks.crdt.state.v1`
   (REGISTRY §4 harness/orchestrator, or §3 substrate if it lives in the substrate store — check first,
   repurpose > mint). JSON-Schema file in `docs/schemas/` once v1 (REGISTRY rule 3, it crosses a file
   boundary). Run the registry gate from root.
4. **CLI** (optional): `lgwks crdt merge <a> <b>` for ops/debug is reasonable; if added, wire both places
   (`add_parser` + `_DOMAINS`).
5. Tests `tests/test_crdt.py`; BUILDLOG row; HANDOFF / INGESTION-PLAN / INGESTION-LAYER §6 updates.

### Acceptance (SEC proof, executed — all required, falsifiable)
- **Convergence (the SEC proof):** apply the same update multiset in **N random permutations across M
  replicas** → all replicas converge to **byte-identical** state. This is the load-bearing test — assert
  byte equality, not "looks equal".
- **Idempotent add:** adding the same cid-fact twice is a no-op (G-Set; follows from I1 cid dedup — assert
  it explicitly, do not assume).
- **CvRDT laws (property tests):** `merge` is commutative (`merge(a,b)==merge(b,a)`), associative
  (`merge(merge(a,b),c)==merge(a,merge(b,c))`), idempotent (`merge(a,a)==a`) — fuzz over random states.
- **OR-Set add-wins** (if OR-Set chosen): concurrent add+remove of the same element → element present.
- **LWW determinism** (if LWW chosen): tie-break uses the cognition-chain head/seq, NOT wall-clock —
  same inputs → same winner across runs (no `Date.now()`-style nondeterminism).

### Done = green SEC/convergence + CvRDT-law tests + registry gate green + byte-identical-convergence proof recorded in BUILDLOG + issue filed and closed.

---

## PACKET I10 — deterministic 3-D viz projection (DECOUPLED from semantic space) · P3 · NOT YET ISSUED (file it) · depends: I4 (┄, done)

**One line:** a replayable X/Y/Z coordinate per node for the visualization engine — `y_i = Wᵀêᵢ ∈ ℝ³`,
`W` = top-3 PCA axes (SVD), sign-fixed; a **viz-only** artifact that is provably one-way decoupled from
scoring/retrieval (it never feeds back).

### Why P3 / the standing warning
I10 is viz-only and the LEAST load-bearing packet. **Never let it run ahead of the spine**
(INGESTION-PLAN.md sequencing note + INGESTION-LAYER §7.5): the math must never be distorted to make a
prettier picture, and the picture is never the semantic truth. The decoupling is the whole point of the
packet — the acceptance test below *proves* it.

### Scope fence
Projection output ONLY — coordinates per node. **Not the renderer** (the D3/HTTP front-end already exists),
**not the scoring**, no model layer. The projection is derived one-way from the embedding and **never feeds
back** into scoring/retrieval (INGESTION-LAYER §7.5).

### Verified inputs (file:line — read, do not rebuild)
- `lgwks_graph_viz.py` — `GraphDataAdapter` (`:44`): `load()` (`:53`) loads the graph cache;
  `to_frontend() -> {"nodes":[...], "edges":[...]}` (`:64`) is the D3.js feed. **The current front-end
  computes positions client-side via D3 force layout — there are no server-side coordinates today
  (grepped: no x/y/z/coord/pca in the module).** I10 adds deterministic server-side coords to each node in
  `to_frontend`'s output (additive — do not remove the force-layout fallback).
- `lgwks_vector.py` — `VectorRecord.embedding` (BLOB, float32[d] big-endian, L2-normalized, I1);
  `source_cid` (`:76`) + index `vr_source` (`:50`); store helpers join node ↔ embedding **by cid**. This is
  the `êᵢ` input — already normalized, so PCA operates on unit vectors.
- INGESTION-PLAN.md I10 (line 221) + INGESTION-LAYER §7.5 — the decoupling law and the formula.

### Formula (implement exactly — INGESTION-PLAN.md I10)
```
Ê = stack of L2-normalized embeddings (n × d)
W = top-3 right-singular vectors of Ê (PCA axes, via SVD)      # W is d × 3
sign of each column fixed by the largest-magnitude-positive rule   # kills SVD sign ambiguity → replayable
y_i = Wᵀ êᵢ ∈ ℝ³                                                # the (x,y,z) coordinate per node
```
- **Sign-fix is mandatory:** SVD columns are sign-ambiguous; without fixing, the same Ê yields different
  coords across runs (replay fails). Rule: for each column of `W`, if the entry of largest magnitude is
  negative, flip the column's sign.
- **Optional seeded UMAP fallback** ONLY if PCA reconstruction stress exceeds a **pre-registered**
  threshold — and only seeded (deterministic). Do not add UMAP speculatively; PCA is the default.
- Pure function of `Ê`. No model call (use `numpy.linalg.svd`; the embedding is already computed by I4).

### Ordered steps
1. File the GitHub issue "I10 — deterministic 3-D viz projection" (label `ingestion`), pasting this packet.
   Note the "viz-only, never ahead of the spine, never feeds back" guard in the body.
2. **New module `lgwks_viz_project.py`** (root convention) — keep it separate from `lgwks_graph_viz.py`
   so the renderer's import graph cannot pull projection into a scoring path. API:
   - `fit_axes(embeddings: list[bytes|ndarray]) -> ndarray` (the d×3 `W`, sign-fixed).
   - `project(embedding, W) -> tuple[float,float,float]` (one node's coord).
   - `project_all(records) -> dict[cid, (x,y,z)]` (join by cid).
   - `reconstruction_stress(Ê, W) -> float` (the fidelity metric, for the threshold gate).
3. **Wire into the viz feed:** `GraphDataAdapter.to_frontend` (`lgwks_graph_viz.py:64`) adds `"xyz":[x,y,z]`
   per node when projection data is available — **additive**, force-layout stays as fallback. Do NOT import
   `lgwks_viz_project` into any scoring/ranking module.
4. **Contract:** the coords ride the existing viz JSON feed (front-end consumer). If you bump that feed's
   contract, register/version it; if `to_frontend` is currently versionless viz output, a `//why` noting
   the additive field is enough — check REGISTRY first. Run the registry gate from root.
5. Tests `tests/test_viz_project.py`; BUILDLOG row; HANDOFF / INGESTION-PLAN / INGESTION-LAYER §7.5 updates.

### Acceptance (decoupling proof, executed — all required, falsifiable)
- **Replayable:** same `Ê` → **byte-identical `W` and coords** across runs (this is what the sign-fix
  buys; assert it, do not assume).
- **One-way decoupling (THE load-bearing test):** **scoring/ranking output is bit-identical with I10
  present or absent.** Run `lgwks score` / `lgwks rank` on a fixture with and without the projection wired;
  assert byte-identical results. This proves coords never feed back (INGESTION-LAYER §7.5).
- **Reconstruction stress reported:** the PCA stress metric is computed and logged (not hidden); if it
  exceeds the pre-registered threshold, the seeded-UMAP fallback is invoked (and is itself deterministic).
- **Coords are bounded/finite:** no NaN/Inf in any coordinate (a degenerate embedding must surface loudly,
  not emit garbage — no silent failure).

### Done = green replay + decoupling (bit-identical scoring with/without) + stress tests + registry gate green + decoupling proof recorded in BUILDLOG + issue filed and closed.

---

## PACKET I11 — waste ledger (the proof context-optimization works) · P3 · NOT YET ISSUED (file it) · depends: I7 (done)

**One line:** measure that the score actually reduces tokens — a per-session ledger correlating every
injected/packed item against its downstream use (cited/acted-on within N turns, from the transcript), so
the cockpit shows a **waste-rate**, not just spend. Without this, the whole optimization is asserted, not
proven (gap G-13).

### Why now
I7 produces `lgwks.inbound.v1` packs; I11 is the instrument that proves those packs aren't waste. PRD-04
§04-c makes the waste ledger **the governing metric** ("token economy ≠ token minimization … kill waste,
not thinking"). It is the one thing that catches both failure modes — an over-stuffed reflex channel
(high waste-rate) and an over-pruned one (load-bearing context missing). File it when you want the proof
that the spine pays for itself.

### Scope fence
Measurement ONLY. **Does not change the router / the selection cut** — it *informs* the next tuning
(INGESTION-PLAN.md I11 scope fence + PRD-04 INV: "non-generative, waste-measured"). No model layer. Reads
the transcript + the packs; writes a ledger; computes a rate. It does not decide what to inject.

### Verified inputs (file:line — read, do not rebuild)
- `lgwks_inbound.py` — `lgwks.inbound.v1` packs (I7, done): `handles[]`, `scores{}`,
  `budget{limit_tokens, used_tokens, truncated_count, truncated[]}`, `depth_handles[{id, est_tokens,
  kind}]` (REGISTRY.md:142). **These are the injected items the ledger accounts for — each handle's
  est_tokens is the "tokens injected" side; downstream use is the other side.**
- PRD-04 `spec/second-harness/prd/PRD-04-context-economy.md` — §04-c (line 85): "per-session ledger in db:
  tokens injected/packed AND downstream-use signal per item (cited/acted-on within N turns, from
  transcript); cockpit shows waste-rate; sums verified against transcript." Line 60: the signal is derived
  "from the transcript the daemon already tails." Line 93 (open-Q): the **N-turn window is a pre-registered
  knob** — "cited within how many turns?" — set a documented constant, do not fiddle.
- `lgwks_cognition.py` — `CognitionLog` (`:40`), `store/cognition/<stream>-*.cognition.jsonl` (`:32`): the
  append-only store for the ledger (reuse — do not mint a second log/store; REGISTRY §1 one byte-truth).
- The transcript source: the Claude Code session transcript (JSONL). **Inject the transcript path as an
  argument, env-pinnable (mirror `probe_host`'s `LGWKS_*` override discipline) — do NOT hardcode a
  `~/.claude/...` path** (the dead-space-named-dir trap that bit I7's hook re-registration; INGESTION-PLAN
  header item 4). Confirm the live transcript path with the Director if ambiguous.

### Contract to ship: `lgwks.waste.ledger.v1` (family: harness — REGISTRY.md:143, currently "planned (I11), spec only")
Per-session ledger, **typed only — no free-text**:
```
{ "schema": "lgwks.waste.ledger.v1",
  "session_id": "<str>",
  "window_turns": <int>,                         # the pre-registered N (cited-within-N-turns); documented, fixed
  "items": [ { "cid": "<cid>",                    # the injected/packed handle
               "tokens": <int>,                   # tokens injected/packed (from est_tokens / pack budget)
               "used_within_n": <bool>,           # cited/acted-on within window_turns, derived from transcript
               "first_use_turn": <int|null> } ],
  "totals": { "tokens_injected": <int>,
              "tokens_used": <int>,               # tokens of items with used_within_n == true
              "waste_rate": <float> } }           # 1 − tokens_used/tokens_injected  ∈ [0,1]
```

### Formula (implement exactly — PRD-04 §04-c)
```
used_within_n(item) = the item's cid/content is cited or acted-on within window_turns of injection   # from transcript
waste_rate = 1 − ( Σ tokens of used items / Σ tokens of all injected items )    # 0 = perfect, 1 = pure waste
```
- `window_turns` (N) is the **only knob** — pre-register it (a module constant + `//why`), do not tune
  under test (PRD-04 open-Q line 93).
- "Cited/acted-on" detection must be **deterministic and explainable** — a high-waste injection must be
  attributable to a specific low-yield item (acceptance below). Match handle cids / their content against
  the transcript; document the matching rule.

### Ordered steps
1. File the GitHub issue "I11 — waste ledger" (label `ingestion`), pasting this packet.
2. **New module `lgwks_waste.py`** (root convention). API:
   - `build_ledger(packs, transcript, *, window_turns=N) -> dict` (the `lgwks.waste.ledger.v1` dict;
     pure given packs + transcript — injectable, replayable).
   - `waste_rate(ledger) -> float`.
   - `add_parser(sub)` + `main(argv)` — verb `waste` with a `report`/`info` surface mirroring
     `lgwks_rank.py:456`.
3. **Persist** the ledger via `lgwks_cognition` / `store/cognition` (reuse the append-only store; do not
   mint a new one). The transcript path is an argument, env-pinnable — never hardcoded.
4. **Wire CLI** both places: `import lgwks_waste; lgwks_waste.add_parser(sub)` near `lgwks:1476` + add
   `"waste"` to the right domain in `lgwks_home.py:419`.
5. **REGISTRY row:** flip `docs/schemas/REGISTRY.md:143` `lgwks.waste.ledger.v1` from **planned (I11)** →
   **live (I11)**, source `lgwks_waste.py`, list the fields above. JSON-Schema file in `docs/schemas/` (it
   crosses the CLI-JSON boundary, REGISTRY rule 3). Run the gate from root.
6. Tests `tests/test_waste.py`; BUILDLOG row; HANDOFF / INGESTION-PLAN / INGESTION-LAYER §8 (G-13) updates.

### Acceptance (PRD-04 §04-c, executed — all required, falsifiable)
- **Sums reconcile:** ledger `totals.tokens_injected` reconciles against the actual packs and the
  transcript — assert the sum, do not eyeball it (PRD-04 "sums verified against transcript").
- **Waste-rate computed:** `waste_rate ∈ [0,1]` on a fixture session with a known used/unused split →
  matches the hand-computed expected rate.
- **Attributable:** a high-waste injection is **attributable to a specific low-yield item** (the ledger
  names the cid) — assert the worst item is identifiable, not just the aggregate.
- **No prose:** the ledger dict has no free-text field (only cids, ints, bools, floats) — assert
  recursively (mirror I7's no-prose test).
- **Threshold pre-registered:** the selection-cut threshold the ledger would recommend raising is
  pre-registered (a documented constant) — I11 reports it, does NOT act on it (scope fence).
- **Deterministic:** same (packs, transcript, N) → identical ledger (no wall-clock, no nondeterminism).

### Done = green reconcile/rate/attribution tests + registry gate green (`lgwks.waste.ledger.v1` row flipped to live) + ledger sums reconciled in BUILDLOG + issue filed and closed.

---

## Sequencing reminder (reduce blur)
**I8 is next.** After I8, I9/I10/I11 are independent (deps all green) — but I10 is viz-only and must never
run ahead of the spine, and I11 only earns its keep once I7 packs exist to measure (they do). Do not start
a packet whose dependency is not tested-green — that is the blur the ordering exists to prevent
(INGESTION-PLAN.md sequencing note). File the GH issue before coding each one (CLAUDE.md: issue-backed
work). This completes the I-series backlog (I1–I12); after I11 the ingestion plan is fully landed.
