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

## 2026-06-11 (session 6) · Post-merge planning — I8 P3→P0 hardening specced (branch: claude/post-merge-planning-fpzmu8)

**Build-state summary:** PR #76 merged the I8–I11 boilerplate to main (@ 6c2fdac). GH issues #72–#75 filed and open. No code change this session — planning + spec + doc hygiene only. Registry gate re-verified green (95 ids / 103 rows). The I-series (I1–I12) is the entire active backlog; there is no I13.

**Specced:** `spec/second-harness/PLANS-NEXT-5.md` — the I8 (#72) hardening contract, the gap between "boilerplate green" and the issue's `Done =` line. Three falsifiable gaps, split NOW-safe vs exposure-gated:
- **Gap A (NOW, load-bearing):** the capability boundary is **not wired into the live store reads** — `lgwks_vector.get_record` (:248) and `query_by_source` (:260) filter on cid/source_cid/space_id, never `tenant`, despite the `vr_space_tenant` index (:49) and `VectorRecord.tenant` (:75) existing. `lgwks_capability.guard()`/`make_tenant_filter()` exist but bind to nothing. Fix: add `*_for_tenant` reads, route the guarded path through them, keep `make_tenant_filter` as defense-in-depth. Isolation is a fiction until a read path cannot return another tenant's cid.
- **Gap B (exposure-gated):** sustained-load λ-sweep {0.5cμ, cμ, 2cμ} with zero 5xx (T1 today is a step-clock replay, not sustained arrival).
- **Gap C (exposure-gated):** the P3→P0 escalation is prose in `lgwks admission info`/`capability info`, not an enforced fail-closed checkpoint. Wire a `require_*` guard at the exposure entrypoint; entrypoint choice depends on which surface opens first (Director fork).

**Exposure fork (Director's):** I8 is P3 single-operator-local, P0 before exposure (second operator / network surface / client data in shared substrate / concurrent writers). NOW-safe half (Gap A + determinism + idempotent-shed) is worth building regardless; gated half lands before the first trigger event. Director selected I8 as the next issue to close; exposure-timeline confirmation pending.

**Doc hygiene:** HANDOFF.md refreshed — added session-6 current-state block + reframed "Suggested next step" around closing the open tail (I8 → #73 I9 → #74 I10 → #75 I11); flagged the dated sections as append-only history. Governance verified clean (governance/README.md ingestion-authority pointer + principles.md "capability check" layer both consistent with I8 — nothing stale).

**Next (sequenced):** I8 hardening per PLANS-NEXT-5 → close #72 → #73 (I9, nearest done) → #74 (I10 vector-store join) → #75 (I11 daemon wiring). After #75 the ingestion plan is fully landed.
