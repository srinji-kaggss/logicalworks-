# Ingestion Layer — architecture, proven math, gaps, plan

Status: v1.0 — math + model architecture finalized · author: Logical Claude · branch `logical-claude-2nd-harness`
Governs: the data-ingestion layer (crawler → ingestor → world-model) that feeds the
eventual data-visualization engine. **This is not "a graph" — the graph and the vector
matrix are two *outputs* of one ingestion.** Builds on [machine-nervous-system.md](../../docs/machine-nervous-system.md)
runtime lanes, [PRD-04](prd/PRD-04-context-economy.md), [lgwks_workercap.py](../../lgwks_workercap.py),
[lgwks_cognition.py](../../lgwks_cognition.py), the crawler `lgwks.crawl.v1` ([CRAWLER-spec.md](CRAWLER-spec.md)).

Rule this doc obeys: **rely on what exists → map the best → report.** Every §math block
states the formula, a one-line proof, and an independent verification (falsifiable, pre-registered).

---

## §0 Principle — where AI is allowed, and where it is forbidden

Three lanes. The semantic-ingestion path contains **no LLM**:

| Lane | Mechanism | AI? |
|---|---|---|
| **Structure** | deterministic parse (AST/tree-sitter/DOM/mime) + LFM2-Extract *form-fill only* | extract model fills a schema; it never scores the node |
| **Semantics** | Qwen3-VL-Embedding-8B → vector; cosine/structure math | embedding is math; the *similarity and node value are not AI* |
| **Human** | resolves genuine ambiguity / value calls | the only non-deterministic adjudicator — never a model standing in |

The AI **may and should emit its own score** — it is recorded as a *signal*, compared against
the deterministic node value as a slop-detector (§4.3). It is never authoritative.

---

## §1 Two-tier store (machine-facts vs tenant) — the GitHub replacement

```
WORLD-NODES DB        global, append-only, content-addressed facts (the world-model / OS-layer knowledge)
   ▲ promote (explicit, audited)
TENANT / PROJECT FOLDERS   per-tenant isolated stores = "repos": own graph + vectors + audit chain
```

Existing anchors: `store/substrate-global/` (world tier), `store/projects/` (tenant tier),
`store/untrusted/` (quarantine), `store/cognition/` (audit chain). We formalize, not invent.

**GitHub-replacement mapping:** project folder = repo · cognition hash-chain = commit history ·
canonical schema artifacts = tracked objects · signed audit-state DB = the immutable log ·
CRDT merge (§5) = branchless concurrent collaboration · world-nodes = the shared "package index".

**§1-INV Tenant isolation (T0).** A read in tenant A can never observe tenant B's rows.
Enforced by a **capability token** carried with the query, verified cryptographically — *not*
`if tenant == ...`. Cross-tenant flow happens only by promotion to world-nodes.
*Verify:* property test — generated A/B workloads; assert zero B-cid appears in any A result set
across 10⁴ randomized queries; assert every cross-read without a valid cap is rejected.

---

## §2 Universal input handler — accept any file type

`handle(bytes, origin) → ModalityItem`:

```
detect(bytes)            mime/magic + extension                    (graphify detect.py precedent; fitz at lgwks_extract.py:156)
  ├ text/code     → AST/DOM parse → text chunks
  ├ pdf/docx/rtf  → text-extract → text chunks
  ├ image         → image item (vision encoder)
  ├ video         → video item (keyframe-sample → vision encoder)         [§3 bypass]
  ├ audio         → transcribe lane (deferred — flagged §7)
  └ unknown       → store/untrusted quarantine + human lane              (never crash)
```

Invariant: no input crashes the handler; an unhandled type is *quarantined and surfaced*, not dropped.

---

## §3 The crawler (v2) and the direct-to-embed bypass

Crawler is *one* source adapter; a local file-walker emits the **same contract**. Schema bump
`lgwks.crawl.v1 → v2`: three modality-typed, content-addressed, *fetched* streams
(text chunks / image items / video items) replacing today's text-only `chunks` + image-URL `assets`.
LFM2-Extract (GGUF, per-page, tiny) fills the strict schema → the "complex artifacts".

**Bypass gate** `route(input)`:
```
if modality == video            → skip extract (no text structure) → keyframe-sample → embed
elif schema_valid(input, S)     → skip crawler + LFM2-Extract        → embed directly      (human OR AI fast-path)
else                            → crawler → extract → embed
```
`schema_valid` = deterministic JSON-Schema validation against the declared strict schema `S`.
*Verify:* a schema-valid POST and a video both reach the embedder with zero extract invocations
(assert call-count == 0 on the extract model in those paths).

---

## §3.5 Pinned model architecture (the only two open gates)

| Role | Model (pinned) | Facts | Runtime (pinned, verified 200) |
|---|---|---|---|
| **Semantic embedder** | `Qwen/Qwen3-VL-Embedding-8B` | 4096-d (MRL 64–4096), 36 layers, 32K seq, instruction-aware, multimodal (text + image + video-frames) → one shared 4096-d space | MLX `jedisct1/Qwen3-VL-Embedding-8B-mlx` (Apple-silicon) **or** llama.cpp `ganeshrao/Qwen3-VL-Embedding-8B-Q8_0-GGUF` (portable) |
| **Crawler extractor** | `LiquidAI/LFM2-1.2B-Extract` (+ `LFM2.5-VL-1.6B-Extract` for image+text) | hybrid Liquid: **10 double-gated short-range LIV-conv blocks + 6 GQA attention blocks** → linear-time, constant-memory/token, CPU/edge, streaming-native (vs transformer O(n²) attention + growing KV-cache). Fills a schema; never scores the node. | llama.cpp `LiquidAI/LFM2-1.2B-Extract-GGUF` / `LFM2.5-VL-1.6B-Extract-GGUF` |

Deferred (gate closed): NeoBERT (future engine). All other model gates closed. Why LFM2's
architecture suits the crawler: a crawler is a *stream*; conv/recurrent processes streaming input at
constant memory and high CPU throughput, where a transformer LLM is the wrong shape (batchy, KV-heavy).

---

## §4 The scoring math — AI is order 2, schema is order 3

The central claim: **the AI lane is a second-order (quadratic) object; the schema lane is a
third-order (cubic) object; the AI's quadratic similarity is exactly the relation-collapsed
marginal of the schema's cube.** Therefore the AI cannot compute the deterministic node — it
structurally lives one order below.

**Terminology — three different "N"s, do not conflate:** the embedding space is **N-dimensional**
(`d = 4096`). "Order-2 / order-3" refers to the tensor **order** = number of modes/indices (a matrix
`S[i,j]` is order-2; the relational tensor `T[i,k,j]` is order-3) — *not* a dimension count. The
**literal 3-D (X,Y,Z) coordinate is a separate viz-only artifact** (§7.5), derived one-way from the
N-dim embedding for human UX; it is decoupled from this math and never enters scoring.

### §4.1 AI lane — order 2 (quadratic)
Embedding `eᵢ ∈ ℝ^d`, `d = 4096` (Qwen3-VL-Embedding-8B). L2-normalize: `êᵢ = eᵢ/‖eᵢ‖₂`, `‖êᵢ‖ = 1`.
```
sim(i,j) = ⟨êᵢ, êⱼ⟩ = êᵢᵀ êⱼ = cos θᵢⱼ ∈ [−1, 1]        (a quadratic form; degree 2)
S = Ê Êᵀ                                                  (Gram matrix: symmetric, PSD, rank ≤ d)
```
**Proof of order:** `sim` is bilinear in `(êᵢ, êⱼ)` ⇒ degree 2. ∎
MRL truncation to `k ∈ [64,4096]`: `êᵢ^(k) = eᵢ[1:k] / ‖eᵢ[1:k]‖`. Validity is *claimed* by the
Matryoshka objective (Kusupati 2022), **not assumed** —
*Verify (pre-registered):* plot recall@10 vs `k ∈ {128,256,512,1024,2048,4096}` on a frozen eval;
adopt the smallest `k` within 1% of full-dim recall, else use 4096. Reject if monotonicity fails.

### §4.2 Schema lane — order 3 (cubic / trilinear)
Strict schema `S` defines relation types `R = {r₁…r_m}`. Extraction yields typed triples
`(i, r_k, j)`. Relational tensor `T ∈ ℝ^{n×m×n}`, `T[i,k,j] =` conformance weight ∈ [0,1] (§4.4),
0 if absent/invalid. The schema assigns each `r_k` a **deterministic** operator `R_k ∈ ℝ^{d×d}`
(derived from the schema typing — directional/projection structure — **not learned by AI**).
```
score(i,k,j) = êᵢᵀ R_k êⱼ          (RESCAL form: bilinear in embeddings × the relation operator → trilinear; degree 3)
```
**Proof that AI(²) ⊂ schema(³):** marginalize the cube over the relation mode with `R_k = I`:
```
(1/m) Σ_k score(i,k,j) = êᵢᵀ ( (1/m) Σ_k R_k ) êⱼ = êᵢᵀ êⱼ = sim(i,j)   when (1/m)ΣR_k = I
```
So **cosine similarity is the order-2 relation-collapsed marginal of the order-3 schema score**;
the AI sees the cube projected down one mode and cannot recover `R_k`. ∎ (Grounding: RESCAL,
Nickel 2011 — KG scoring is exactly `eᵢᵀ R_k eⱼ`; cosine is its `R_k=I`, relation-agnostic case.)
*Verify:* assert numerically that summing the per-relation scores with `R_k=I` reproduces the cosine
matrix to ≤1e-6; assert a relation-typed query (`R_k≠I`) returns rankings a pure-cosine query cannot.

### §4.3 The deterministic node value — cubic centrality + the AI-discrepancy signal
Node standing = stationary point of the **cubic form** over the symmetric 3-tensor (Lim/Qi
Z-eigenpair):
```
f(x) = Σ_{i,k,j} T[i,k,j] · xᵢ wₖ xⱼ = Σ_k wₖ (xᵀ Tₖ x)      (degree 3 in x; wₖ = schema relation weight)
node = argmax_{‖x‖=1} f(x)     via power iteration   x ← normalize( Σ_k wₖ Tₖ x )   (deterministic, seeded)
```
The order-2 analog (eigenvector of `S`, i.e. PageRank/spectral) is the relation-collapsed special
case → again AI=² ⊂ schema=³. The **AI's emitted score** `s_ai(i)` is kept and compared:
```
δᵢ = | rank_det(i) − rank_ai(i) |       large δᵢ ⇒ slop signal ⇒ route node to the human lane
```
*Verify:* power iteration converges (‖Δx‖ < 1e-9) on the two existing graphs; seed-stability
(same inputs → identical ranking); δ distribution is computed and a threshold pre-registered.

### §4.4 Schema-compression score + content hash (MDL)
Canonicalize instance `I → c(I)`: sort keys, normalize types/units, move AI score to a side-channel.
Quality = how well `c(I)` compresses **against the schema grammar `S`** (Minimum Description Length):
```
bits(I | S) = −log₂ P_S(c(I))                          (description length under the schema's structural prior)
score_mdl(I) = 1 − |compress(c(I) | S)| / |compress(c(I))|   ∈ [0,1]      (1 = perfectly conformant; 0 = slop)
cid(I) = BLAKE2b( c(I) )                                (content address = dedup key = audit anchor)
```
**Proof of the cross-model property:** two extractions with identical canonical form `c(I)` ⇒
identical `cid` and identical `score_mdl`, *regardless of which AI produced them* — agreement and
dedup fall out of the math, not trust. ∎ (MDL: Rissanen 1978. Compressor: canonical CBOR + a fixed
`S`-trained dictionary, e.g. zstd `--train`, so the dictionary is deterministic and replayable.)
*Verify:* feed the same fact through 2 different extract models → assert equal `cid`; feed conformant
vs corrupted instances → assert `score_mdl` separates them with a pre-registered margin.

### §4.5 The relation operators `R_k` — finalized, schema-derived (no learning)
Each relation type `r_k ∈ R` gets a deterministic operator built from its declared typing — **no AI,
no training**:
```
R_k = P_k · diag(d_k)        where
  P_k       fixed permutation/projection encoding the relation's DIRECTION + argument typing
            (asymmetric edge a→b ⇒ P_k makes R_k ≠ R_kᵀ ; symmetric relation ⇒ P_k = I ⇒ R_k symmetric)
  diag(d_k) diagonal mask over the embedding dims the schema declares relevant to r_k (MRL slice per
            relation; d_k ∈ {0,1}^d) ; default d_k = 1 (all dims)
```
`R_k` is a pure function of the schema file ⇒ replayable. With every relation at default
(`P_k=I, d_k=1`), `(1/m)Σ_k R_k = I`, preserving the §4.2 marginal proof exactly.
*Verify:* same schema → byte-identical operators; directed relation ⇒ `score(i,k,j) ≠ score(j,k,i)`;
marginal identity to ≤1e-6.

**I5.1 refinement (implemented, issue #69) — direction via an antisymmetric term, not `P_k`.**
A pure signed-permutation `P_k` (with `d_k=1`) provably *cannot* be both asymmetric and
marginal-preserving: it is orthogonal, so each `P_k` adds at most `+1` to any diagonal entry,
and `Σ_k P_k = m·I` then forces every `P_k = I` (and an orthogonal involution is symmetric).
So directionality is supplied by an **additive antisymmetric operator**: `R_k = P_k·diag(d_k) + N_k`,
`N_kᵀ = −N_k`. The `m` directed relations are paired so `Σ_k N_k = 0`, giving
`(1/m)Σ_k R_k = I` **exact** (proof intact) while `R_k ≠ R_kᵀ` for each directed relation. This is
*structural* direction (deterministic/replayable, breaks the cosine collapse); semantic
argument-typing remains future work (all `arg_typing = None` today).

### §4.7 How the score yields optimized context (the consumer payoff)
Context optimization = fewest load-bearing tokens, zero pollution. The scores are the deterministic
instrument:
1. **Selection costs ≈0 consumer tokens** — node centrality is daemon-precomputed; assembly = rank →
   threshold → stop. No LLM-judge relevance pass.
2. **Order-3 fetches less than order-2** — typed edges let the router walk the *dependency closure* of
   the relevant relations, not the whole similar-neighborhood. Typing prunes the walk.
3. **MDL filters slop pre-injection** — low-conformance items never enter the candidate set.
4. **cid dedup** — identical content injected once; kills the redundancy waste class.
5. **Score = RRF rank → deterministic truncation order** — when the budget cuts, the load-bearing
   survived by construction; the dropped tail is the low-yield.
6. **δ enables trust-without-reread** — low δ + high MDL ⇒ consume the handle+score (few tokens), not
   the prose; high δ ⇒ skip/escalate.
*Verify:* the **waste ledger (PRD-04 §04-c)** measures injected-but-unused rate per item — the proof
the optimization is real, not asserted (gap G-13).

---

## §5 CRDT for the nervous system (concurrent state, no conflict)

Many agents/processes write the world + tenant state concurrently. Use **state-based CRDTs (CvRDT)**:
state `(𝒮, ⊔)` is a **join-semilattice** — merge `⊔` is commutative, associative, idempotent; updates
are inflationary.
```
Theorem (Shapiro 2011): CvRDTs reach Strong Eventual Consistency — replicas with the same update
set have equal state, independent of order/duplication.
Proof sketch: ⊔ is the least-upper-bound; any merge order reaches the same LUB by assoc+comm+idem. ∎
```
**Concrete choices (and why content-addressing makes this free):**
- World-nodes = **G-Set** of facts keyed by `cid`. Adding the same fact twice is idempotent because
  `cid` is the content hash ⇒ trivially a CvRDT. (This is *why* the cid spine is load-bearing.)
- Tenant edges = **OR-Set** (add/remove with unique tags) or **LWW** tie-broken by the
  [cognition hash-chain](../../lgwks_cognition.py) head as the logical clock.
*Verify:* randomized concurrent-merge test — apply the same update multiset in N permutations to M
replicas; assert all replicas converge to byte-identical state.

---

## §6 Concurrency, queuing, backpressure — no 5xx under load

Systems view: the 8B embedder is the bottleneck *stock*; everything else feeds it.
Worker ceiling from [lgwks_workercap.py](../../lgwks_workercap.py):
```
c = min( ⌊(RAM_gib − Σreserves)/per_worker_gib⌋ , ⌊(CPU − cpu_reserve)/cpu_per_worker⌋ , |mapper_roles| )
  reserves include the always-on 8 GiB Deep-ML reserve (the embedder) — a recorded invariant, not a comment.
```
Stability + admission:
```
ρ = λ / (c · μ)                          λ = arrival (items/s), μ = service rate/worker
STABILITY INVARIANT:  ρ < 1              else the queue grows unbounded (Little's law: L = λ·W)
Bounded queue depth Q_max + token-bucket admission (rate c·μ, burst B).
OVERLOAD INVARIANT:  Q ≥ Q_max ⇒ typed 429 + Retry-After   — NEVER a 5xx.
```
Embedding work is **idempotent by cid** ⇒ a shed/retried item re-embeds to the same `cid`, so load-shedding
is safe and retries don't duplicate. Retry storms (reinforcing loop) damped by jittered backoff
(already in the crawler politeness layer).
*Verify:* load test at λ = 0.5·cμ, cμ, 2·cμ → assert: stable below 1, bounded queue at 1, and at 2×
every rejection is a 429 with Retry-After and **zero 5xx**; assert duplicate-submission yields one row.

---

## §7 The AI-consumer tail — multi-layer bias stripping, token-optimized, zero pollution

I (the orchestrator) am the final consumer. Each layer strips human language + bias and sheds tokens:
```
L1 raw text (human, polluted)
L2 canonical schema instance      prose → typed fields            (§4.4 c(I))
L3 embedding                       semantics → 4096-d vector       (language-agnostic)
L4 cubic score + cid               structure → math                (§4.3, §4.4)
L5 consumer pack                   cids + scores + minimal typed fields only — token-budgeted (PRD-04 reflex cap)
```
**§7-INV No prose crosses into L5** except as a cited, content-addressed handle. Bias and natural-language
ambiguity are gone by L4; the consumer reads math + pointers, never raw human text.
*Verify:* assert the L5 pack contains no free-text field; assert token count ≤ PRD-04 reflex cap; assert
every handle resolves to a `cid` present in the store (no dangling/hallucinated reference).

---

## §7.5 Visual representation — decoupled from the semantic space

The semantic space (N=4096) and the order-3 tensor are **math**; the visualization is a **separate
concern** with its own, unrelated, 3 axes (X, Y, Z for human UX). They are decoupled: the projection is
derived *one-way* from the N-dim embedding and **never feeds back** into scoring (§4) or retrieval (§7).
```
y_i = Wᵀ êᵢ ∈ ℝ³        W = top-3 principal axes of the tenant embedding matrix Ê (PCA via SVD)
                         SVD deterministic up to sign; sign fixed by a canonical rule
                         (largest-magnitude component positive) ⇒ replayable, no model
```
PCA (linear, exact) is default; a seeded UMAP is an optional non-linear layer only if PCA stress exceeds a
pre-registered threshold. //why decoupled: the math must never be distorted to make a picture look good,
and the picture must never be mistaken for the semantic truth. Changing the viz cannot change a score.
*Verify:* same Ê → byte-identical `W` + coords; scoring (§4) output is bit-identical with the viz layer
present or absent (proves one-way decoupling); reconstruction stress reported.

---

## §8 Gap log (honest — unbuilt or unverified)

| id | gap | severity |
|---|---|---|
| G-01 | crawler v2 schema (3 modality streams + fetched media) — not built; today text-only + image URLs | high |
| G-02 | LFM2-Extract integration + GGUF runtime wiring — not built | high |
| G-03 | Qwen3-VL-Embedding-8B runtime (MLX `jedisct1/...-mlx` or GGUF `ganeshrao/...Q8`) — not installed/wired | high |
| G-04 | schema operators `R_k` — ✅ **CLOSED (I5, PR #65; I5.1, issue #69)**: factored `R_k=P_k·diag(d_k)+N_k`, O(d). Directional activation via antisymmetric `N_k` (Σ_k N_k=0 ⇒ marginal stays identity); schema relations v2. Structural directionality; semantic arg-typing still future | ~~high~~ |
| G-05 | MDL compressor + `S`-trained dictionary — ✅ **CLOSED (I5, PR #65)**: canonical CBOR + zstd dict; cross-model equal-cid + separation margin tested | ~~med~~ |
| G-06 | tensor Z-eigen centrality — ✅ **CLOSED (I6, PR #67)**: σ-shifted power iteration + Rayleigh convergence; both eval graphs converge, seed-stable | ~~med~~ |
| G-07 | capability-token tenant isolation — ⚠ **boilerplate landed (I8, PR #76), NOT wired**: `lgwks_capability.py` (`guard`/`make_tenant_filter`, hmac-sha256 token) exists + tested, but the live store reads (`lgwks_vector.get_record`/`query_by_source`) do not yet filter on `tenant`. Wiring + live-store 10⁴ isolation proof specced in PLANS-NEXT-5.md (Gap A). MUST close before any multi-tenant/network exposure | high (T0) |
| G-08 | CRDT layer (G-Set/OR-Set + cognition-clock) — ⚠ **boilerplate landed (I9, PR #76)**: `lgwks_crdt.py` (G-Set/OR-Set/LWW, cognition-chain clock, SEC convergence over 8 permutations) exists + tested green. Issue #73 — nearest to done; needs BUILDLOG byte-identical-convergence proof + close | med |
| G-09 | queue/admission (token bucket, 429 path, Q_max) — ⚠ **boilerplate landed (I8, PR #76)**: `lgwks_admission.py` (`TokenBucket`/`AdmissionQueue`/`admission_decision`, idempotent cid shed) exists + tested. Sustained-load λ-sweep with zero-5xx proof still pending (PLANS-NEXT-5.md Gap B); engine still sequential per run | high |
| G-10 | audio transcribe lane — deferred | low |
| G-11 | embeddings stored as JSON text — ✅ **CLOSED (I1/I4)**: float32 binary BLOB store, `migrate_json_embeddings()` | ~~med~~ |
| G-12 | graphify Leiden→Louvain fallback on py3.14 — ✅ **CLOSED (I12, PR #63)**: `LeidenUnavailableError`, no silent substitution | ~~med~~ |
| G-13 | waste ledger (PRD-04 §04-c) — the *only* proof the score optimizes context; injected-but-unused rate per item — ⚠ **boilerplate landed (I11, PR #76)**: `lgwks_waste.py` (`build_ledger`/`waste_rate`/`worst_item`, `lgwks.waste.ledger.v1` live) exists + tested. Issue #75 — needs daemon-loop wiring + live transcript path (`LGWKS_TRANSCRIPT_PATH`, confirm with Director) to measure a real session | high |

Gaps should also be appended to [docs/os-framework-architectural-gaps.json](../../docs/os-framework-architectural-gaps.json).

---

## §9 Implementation plan — self-contained, sequenced units

Each unit: issue-backed, tested-green before the next, math from §4–§6 proven by its eval.
Dependency order (← depends on):

```
I1 store + contract           I2 ← I1        I3 ← I1        I4 ← I2,I3
I5 ← I4                        I6 ← I5        I7 ← I6        I8 ← I4
```

| Unit | Scope | Acceptance (the proof) |
|---|---|---|
| **I1** vector-space + cid contract | float32 binary vectors, L2-normalized; `cid` content-address; manifest declares space (G-11) | §4.1 norms == 1±1e-6; identical input → identical cid; round-trip lossless |
| **I2** universal input handler | detect → modality route → quarantine unknown (§2) | every fixture type routes; unknown → `untrusted`, no crash |
| **I3** crawler v2 (3 modality streams) | schema `lgwks.crawl.v2`, fetched+cid'd media (G-01) | 3 typed streams emitted; cid stable; frontier audit complete |
| **I4** embedder runtime (Qwen3-VL-8B) | MLX or GGUF behind one port; 3 encoder paths → one 4096-d space (G-03) | cosine bounds; MRL recall@k curve (§4.1 verify) |
| **I5** schema scoring (²/³ + MDL) | `R_k` construction, RESCAL score, MDL conformance + cid (G-04,05) | §4.2 marginal==cosine ≤1e-6; cross-model equal-cid; MDL separation margin |
| **I6** cubic node centrality | tensor Z-eigen power iteration + AI-discrepancy δ (G-06) | converges; seed-stable; δ threshold pre-registered |
| **I7** consumer tail (L5 pack) | token-budgeted, prose-free, handle-resolving (§7) | §7-INV holds; ≤ reflex cap; no dangling handle |
| **I8** concurrency + isolation | worker-cap queue, token-bucket, 429 path (G-09); capability-token isolation (G-07) | §6 load test (0 × 5xx); §1-INV zero cross-tenant leak |
| **I9** CRDT state | G-Set world / OR-Set tenant + cognition clock (G-08) | §5 permutation-convergence test byte-identical |

LFM2-Extract (G-02) slots into I3 (the extract step) once I1's contract exists.
graphify clustering fix (G-12) is independent — schedule anytime.

---

## §10 Decisions — finalized in v1.0 (flag if any is wrong)

1. **`R_k` = schema-derived, not learned** (§4.5) — keeps AI out of the node. FINALIZED.
2. **"3-dimensional" = two decoupled things** — (a) the order-3 *tensor* (3 modes over the N=4096-d
   space, the scoring math, §4); (b) a separate viz-only X/Y/Z projection (§7.5), one-way, never feeds
   scoring. The math and the picture are decoupled. FINALIZED.
3. **Models pinned** (§3.5): Qwen3-VL-Embedding-8B + LFM2-Extract; MLX or llama.cpp. FINALIZED.
4. **Start at I1** (vector-space + cid contract — everything reads from it). Awaiting approval to begin.

Self-contained per-unit work packets: [INGESTION-PLAN.md](INGESTION-PLAN.md).
