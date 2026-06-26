---
type: ADR
title: ADR-pipeline-001: Pipeline Parameter Tuning
description: lgwks_pipeline.py introduces a multi-stage signal-driven ranking pipeline.
tags: [adr]
timestamp: 2026-06-08T07:20:19-04:00
---

# ADR-pipeline-001: Pipeline Parameter Tuning

**Status:** PROVISIONAL — confirm after 3+ production runs  
**Created:** 2026-06-08  
**Owner:** TBD  
**Related file:** `lgwks_pipeline.py`

---

## Context

`lgwks_pipeline.py` introduces a multi-stage signal-driven ranking pipeline. Every
numeric threshold in that file is a named module-level constant tagged with an
ADR section (e.g. `[ADR §2.1]`). These defaults are educated first-run guesses
based on recommender system literature (see `Untitled 7.json` research substrate).

They are NOT tuned on real lgwks corpus data. They must be confirmed or adjusted
here after sufficient production usage.

---

## §2: Recall Stage

### §2.1 RECALL_K (default: 2000)

**What it governs:** How many candidates ANN cosine recall returns before fast-rank.  
**Env override:** `LGWKS_RECALL_K`

| Corpus size | Recommended value | Rationale |
|---|---|---|
| < 500 chunks | 500 | Over-recall adds no value |
| 500–5 000 | 2000 (default) | Covers most corpora comfortably |
| 5 000–50 000 | 5000–10 000 | Need wider candidate pool |
| > 50 000 | 10 000–20 000 | Two-tower ANN still fast at this scale |

**Confirmation gate:** RECALL_K is correctly sized when fast-rank precision@50 ≥ 0.80.  
**Status:** ☐ Not yet confirmed

---

### §2.2 FAST_RANK_K (default: 200)

**What it governs:** How many candidates pass from fast-rank to heavy-rank.  
**Env override:** `LGWKS_FAST_RANK_K`

Tune this when heavy-ranker precision is too low. If the final top-50 consistently
lacks expected chunks, raise FAST_RANK_K to 300–500. Raising too high degrades
heavy-rank latency (BERT runs on every candidate).

**Status:** ☐ Not yet confirmed

---

### §2.3 HEAVY_RANK_K (default: 50)

**What it governs:** Candidates passed to the reranker after BERT/classifier scoring.  
**Env override:** `LGWKS_HEAVY_RANK_K`

50 is standard for production recsys (YouTube, Instagram Explore). Raise only if
downstream consumers need a wider ranked list (e.g. a UI that paginates deeply).

**Status:** ☐ Not yet confirmed

---

## §3: Disambiguation Stage

### §3.1 DISAMBIGUATION_CONF_THRESHOLD (default: 0.72)

**What it governs:** Intent classifier confidence below which Gemma 1B paraphrase
generation triggers for a chunk.  
**Env override:** `LGWKS_DISAMBIG_CONF_THRESHOLD`

| Setting | Effect |
|---|---|
| 0.85–0.95 | Aggressive disambiguation — almost every uncertain chunk gets variants |
| 0.72 (default) | Moderate — triggers on genuinely ambiguous chunks |
| 0.50–0.60 | Conservative — only highly uncertain chunks |
| 0.00 | Never disambiguate (pure ML path) |

**Recommended first adjustment:** Lower to 0.65 for financial/regulatory corpora
where technical jargon is systematically misclassified by generic intent classifiers.

**LLM cap interaction:** Disambiguation is subject to `MAX_LLM_INVOLVEMENT_RATIO`.
Even if threshold is met, LLM is not called once the cap is hit.

**Status:** ☐ Not yet confirmed

---

### §3.2 DISAMBIGUATION_MAX_VARIANTS (default: 4)

**What it governs:** Max paraphrase variants Gemma generates per ambiguous chunk.  
**Env override:** `LGWKS_DISAMBIG_MAX_VARIANTS`

Research on embedding augmentation suggests 3–5 variants is optimal.
Above 6 the marginal variants tend to be repetitive and add noise.

**Status:** ☐ Not yet confirmed

---

## §4: Rerank Stage

### §4.1 NOISE_SCORE_THRESHOLD (default: 0.72)

**What it governs:** Chunks with noise_score above this are quarantined.  
**Env override:** `LGWKS_NOISE_THRESHOLD`

The `noise_score` function is a weighted sum of:
- Boilerplate signal ratio (0.30 weight)
- Punctuation spam / ALL CAPS ratio (0.20)
- Link density (0.20)
- Inverse fact density (0.30)

Start at 0.72. Lower (0.60) if too much boilerplate survives. Raise (0.85)
if legitimate technical content is being quarantined.

**Status:** ☐ Not yet confirmed

---

### §4.2 DIVERSITY_PENALTY_WEIGHT (default: 0.30)

**What it governs:** How heavily same-content similarity is penalised in reranking.  
0 = no diversity enforcement. 1 = pure diversity ignoring relevance.  
**Env override:** `LGWKS_DIVERSITY_PENALTY`

0.30 is a reasonable starting point (similar to MMR lambda in information retrieval).
For legal/regulatory corpora where repetition is intentional (same rule stated
multiple ways), lower to 0.10–0.15.

**Status:** ☐ Not yet confirmed

---

### §4.3 SAME_SOURCE_CAP (default: 5)

**What it governs:** Max chunks from the same source URL/file in the final output.  
**Env override:** `LGWKS_SAME_SOURCE_CAP`

For broad web crawls: 3–5. For single-document deep-dive: 20–50 (or disable).
When ingesting a single large dataset, set this to a high value (e.g. 500) to
avoid capping a legitimately dense source.

**Status:** ⚠ Adjusted — default=5 is too aggressive for focused regulatory corpora.
Fundserv run (2026-06-08): 20/21 quarantines were source_cap with 10-source corpus.
Recommended: raise to 10 for regulatory/portal corpora. Use `LGWKS_SAME_SOURCE_CAP=10` until default is tuned.

---

## §5: LLM Governance

### §5.1 MAX_LLM_INVOLVEMENT_RATIO (default: 0.20)

**What it governs:** Hard cap — if more than this fraction of chunks touch an LLM
at any stage, no further LLM calls are made and a warning is written to the manifest.  
**Env override:** `LGWKS_MAX_LLM_RATIO`

This enforces the architecture principle: LLM as reader, not driver.

A run where llm_involvement_score > 0.20 should trigger review:
- Is the corpus unusually ambiguous? (lower threshold)
- Is the classifier undertrained? (retrain classifier)
- Is the domain vocabulary missing from POLYSEMOUS_DOMAIN_TERMS?

**Status:** ☐ Not yet confirmed

---

## §6: Fast-Rank Signal Weights

### §6.1 Linear weight vector

Default weights (must sum to 1.0):

| Signal | Weight | Note |
|---|---|---|
| BM25 | 0.40 | Dominant signal — term frequency |
| Fact density | 0.20 | Procedural vs narrative ratio |
| Recall score | 0.15 | Cosine from Stage 5 |
| Entity overlap | 0.15 | Jaccard of extracted entities |
| Recency | 0.10 | Placeholder — tune when timestamps available |

These weights are hardcoded (not env-overridable) because they interact.
Change them together in `lgwks_pipeline.py` and verify sum = 1.0.

**First tuning signal:** If BM25 over-weights stop words, reduce BM25 to 0.30
and raise fact_density to 0.30.

**Status:** ☐ Not yet confirmed

---

## §7: Dataset Intake

### §7.1 DATASET_BATCH_SIZE (default: 256)

**What it governs:** Items processed per batch during streaming dataset intake.  
**Env override:** `LGWKS_BATCH_SIZE`

| Dataset size | Recommended | Note |
|---|---|---|
| < 10 000 rows | 256 (default) | RAM-safe |
| 10 000–500 000 | 512 | Faster I/O |
| > 500 000 | 1024 | Profile memory before increasing |

**Status:** ☐ Not yet confirmed

---

## §8: Multimodal Embedding

### §8.1 MULTIMODAL_EMBED_MODEL (default: google/gemini-embedding-2)

**What it governs:** Model used for image + text multimodal chunks.  
**Env override:** `LGWKS_MM_EMBED_MODEL`

Deliberately not the free OpenRouter VL model — privacy requirement.
Uses OpenRouter with the `openrouter` keychain secret.

If `google/gemini-embedding-2` is unavailable via OpenRouter, fallback options:
- `google/gemini-embedding-exp-03-07` (experimental)
- Text-only degradation (automatic — no image embedding)

**Status:** ☐ Not yet confirmed — verify model availability via OpenRouter

---

### §8.2 MULTIMODAL_MAX_IMAGE_BYTES (default: 6 MB)

**What it governs:** Max raw image size before the image is skipped (not base64-encoded).  
**Env override:** `LGWKS_MM_MAX_IMG_BYTES`

6 MB raw → ~8 MB base64. Gemini embedding-2 context limit is ~10 MB per request.
Reduce to 2 MB for faster throughput on image-heavy datasets.

**Status:** ☐ Not yet confirmed

---

## §9: Coherence Gate

### §9.1 COHERENCE_THRESHOLD (default: 0.65)

**What it governs:** Cosine similarity between query embedding and pack summary
embedding below which a warning is written to the manifest.  
**Env override:** `LGWKS_COHERENCE_THRESHOLD`

This is not a hard block — it is a semantic quarantine flag. A pack below
threshold is still returned but marked for human review.

Cosine similarity interpretation (approximate):
- > 0.85: very high coherence
- 0.65–0.85: acceptable
- 0.50–0.65: borderline (flag for review)
- < 0.50: pack likely diverged significantly from query intent

**Status:** ☐ Not yet confirmed

---

## Confirmation Protocol

After each production run, the pipeline manifest includes a `parameters` snapshot.
Review the manifest and update the Status field above:

- ☐ Not yet confirmed
- ✓ Confirmed (date, corpus type)
- ⚠ Adjusted (from → to, reason)

Target: 3 production runs on distinct corpus types before marking parameters as stable.

Corpus types needed:
1. ☐ Web crawl (support.walkme.com — 100 pages)
2. ✓ Regulatory document dataset (Fundserv portal corpus, 2026-06-08)
   Run: pipeline-96b888e6c8178d30-20260608-104613, target=fundserv-portal-test-20260607-120840
   coherence=0.688, ingested=58, final_ranked=29, quarantined=21 (20 by source_cap, 1 by noise)
   Note: source_cap=5 too aggressive for focused 10-source corpus — raise to 10 for regulatory corpora
3. ☐ Mixed image + text dataset

---

## Decision Record

The multi-stage recall+rank architecture is derived from:
- YouTube Deep Neural Networks for Recommendations (2016)
- Instagram Explore multi-stage pipeline (Meta Engineering, 2023)
- Meta DLRM architecture (2019)

See `Untitled 7.json` in the research substrate for full reading list and citations.

The "LLM as reader, not driver" principle is documented in the draw.io diagram
(`What I mean.json`, 2026-06-08) and the architecture discussion that preceded
this ADR.
