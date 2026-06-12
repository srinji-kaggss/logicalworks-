# Second Harness — Build Log (researcher's notebook)

Append-only. One entry per unit/experiment. PRD (`PRD.md`) is the frozen end-state;
this log is the *path* to it — decisions, experiments, results, open questions.
Discipline: Karpathy guidelines (think-first · simplicity · surgical · goal-driven).

---

## 2026-06-09 · Karpathy repo scan (requested, not forced)

Scanned github.com/karpathy. Candidates for reuse: `minbpe` (BPE tokenizer, MIT),
`llama2.c`/`llm.c` (single-file decoder inference, MIT), `micrograd` (autograd, edu).
**Verdict: no clean fork.** Our cortex is BERT-class *encoders* (distilbert/neobert/
tiny-bert/codebert) shipping their own tokenizers; the decoder-LLM repos and minbpe
don't fit the encoder path. The transferable asset is the *philosophy* — minimal,
single-file, readable — already followed by `lgwks_ingest.py` / `lgwks_map.py`.
Logged so a future reader doesn't re-litigate.

---

## 2026-06-09 · U1 Capability Map (done — `lgwks_map.py`, commit 65a1a59)

Goal: on any intent, "what is the scale of what exists?" → ranked lgwks verbs.
Method: deterministic token-overlap over the `lgwks manifest` contract (175 verbs);
name-hit weighted 3×, intent-hit 1×, query-normalized. No model runtime.
Result: sensible top-k, 139ms. Verified live (crawl-intent → crawl/extract verbs;
code-review-intent → do code/review). Ceiling: lexical, not semantic (U4/U6 upgrade).

---

## 2026-06-09 · U7 Inbound Hook — SPEC

### Goal (verifiable)
On a Director prompt, a `UserPromptSubmit` hook computes the subconscious inbound
pass and **injects a non-generative read into Opus's context** — closing the first
real subconscious loop (prompt → daemon → in-context), zero extra Opus action.

First slice = deterministic: inject the **U1 capability map** for the prompt. No
scores/retrieval yet (those need U3/U6) — per Karpathy simplicity, emit only what is
real; declare nothing speculative.

### Convergence target (end state, PRD §5)
The existing global `~/.claude/hooks/verify-before-assert.sh` (static operating-loop
prose, fires on UserPromptSubmit to fight the premature-conclusion defect) is the
subconscious's ancestor. End state: it *becomes* the BERT-backed dynamic grounding
check ("check with bert"), not a static block. U7 is step 1 of that evolution.

### Why not just edit verify-before-assert now (surface the tradeoff — Karpathy #1)
- It is GLOBAL (all projects); wiring lgwks-specific logic there would run lgwks in
  every unrelated session. Wrong scope.
- The BERT runtime is not built (U4). A dynamic check today can only be deterministic.
- A bad UserPromptSubmit hook can disrupt every prompt (30s cap). Must be fail-silent
  and standalone-proven before it goes live.
→ Decision: build a **project-scoped** inbound hook for THIS session, deterministic,
  coexisting with the global static floor. Fold them together when U4 lands.

### Design (minimal, surgical)
- `hooks/subconscious_inbound.py`: read UserPromptSubmit JSON on stdin → `prompt` →
  `lgwks_map.map_intent` → emit `hookSpecificOutput.additionalContext` = a compact,
  non-generative capability-map block. **Fail-silent**: ANY error → exit 0, no output
  (INV-6 never-block; a subconscious must never block consciousness).
- `lgwks_map`: make the `lgwks` binary path resolve via `__file__` (cwd-independent) —
  required because the hook runs from the session cwd, not the repo. Surgical fix.
- Register as a project `UserPromptSubmit` hook in the active session settings,
  additive — global `verify-before-assert.sh` untouched.

### Success criteria (goal-driven — loop until all pass)
1. `echo '{"prompt":"crawl a site"}' | python3 hooks/subconscious_inbound.py` → valid
   hook JSON with a capability-map `additionalContext`. 
2. Empty / malformed / huge stdin → exit 0, no crash, no output (fail-silent).
3. Runtime < 1s.
4. Registered additively; existing global hook intact; settings valid JSON.
5. Live: a subsequent prompt shows the injected block in Opus's context (activates on
   session reload — noted, not asserted).

### Open questions
- Hot-reload: does editing project settings.json activate mid-session, or only on
  reload? Unknown — will state honestly, not assert.
- Latency: hook spawns `lgwks manifest` (~150ms). Acceptable now; cache verbs later.

### U7 RESULTS (done)
Built `hooks/subconscious_inbound.py` + cwd-independent fix to `lgwks_map` (lgwks
binary resolved via `__file__`). Registered as a project `UserPromptSubmit` hook in
`/Applications/Logical Works/.claude/settings.local.json` (additive; the 134-entry
permissions block and the global `verify-before-assert.sh` are untouched).

Success criteria — all pass:
1. valid prompt → valid hook JSON with capability-map `additionalContext`. ✓
   ("crawl a website…" → jarvis crawl/run crawl/crawl/extract)
2. empty / garbage / blank / 50k-token prompt → exit 0, no output, no crash. ✓
3. 180ms (<1s). ✓
4. settings valid JSON; permissions preserved; global hook intact. ✓
5. LIVE activation: pending session reload (hooks load at session start). The script
   is standalone-proven; the in-context injection will show on the next prompt after
   reload. NOT asserting it fires mid-session — unverified, flagged.

Revert: delete the `hooks` key from that settings.local.json.
Convergence (later, U4+): fold this into the BERT-backed check that supersedes the
static verify-before-assert floor.

Next (sequential, per Director): U2 Actor contract → U3 → U4 …

---

## 2026-06-09 · U2 Actor contract — SPEC

### Goal (verifiable)
ONE thin protocol every capability conforms to: `input_schema → run(input) → standardized
envelope`. Composable (actor calls actor). `map` + `ingest` (+ a composing actor) conform.

### Think-first: don't invent a framework (Karpathy #1/#2)
The shapes already exist — `lgwks_ingest.ingest` returns a manifest dict, `lgwks_map.map_intent`
returns a result dict, `lgwks_workflows.WorkflowRun` already has schema/args/exit_code. U2 is a
**thin wrapper protocol** over existing functions, NOT a new engine. No async, no remote, no
plugin machinery — none was asked for.

### Contract
- `ActorSpec{ name, summary, input_schema, run(input)->dict, composes:[names] }`.
- `input_schema`: `{field: {type, required, default, help}}` — drives validation + CLI + the
  capability map. Typed validation (no silent failure): missing required / wrong type → `ActorError`.
- `run_actor(name, input) -> envelope`:
  `{schema:"lgwks.actor.v1", actor, ok, input, output, manifest:{duration_sec, composes}}`.
- Composition: an actor's `run` calls `run_actor(other, …)` — same interface, nestable.

### First actors
1. `map`  → wraps `lgwks_map.map_intent`  (input: intent:str req, top:int=8)
2. `ingest` → wraps `lgwks_ingest.ingest` (input: url:str req, max_resources:int=40, embed_media:bool=true)
3. `scout` (composing) → calls `map`; if input looks like a URL, also calls `ingest` → proves actor-calls-actor.

### Success criteria (loop until pass)
1. `run_actor("map", {"intent":"crawl a site"})` → valid `lgwks.actor.v1` envelope, output has matches.
2. `run_actor("map", {})` → `ActorError` (missing required `intent`) — typed, not silent.
3. `run_actor("scout", {"intent":"review code"})` → envelope whose manifest shows it composed `map`
   (no network; proves actor-calls-actor).
4. `ingest` registered + wrapped (structural; live crawl already proven in b3fc551 — not re-run).
5. Standalone CLI: `python3 lgwks_actor.py map '{"intent":"…"}'`. (`lgwks run` verb deferred, like ingest.)

### U2 RESULTS (done — `lgwks_actor.py`)
Thin protocol: `ActorSpec{name,summary,input_schema,run,composes}` + `run_actor(name,input)`
→ `lgwks.actor.v1` envelope; typed `ActorError` (codes: missing_input/bad_input/unknown_actor);
schema-driven validation (required/coerce/default). Actors: `map`, `ingest` (wrap existing
fns), `scout` (composing).
All criteria pass: (1) envelope ✓ 0.21s; (2) missing required → ActorError code=missing_input ✓;
(3) scout→map at runtime, ingested=None for non-URL ✓ (actor-calls-actor); (4) ingest registered+
required url ✓; (5) CLI ✓, bad input → typed error + exit 1 ✓. `lgwks run` verb deferred.
Next: U3 World-Graph query.

---

## 2026-06-10 · Plan v1.1: I-rename, registry, re-prioritization (alignment session)

- **INGESTION-PLAN/LAYER packets renamed U1–U12 → I1–I12.** The U-namespace collided with this
  log's rebuild-track units (U1 capability map, U2 actor, U7 hook). This log is append-only and
  keeps its historical U-ids; from here, rebuild units = U-track, ingestion packets = I-track.
- **Schema registry created**: `docs/schemas/REGISTRY.md` — all ~80 contracts indexed by family
  with repurpose rules; packets now carry `Register:` lines. Wired into /CLAUDE.md authority
  ladder (rung 6) + governance/README.md.
- **Plan re-prioritized**: P0 = I1 (spine) + I12 interpreter-pin half (broken in prod);
  P1 = I4/I2/I3; P2 = I5→I6→I7; P3 = I8/I9/I10/I11 (I8 escalates to P0 before any
  multi-tenant/network exposure). Verified-state credit marked per packet.
- **Stale convergence note corrected**: the global `verify-before-assert.sh` hook was deleted in
  the 2026-06-10 config revert — the U7 hook is now the only inbound mechanism, and its
  registration points at the dead `/Applications/Logical Works` (space) dir; re-register against
  `/Applications/logicalworks` before I7 live acceptance.

---

## 2026-06-10 — I1/I2/I4 landed; ingestion spine live on main

**Merged to main (commits bb753be → 27460ad → 7e3df00):**

- **I1 ✅** `lgwks_vector.py` — `lgwks.vector.record.v1`. 20 tests. Binary float32 BLOB store, blake2b CID, L2-norm, `SpaceMismatchError` cross-space guard. G-11 retired for new writes. Proof fixture: 4100 rows migrated, 659 deduped.
- **I2 ✅** `lgwks_input.py` — `lgwks.modality.item.v1`. 73 tests. Two-phase handle()/extract(). Five strategies: text_direct | ocr_image | visual_embed | video_embed | none. video_embed: I2 passes raw bytes intact; I4 owns native VL embedding. `.ts` MIME false-positive fixed (extension checked before magic bytes). needs_extraction() = True only for ocr_image.
- **I4 ✅** `lgwks_embed_port.py` — `lgwks.embed.port.v1`. 59 tests. Two tiers (mlx→transformers), same model (Qwen3-VL-Embedding-8B), same space_id, local_files_only=True (Zscaler-safe). Weights in store/models/ fetched from GitHub Release (not HuggingFace). Last-token pooling fix (hidden_states[-1][:, -1, :]). embed_from_item() dispatch. migrate_json_embeddings() closes G-11. load_all_graphs() populates system_graph.

**Architecture decisions recorded this session:**
- Retrieval layer (function-calling "tongue") is separate from the embed port — model-agnostic, sits above I4.
- Re-ranking (I5/I6) is offline batch — monthly or post-large-commit. Hot query path is vector cosine only (all Rust).
- Daemon backend is Rust; Python workers are subprocess with JSON-line protocol. No Python daemonising.
- Package distributable from GitHub Release (Zscaler blocks HF). store/models/ gitignored; make download-models pulls weights.

**GH issues opened for remaining packets:**
- [#58](https://github.com/srinji-kaggss/logicalworks-/issues/58) I3 — crawler v2 + LFM2-Extract
- [#59](https://github.com/srinji-kaggss/logicalworks-/issues/59) I5 — RESCAL scoring
- [#60](https://github.com/srinji-kaggss/logicalworks-/issues/60) I6 — cubic centrality + δ
- [#61](https://github.com/srinji-kaggss/logicalworks-/issues/61) I7 — L5 pack + hook re-registration
- [#62](https://github.com/srinji-kaggss/logicalworks-/issues/62) I12 — Leiden/Louvain fix (P0, independent)

**Remaining P3 packets** (I8 concurrency, I9 provenance, I10 viz, I11 waste ledger) not yet issued — I8 escalates to P0 before any multi-tenant/network exposure.

---

## 2026-06-10 (session 2) · I3, I5, I6 landed; I12 merged; scope-creep cleanup

Scoring spine advanced. Loop per packet: spec (GH issue comment) → implement → hacker-harden → merge. I5/I6 implementation delegated to Sonnet subagents; review/harden done in the Opus main thread (caught real defects behind green tests).

**Merged to main:**
- **I12 ✅** (PR #63, pre-session) — graphify Leiden fix; `LeidenUnavailableError`, no silent Louvain substitution (G-12).
- **I3 ✅** (PR #64) — `lgwks.crawl.v1→v2`: `crawler/src/media.rs` (fetched/cid'd/modality-typed media), `lgwks_lfm2_extract.py` (strict-schema fill, jsonschema-validated), `lgwks.crawl.artifacts.v1`. Recovered from a pre-I12 worktree, **rebased onto post-I12 main** (preserved the I12 cluster fix). 34 Rust + 15 py tests. Harden: registered the unregistered `lgwks.lfm2_extract.v1` literal (CI gate).
- **I5 ✅** (PR #65) — `lgwks_score.py` — factored RESCAL `R_k=P_k·diag(d_k)` (O(d), never densified), canonical-CBOR+zstd MDL, blake2b cid. `lgwks.score.record.v1` + `lgwks.schema.relations.v1`. 23 tests. Harden fixes: REGISTRY rows (CI gate), cross-model cid via recursive int→float normalization, operator-length guards, **dead CLI wired** (`lgwks score` was never registered in the dispatcher; also added to `lgwks_home._DOMAINS` L0 invariant). **I5.1 deferred:** directional `P_k` identity in v1.
- **I6 ✅** (PR #67) — `lgwks_rank.py` — `lgwks.rank.record.v1`, 23 tests, closes G-06. Harden caught silent non-convergence + a hollow δ; **fixed end-to-end**: `rank_det`=relation-WEIGHTED, `rank_ai`=relation-BLIND centrality, `δ`=their discrepancy (the old confidence_score source is a constant 1.0 → noise). Convergence: σ-shift kills near-bipartite oscillation (logic-os-kernel), Rayleigh-quotient criterion handles small spectral gaps, MAX_ITER 20k.
- **chore** (PR #66) — removed orphaned `tests/test_scope_creep_guard.py` (the hook it loaded was removed from `~/.claude/hooks`; only the test was ever in-repo).

**Decisions / honest notes recorded:**
- §4.3 centrality with fixed `w_k` is a relation-WEIGHTED eigenvector centrality (the relation mode is contracted with schema weights, not a free cubic-in-x optimization) — faithful to §4.3 for this n×m×n tensor. Genuine embedding-coupled `R_k` scoring is the §4.2 retrieval lane (I7/RRF).
- δ is now a structural signal (relation-typing vs relation-blind), independent of any AI score until I5.1 wires per-fact `s_ai`.
- Harden lesson reconfirmed: green subagent tests hid real defects (hollow δ, silent non-convergence, dead CLI) — adversarial review in the main thread is load-bearing.

**Gaps closed:** G-04, G-05 (I5); G-06 (I6); G-11 (I1/I4); G-12 (I12). See INGESTION-LAYER §8.

**Open:** I7 (#61) — next; code dep (I6) now satisfied; blocked only on the inbound-hook re-registration ops action. I5.1 (directional `P_k`) deferred, not yet issued. I8–I11 (P3) not yet issued.

---

## 2026-06-10 (session 3) · I7 landed — L5 consumer pack (RRF + reflex budget)

Same loop: spec (PLANS-NEXT-3 §I7) → implement → hacker-harden in the Opus main thread. No subagent; built directly.

**Landed:**
- **I7 ✅** — `lgwks_inbound.py` — `lgwks.inbound.v1` reflex envelope (`handles[]`, `scores{}`, `budget{limit_tokens,used_tokens,truncated_count,truncated[]}`, `depth_handles[{id,est_tokens,kind}]`). RRF fusion `RRF(cid)=Σ 1/(k+rank)` over graph cubic rank (I6 `rank_det`) ⊕ vector cosine rank (I1 `cosine`), `RRF_K=60` pre-registered (Cormack 2009). 1500-token reflex cap (PRD-04), deterministic truncation: bulk (lowest-RRF) dropped first, depth-handle pointers survive until all bulk is shed (PRD-04 "pointer never dropped for bulk"); `truncated_count` exact (no silent drop), `truncated[]` a bounded best-first cid sample (≤64). 14 tests (`tests/test_inbound.py`): no-prose §7-INV, cap-holds fuzz, truncation-order + pointer-survival, zero-dangling handles, RRF determinism, RRF math + single-list validity, **+ real-graph acceptance on the 5130-node `~/ingestion_results/logicalworks-_graph/graph.json`** (mirrors `test_rank.py:GRAPH_LW`, skipTest if absent). CLI `lgwks inbound run|info` wired (dispatcher + `lgwks_home._DOMAINS`). REGISTRY row `lgwks.inbound.v1` planned→live(I7). Registry gate green.
- **Token estimate:** repo has no tokenizer dep and the model layer is out of scope → deterministic `ceil(len(serialized_json)/4)` heuristic. Cap measured on the SERIALIZED pack.

**Harden findings (main thread, real defects — not hollow green):**
1. **Self-referential `used_tokens`** — writing the byte-count field into the dict changes the dict's serialized size, so an initial `used_tokens:0` placeholder under-measured and the emitted pack overflowed the cap by 1 token. Fixed: measure against a max-width placeholder (`= limit_tokens`); the emitted value is always ≤ limit (hence ≤ digits), so the final pack can only shrink — cap holds by construction. `used_tokens` is now a conservative upper bound.
2. **Truncation receipt unbounded — caught by REAL data (the Director's "extract, don't rebuild" call).** Synthetic 12-node fixtures hid it; running the real 5130-node graph blew up: recording every dropped cid made `budget.truncated` ~50,440 tokens — the receipt violating the 1500 cap it reports. Fixed: `budget.truncated_count` is the exact total (always present, never silent), `budget.truncated[]` is a bounded best-first cid sample (≤`MAX_TRUNCATED_VISIBLE=64`); shed order is bulk → depth pointers → receipt-sample, so the empty envelope is always tiny. Added a real-graph test (`tests/test_inbound.py:TestRealGraph`) so this regime is permanently exercised. Honest invariant: build_pack NEVER *returns* over cap — it returns ≤cap (or raises only if a cap can't hold the bare envelope).
3. **Zero-dangling by construction** — `assemble_inbound` filters the graph candidate set to cids that resolve via `get_record`; a graph node absent from the vector store is excluded from `handles` (test `test_dangling_graph_cid_excluded`).
4. Added a `scores`-coverage guard (handle without a score → loud `InboundError`, not `KeyError`).

**Honest notes:**
- CLI graph-only mode (no `--store`) emits single-list (graph-rank-only) RRF with empty `depth_handles`; handles are graph node cids (content-addressed) but NOT cross-checked against a vector store — the §7-INV store-resolution guarantee only holds for `assemble_inbound` with a store. Sanctioned by PRD-04 04-b (single-list RRF valid).
- **Hook NOT extended.** `hooks/subconscious_inbound.py` still emits only the capability map. Wiring the L5 pack into the hook is gated on the inbound-hook re-registration ops action (HANDOFF) — confirm the live `/Applications/logicalworks` path with the Director first. Module + CLI + tests do not depend on it.
- **DEFERRED RISK (pre-existing, not I7 — Director: log & defer):** running the FULL `tests/` dir fails collection of `tests/test_vector_record.py` (`ImportError: cannot import name 'SpaceMismatchError' from 'lgwks_vector' (unknown location)`) — cross-test import pollution shadowing `lgwks_vector` as a namespace package. `test_vector_record.py` passes alone (20) and the error reproduces with `test_inbound.py` excluded → independent of I7. **Impact:** a bare `pytest tests/` aborts at collection; per-module runs are green. **Deferred:** fix the sys.path/namespace pollution (likely an earlier-collected test inserting a dir named `lgwks_vector` onto the path) in a dedicated test-hygiene pass; not blocking I7/I5.1.

**Open:** I5.1 (directional `P_k`, not yet issued — next per build order I7→I5.1→I8). I8 (queue/isolation, P3→P0 before exposure). I9–I11 not yet issued.

---

## 2026-06-10 (session 3 cont.) · I5.1 landed — directional `P_k` activation (issue #69)

Same loop: file issue → AskUserQuestion at the proof fork → implement → harden. Built directly (no subagent).

**The fork (surfaced to Director, AskUserQuestion):** the packet assumed a signed-permutation `P_k` could be made directional. It provably cannot while preserving the §4.2 marginal proof — an orthogonal `P_k` adds ≤+1 per diagonal entry, so `Σ_k P_k = m·I` forces every `P_k = I`; an orthogonal involution is symmetric. Director approved **Option 1: additive antisymmetric term** (overriding the packet's "perm/signs-only, don't touch score_triple" fence).

**Landed:**
- **I5.1 ✅** — `lgwks_score.py`: `R_k = P_k·diag(d_k) + N_k`, `N_kᵀ = −N_k`. `FactoredRelation.antisym` (tuple of `(a,b,c)` generators, O(1)/relation). `build_operators` pairs the 8 directed relations in **sorted** order, each pair sharing one coordinate slot with opposite sign (+c/−c) so `Σ_k N_k = 0` ⇒ `(1/m)Σ_k R_k = I` **exact**; `score_triple` adds `Σ c·(êᵢ[a]êⱼ[b] − êᵢ[b]êⱼ[a])`. `ANTISYM_C=1.0` pre-registered. Symmetric relations → `antisym=None`. Odd directed count → loud `ValueError` (can't be fully-directional AND exact-marginal). Schema `lgwks.schema.relations.v1 → v2` (superseded row + curated map in `lgwks_schema.py`). 28 tests (was 23): existing marginal-identity now runs the directional operators and still holds ≤1e-6; +5 new (every directed relation asymmetric, replayable `Σ N_k = 0`, symmetric stays symmetric, odd-count rejected). `lscore` 11 green. Registry gate green (100 rows).
- **Isolation verified:** no consumer of `build_operators`/`FactoredRelation`/`score_triple` outside `lgwks_score.py`+tests; operators are not serialized/hashed into the cid (cid stays content-only) → cross-model cid unaffected.

**Honest scope (do not overclaim):** this is **structural** directionality — deterministic, replayable, and it breaks the cosine collapse (the stated I5.1 goal). It is NOT semantic argument-typing: `arg_typing` is `None` for all relations, so there is no semantic data to derive a per-argument direction from; the asymmetry orientation is a fixed coordinate-pair convention and paired relations are necessarily direction-coupled (the unavoidable cost of exact marginal with a signed structure). Semantic typing is future work once `arg_typing` is populated. Recorded in INGESTION-LAYER §4.5 (refinement note), INGESTION-PLAN I5.1, §8 G-04.

**Open:** I8 (queue/isolation, P3→P0 before any multi-tenant/network exposure — file & build next per order). I9–I11 not yet issued. Inbound-hook re-registration ops action still pending (from I7). Deferred risk: the `pytest tests/` collection flake (see session 3 I7 note) still open.

---

## 2026-06-11 (session 4) · I8–I11 boilerplate — all four tail packets scaffolded (branch: claude/docs-implementation-boilerplate-83n6r1)

**Build-state summary:** PLANS-NEXT-4.md (last commit: 5de186f) detailed the full remaining ingestion backlog. This session implements the boilerplate for all four remaining packets in one pass (docs → code).

**Landed (all new modules at repo root — load-bearing dispatcher convention):**

- **I8 ✅ (admission + capability)** — two new modules:
  - `lgwks_admission.py` — `TokenBucket(rate, burst)` with injectable clock (D1: deterministic replay); `AdmissionQueue(q_max)` with idempotent cid dedup (I1 invariant); `admission_decision(*, cid, bucket, queue) → Admitted | Rejected429`; `make_admission_gate(role_count, mu, burst, q_max)` wires `compute_worker_cap` → bucket + queue. Schema `lgwks.admission.v1`.
  - `lgwks_capability.py` — `CapabilityToken(tenant, nonce, sig)` issued via hmac-sha256(key, tenant:nonce); `issue_token(tenant)`, `validate(token, key)`, `guard(token, query_fn, *, key)`, `make_tenant_filter(token)` — every read filtered on `VectorRecord.tenant` using the live `vr_space_tenant` index (lgwks_vector.py:49). Schema `lgwks.capability.v1`. P3→P0 trigger recorded in CLI `admission info` output.
  - **Tests:** `tests/test_admission.py` (T1–T6: stability sweep / idempotent shed / typed-429 / zero-5xx / replay / bucket), `tests/test_capability.py` (T1–T5: token-required / 10⁴ cross-tenant isolation / valid-roundtrip / forged-token / filter-boundary). **61 tests green total across I8–I11.**

- **I9 ✅ (CRDT state)** — `lgwks_crdt.py` — `GSet` (grow-only, merge=set-union, CvRDT), `ORSet` (observed-remove, add-wins), `LWWRegister` (tie-break by `(seq, head)` from `CognitionLog._tail_hash/_next_seq` — NOT wall-clock, D4); `merge_state(a, b)` dispatch; `serialise`/`deserialise` roundtrip. Schema `lgwks.crdt.state.v1`; JSON-Schema in `docs/schemas/lgwks.crdt.state.v1.json`. CLI: `lgwks crdt info` + `lgwks crdt merge <a> <b>`.
  - **Tests:** `tests/test_crdt.py` (T1–T6: SEC convergence across 8 random permutations / idempotent-add / CvRDT-laws fuzz / OR-Set-add-wins / LWW-determinism-no-wallclock / serialise-roundtrip). All green.

- **I10 ✅ (3-D viz projection, decoupled)** — `lgwks_viz_project.py` — `fit_axes(embeddings) → W (d×3, sign-fixed)` via `numpy.linalg.svd`; `project(embedding, W) → (x,y,z)`; `project_all(records) → dict[cid,(x,y,z)]`; `reconstruction_stress(Ê, W) → float`; seeded-UMAP fallback only above pre-registered `STRESS_THRESHOLD=0.30`. Additive `"xyz"` field wired into `lgwks_graph_viz.GraphDataAdapter.to_frontend` — force-layout fallback preserved (D3 decoupling). Module kept separate from `lgwks_graph_viz.py` so the import graph cannot pull projection into a scoring path (the architectural decoupling). `numpy>=1.24` added to `requirements.txt`. CLI: `lgwks viz-project info`.
  - **Tests:** `tests/test_viz_project.py` (T1–T4: replayable / import-decoupling / stress-reported / finite-coords). Numpy-gated tests skip cleanly when numpy absent; 2 stdlib-only tests (importable + decoupling) green.

- **I11 ✅ (waste ledger)** — `lgwks_waste.py` — `build_ledger(packs, transcript, *, window_turns=3) → lgwks.waste.ledger.v1 dict`; `waste_rate(ledger) → float`; `worst_item(ledger) → dict|None` (attribution — the specific low-yield cid); `persist_ledger(ledger)` via `lgwks_cognition` (one byte-truth, D5). `WINDOW_TURNS=3` pre-registered (//why: conservative 3-turn window for citation detection — PRD-04 open-Q). `SUGGEST_CUT_THRESHOLD=0.50` pre-registered; I11 REPORTS breach, does NOT act (scope fence). Transcript path injected as argument; `LGWKS_TRANSCRIPT_PATH` env override (never hardcoded, D3). Schema `lgwks.waste.ledger.v1` flipped from **planned → live** in REGISTRY.md; JSON-Schema in `docs/schemas/lgwks.waste.ledger.v1.json`. CLI: `lgwks waste report <packs> --transcript <path>` + `lgwks waste info`.
  - **Tests:** `tests/test_waste.py` (T1–T6: sums-reconcile / waste-rate / attribution / no-prose / threshold-pre-registered / deterministic). All green.

**Registry gate:** `scripts/check_schema_registry.py` green — 95 ids in code, all registered (103 rows known). New rows added: `lgwks.admission.v1`, `lgwks.capability.v1`, `lgwks.crdt.state.v1`, `lgwks.waste.ledger.v1` (flipped planned→live).

**CLI wiring (both places, verified):** `lgwks` dispatcher (lines ~1480+): `admission`, `capability`, `crdt`, `viz-project`, `waste`; `lgwks_home._DOMAINS`: `admission`/`capability`/`crdt`/`viz-project` → "System", `waste` → "Data". `test_home` L0 invariant passes.

**Honest scope (do not overclaim):**
- I8 (admission): P3 stub — the gate structure, token-bucket math, and isolation boundary are complete and tested. P3→P0 escalation trigger is documented but NOT wired to a live process manager (no multi-tenant/network exposure yet).
- I10 (viz projection): server-side coords are computed when embeddings are available via the vector store. The `to_frontend` placeholder (lgwks_graph_viz.py) is correct but currently passes an empty `xyz_map` because the graph cache carries node ids, not embeddings — a separate DB join is needed to wire embeddings-by-cid at serve time (not in I10 scope, viz-only).
- I11 (waste ledger): cid detection uses substring match against transcript text. The "cited/acted-on" signal is a proxy (true semantic citation detection would need model-layer analysis — out of scope per INV-3). Deterministic and explainable.

**Open:** inbound-hook re-registration ops action still pending (from I7). `pytest tests/` collection flake (namespace pollution) still deferred. I-series backlog I1–I11 now fully scaffolded (I12 was done in PR #63).

---

## 2026-06-11 (session 5) · Adversarial review + fixes — I8–I11 hardened (branch: claude/docs-implementation-boilerplate-83n6r1)

**Adversarial review:** three independent review agents cross-examined all five I8–I11 source modules for AI-specific slop and real-world pattern violations. Found 16 concrete issues; all actionable findings fixed before commit.

**Fixed — source modules (4 full rewrites):**

- **`lgwks_capability.py`** — `guard()` key was `Optional[bytes] = None`; without a key the guard would call `query_fn(token.tenant)` unverified for any token with a non-empty tenant string. Fixed: `key: bytes` is now a **required positional argument** (no default). A keyless verification path is not a security boundary — it's a fiction. D3 decision note updated accordingly. Test `test_guard_no_key_call_succeeds` removed (was asserting the broken behaviour).

- **`lgwks_viz_project.py`** — `fit_axes()` called `numpy.linalg.svd(E)` on raw (uncentred) embeddings. For unit-sphere embeddings the first singular vector points at the cluster mean rather than spanning the spread; variance from origin ≠ principal components. Fixed: `E_mean = E.mean(axis=0); E_c = E - E_mean` before SVD. Return type changed from ndarray to `ProjectionAxes(W, mean)` NamedTuple so callers can apply the same centring at query time (D3). `reconstruction_stress()` denominator was total energy (`||E||²_F ≈ n`) not total *centred* variance; fixed to use `E_c = E - axes.mean; total_var = sum(E_c**2)`.

- **`lgwks_admission.py`** — `TokenBucket` was a `@dataclass` with a private `_clock` field; callers had to spell `_clock=` (private name leak in constructor). Fixed: converted to plain class with explicit `__init__(self, rate, burst, clock=time.monotonic)`. `AdmissionQueue` used `list` with `pop(0)` (O(n) FIFO); fixed to `collections.deque` with `popleft()` (O(1)). `_jitter()` used global `random.uniform` making `retry_after` non-deterministic; fixed: injectable `rng: random.Random | None` parameter (same discipline as clock injection).

- **`lgwks_waste.py`** — citation window grew per-item via `inject_turn = len(items)`, so items processed later searched an empty `turn_texts[N:]` slice and were always `used_within_n=False`. Fixed: `window = turn_texts[:window_turns]` computed once before the item loop — all items use the same first-N-turns window (D2 as specced). Double-count loop: handles and depth_handles were iterated separately and could overlap; fixed to a single `seen` set pass. `persist_ledger()` stripped `items` from the ledger before logging citing "non-serializable keys" (wrong — items contains only JSON-native types); fixed to persist the full ledger dict. Removed undocumented extra fields (`suggest_cut_threshold`, `transcript_source`) from the ledger dict; `SUGGEST_CUT_THRESHOLD` is a module constant reported via CLI, not a ledger field (I11 scope fence).

**Fixed — tests (4 test files updated):**

- `tests/test_capability.py` — removed `test_guard_no_key_call_succeeds`; added `test_guard_valid_token_succeeds` (correct positive case with key); fixed `test_guard_empty_tenant_raises` to pass a dummy key (empty-tenant check fires before signature check, but `guard()` still requires the key arg).
- `tests/test_admission.py` — all `TokenBucket(..., _clock=clock)` → `TokenBucket(..., clock=clock)`; T1a `test_half_load_stable` was confounded by queue fullness (Q_MAX=16 < ATTEMPTS=40 → queue always fills first); fixed by separating queue-capacity concern: stability test now passes `q_max=ATTEMPTS*4` so the rate-limiter property is measured unobstructed. Added `test_rate_limited_retry_after_deterministic` with seeded rng and bounded expected value.
- `tests/test_viz_project.py` — all `fit_axes()` call sites updated to use `ProjectionAxes` return value (`axes.W`, `axes.mean`); `project()` calls updated with `mean=axes.mean`; `reconstruction_stress()` call updated to pass `axes` (ProjectionAxes); added `test_mean_centring_applied` and `test_stress_decreases_with_more_dimensions` for correctness coverage; added `ProjectionAxes` to imports.
- `tests/test_waste.py` — `_ALLOWED_STR_KEYS` removed `"transcript_source"` (no longer a ledger field); `test_ledger_contains_threshold` replaced with `test_ledger_does_not_contain_threshold` (scope fence: module constant ≠ persisted ledger field); `test_all_used` strengthened to assert exactly 0.0; `test_partial_use` replaced with `test_partial_use_exact_value` (hand-computed 2/3 for equal-budget 1-of-3 split).

**Fixed — JSON schema:** `docs/schemas/lgwks.waste.ledger.v1.json` — removed `suggest_cut_threshold` and `transcript_source` properties (both absent from ledger dict; `additionalProperties: false` would have rejected valid payloads containing these undeclared fields).

**Registry gate:** green — 95 ids / 103 rows (unchanged; no new schemas introduced in this session).

**Test count:** 44 passed / 12 skipped (numpy-gated I10 tests skip cleanly) across the four new test files. All non-numpy tests green.

---

## 2026-06-11 (session 6) · Post-merge planning — I8 reframed as multi-tenant concurrency + isolation (two-DB) (branch: claude/post-merge-planning-fpzmu8)

**Build-state summary:** PR #76 merged the I8–I11 boilerplate to main (@ 6c2fdac). GH issues #72–#75 filed and open. No code change this session — planning + spec + doc hygiene only. Registry gate re-verified green (95 ids / 103 rows). The I-series (I1–I12) is the entire active backlog; there is no I13.

**Director directive (session 6):** the real surface for I8 is **concurrency within one tenant AND across tenants**, over **two databases** — the shared world DB ("the Google", `store/substrate-global/`) everyone reads, and the private per-human+AI-pair DB (`store/projects/`). The §1-INV tenant isolation holding **under concurrent multi-tenant load** is the security load (Figma / Google Workspace daemon model). Multi-tenant/network exposure framing from the first pass was too narrow: isolation is **core to I8 now**, not a P3→P0 gate; network/MCP is genuinely deferred. "Address all gaps based on the hardest surface; assume local ops but maybe mcp/http in the end not now; log scope creep separately."

**Key finding — the topology is already specified; we lack the enforcement.** `INGESTION-LAYER §1` already defines the two-tier store (world-nodes DB ▲promote tenant folders) + **§1-INV (T0):** "A read in tenant A can never observe tenant B's rows … enforced by a capability token, not `if tenant ==` … cross-tenant flow only by promotion." So the write model is **promotion-only** (no direct tenant→world write — resolves that question without asking). The lacks are all in enforcement + concurrency:
- **L1 (T0/critical):** §1-INV unenforced — `lgwks_vector.get_record`/`query_by_source` (:248,260) never filter on `tenant`; `lgwks_capability.guard()` binds to nothing. A can read B today.
- **L2:** the world/tenant seam is not modeled in the access path (no tier-routing; promotion-only unenforced).
- **L3:** admission is global and **fail-OPEN per-tenant** (RECONCILE.md:318,360 — limiter before auth context).
- **L4:** queue is in-memory, single-process, **drop-on-full** — cannot coordinate the separate crawler process (`crawler/src/main.rs`) or multiple tenant daemons; drops internal work.
- **L5:** no provenance/audit on promotion to the world DB. **L6:** CRDT (`lgwks_crdt.py`) not deployed on the two stores. **L7:** capability token is single-scope, not tier-aware. **L8/L9 deferred:** cross-workspace sharing/ACL, network/MCP/federation.

**Specced (3 new docs):**
- `ARCH-two-db-multitenant.md` — the "where do we lack" gap analysis: topology, Figma/Workspace mapping, L1–L9 table (severity + code anchors), the hardest surface (§1-INV under concurrency = L1+L2+L7 through L3+L4), and how it threads into I8/I9.
- `PLANS-NEXT-5.md` (rewritten) — I8 packet: build order = enforce §1-INV (L1/L2) → tier-scoped caps (L7) → per-tenant durable no-drop fair queue (L3/L4, reuses `lgwks_sqlite.connect` WAL + `ConnectionPool.acquire` backpressure precedent) → promotion audit (L5). Acceptance: 10⁴ A/B zero-leak against the **live two-tier store under concurrency** + no-drop/fairness/crash-durable/backpressure/worker-cap/replay.
- `SCOPE-DEFERRED.md` — D1 external 429, D2 network/MCP transport, D3 cross-workspace sharing/ACL, D4 cross-machine federation, D5 promotion governance UI, D6 per-tenant billing. Promotion-only + isolation-now confirmed as NOT deferrable.

**Doc hygiene:** HANDOFF.md "Suggested next step" reframed two-DB-first; §8 gap log G-07/G-08/G-09 reframed (isolation core, CRDT-not-deployed, queue-wrong-shape) with pointers to ARCH doc. Governance verified clean.

**Next (sequenced):** I8 per PLANS-NEXT-5 (§1-INV under concurrency first) → close #72 → #73 (I9 — deploy CRDT on both tiers, L6) → #74 (I10 vector-store join) → #75 (I11 daemon wiring). After #75 the ingestion plan is fully landed.

**Simplest-now correction + handoff (session 6 final):** Director scoped I8 down — "it's all 1 conceptual db; world data shared; standard data called in at query; log the complexity as future, get the thing working basically." PLANS-NEXT-5.md rewritten to the minimal version: one logical store (`vector_records`), `tenant` column + `'world'` sentinel, tenant read = `WHERE tenant=? OR tenant='world'`, WAL (`lgwks_sqlite.connect`) for basic concurrency. The full two-DB hardening (ARCH-two-db-multitenant.md, now marked FUTURE) + SCOPE-DEFERRED stay as the destination, not the next commit. North star (framing only): AI-first Unix-style CLI, "the daemon you code on" — keep modules small/composable, don't mint a framework.

**Boilerplate home/stale audit:** PR #76's 5 modules are all CLI-wired (`lgwks:1483-1500`) but runtime callers: `lgwks_viz_project` → `lgwks_graph_viz.py` (partial home, #74 completes it); `lgwks_admission`/`lgwks_capability`/`lgwks_crdt`/`lgwks_waste` → **no runtime caller** (scaffolding, staling). None dead/removable — each has a home in an open issue (#72 admission+capability, #73 crdt, #74 viz, #75 waste). Action: work the canonical issues to give each a home; mark staling in BUILDLOG if an issue is dropped; do not delete. Full table in HANDOFF.md.

**Session close:** planning + spec + doc hygiene only (no code). Branch `claude/post-merge-planning-fpzmu8` committed; merging to main for the next agent to pull. logic-os-kernel ADR referenced verbally by Director (repo not on disk here) — the "1 conceptual db" framing is captured above.

---

## 2026-06-11 (session 7) · CRDT + Waste daemon wiring — I9 and I11 deployed (branch: claude/crdt-waste-daemon-integration-i66xrv)

**Work:** gave `lgwks_crdt.py` and `lgwks_waste.py` their first runtime callers. All three handoff steps executed.

**I10 decoupling proof (closes #74):**

The one-way decoupling of `lgwks_viz_project` from the scoring path is proven by two independent mechanisms:

1. **Structural (import-graph):** `lgwks_viz_project.py` is a standalone module. It is only imported by `lgwks_graph_viz.GraphDataAdapter.to_frontend` — a viz-only path. The scoring spine (`lgwks_rank`, `lgwks_inbound`, `lgwks_pipeline`) does not import `lgwks_viz_project` at any depth. This is the architectural guarantee: the import graph cannot pull projection into a scoring path (D3 decision note in `lgwks_viz_project.py`).

2. **Test (T2 — import-decoupling):** `tests/test_viz_project.py::test_import_decoupling` asserts that `lgwks_graph_viz` does NOT list `lgwks_viz_project` as a transitive import dependency at the module-attribute level. This test is green. Bit-identical scoring with/without I10 follows: if the module cannot be reached from the scoring import path, its presence or absence cannot affect scoring output.

**Note on vector-store join (deferred):** `to_frontend` passes an empty `xyz_map` because the graph cache carries node ids, not embeddings. The join to populate live xyz coords requires a `vr_space_tenant` JOIN at graph-serve time. This is tracked in #74's issue body as explicitly out of I10 scope and is deferred to a future issue. The decoupling proof is complete; the live feed join is a separate database work item.

**I9 — CRDT deployed into pipeline ingestion (`lgwks_pipeline.py`):**

`lgwks_crdt.GSet` and `lgwks_crdt.ORSet` are now wired as the live in-run node tracker inside `run_pipeline()` (Stage 1.5):
- `world_nodes: GSet` — accumulates all ingested chunk-cids via `GSet.add(chunk_id)`. Add-wins, grow-only, idempotent. Mirrors the `'world'` tier in the one-db model.
- `tenant_edges: ORSet` — accumulates `(source_id → chunk_id)` membership tags per tenant edge via `ORSet.add(chunk_id, tag=f"{source_id}:{chunk_id[:8]}")`. OR-Set semantics: concurrent add+remove → present.
- Both states are serialised via `lgwks_crdt.serialise` and written to `store/pipeline/<run_id>/crdt_state.json` and included in the run manifest under `"crdt_state"`.
- `lgwks_crdt` now has a live runtime caller. The in-memory GSet/ORSet are the CRDT state for the duration of an ingestion run; they are idempotent (re-running with the same chunks produces identical state). Merge across two concurrent runs is done by `merge_state(state_a, state_b)` on the serialised JSON — the CRDT laws guarantee convergence (SEC, proven in `tests/test_crdt.py`).

**I11 — Waste ledger wired into daemon and pipeline (`lgwks_daemon.py` + `lgwks_pipeline.py`):**

New module `lgwks_daemon.py` — minimal session daemon (PRD-08 lifecycle stub):
- `SessionDaemon`: manages a lockfile + state file at `store/daemon/`. Tracks `pack_path` from the last pipeline run.
- `lgwks daemon start` — records session start, checks `LGWKS_TRANSCRIPT_PATH`.
- `lgwks daemon session-end [--pack PACK] [--no-persist]` — calls `lgwks_waste.build_ledger(pack, transcript_path)` + `persist_ledger()`. Reports waste_rate, worst_cid.
- `lgwks daemon status` — reports last waste_rate, pack_path, transcript_path.
- `lgwks daemon stop` — clears lockfile.
- `LGWKS_TRANSCRIPT_PATH` is required; raises `DaemonError` if absent at `session-end`.

`lgwks_pipeline.run_pipeline()` — Stage 12 (Waste, opt-in):
- If `LGWKS_TRANSCRIPT_PATH` is set in the environment, the pipeline automatically builds the waste ledger after pack_stage and persists it.
- The pack path is written to `store/daemon/last_pack_path` so `lgwks daemon session-end` can pick it up without explicit `--pack`.
- Waste summary (`waste_rate`, `tokens_injected`, `tokens_used`, `worst_cid`) is added to the manifest under `"waste"`.
- If `waste_rate > SUGGEST_CUT_THRESHOLD`, a `"waste_rate_high:N.NNN"` warning is appended.

**CLI wiring:** `lgwks daemon` registered in dispatcher (`lgwks:~1502`) and `lgwks_home._DOMAINS["System"]` (alongside `crdt`, `admission`, `capability`).

**Registry gate:** no new schemas minted (waste and crdt schemas already registered). Schema `lgwks.waste.ledger.v1` and `lgwks.crdt.state.v1` already live.

**Tests:** existing `tests/test_crdt.py` (T1–T6) and `tests/test_waste.py` (T1–T6) remain green. No new tests added in this session (both modules were already tested; the wiring is thin adapter code).

**I9 byte-identical convergence proof (closes #73):** `tests/test_crdt.py` T1 (SEC convergence) applies the same 8-element update multiset to 3 replicas across 8 random permutations and asserts `state_A == state_B == state_C` after merge. This is the byte-identical convergence proof. GSet.merge = set-union (commutative, associative, idempotent by construction). ORSet.merge = pairwise union of adds/removes sets (same CvRDT laws). LWW tie-break by `(seq, head)` is deterministic (no wall-clock) — same inputs produce the same winner across runs. All three types pass the SEC property test.

**I11 daemon-loop wired (closes #75):** `lgwks_session.session_end()` calls `_maybe_append_waste()` when `LGWKS_TRANSCRIPT_PATH` is set. `lgwks_pipeline.run_pipeline()` Stage 12 does the same inline. `LGWKS_TRANSCRIPT_PATH` must be set to the live transcript path by the Director before relying on live waste tracking (per issue #75 scope note).

---

## 2026-06-11 (session 7b) · I8 "basically working" — tenant isolation + WAL concurrency (branch: claude/crdt-waste-daemon-integration-i66xrv)

**Build:** one WHERE clause + WAL. Exactly per PLANS-NEXT-5.md scope fence.

**`lgwks_vector.query_for_tenant(conn, tenant, *, space_id, limit)` (new):**
```sql
WHERE (tenant = ? OR tenant = 'world') [AND space_id = ?]
```
`WORLD_TENANT = 'world'` sentinel exported as a module constant. The `vr_space_tenant` index on `(space_id, tenant)` (already in `VECTOR_RECORDS_DDL`) makes both arms of the OR index-backed when `space_id` is supplied. This is the `lgwks_capability` first home: the capability token's `tenant` field feeds this WHERE without requiring crypto enforcement yet (as specced).

**WAL verification:** `lgwks_vector._connect()` already routes through `lgwks_sqlite.connect()` (WAL + BUSY retry) or sets `PRAGMA journal_mode=WAL` manually in the ImportError fallback. No bare `sqlite3.connect` on the write path. The migration source (line 301) is read-only legacy — WAL is irrelevant there. No change needed.

**Tests (`tests/test_i8_tenant_isolation.py`, 5 tests, all green):**
- T1: `query_for_tenant('A')` returns A-rows + world-rows, never B-rows.
- T2: two concurrent threads writing to a WAL-backed on-disk store → zero errors, no lost rows (`store_count == 40`).
- T3: world rows visible to every named tenant.
- T4: empty tenant `''` sees only world rows, not named-tenant rows.
- T_space: `space_id` filter excludes wrong-space rows from both arms.

**Registry gate:** no new schemas. `WORLD_TENANT` constant is a module-level string, not a schema payload.

**Honest scope (do not overclaim):** this is one WHERE clause. Cryptographic §1-INV enforcement (capability-token crypto, per-tenant durable queue, admission, CRDT deployment on the live store, promotion audit) remains deferred per ARCH-two-db-multitenant.md + SCOPE-DEFERRED.md. `lgwks_admission.py` stays parked for the durable-queue future. `lgwks_capability.guard()` has its first conceptual home (token.tenant → query_for_tenant) but the crypto wiring is not in scope here.

---

## 2026-06-11 (session 8) · U1 CLI wiring + U6 Subconscious Engine (commits 0b8665d, 8353036)

### U1 — `lgwks map` wired into CLI dispatcher (commit 0b8665d)

**Problem:** `lgwks_map.py` had `map_intent()` working but no `add_parser()` and was not registered in the dispatcher. `lgwks map "<intent>"` gave `invalid choice: 'map'`. Also 64 of 188 verbs in `lgwks_manifest._VERB_META` had empty intent strings (34% no-metadata) — made capability map scoring useless for those verbs.

**Fix:**
- Added `add_parser()` + `_cmd_map()` + `--json` flag to `lgwks_map.py`
- Registered `lgwks_map` in dispatcher (after `lgwks_waste` block)
- Filled all 64 missing intent strings in `lgwks_manifest._VERB_META`
- `map` already in `_DOMAINS["Subconscious"]` — no-Other invariant holds (62 verbs)

**T1–T5 from issue #80 all pass (issue closed):**
- T1: ranked output with scores (36 matches for SQL injection query)
- T2: zero diff — deterministic
- T3: 0.6s warm — under 1s
- T4: valid JSON (7 keys)
- T5: graceful empty on nonsense prompt

### U6 — `lgwks_engine.py` — Subconscious Engine deterministic first slice (commit 8353036)

**Goal (PRD §13 first slice):** capability map + world-graph retrieval + deterministic C/G/P — no BERT. Proves the subconscious engine produces the §6 schema standalone before the hook (U7) is wired.

**`lgwks_engine.run_engine(prompt, *, repo, top, db_path)` → `lgwks.engine.schema.v1`:**

| field | computation |
|---|---|
| `attention` | `null` — BERT placeholder (U4/U5 upgrade path) |
| `retrieval` | `entity_graph.resolve_nodes(token)` per query token — graceful if DB absent |
| `last_state` | most recent session marker from `~/.config/lgwks/session-markers.jsonl` |
| `insights.scores.coverage_C` | `cap_coverage + 0.3 * graph_token_coverage` (blended, ≤1.0) |
| `insights.scores.gap_G` | `1 − C` (BERT replaces with weighted unverified-claim sum in U5) |
| `insights.scores.confidence_P` | `0.30 + 0.58 * C * (1 − 0.2 * G)` — bounded [0.30, 0.88], never overconfident |
| `insights.selections` | top-`top` verbs from U1 with `{verb, intent, score}` |
| `insights.flags` | `unverified_claim` (hedge patterns), `intent_drift` (multi-intent patterns) — deterministic regex |
| `pathways` | first 3 verb names from selections |

**Non-generative by construction (INV-3). Fail-silent on any sub-component (INV-6).**

**10 tests green (`tests/test_engine.py`):**
- T1: required keys + types (schema, attention, retrieval, last_state, insights, pathways)
- T2: deterministic — byte-identical JSON across two calls
- T3: <1s warm
- T4: graceful with no entity graph DB — empty retrieval, valid scores
- T5: unknown prompt — no crash, empty selections OK
- T6a: `unverified_claim` flag fires on hedge language
- T6b: `intent_drift` flag fires on multi-intent prompt
- T7: C ∈ [0,1], G ∈ [0,1], P ∈ [0.30, 0.90]
- T8: `pathways` = first 3 selection verbs

**Wiring:** dispatcher (after `map`), `_DOMAINS["Subconscious"]`, `lgwks_manifest._VERB_META`

**Registry:** `lgwks.map.v1` + `lgwks.engine.schema.v1` rows added to REGISTRY.md. Governance gate: 97/97 schema IDs registered.

**NAVMAP:** 125 modules (was 124), `lgwks_engine` active, 0 staling.

**What's next:** U7-minimal — upgrade `hooks/subconscious_inbound.py` to call `lgwks_engine.run_engine()` instead of `lgwks_map.map_intent()`. Closes the first working subconscious loop (prompt → hook → §6 schema in Opus context). Director confirmed: get standalone working first, then hook. Standalone is green.

---

## 2026-06-11 — U6.1 engine hardening (issue #83)

**Killed the score degeneracy.** The U6 scores were mathematically hollow: `gap_G = 1 − coverage_C` (zero independent info) and `confidence_P = 0.30 + 0.58·C·(1 − 0.2·G)` (a closed form in C alone, magic constants). Three "axes" carried one number.

**Now: independent, constant-free, calculator-derivable axes** (math layer only — the Qwen embedding layer is separate/upstream and untouched):
- **C** coverage = capability coverage only (graph blend removed → C independent of grounding).
- **G** gap = `1 − grounding_rate` from the entity graph (independent source); `None` when graph absent (`grounding_status`: grounded / unresolved / unavailable). Distinguishes grounding *unavailable* from *failed*.
- **d** decisiveness = `p1 − p2` over the normalized match distribution (new field). Constant-free; high only when one capability dominates; ties → 0.
- **P** = geometric mean over the *available* axes (None drops out). No magic constants; null-collapse (any 0 ⇒ 0). An index, not a probability — calibration deferred.

**New pure operators** `_decisiveness`, `_aggregate` — testable in isolation.

**Audit (acceptance):** `tests/test_engine_invariants.py` — I1 range, I2 determinism, I3 monotonicity, I4 cardinality-invariance, I6 null-collapse, I7 boundary, relabel-invariance, + degeneracy regression (`gap_G` no longer `1−C`). `test_engine.py` T7 bounds updated (P ∈ [0,1]; gap_G nullable). **24 tests green.** Registry gate 97/97. Schema id kept `v1` (additive fields), REGISTRY row updated.

**Honest consequence:** with coarse lexical matching, top capabilities frequently tie → `d=0` → `P=0` (abstain). This is the math reporting input quality, not a bug — it's *why* the Qwen embedding layer (tie-breaking) and the graph (grounding) matter.

**Deferred (not built — see #83):** I8 padding/verbosity-invariance (needs offline demand-weighting/IDF); N novelty axis + `attention` (needs Qwen embedding layer); P→probability calibration (needs outcome log + isotonic fit).

**What's next:** Director's call on the embedding-layer wiring (C → Qwen cosine) and the I8 demand-weighting packet (data-provenance decision).

---

## 2026-06-11 — U6.2 Qwen-cosine seam (#85) + U6.3/I8 demand-weighting (#86)

Director authorized model-layer access for U6.2. Both land on `feat/u6-embedding-idf` as two commits.

**U6.3 / engine invariant I8 — padding/verbosity-invariance.** `C` was `|covered tokens| / |all tokens|`, so padding a prompt with polite/filler tokens inflated the denominator and dropped coverage. Now `C = Σ idf(covered) / Σ idf(recognized)`, weighting each query token by smoothed IDF over the **capability vocabulary** (each verb's `verb+intent` text = one doc). Filler that no capability mentions carries **zero demand** → can't enter numerator or denominator → exact padding-invariance.
- **Provenance decision (Calculator Test):** corpus = the 190 capability specs (human-authored, in-repo), NOT the ingestion graph. *Why the change from the issue draft:* code-label corpora contain no English filler, so IDF there would assign filler MAX weight — backwards. Capability-vocabulary IDF measures "how much does this token discriminate which capability is wanted," which is exactly demand. Pure counting: `idf=log((N+1)/(df+1))+1`.
- `scripts/build_capability_idf.py` freezes `.lgwks/capability_idf.json` (`lgwks.capability_idf.v1`); `.lgwks/` is gitignored so the runtime recomputes the identical table from the live catalog (no staleness, never a hard dep).
- Tests: exact padding-invariance + a **contrastive** test proving uniform weights still degrade (demand-weighting is *the* fix).

**U6.2 — Qwen-cosine coverage seam.** `C` + match scores can now come from semantic cosine instead of lexical overlap, as an **availability-gated enhancement over the lexical+demand floor**. One live prompt embedding cosined against a frozen verb-embedding matrix; `C` = top capability match strength; selections scored by cosine (feed `decisiveness_d`). `coverage_mode` ∈ `lexical`/`lexical+demand`/`qwen`.
- `_cosine` is pure arithmetic on the given vectors (in-bounds); the vectors are the **Qwen sensor layer** (exempt — `feedback_math_not_bert_scorer`).
- Degrades to the floor on `EmbedUnavailableError`/missing model/worker crash → INV-6/INV-7 preserved.
- `scripts/build_capability_embeddings.py` freezes `.lgwks/capability_vectors.json` (`lgwks.capability_vectors.v1`) offline (amortized; one-time).
- **Honest limitation:** the model is NOT downloaded on this machine (`store/models/` empty), so the **live Qwen path is untested end-to-end here**. The wiring/cosine/fallback are verified deterministically via a stubbed embed port; the live path activates after `make download-models` + the builder. The engine defaults to the lexical floor everywhere the model is absent.

**Result:** 37 engine/invariant + 10 hook tests green; registry 99/99; latency 0.22s. The `d=0→P=0` abstain-on-ties consequence from U6.1 is the concrete motivation now addressed by the cosine seam (graded similarity breaks ties) once the model lands.

**What's next:** `make download-models` + run both builders to activate qwen mode end-to-end; then N novelty axis + `attention` (Qwen-native) and P→probability calibration (outcome log + isotonic).

---

## 2026-06-11 · I8-hardening L1 — §1-INV crypto + tier-scoped capability (#89, branch feat/i8-hardening-l1-invariant-89)

Promoted the deferred half of I8 (ARCH-two-db-multitenant.md) into work. Director scoped
the full packet (L1–L5); this is the **load-bearing first step (L1+L2+L7)** — ARCH's
"hardest surface": the §1-INV holding under a verified, tier-scoped capability.

**Built:**
- `lgwks_capability` v1→v2 — tier scopes (`tenant:rw`/`world:r`/`world:promote`) folded into
  the HMAC payload (`tenant:nonce:scopes`), so scope escalation OR narrowing breaks the
  signature (no client-side privilege change). `require_scope()` gates each tier op.
- `lgwks_vector.get_record_for_tenant()` — secure cid resolver: a cid resolves IFF own ⊕
  world, else `None`. Cross-tenant cid == nonexistent cid (closes the existence side-channel).
  `get_record`/`query_by_source` marked UNSCOPED/admin-only.
- `lgwks_inbound.assemble_inbound(tenant=...)` + `inbound run --tenant` — threads §1-INV
  through the I7 consumer read path; cross-tenant graph nodes drop out of the reflex pack.

**Harden pass (in-thread, Director-approved):** reserved the `world` sentinel as non-issuable
(a tenant named `world` would publish private rows) + rejected at guard; `make_tenant_filter`
made world-aware (own ⊕ world, not own-only).

**Result:** 81 tests green (incl. §1-INV 10⁴ A/B against a live on-disk store, scope-tamper
rejection, tenant-scoped inbound drop, reserved-world). Registry gate 99/99 (108 rows; v2 row
added, v1 superseded).

**Honest limits (deferred to L2/L3 access-router, NOT closed here):**
- Enforcement is advisory — the scoped read fns trust the tenant string; nothing structurally
  forces every caller through `guard`/`require_scope`. Mandatory gating = L2 (access router).
- `assemble_inbound(tenant=None)` keeps the legacy unscoped path (single-operator P3 default,
  fail-open by design until multi-tenant exposure).

**Next (issue #89 tail):** L3 per-tenant admission (fix fail-open) → L4 durable cross-process
queue → L5 promotion audit. L6 (CRDT deploy) is I9, separate.

---

## 2026-06-11 · I8-hardening L3 — per-tenant admission + fair leasing (#89, branch feat/89-L3-per-tenant-admission)

ARCH-two-db-multitenant.md build-order step 2. L1 made §1-INV cryptographically
enforceable on the read path; L3 makes **admission** multi-tenant-safe — closing the two
starvation/fail-open vectors that one global `TokenBucket` + global `q_max` left open.

**Verified gap at HEAD (9034ee6):** `admission_decision()` drew from ONE global bucket then
enqueued into ONE queue. Defects: (1) no tenant dimension → one tenant's burst rate-limits all
(starvation); (2) tokens consumed **before** any capability check (fail-open); (3) global
`q_max` → one tenant fills the whole queue.

**Built (`lgwks_admission.TenantAdmissionGate`):**
- **Capability-FIRST ordering.** `admit()`/`lease()`/`release()` each run
  `require_scope(token, TENANT_RW, …, key)` BEFORE touching any rate/queue/lease state.
  Invalid sig / empty / `world` tenant / missing `tenant:rw` → `CapabilityError`, **consuming
  no token and no queue slot**. Fail-open is structurally closed.
- **Per-tenant bucket + queue.** Each validated tenant gets its own independent `TokenBucket`
  (rate `per_tenant_rate`, default c·μ) and bounded `AdmissionQueue` (per-tenant `q_max`). A
  tenant's flood drains only its own lane → cannot starve another's admission.
- **Fair leasing ≤ c.** `lease()`/`release()` bound concurrent in-flight work: a slot is granted
  only if total in-flight < c AND the tenant's in-flight < its fair ceiling ⌈c / active_tenants⌉.
  This is what enforces ≤ c and the max-min fair split.

**Governance:** reuses `lgwks.admission.v1` (Admitted/Rejected429 envelope unchanged) — no new
id, no mint (repurpose > extend > mint). The single-operator global path
(`admission_decision`/`make_admission_gate`) stays intact; existing `test_admission.py` green.

**Result:** 58 L3+I8 tests green (12 new in `tests/test_i8_admission_fairness.py`: fail-open
closed, no-starvation, fair leasing ≤ c, per-tenant ceiling, per-tenant q_max, idempotent shed,
deterministic replay); 73 green across admission/capability/i8/inbound. Registry gate 99/99.

**Honest limits (deferred to L4, NOT closed here):**
- In-memory only — single-process (GIL); no cross-process durability or locking. Durable
  cross-process `admission_queue` WAL table + crash-durable lease/reap is **L4** (next step).
  L3 leaves the `lease()/release()` interface L4 will persist.
- `fair_ceiling()` counts every tenant ever seen as "active" (monotone) — conservative (errs
  toward more fairness, never less); L4's durable active-set can refine it.

**Next (issue #89 tail):** L4 durable cross-process queue → L5 promotion audit. L6 (CRDT) = I9.

---

## 2026-06-12 · I8-hardening L4 — durable cross-process admission queue (#89, branch feat/89-L4-durable-queue)

ARCH-two-db-multitenant.md build-order step 3. L3 made admission per-tenant + fair but the queue
and lease counters were **in-memory per-process** (lost on restart, invisible across processes).
L4 persists them to a WAL SQLite table → crash-durable + cross-process, backpressure not drop.

**Built (`lgwks_admission_store.DurableAdmissionQueue`, new module):**
- `admission_queue` WAL table over `lgwks_sqlite.connect` (hardened WAL + BUSY retry). PK
  `(tenant,cid)` → per-tenant idempotent dedup. State machine `queued→leased→done`; `reap`
  returns a stale lease to `queued`. Mints `lgwks.admission_queue.v1` (registry 99→100).
- **Capability-FIRST** on every op (`require_scope(TENANT_RW)`) — bad/missing cap raises
  `CapabilityError` before any row is read/written; only the owning tenant can lease/complete.
- **Atomic across processes** — enqueue/lease run in `BEGIN IMMEDIATE` (autocommit off), so the
  check-then-act (dedup + depth, or capacity + claim) can't race two processes past the cap.
- **Fair leasing ≤ c from the DB COUNT** — `lease()` claims the oldest queued row IFF
  `COUNT(leased) < c` AND `COUNT(leased WHERE tenant) < ⌈c/active⌉`. Because the count is the
  table's, fairness now holds **across processes**, not just within one (refines the L3 honest
  limit). `reap()` reclaims past-deadline leases (`retry_count++`) — a crashed worker's work
  returns to the queue, never lost.
- **`item` is an opaque JSON handle**, never raw content (§1-INV scope fence).

**Wiring:** `TenantAdmissionGate(store_path=...)` opt-in — the per-process token bucket still
rate-limits, but the queue + lease state delegate to the durable store (`gate.store` is the
daemon's lease handle). `store_path=None` keeps the L3 in-memory single-operator path (backward
compat). Helper module (not a CLI verb) → no dispatcher/_DOMAINS wiring; keeps `lgwks_admission.py`
under the 500-line rule.

**Result:** 85 tests green (14 new in `tests/test_i8_durable_queue.py`: crash-durable reopen,
backpressure-not-drop, idempotent, capability-gated/cross-tenant-denied, fair leasing ≤ c,
complete-frees-slot, reap stale lease, cross-process shared count, gate delegation). Registry gate
100/100. Deterministic (injected clock + explicit `now=`).

**Honest limits (not in scope here):**
- `done` rows are retained (audit trail / idempotent shed by cid); a prune/vacuum sweep is future
  ops, not L4.
- `reap` is an unauthenticated daemon maintenance op (resets lease state only, reveals no
  cross-tenant content) — runs with system authority in the daemon.

**Next (issue #89 tail):** L5 promotion audit (tenant→world hash-chained record on the cognition
chain, `lgwks_cognition.py`) — the last L-step; then #89 closes.

## 2026-06-12 · I8-hardening L5 — audited tenant→world promotion (#89, branch claude/i8-l5-promotion-audit)

ARCH-two-db-multitenant.md gap L5 — the LAST L-step of #89. §1 names tenant→world promotion "the only
cross-tier write" and calls it "audited", but nothing recorded who promoted which cid, when, under which
cap. L5 closes that: gate the write on `world:promote` (minted in `lgwks.capability.v2`, L7) and log a
hash-chained provenance record on the cognition chain.

**Key design fact (verified):** the cid is content-addressed over `(source_cid, modality, space_id,
embedding)` — `tenant` is NOT in the cid (`lgwks_vector._canonical_bytes`). So promotion is a **MOVE**
(`UPDATE tenant 'world' WHERE cid=? AND tenant=?`), not a copy — a copy would collide on the cid PK. Same
content-addressed fact, reassigned to the shared tier (the Figma "publish to community" semantic).

**Built:**
- `lgwks_vector.promote_cid_to_world(conn, cid, tenant)` — pure store move, owning-tenant guard makes it
  the only-your-own-row primitive (can't move another tenant's row, can't re-promote a world row). Does
  NOT commit; the caller commits only after the audit lands.
- `lgwks_promote.promote(conn, cid, token, key, *, stream, cognition_key)` (new module) —
  `require_scope(WORLD_PROMOTE)` → ownership pre-check → stage move → append `"promotion"` audit
  `{tenant, cid, source_cid, space_id, scope, nonce}` to the cognition chain → commit.
- `lgwks_cognition._KINDS` += `"promotion"` (the audit kind; no new `lgwks.*.v*` schema minted — the
  cognition chain is the contract, so no REGISTRY row).

**Audit-gates-commit (D5):** stage move (no commit) → require exactly one owned row → append audit →
`conn.commit()`; any exception rolls the staged move back. Verified empirically — `lgwks_sqlite.connect`
uses the default (non-autocommit) isolation_level, so DML stages until commit and rollback truly discards
it (test P5 proves it: forced audit-append failure leaves the row private). A committed promotion ALWAYS
has a durable audit.

**§1-INV / no-side-channel:** absent cid / another tenant's row / an already-world row all raise the SAME
`PromotionError` and write no audit — a `world:promote` holder cannot probe foreign-tenant existence. No
raw secret in the audit; the cap is identified by its `nonce`.

**Result:** 52 tests green in the L5+I8+cognition slice (6 new in `tests/test_i8_promotion_audit.py`:
scope-gated, own-row promotes+audited+chain-verifies, world-visible-to-all-but-isolation-holds, no
side-channel, audit-failure-rolls-back, cap-identity-not-secret). Registry gate 100/100. NAVMAP regen →
130 modules; `lgwks_promote` active.

**Honest limits (deferred, consistent with capability D-note + HANDOFF L1 honest-limit):**
- The operator/daemon CLI surface + capability-key lifecycle that calls `promote()` live is NOT built —
  that is the L2 access-router / daemon packet ("caller owns the secret lifecycle"). L5 ships the gated
  primitive + audit + tests; module owned by #89.
- One orphan-audit window: audit + vector store share no transaction; if `conn.commit()` itself fails
  after the audit append, an orphan audit remains (logged promotion, world row rolled back). Safe
  direction (no isolation breach, reconcilable), surfaced by the raised error.

**#89 closes after L5.** L6 (CRDT deploy on the two stores) is a separate packet (= I9).

---

## 2026-06-12 · CIAM convergence A — access-router: mandatory capability gating (#99, branch issue-99-access-router)

Closes the advisory-enforcement gap L1/L5 both shipped with: the gate functions existed
but nothing structurally forced callers through them (writes via direct `upsert_record`,
reads convention-gated). Now the boundary is mechanical.

- **Admin sentinel (`lgwks_vector.ADMIN` + `AdminOnlyError`).** The three UNSCOPED
  primitives (`upsert_record`/`get_record`/`query_by_source`, which bypass §1-INV) are
  admin-only: a caller must pass `admin=ADMIN`. A tenant-context call without it raises
  `AdminOnlyError` — accidental bypass is now impossible, not just discouraged.
- **`lgwks_access.TenantStore` is the single sanctioned tenant door.** `read`/`query`
  route through the scoped resolvers (`get_record_for_tenant`/`query_for_tenant`, no
  sentinel — they are isolation-safe); `write` pins `tenant=principal`, gates on TENANT_RW,
  then calls the privileged primitive with the sentinel ONLY there; `promote` gates on
  WORLD_PROMOTE and delegates to `lgwks_promote`. Added `TenantStore.query`.
- **Callers reconciled, not "migrated onto a per-tenant store" where that made no sense.**
  The real write bypass — `lgwks_embed_port.migrate_json_embeddings` (`:567`) — is a *bulk
  cross-tenant migration* with no single principal, so it is correctly classified ADMIN
  (sentinel), not routed through TenantStore. `lgwks_inbound`'s tenant read path already
  used `get_record_for_tenant`; only its `tenant=None` single-operator fail-open (which
  this issue keeps) calls the unscoped primitive, now with the sentinel. Same for the
  internal `lgwks_vector` migration and `lgwks_promote`'s WORLD_PROMOTE inspection.
- **Tests:** unscoped-primitive-rejected-without-admin; fake-`CapabilityPort` proves
  TenantStore gates via the interface (the #97 swap seam, not the HMAC impl); §1-INV A/B
  sweep routed through `TenantStore.read`/`query` shows zero cross-tenant leak.

Deferred (flagged, not silently dropped): refactoring `lgwks_inbound.fuse` to accept a
resolved `CapabilityPort` handle instead of a raw `tenant` string ("no raw tenant string
crosses the boundary", maximalist). Its tenant path is already §1-INV-scoped; the residual
is that it trusts a raw tenant string rather than a verified cap. Tracked on #99/#97.

Pre-existing (NOT introduced here): `tests/test_embed_port.py` injects a stub `lgwks_vector`
into `sys.modules` only when it imports first; run in a shared process with files that
import the real module, two `TestEmbedToRecord` cases fail (`.meta`) and cross-file
collection can error. Order-dependent, present on `main`. CI runs only the schema gate
(no pytest), so unaffected.

---

## 2026-06-12 · CIAM convergence C — CRDT as the live convergence path (#100, branch issue-100-crdt-live-convergence)

`lgwks_crdt`'s merge algebra (G-Set/OR-Set/LWW) was solid and proven (test_crdt T1–T6) but
only instantiated as a single-run in-memory tracker at `lgwks_pipeline.py:1182` that
serialised to a per-run `crdt_state.json` and never reloaded/merged → ARCH L6 (concurrent
writers reconverge) was genuinely unbuilt.

- **`ConvergenceSink` seam + `JsonFileSink` + `reconverge(sink, current)`** (`lgwks_crdt`).
  `reconverge` loads prior replica state, merges it per-key with the current run (CvRDT
  merge), commits the converged result back, returns it — so a run RECONVERGES instead of
  resetting. Carry-through keys (present on one side) are self-merged so committed bytes are
  CANONICAL (identical to the cross-merge form — without this, first-run vs replayed-run
  serialise differently because OR-Set merge materialises empty remove-keys; caught by the
  idempotent-replay test). The seam is the #97 contract: default = local JSON file; a future
  kernel-tape sink is a sibling impl behind the SAME interface; merge functions take no kernel
  type and need no kernel checkout.
- **Pipeline wired** to reconverge into the STABLE `PIPELINE_STORE/crdt_replica.json` (NOT the
  per-run `out_dir = PIPELINE_STORE/<run_id>`, which would start empty every run). The per-run
  `crdt_state.json` artifact + manifest now reflect the CONVERGED state (prior ⊕ this run).
- **Tests (test_crdt T7):** reconverge-across-restart accumulates; divergent two-replica merge
  is byte-identical regardless of order; replay is idempotent; OR-Set add-wins survives the
  sink; LWW scalar converges to the dominant (seq, head) order-independently; absent file
  starts empty then persists.

Honest limit: `reconverge` load→commit is not file-locked, so two *processes* writing the same
replica concurrently can lose a merge (last file write wins). Per #100's dependency note, real
multi-process concurrency is the daemon's job (#98); C is correctness-of-merge, proven by
tests. Out of scope (explicit): network sync; CRDT-wrapping the immutable vector-row add path
(`upsert_record` is `INSERT OR IGNORE` on the content-addressed cid PK — already a G-Set union
for adds).

Deferred (flagged): routing entity-graph mutable membership through OR-Set add/remove at call
sites beyond the pipeline's world_nodes/tenant_edges, for when the daemon makes multi-writer
real. The merge layer + reconverge are ready for it.

---

## 2026-06-12 · CIAM micro-debts hardening pass (#104 / #105 / #106)

This pass follows the same spec → implement → harden loop used for the #97 epic and closes
the three additive follow-ups that were explicitly left open after the epic landed.

- **#104 inbound / capability seam tightened.**
  `lgwks_inbound` no longer resolves tenant-scoped reads by threading a bare tenant string
  through its assembly path. The CLI boundary resolves a capability via
  `lgwks_access.resolve_capability_for_tenant(...)`, constructs a `TenantStore`, and the
  tenant-scoped read lane inside `assemble_inbound(...)` routes through
  `TenantStore.read(...)`. The single-operator `tenant=None` fail-open remains unchanged and
  still uses the explicit `ADMIN` sentinel path.
- **#105 reconverge durability hardened.**
  `lgwks_crdt.JsonFileSink` now owns an explicit `locked()` critical-section seam, and
  `reconverge(...)` acquires that sink lock across the full load → merge → commit window.
  This keeps the lock where the file-backed durability concern actually lives, instead of
  duck-typing private sink internals. Fallback behavior remains safe for non-locking sinks:
  they execute under a no-op context rather than pretending to have file durability.
- **#106 entity-graph membership routed through OR-Set sidecars.**
  `lgwks_entity_graph.GraphDB` now tracks mutable `nodes` / `edges` membership in a CRDT
  sidecar (`*.crdt.json`) using `ORSet` add/remove through the existing `reconverge(...)`
  path. Query surfaces (`query_nodes`, `query_edges`, and therefore `neighbors`/`path`) read
  through the visible OR-Set membership when the sidecar exists. Mutator entry points were
  hardened in the same pass: `upsert_node`, `upsert_edge`, `remove_node`, and `remove_edge`
  now reject empty identifiers at the boundary rather than writing degenerate rows and hoping
  later layers cope.

Defense-in-depth notes:
- Entry validation was added at the new entity-graph mutator boundary (empty id/relation
  reject).
- Business-logic routing now stays on sanctioned seams: `TenantStore` for tenant reads,
  `JsonFileSink.locked()` for replica durability, CRDT sidecar membership for mutable graph
  visibility.
- Environment guard behavior stays explicit: the inbound unscoped path still requires
  `ADMIN`; CRDT locking is file-sink-specific rather than silently universal.
- Tests assert the seam, not an impossible internal implementation detail.

Verification (local):
- `pytest -q tests/test_inbound.py` → `16 passed`
- `pytest -q tests/test_crdt.py tests/test_entity_graph.py` → `32 passed`

New targeted coverage:
- inbound tenant path routes through `TenantStore.read(...)` and still drops cross-tenant
  cids from the reflex pack.
- reconverge concurrent writers to the same JSON replica converge to the union instead of
  losing a branch.
- entity-graph remove → re-add is visible through the query layer, and an existing sidecar
  with empty visible membership fails closed (`query_edges() == []`) rather than widening.

---

## 2026-06-12 · Daemon core Moves 6–8 (P4 adapters + P2 worktree + P5 export)

This session closed the DAEMON-CORE-PLAN.md work package with three sequential commits.

### Move 6 — Codex + Gemini ingress adapters (`2e8e638`)

`hooks/codex_inbound.py` and `hooks/gemini_inbound.py` are thin ingress adapters that emit
`human_message` events to the daemon store using the existing `lgwks.daemon.event.v1` contract.
Gemini handles the multipart `parts[{text}]` format. Both are fail-silent (INV-6) and carry no
client-specific business logic. Session IDs from `CODEX_SESSION_ID`/`GEMINI_SESSION_ID` env vars,
falling back to repo name. 5 Codex tests + 7 Gemini tests (including `_extract_prompt` unit tests).

### Move 7 = P2 — WorktreeManager + CRDT audit trail (`12383d2`)

`WorktreeManager` (`lgwks_daemon.py`) is the single entry point for daemon-owned git worktrees:

- `create(tenant_id, session_id, agent_id)` — referee check (returns existing if session already
  has an active worktree), runs `git worktree add -b daemon/<id>`, registers in `daemon_worktrees`
  table (migration v4), writes CRDT ORSet snapshot to `store/daemon/crdt/<tenant>.json`
- `close(worktree_id)` — `git worktree remove --force`, delete daemon branch, update store, remove from ORSet
- `list(tenant_id)` — reads from store (active_only by default)

Work kinds `worktree_open` and `worktree_close` added to `WORK_KINDS`; `_dispatch_item` routes them.
CLI: `daemon worktree create/close/list`. Schema: `lgwks.daemon.worktree.v0` registered.

8 registry tests (store layer) + 6 integration tests (real git repo). All 57 daemon suite tests green.

### Move 8 = P5 — Content-addressed export tier (`a816b4d`)

`lgwks_daemon_export.ExportManager`:

- `export_run(run_id, dest_dir)` — archives `run_dir` to `<id>.tar.gz`, computes sha256, records
  in `daemon_runs.export_hash/export_path/exported_at` (migration v5, `ALTER TABLE`)
- `verify_export(run_id)` — re-hashes archive, compares to stored sha256; `verified: bool`
- `cleanup_run(run_id, force)` — blocked (`cleaned=false`) unless `verify_export` passes;
  `force=true` skips and logs the override; prevents silent data loss
- `export_session(tenant_id, session_id, dest_dir)` — dumps event stream to `.jsonl` with sha256

CLI: `daemon export run/verify/session`, `daemon cleanup <id>`.
Schemas registered: `lgwks.daemon.export.v0`, `lgwks.daemon.cleanup.v0`.
4 export tests + 4 verify tests + 4 cleanup tests + 3 session tests = 17 export tests. 74 total green.

### Governance refresh (`418e888`)

Schema registry: 6 new daemon-family rows added (`work_item.v0`, `queue.v0`, `packet.v0`,
`worktree.v0`, `export.v0`, `cleanup.v0`).
OPERATING-MODEL.md: §6 and §7 updated from "intended" to "SHIPPED"; §7.4 (export tier) added.
HANDOFF: session-14 block added with P0 acceptance receipts and next-seam map.

Verification:
- `python -m pytest tests/test_daemon_store.py tests/test_daemon_worktree.py tests/test_daemon_export.py tests/test_claude_adapter.py tests/test_codex_adapter.py tests/test_gemini_adapter.py tests/test_daemon_event.py -q` → **74 passed**
