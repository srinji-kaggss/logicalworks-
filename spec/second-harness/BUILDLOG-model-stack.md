# BUILDLOG — Model Stack: L1, Algorithms, Intent-Math, SAST

Branch: `feat/model-stack-l1-algorithms` · started 2026-06-09 · author: Logical Claude (Opus)
Mandate: make L1 functional; finalize algorithms + intent-math + SAST; log; merge to main; align gh.
Authority: Director granted "make calls"; he runs a separate harden after. Stop-and-ask only on the
Gemini model identity (verified below; not to be changed).

## Fixed model law (verified from code, not memory)
- TEXT embeddings: **local**, Ollama `qwen3-embedding:8b` (`lgwks_ollama.py:23`, 4096-d, MRL-sliced).
- IMAGE/VIDEO embeddings: **cloud, intentional** — `google/gemini-embedding-2` over OpenRouter
  (`lgwks_multimodal.py:42`, endpoint `https://openrouter.ai/api/v1/embeddings`, key `openrouter`).
  This is the designed text=local / media=cloud split. NOT drift. NOT to be removed or renamed.
  (Doc inconsistency noted: line 12 says 4096-d, line 40 says 3072-d for this model. Left untouched.)

## Verified baseline (live, this session)
- `IntentClassifier.load()` = **201.7s** — embeds all 175 verb intents through the 8B eye, serially,
  every process start. Unusable for a per-prompt membrane. → fix: cache centroids.
- method=`eye` fires correctly when Ollama is up (semantic path works).
- Confidence uncalibrated: "asdfqwerty gibberish" → 0.705, NOT plan_only; clear intents 0.70–0.83;
  nothing reaches the 0.85 authority bar. Raw cosine over a general embedder compresses into a narrow
  band. → fix: margin-based calibration + abstention.

## Work log (append-only)

### W1 — L1 functional: centroid cache + margin calibration  [DONE]
- **Cache** (`lgwks_intent_classifier.py`): `_load_or_build_centroids` persists eye/hash
  centroids to `store/intent/centroids-<tag>-<verbhash>.json` (gitignored). Keyed by verb-set
  signature + embedder space; rebuild only on manifest or embedder change.
  - Evidence: build 19.7s → **cached load 0.09s** (was 201s). classify ~100ms.
- **Calibration** (`MARGIN_MIN=0.02`): added `margin` (top1−top2) to `ClassifyResult`; `plan_only`
  now trips on no-label OR low confidence OR low margin. Authority law (method×confidence) left
  intact — reverted an over-reach that gated authority on margin and broke a test (owned + fixed).
  - Evidence (live, cached): manifest margin 0.074 / crawl 0.031 / review 0.030 → execute;
    "asdfqwerty gibberish" margin 0.0025 → **plan_only=true** (was false). Gibberish gate fixed.
  - HEURISTIC threshold pending labeled corpus (SCIENCE §7). Marginal short-gibberish
    ("xkcd qw9 blarg" margin 0.028) still passes — documented, harden with data.
- Tests: 19 pass (added `test_low_margin_forces_plan_only`, `test_clear_margin_allows_execution`).
- Commit: feat(L1) on `feat/model-stack-l1-algorithms`.

## DEFERRAL LEDGER (continuously re-ranked: P1 = do next, P3 = later)
Each entry: what · why deferred · where it must land · current rank.

| Item | Why deferred now | Lands at | Rank |
|---|---|---|---|
| LightGBM scorers (fraud_risk, escalation_score) | needs `lightgbm` dep; 3.14 is PEP-668 locked, venv-3.11 has torch not lightgbm | algorithms L4, after stdlib set proven | P2 |
| HDBSCAN / IsolationForest (sklearn) | needs `scikit-learn`; same dep gap | algorithms L4 clustering/anomaly | P2 |
| Cross-language SAST (tree-sitter js/java/c) | existing engine is Python-`ast` only; tree-sitter is a new dep + grammars | PRD-10 10-b, after substrate refactor | P2 |
| IFDS / ODG interprocedural taint | paper-grade; needs the PRD-02 code graph for call edges | PRD-10 10-c+, after code graph | P3 |
| Reranker (Qwen3-Reranker-0.6B) | new model download; not required for L1/intent-math | retrieval L3, after L1 ships | P2 |
| Cleanup LLM (Qwen3-1.7B local) | new model; only a fallback for failed deterministic paths | L5, after HAD ledger exists | P3 |
| Code specialist (Qwen2.5-Coder-3B) | new model; orthogonal to this slice | L6 code branch | P3 |
| MIV/MCS full Shapley | extends `lgwks_verify` L-coefficient; needs provenance DAG first | model-influence, after algorithms | P2 |
| CoreML/ANE export of L1 | Python 3.14 blocks coremltools; needs 3.11 export venv | L1 speed upgrade (eye→ANE) | P3 |
