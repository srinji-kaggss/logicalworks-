# Ingestion Layer — implementation plan v1.1 (self-contained work packets)

Companion to [INGESTION-LAYER.md](INGESTION-LAYER.md) (architecture + proofs). Each packet below is
**self-contained**: it names its inputs (existing files/models), its output contract, the *one* formula
it implements (inline), a falsifiable acceptance test, and an explicit scope fence. An executor (AI or
human) picks up a packet and needs **only** the packet + the named files — not this conversation, not
the other packets. This is the anti-context-blur, anti-slop discipline.

## v1.1 changes (2026-06-10) — read before executing anything
1. **Packets renamed U1–U12 → I1–I12.** The U-namespace collided with the rebuild-track units in
   `PRD.md`/`BUILDLOG.md` (U1 capability map, U2 actor, U7 inbound hook — different work). `I` = ingestion.
   INGESTION-LAYER.md renamed to match. BUILDLOG history is append-only and keeps its U-ids.
2. **Self-containment now routes through the repo's entry layer** (created 2026-06-10): authority ladder
   in [/CLAUDE.md](../../CLAUDE.md) (this plan is rung 1 for the data layer), governance map in
   [/governance/README.md](../../governance/README.md), and the **schema registry** in
   [/docs/schemas/REGISTRY.md](../../docs/schemas/REGISTRY.md). Every packet that mints or bumps a
   contract MUST register it there (see per-packet `Register:` lines).
3. **Verified-state credit.** What already exists is marked per packet so executors do not rebuild it:
   crawler v1 landed (30 tests, `crawler/`); local text embedding live (`lgwks_ollama.py`
   qwen3-embedding:8b, 4096-d, centroid cache 0.09s); actor envelope protocol live
   (`lgwks_actor.py`, `lgwks.actor.v1`); subconscious inbound hook built (`hooks/subconscious_inbound.py`).
4. **Hook re-registration required (action item, not a packet):** the inbound hook is registered in
   `/Applications/Logical Works/.claude/settings.local.json` — the OLD space-named project dir. The live
   project is `/Applications/logicalworks` (renamed; its settings carry no hooks key). The global
   `verify-before-assert.sh` static floor was **deleted in the 2026-06-10 config revert** — the
   BUILDLOG U7 "convergence target" note is stale; the project-scoped hook is now the only inbound
   mechanism and must be re-registered against the no-space project before I7 acceptance can be observed live.
5. **I4 model-law reconciliation (explicit, was implicit):** the model-stack law (BUILDLOG-model-stack,
   2026-06-09) pins the *interim* split — text=local `qwen3-embedding:8b`, image/video=cloud
   `gemini-embedding-2` (intentional, not drift). I4's unified local Qwen3-VL space **supersedes that
   split when it lands and passes its eval**; until then the split stands. Do not "fix" the cloud media
   path as drift, and do not treat I4 as optional — it is the planned successor.

## Priorities (v1.1 re-prioritization)

| Tier | Packets | Why now |
|------|---------|---------|
| **P0 — start immediately** | **I1**, **I12** | I1 is the spine every packet reads; without it everything drifts (and G-11's lossy JSON-text embeddings keep accumulating). I12 is independent, currently **broken in prod** (Leiden silently degrades to Louvain on py3.14), and a contained quick win. |
| **P1 — fan out once I1 is tested-green** | **I4**, **I2**, **I3** | I4 has the largest existing credit (text path live) and unblocks I5/I6/I10; I2 and I3 are independent given I1. |
| **P2 — the scoring spine, strictly ordered** | **I5 → I6 → I7** | Deterministic scoring → centrality/δ → consumer pack. I7 additionally needs the hook re-registration (header item 4). |
| **P3 — attach where the DAG shows** | **I8**, **I9**, **I10**, **I11** | I8 (queue/isolation) becomes P0 **before any multi-tenant or network exposure** — it is P3 only while ingestion remains single-operator local. I10 is viz-only; never let it run ahead of the spine. I11 needs I7 output to measure. |

Dependency DAG (unchanged semantics, new ids):
```
I1 ──┬─ I2 ─┐
     ├─ I3 ─┤
     └─ I4 ─┴─ I5 ── I6 ── I7
              I8 (┄ I1)     I10 (┄ I4)
              I9 (┄ I1)     I11 (┄ I7)
I12 independent
```

Conventions every packet obeys: issue-backed · tested-green before the dependent starts · math proven by
its acceptance eval · no scope beyond the fence · `//why` on non-obvious choices · evidence before "done" ·
new/bumped contracts registered in [REGISTRY.md](../../docs/schemas/REGISTRY.md).

---

## I1 — vector-space + cid contract  ·  P0  ·  depends: none  ·  the spine everything reads

**Status:** ✅ **done** (2026-06-10). `lgwks_vector.py` — 20 green tests. Proof fixture: `~/ingestion_results/code_embeddings_v1.db` (4100 rows migrated, 659 deduped by cid). G-11 retired for new writes. `lgwks.vector.record.v1` registered in REGISTRY.md.
**Goal:** one content-address + vector-space contract that every other unit reads/writes.
**Inputs (exist):** `lgwks_substrate_db.py`, `lgwks_sqlite.py`, `store/substrate/`; today's lossy store
`~/ingestion_results/code_embeddings.db` (embedding = JSON TEXT — the thing to replace, gap G-11);
crawler `Chunk{cid,position,text,word_count,simhash}` ([crawler/src/chunk.rs](../../crawler/src/chunk.rs)).
**Output contract:**
```
record = { cid: blake2b(canonical_bytes),         # content address (dedup + audit anchor)
           modality: text|image|video,
           embedding: float32[d]  (BINARY blob, NOT json text),  d∈[64,4096]
           norm: f32,                              # stored ‖e‖ pre-normalization (audit)
           dim: u16, space_id: str,                # vector-space descriptor (manifest authority)
           tenant: str, source_cid: str }
```
**Formula it guarantees:** `êᵢ = eᵢ/‖eᵢ‖₂`, stored normalized, `‖êᵢ‖ = 1`.
**Acceptance (proof):** round-trip a vector → bit-identical out; `‖ê‖ = 1 ± 1e-6`; identical input bytes →
identical `cid`; manifest declares `space_id` and a cross-space compare raises (never silently compares).
**Register:** `lgwks.vector.record.v1` in REGISTRY.md (family: substrate) on landing.
**Scope fence:** storage + contract only. No embedding model, no scoring. Migrate `code_embeddings.db`
JSON→binary as the proof fixture.

---

## I2 — universal input handler  ·  P1  ·  depends: I1

**Status:** ✅ **done** (2026-06-10). `lgwks_input.py` — 71 green tests. Two-phase design (classify/extract). Video frame extraction via ffmpeg. Image OCR via tesseract (graceful fallback to visual_embed). `extraction_strategy` contract field. 50-fuzz no-crash on both phases. `lgwks.modality.item.v1` registered in REGISTRY.md.
**Goal:** accept ANY file type; route to modality; quarantine unknown; never crash.
**Inputs (exist):** `graphify/detect.py` (file-type detect precedent), `lgwks_extract.py:156` (pdf via fitz),
`lgwks_multimodal.py` (image seam), `store/untrusted/` (quarantine dir).
**Output:** `handle(bytes,origin) → [ModalityItem{modality, parsed_unit|raw_ref, mime}]` per
INGESTION-LAYER §2.
**Routing table:** text/code→AST/DOM·chunk; pdf/docx/rtf→text-extract·chunk; image→image item;
video→video item (keyframe-sample flag); audio→transcribe lane (deferred, G-10); unknown→`store/untrusted` + human.
**Acceptance:** a fixture of every listed type routes correctly; an unknown/corrupt byte-blob lands in
`untrusted` and the handler returns Ok (no panic, no exception escapes).
**Register:** `lgwks.modality.item.v1` in REGISTRY.md (family: substrate).
**Scope fence:** detection + routing only. No fetching (I3), no embedding (I4).

---

## I3 — crawler v2 (3 modality streams) + LFM2-Extract  ·  P1  ·  depends: I1

**Status:** partial credit — crawler v1 (`lgwks.crawl.v1`) landed with 30 green tests; this packet is the
v1→v2 bump only.
**Goal:** bump `lgwks.crawl.v1 → v2`: three fetched, cid'd, modality-typed streams; LFM2-Extract fills the
strict schema into structured artifacts.
**Inputs (exist):** crawler crate [crawler/src/](../../crawler/src) (gather/engine/extract/chunk/schema),
today's `Assets{images: Vec<String>}` (URLs only — extend to fetched bytes); model
`LiquidAI/LFM2-1.2B-Extract-GGUF` (+ `LFM2.5-VL-1.6B-Extract-GGUF`), runtime llama.cpp.
**Output contract (`lgwks.crawl.v2`):** `Page.media: Vec<MediaItem{cid, modality, url, bytes_ref, mime}>`
replacing text-only chunking; `Page.artifacts: StrictSchemaInstance` (LFM2-Extract fill).
**Acceptance:** crawl a fixture page → 3 typed streams emitted; image/video bytes fetched + cid'd (not URL);
frontier audit log complete (every URL terminal status); LFM2-Extract output **validates against the strict
schema** (JSON-Schema pass) — a non-conformant fill is rejected, not stored.
**Register:** `lgwks.crawl.v2` in REGISTRY.md (family: crawl), marking `lgwks.crawl.v0` (python) deprecated
and `v1` superseded-on-landing.
**Scope fence:** capture + typed emission + schema-fill only. No embedding (I4), no scoring (I5).
LFM2-Extract fills; it does not score (scoring is I5, deterministic).

---

## I4 — embedder runtime (Qwen3-VL-Embedding-8B)  ·  P1  ·  depends: I1

**Status:** ✅ done (2026-06-10). `lgwks_embed_port.py` — 59 green tests. Two tiers (mlx primary → transformers fallback), same model, same space_id. No Ollama, no HuggingFace at runtime (Zscaler-safe; weights in `store/models/`, fetched from GitHub Release). Native video: I4 extracts N frames, passes to VL processor → one 4096-d vector. `embed_from_item()` dispatches text/image/video by modality+strategy. `migrate_json_embeddings()` closes G-11. `load_all_graphs()` populates system_graph.

**Goal:** one embedding port, two runtimes (mlx/transformers), one shared 4096-d space — text + image + video.
**Inputs (exist/pinned):** `Qwen/Qwen3-VL-Embedding-8B`; runtime MLX `jedisct1/Qwen3-VL-Embedding-8B-mlx`.
**Output:** `embed_from_item(item, instruction) → float32[k]` (k = chosen MRL dim) → I1 record via `embed_to_record()`.
**Formula:** L2-normalize output; cosine `sim = êᵢᵀêⱼ ∈ [−1,1]` (INGESTION-LAYER §4.1). Last-token pooling.
**Acceptance (pre-registered eval — still pending live model):** cosine bounds hold; recall@10 vs k∈{128,256,512,1024,2048,4096} curve plotted on a frozen eval; adopt smallest k within 1% of full-dim recall, else 4096; reject if monotonicity fails. Text + image of the same concept land close in the shared space (cross-modal sanity). Old gemini-embedding-2 space never silently compared against new space_id (I1 cross-space guard).
**Register:** `lgwks.embed.port.v1` + `space_id` scheme in REGISTRY.md (family: substrate). ✅ done.
**Scope fence:** embedding behind a port only. Model swappable (MLX↔transformers) without changing callers. Retrieval (function-calling tongue) is a separate layer above this port.

---

## I5 — schema scoring: ²/³ + R_k + MDL  ·  P2  ·  depends: I4

**Status:** not started.
**Goal:** the deterministic, non-AI score — cubic schema score + MDL conformance + cid.
**Inputs:** I4 embeddings; strict schema `S`; INGESTION-LAYER §4.2/§4.4/§4.5.
**Formulas (implement exactly):**
```
R_k = P_k · diag(d_k)                         # schema-derived, no learning (§4.5)
score(i,k,j) = êᵢᵀ R_k êⱼ                     # cubic / order-3 (RESCAL)
score_mdl(I) = 1 − |compress(c(I)|S)| / |compress(c(I))|     # canonical CBOR + zstd S-dictionary
cid(I) = blake2b(c(I))
```
**Acceptance (proof):** `(1/m)Σ_k score(i,k,j)|_{R_k=I}` reproduces the cosine matrix ≤1e-6 (the §4.2
marginal proof, executed); directed relation ⇒ `score(i,k,j)≠score(j,k,i)`; **same fact via 2 different
extract models ⇒ identical cid**; `score_mdl` separates conformant vs corrupted fixtures by a
pre-registered margin.
**Register:** `lgwks.score.record.v1` in REGISTRY.md (family: scoring).
**Scope fence:** scoring math only. The AI's self-score is *recorded* (I6 uses it), never used here.

---

## I6 — cubic node centrality + AI-discrepancy δ  ·  P2  ·  depends: I5

**Status:** not started; both eval graphs exist on disk.
**Goal:** the deterministic node value (cubic centrality) and the slop signal δ.
**Formulas:**
```
node = argmax_{‖x‖=1} Σ_k wₖ (xᵀ Tₖ x)        # tensor Z-eigen (Lim/Qi); power iter x←normalize(Σ wₖ Tₖ x)
δᵢ = | rank_det(i) − rank_ai(i) |             # AI score kept as signal; large δ ⇒ human lane
```
**Acceptance:** power iteration converges (‖Δx‖<1e-9) on the two existing graphs
(`~/ingestion_results/{logicalworks-,logic-os-kernel}_graph/graph.json`); seed-stable (same inputs →
identical ranking); δ distribution computed, threshold pre-registered; high-δ nodes routed to human lane.
**Register:** `lgwks.rank.record.v1` in REGISTRY.md (family: scoring).
**Scope fence:** ranking + δ only. No injection/packing (I7).

---

## I7 — consumer tail (L5 pack)  ·  P2  ·  depends: I6

**Status:** seam exists — `hooks/subconscious_inbound.py` is built, standalone-proven, fail-silent; but it
is registered against the dead space-named project dir (header item 4). Re-register before acceptance.
**Goal:** the token-optimized, prose-free pack the AI consumer reads.
**Inputs:** I6 ranks; [PRD-04](prd/PRD-04-context-economy.md) reflex cap + `lgwks.inbound.v1`;
`lgwks_context.py`, `hooks/subconscious_inbound.py`.
**Output (`lgwks.inbound.v1` extension):** `{ handles:[cid], scores, minimal_typed_fields }` — RRF-ordered
(graph cubic rank ⊕ vector cosine rank), deterministic truncation order.
**Acceptance (§7-INV):** L5 pack contains **no free-text field**; token count ≤ PRD-04 reflex cap; every
handle resolves to a `cid` present in the store (zero dangling/hallucinated reference); truncation drops
lowest-RRF first (load-bearing survives the cut).
**Register:** `lgwks.inbound.v1` extension fields in REGISTRY.md (family: harness).
**Scope fence:** assembly + budgeting only. Generation/decisions stay with the consumer (PRD-04 INV-3).

---

## I8 — concurrency, queue, isolation  ·  P3 (P0 before any multi-tenant/network exposure)  ·  depends: I1 (┄)

**Status:** not started; worker-cap formula exists.
**Goal:** no 5xx under load; hard tenant isolation.
**Inputs (exist):** [lgwks_workercap.py](../../lgwks_workercap.py) (worker-cap formula), crawler politeness
(jittered backoff), `store/projects/` + `store/substrate-global/`.
**Formulas:** `c = min(⌊(RAM−Σreserve)/per_worker⌋,⌊(CPU−cpu_reserve)/cpu_per_worker⌋,|roles|)`;
stability `ρ=λ/(cμ)<1`; token-bucket admission (rate cμ, burst B); `Q≥Q_max ⇒ 429 + Retry-After`.
**Acceptance:** load test at λ ∈ {0.5cμ, cμ, 2cμ} → stable<1, bounded at 1, and at 2× **every** rejection is
a typed 429 (zero 5xx); duplicate submission (same cid) ⇒ one row (idempotent shed); **§1-INV**: 10⁴
randomized A/B queries leak zero cross-tenant cids; a query without a valid capability token is rejected.
**Scope fence:** queue/admission/isolation only. No new compute.

---

## I9 — CRDT state  ·  P3  ·  depends: I1 (┄)

**Status:** not started.
**Goal:** concurrent writers converge without conflict.
**Inputs:** I1 cid; [lgwks_cognition.py](../../lgwks_cognition.py) (hash-chain = logical clock).
**Design:** world-nodes = **G-Set keyed by cid** (idempotent ⇒ CvRDT for free); tenant edges = **OR-Set**
(add/remove + unique tags) or **LWW** tie-broken by cognition-chain head.
**Acceptance (SEC proof, executed):** apply the same update multiset in N permutations across M replicas →
all replicas converge to **byte-identical** state; adding the same cid-fact twice is a no-op.
**Scope fence:** state-merge semantics only. No transport/networking.

---

## I10 — deterministic 3-D viz projection (DECOUPLED from semantic space)  ·  P3  ·  depends: I4 (┄)

**Status:** not started. Never let this run ahead of the spine — it is viz-only.
**Goal:** a replayable X/Y/Z coordinate per node for the visualization engine. This is a **viz-only**
artifact, fully decoupled from the N-dim semantic space and the order-3 scoring (INGESTION-LAYER §7.5):
derived one-way from the embedding, it **never feeds back** into scoring/retrieval.
**Inputs:** I4 embeddings; `lgwks_graph_viz.py` (D3 renderer to feed).
**Formula:** `y_i = Wᵀêᵢ ∈ ℝ³`, `W` = top-3 PCA axes (SVD), sign fixed by largest-magnitude-positive rule.
**Acceptance:** same Ê → byte-identical `W` + coords; **scoring output is bit-identical with I10 present or
absent** (proves one-way decoupling); reconstruction stress reported; optional seeded UMAP only if PCA
stress > pre-registered threshold.
**Scope fence:** projection output only. Not the renderer, not the scoring. The math must never be
distorted for the picture; the picture is never the semantic truth.

---

## I11 — waste ledger (the proof context-optimization works)  ·  P3  ·  depends: I7

**Status:** not started.
**Goal:** measure that the score actually reduces tokens (else the whole optimization is asserted, G-13).
**Inputs:** PRD-04 §04-c; the transcript the daemon tails; I7 packs; `lgwks_cognition.py` store.
**Output:** per-session ledger: per injected item → `{tokens, used_within_N_turns: bool}` (cited/acted-on,
derived from transcript). Cockpit shows **waste-rate**.
**Acceptance:** ledger sums reconcile against the transcript; waste-rate computed; a high-waste injection is
attributable to a specific low-yield item; threshold to raise the selection cut is pre-registered.
**Register:** `lgwks.waste.ledger.v1` in REGISTRY.md (family: harness).
**Scope fence:** measurement only. Does not change the router (it informs the next tuning).

---

## I12 — graphify clustering fix  ·  P0 (independent quick win)  ·  depends: none

**Status:** broken in prod today — Leiden silently degrades to Louvain on py3.14 (gap G-12).
**Goal:** stop Leiden→Louvain degradation; add embedding-weighted edges.
**Inputs:** `graphify/cluster.py` (Leiden via graspologic pinned `<3.13`); I4 embeddings (edge-weighting
half waits on I4 — split the packet: fix the interpreter pin NOW, add semantic weights after I4).
**Fix:** pin a py<3.13 interpreter for the cluster step OR vendor a Leiden impl; weight/augment edges by
embedder cosine (semantic+structural hybrid) → tuned-resolution Leiden.
**Acceptance:** Leiden actually runs (not Louvain fallback); on the two existing corpora, community count +
modularity vs the current Louvain baseline reported; fewer, more coherent communities (pre-registered metric).
**Scope fence:** clustering only.

---

## Sequencing note (reduce blur)

Build **I1 first** — it is the contract every other packet reads; without it the others have no stable
target and will drift (context blur). I12's interpreter-pin half can run in parallel (independent, broken
now). Then I2/I3/I4 fan out (independent given I1). I5→I6→I7 is the scoring spine. I8/I9 (infra) and
I10/I11 (viz/proof) attach where the DAG shows. Do not start a packet whose dependency is not
tested-green — that is the blur/slop the sequencing exists to prevent.
