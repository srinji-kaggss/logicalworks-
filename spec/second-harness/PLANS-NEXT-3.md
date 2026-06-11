# Implementation plans — next 3 packets · 2026-06-10

Self-contained work packets for the agent after the `scoring-spine` landing (HANDOFF.md).
Build order: **I7 → I5.1 → I8**. Each section below is pickup-able alone: it names verified
inputs (file:line), the exact contract, the formula inline, ordered steps, falsifiable
acceptance, and the integration traps that this repo's CI/dispatcher enforce. AI-for-AI;
receipts, not essays.

Authority ladder (on conflict): `/CLAUDE.md` → `spec/second-harness/INGESTION-LAYER.md` +
`INGESTION-PLAN.md` → `docs/ARCHITECTURE.md` → the GitHub issue. Build-state truth =
`spec/second-harness/BUILDLOG.md`, not spec prose.

## Constraints inherited from HANDOFF.md (do not relitigate)
1. Model layer is OUT OF SCOPE. Models are opaque deps. If a step needs the model layer, STOP AND ASK.
2. Verify before assert: `cargo test` / `.venv/bin/python -m pytest` is the verifier. Run from repo root.
3. No silent failure, no gate weakening. Surface non-convergence/degeneracy loudly.
4. On a real fork in intent, ask (AskUserQuestion). Don't ask what the code answers.

## Integration traps every packet here hits (verified this session)
- **REGISTRY gate.** `scripts/check_schema_registry.py` greps every `lgwks.<x>.v<N>` literal in
  `*.py/*.rs/*.sh` (excludes `tests/`, `.claude/`, `store/`) and fails CI unless a row exists in
  `docs/schemas/REGISTRY.md`. Mint a literal → add the row in the same PR. Run the gate from repo
  root: `.venv/bin/python scripts/check_schema_registry.py`.
- **CLI wiring is two places.** A new verb registers in the `lgwks` dispatcher via
  `<module>.add_parser(sub)` (pattern at `lgwks:1466-1476` — `lgwks_score`/`lgwks_rank`) AND must be
  added to `lgwks_home._DOMAINS` (`lgwks_home.py:410-419`) or the `test_home` L0 "no Other catch-all"
  invariant fails. Each module owns `add_parser(sub)` + `main(argv)` (see `lgwks_rank.py:456`).
- **Subagent green ≠ correct.** This session repeatedly caught hollow signals / silent
  non-convergence / dead CLI behind green subagent tests. Review/harden in the main thread; assert
  the math, not just exit 0.

---

## PACKET I7 — consumer tail (L5 reflex pack + RRF) · P2 · issue #61 · depends: I6 (done)

**One line:** assemble the token-budgeted, prose-free pack the AI consumer reads — RRF fusion of
graph cubic rank ⊕ vector cosine rank, hard 1500-token cap, deterministic truncation, zero dangling
handles.

### Scope fence
Assembly + budgeting ONLY. No generation, no "what Opus does with it" (PRD-04 INV-3). No new scoring
math (consume I6 ranks + I1 cosine as-is). No model layer.

### Verified inputs (read these, do not rebuild)
- `lgwks_rank.py:403` `rank_graph(graph) -> list[RankRecord]` — graph cubic centrality. `RankRecord`
  (`:99`) fields: `node_cid, centrality, rank_det, rank_ai, delta, lane, schema_id`. Sorted best-first
  by `rank_det`. Raises `RankError` on non-convergence. **This is the graph rank input.**
- `lgwks_vector.py` — `VectorRecord` (`:67`); `cosine(a,b)` (`:180`); `require_same_space(a,b)` (`:195`,
  raises `SpaceMismatchError` — never silently cross-compare); store helpers `_connect`/`get_record`/
  `query_by_source`/`store_count` (`:207-285`). **This is the vector cosine input.**
- `hooks/subconscious_inbound.py` (45 lines) — the shipped, fail-silent `UserPromptSubmit` consumer.
  Currently emits the capability map (`lgwks_map.map_intent`). I7 extends what it can inject. FAIL-SILENT
  is law (INV-6): any error → exit 0, emit nothing. Do not break that.
- `lgwks_context.py` — `assemble(run_dir)`, `write_pack(run_dir)`, `add_parser(sub)`,
  `_context_command(args)`, `main(argv)`. Dispatched via `_context_dispatch` in `lgwks`.
- PRD-04 `spec/second-harness/prd/PRD-04-context-economy.md:52-92` — the reflex-cap + RRF authority.
- INGESTION-LAYER `§7` (lines 252-266) — the L1→L5 strip ladder and §7-INV.

### Contract to ship: `lgwks.inbound.v1` extension (family: harness)
Reflex envelope (PRD-04 §Contract, line 74). Fields, **typed only — no free-text field**:
```
{ "schema": "lgwks.inbound.v1",
  "handles": ["cid", ...],                 # ordered, RRF-best first; every cid present in the store
  "scores":  { "<cid>": <float> },          # the fused RRF score per handle
  "budget":  { "limit_tokens": 1500,        # PRD-04 reflex cap default (tunable, never absent)
               "used_tokens":  <int>,
               "truncated":    ["<cid>", ...] },   # what the cap dropped, visible (no silent drop)
  "depth_handles": [ { "id": "<cid>", "est_tokens": <int>, "kind": "<str>" } ] }
```
Truncation order (PRD-04 line 52, drop LAST first): `flags > scores > selections > retrieval >
pathways > last_state`. **depth_handles are never dropped for bulk** — a pointer survives the cut
(PRD-04 04-a). For I7's minimal pack, the load-bearing ordering reduces to: keep highest-RRF
handles + their scores; drop lowest-RRF tail first.

### Formula (implement exactly) — Reciprocal Rank Fusion
```
RRF(cid) = Σ_lists  1 / (k + rank_list(cid))      # k = RRF_K constant, PRE-REGISTER, do not fiddle (PRD-04 open-Q)
lists = { graph_rank: rank_det from lgwks_rank ; vector_rank: dense rank by cosine to the query embedding }
```
- `k` is the only knob — set a module constant `RRF_K` (default 60, the canonical Cormack 2009 value),
  document the pre-registration in a `//why`, and do not tune it inside this packet.
- Deterministic by construction: same (graph ranks, vector ranks, k) → identical fused order. Add a
  seed-stability test like `test_rank.py` already does for I6.
- Token estimate: use a deterministic estimator (e.g. `len(serialized)/4` chars-per-token heuristic, or
  the repo's existing token counter if one exists — grep `lgwks_context` / `lgwks_*token*` first; do NOT
  add a model call). Cap is on the SERIALIZED reflex pack.

### Ordered steps
1. **Locate the token estimator.** `git grep -niE 'est_tokens|token.?count|tiktoken|len\(.*\)//4' -- '*.py'`.
   Reuse it; if none, add a tiny deterministic char/4 estimator in the new module with a `//why`.
2. **New module `lgwks_inbound.py`** (root — load-bearing root convention, CLAUDE.md). Public API:
   - `fuse(graph_ranks: list[RankRecord], vector_ranks: list[tuple[str,float]], *, k=RRF_K) -> list[(cid,score)]`
   - `build_pack(handles, scores, *, limit_tokens=1500) -> dict` (the `lgwks.inbound.v1` dict above;
     enforces cap, fills `budget.truncated`, preserves `depth_handles`).
   - `assemble_inbound(query_embedding, graph, store_conn, *, limit_tokens=1500) -> dict` (end-to-end).
   - `add_parser(sub)` + `main(argv)` — verb `inbound` with `run`/`info` subcommands mirroring
     `lgwks_rank.py:456-536`.
3. **Vector rank list.** Rank store records by `cosine(query_vec, record)` after
   `require_same_space` — surface `SpaceMismatchError`, never silently skip. If no query embedding is
   available in the reflex context, the graph list alone feeds RRF (single-list RRF is still valid;
   `log`/note it). Confirm the query-embedding source with the Director if ambiguous (model layer is
   out of scope — do NOT embed here; consume an already-embedded query vector).
4. **Wire CLI.** Add `import lgwks_inbound; lgwks_inbound.add_parser(sub)` near `lgwks:1476`; add
   `"inbound"` to the appropriate domain list in `lgwks_home.py:419`.
5. **Extend the hook (optional, gated on re-registration).** `hooks/subconscious_inbound.py` may call
   `assemble_inbound` to inject the L5 pack as `additionalContext`. Keep fail-silent. Do this ONLY after
   the re-registration ops action below; otherwise ship the module + CLI and leave the hook untouched.
6. **REGISTRY row.** Update `docs/schemas/REGISTRY.md:142` (`lgwks.inbound.v1` is currently "planned …
   extended by I7") → mark **live (I7)**, source `lgwks_inbound.py`, list the extension fields. Run the
   gate from root.
7. **Tests** `tests/test_inbound.py`: see acceptance below.
8. **BUILDLOG.md** append a 2026-06-xx I7 landing row. Update HANDOFF.md "NOT built" → built.

### Ops pre-condition (NOT code — confirm with Director)
The inbound hook is registered in the DEAD space-named dir
`/Applications/Logical Works/.claude/settings.local.json`. The live project is
`/Applications/logicalworks` (settings carry no hooks key). Re-register the hook against the live dir
before claiming live hook behavior. **Confirm the path with the Director before relying on it**
(INGESTION-PLAN.md header item 4; the global `verify-before-assert.sh` floor was deleted in the
2026-06-10 revert — the project-scoped hook is now the only inbound mechanism). The module + CLI + tests
do NOT depend on this; only the live-hook acceptance does.

### Acceptance (§7-INV — all required, falsifiable)
- **No prose:** property/fuzz test — NO input produces a pack with any free-text field (only cids,
  numbers, typed enums). Assert recursively over the dict.
- **Cap holds:** property test — NO input produces a serialized reflex pack over `limit_tokens`
  (PRD-04 04-a). Force overflow and assert truncation triggered.
- **Truncation order proven:** force overflow → assert lowest-RRF handles dropped first and every
  dropped cid appears in `budget.truncated`; assert `depth_handles` survive truncation.
- **Zero dangling handles:** every cid in `handles` resolves via `get_record` to a record present in
  the store (`store_count` > 0 fixture). A hallucinated/absent cid is a test failure.
- **RRF deterministic:** same inputs → byte-identical fused order (seed-stability, mirror `test_rank.py`).
- **Live (only after re-registration):** submit a prompt → hook injects a conformant `lgwks.inbound.v1`
  pack; on any internal error the hook still exits 0 and emits nothing.

### Done = green pytest + registry gate green + CLI `lgwks inbound run` works + REGISTRY/BUILDLOG/HANDOFF updated.

---

## PACKET I5.1 — directional `P_k` operator activation · P2 · NOT YET ISSUED (file it) · depends: I5 (done)

**One line:** make the schema relation operators genuinely directional — derive non-identity `P_k`
from the schema's declared relation direction so the cubic score stops collapsing to cosine, WITHOUT
breaking the §4.2 marginal-identity proof.

### Why this is next (honesty gap, HANDOFF.md "NOT built")
I5 shipped `R_k = P_k·diag(d_k)` with `P_k = I` for all 8 relations (`lgwks_score.py:73` `build_operators`
returns `perm=None, signs=None, mask=None`). So `score(i,k,j) = êᵢᵀêⱼ` — pure cosine, no directionality.
The machinery to be directional already exists and is tested (`score_triple` at `lgwks_score.py:98`
handles `perm`/`signs`/`mask`); only the DERIVATION is stubbed. I6's δ is a structural signal and I7's
RRF graph lane is relation-weighted-but-direction-blind until this lands. This packet activates the
real §4.2/§4.5 lane.

### Scope fence
The `P_k` derivation + its proofs ONLY. No new relations (the 8 in `RELATIONS` stand). No `diag(d_k)`
MRL slicing (that stays default-ones, DECISION §4). No re-rank of I6 semantics. No model layer — `P_k`
is a pure function of the schema file (`lgwks_score.py:33` `RELATIONS`), never learned.

### Verified inputs
- `lgwks_score.py:33-42` `RELATIONS` — 8 relations, all `direction: "directed"`, `arg_typing: None`,
  `dim_mask: None`.
- `lgwks_score.py:51-63` `FactoredRelation` (frozen): `relation_id, perm, signs, mask, direction`.
- `lgwks_score.py:73` `build_operators(dim, *, relations=RELATIONS)` — the function to change (currently
  all-identity).
- `lgwks_score.py:98` `score_triple(ei, rel, ej)` = `(P_k^T êᵢ)ᵀ (d_k ⊙ êⱼ)` — already consumes
  `perm`/`signs`; validates lengths; do NOT change its math.
- INGESTION-LAYER `§4.2` (line 128) and `§4.5` (line 176) — the RESCAL form and the `R_k = P_k·diag(d_k)`
  spec; the marginal-identity requirement `(1/m)Σ_k R_k = I`.
- REGISTRY.md:169 `lgwks.schema.relations.v1` (live, I5) — "operators identity in v1, directional Pₖ
  deferred → I5.1". Bump/extend this row.

### The hard constraint (the proof that must keep holding)
§4.2 proves AI(²) ⊂ schema(³) via: marginalizing the cube with `R_k = I` reproduces cosine. §4.5 keeps
this exact only if `(1/m) Σ_k R_k = I`. A naive directional `P_k` (e.g. a fixed shift permutation per
relation) will violate `(1/m)Σ P_k = I` and BREAK the marginal proof. **Design `P_k` so the per-relation
operators still average to identity**, OR explicitly renegotiate the proof with the Director (this is a
real fork — use AskUserQuestion). Two viable directions to evaluate:
- **(a) Direction via sign-flip involution:** `P_k` = a signed permutation that is its own inverse and
  whose family averages to `I`. Asymmetry `R_k ≠ R_kᵀ` comes from the sign pattern, marginal preserved if
  the family is balanced. Cheapest path that keeps the proof exact.
- **(b) Antisymmetric tie-break:** keep `(1/m)Σ R_k = I` by pairing each directed relation with a
  complementary operator so the mean is identity, while individual `R_k` are directional.
Pick the one that satisfies BOTH `score(i,k,j) ≠ score(j,k,i)` for directed relations AND
`(1/m)Σ_k R_k = I` to ≤1e-6. If neither closes cleanly, STOP AND ASK (the proof is load-bearing).

### Ordered steps
1. File the GitHub issue "I5.1 — directional `P_k` activation" (label `ingestion`), pasting this packet.
   Get it into the tracker before coding (CLAUDE.md: issue-backed work).
2. Decide derivation (a) vs (b) against the dual constraint above; record the choice + `//why` in the
   code. If it forks the §4.2 proof, AskUserQuestion first.
3. Implement the derivation INSIDE `build_operators` (`lgwks_score.py:73`): for `direction=="directed"`,
   emit a non-identity `perm`/`signs` derived purely from `relation_id`/typing (deterministic, replayable);
   `symmetric` relations keep identity. Do NOT touch `score_triple`.
4. Bump the schema if the operator semantics change observably: `lgwks.schema.relations.v1 → v2`
   (REGISTRY rule: bump on contract change). Update REGISTRY.md:169 + the `RELATIONS_SCHEMA` literal in
   `lgwks_score.py`. Run the registry gate from root.
5. Extend `tests/test_score.py` (and `test_lscore.py` if it covers operators) with the acceptance below.
6. BUILDLOG.md row; HANDOFF.md "NOT built / I5.1" → built; INGESTION-PLAN.md note + §8 G-04 line
   (currently "Directional `P_k` identity in v1 → I5.1") → closed.

### Acceptance (proofs, executed — all required)
- **Marginal identity preserved:** `(1/m) Σ_k score(i,k,j)|_{built operators}` reproduces the cosine
  matrix to ≤1e-6 on a frozen fixture (the §4.2 proof, re-run with the NEW operators — this is the
  guard that the directionality didn't break the order-2 ⊂ order-3 claim).
- **Genuine directionality:** for every `directed` relation, ∃ embeddings with
  `score(i,k,j) ≠ score(j,k,i)` by a pre-registered margin (today this is exactly 0 — that's the bug).
- **Replayable:** same schema → byte-identical operators (assert on `perm`/`signs` tuples).
- **Symmetric stays symmetric:** any `symmetric` relation ⇒ `R_k = R_kᵀ` ⇒ `score(i,k,j)==score(j,k,i)`.
- **Cross-model cid unaffected:** the I5 "same fact via 2 models → identical cid" test still passes
  (operators are scoring, not canonicalization — must be orthogonal).

### Done = green pytest (marginal + directionality + replay) + registry gate green + REGISTRY/BUILDLOG/HANDOFF/INGESTION-PLAN updated + issue closed.

---

## PACKET I8 — concurrency, queue, isolation · P3 (→ P0 before any multi-tenant/network exposure) · NOT YET ISSUED (file it) · depends: I1 (┄, done)

**One line:** no 5xx under load + hard tenant isolation — token-bucket admission, typed 429 + Retry-After
at saturation, idempotent shed on duplicate cid, and a capability-token isolation boundary that leaks
zero cross-tenant cids.

### Why P3 now but flagged
While ingestion is single-operator local, this is P3. It **escalates to P0 before any multi-tenant or
network exposure** (INGESTION-PLAN.md priorities; §8 gaps G-07 capability-token isolation = high/T0,
G-09 queue/admission = high). File it now so the boundary is built before exposure, not after an incident.

### Scope fence
Queue / admission / isolation ONLY. **No new compute, no new scoring, no model layer.** Does not change
what a worker does — only whether/when it is admitted and which tenant's data it can see.

### Verified inputs
- `lgwks_workercap.py` (98 lines, read in full) — `RESERVES` dict (`:26`), `probe_host()` (`:36`,
  env-pinnable via `LGWKS_HOST_RAM_GIB`/`LGWKS_HOST_CPU`, fail-closed), `compute_worker_cap(role_count,
  *, host, reserves)` (`:64`) → `{computed_cap, formula_headroom, memory_cap, cpu_cap, cap_basis, ...}`,
  schema `lgwks-worker-cap/1`. **`c` (the concurrency cap) = `compute_worker_cap(...)["computed_cap"]`.**
- crawler politeness (jittered backoff) — `crawler/src/` (gather/engine); reuse the backoff pattern, do
  not reinvent.
- `store/projects/` + `store/substrate-global/` — the path-separation that is TODAY's only isolation
  (G-07: path separation, no capability token). I8 adds the token boundary on top.
- `lgwks_vector.py` `VectorRecord` carries `tenant: str` (I1 contract, `:67`) — the field isolation keys on.

### Formulas (implement exactly — INGESTION-PLAN.md I8 + INGESTION-LAYER §6)
```
c   = compute_worker_cap(role_count)["computed_cap"]          # already built; do not recompute by hand
ρ   = λ / (c·μ)                          # utilization; STABLE requires ρ < 1
admission: token bucket, refill rate c·μ, burst capacity B    # rate-limit at the cap
Q ≥ Q_max  ⇒  reject with typed 429 + Retry-After             # bounded queue, never unbounded growth
duplicate submission (same cid) ⇒ ONE row                     # idempotent shed (cid is the dedup key, I1)
```
`μ` (service rate) and `B`, `Q_max` are config inputs — probe or pin them like `lgwks_workercap` pins the
host (env override for replay). Pre-register the values; do not fiddle under test.

### Ordered steps
1. File the GitHub issue "I8 — concurrency, queue, isolation" (label `ingestion`), pasting this packet.
   Note the P3→P0 escalation trigger explicitly in the issue body.
2. **New module `lgwks_admission.py`** (root convention). API:
   - `TokenBucket(rate, burst)` — `try_acquire() -> bool` (deterministic given a injected clock; make the
     clock injectable for replay/test, mirroring `probe_host`'s env-override discipline).
   - `Queue(q_max)` — `submit(item) -> Admitted | Rejected429(retry_after)`; dedup by cid (idempotent).
   - `admission_decision(load, *, cap, mu, ...)` → typed result.
   Reuse `compute_worker_cap` for `c`. Reuse crawler backoff for Retry-After jitter.
3. **Isolation boundary `lgwks_capability.py`** (or extend an existing tenant module — `git grep -niE
   'tenant|capability.?token|store/projects' -- '*.py'` FIRST to avoid minting a duplicate; repurpose >
   mint, REGISTRY rule 5). A capability token scopes a query to one `tenant`; a query without a valid
   token is rejected; cross-tenant cid access is impossible by construction (filter on `VectorRecord.tenant`).
4. **Contract:** if a payload crosses modules, register it (`lgwks.admission.v1` / `lgwks.capability.v1`
   — check REGISTRY.md harness family first; the `lgwks-worker-cap/1` artifact already exists and may be
   the right family). Run the registry gate from root.
5. **CLI** (if a verb is warranted): `add_parser(sub)` + `lgwks_home._DOMAINS` entry. A `lgwks admission
   info` / `lgwks workercap` surface for ops is reasonable; confirm scope with the Director if adding net-new
   operator surface.
6. Tests `tests/test_admission.py` + `tests/test_capability.py`; BUILDLOG row; HANDOFF/INGESTION-PLAN/§8
   (G-07, G-09) updates.

### Acceptance (§1-INV + §6, falsifiable — all required)
- **Stability sweep:** load test at λ ∈ {0.5·cμ, cμ, 2·cμ} → ρ<1 stable at 0.5×; bounded (no unbounded
  queue growth) at 1×; at 2× **every** rejection is a typed 429 with Retry-After and **zero 5xx**.
- **Idempotent shed:** duplicate submission of the same cid ⇒ exactly one row (dedup by cid, I1).
- **Tenant isolation (§1-INV):** 10⁴ randomized A/B cross-tenant queries leak **zero** cross-tenant cids.
- **Token required:** a query without a valid capability token is rejected (not served, not partial).
- **Replayable:** injected clock + pinned host/μ/B → deterministic admission decisions across runs.

### Done = green load/isolation tests + registry gate green + zero-5xx + zero-leak proofs recorded in BUILDLOG + issue filed and closed.

---

## File-it-too (HANDOFF.md backlog, NOT in this 3)
I9 (CRDT state), I10 (viz projection — never run ahead of the spine), I11 (waste ledger, needs I7
output). File as issues when their dependency is tested-green. Do not start a packet whose dependency is
not green (INGESTION-PLAN.md sequencing note — that is the blur the ordering prevents).
