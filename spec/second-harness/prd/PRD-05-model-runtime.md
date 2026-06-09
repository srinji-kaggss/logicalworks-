# PRD-05 — Local Model Runtime & Training (FINALIZED)

Parent: [PRD.md](../PRD.md) U4 + §4 division of labor · Status: **v1.0 finalized · build spec** · 2026-06-09
Replaces: runtime cloud inference of every kind (INV-5 is the law of this PRD).
Grounded against verified repo state (see §0) — no assumed capabilities.

## §0 Verified reality (checked 2026-06-09, updated after T-TORCH resurrection)

Commands run: `python3 --version`, `lgwks_model_hub.doctor()`, `ls models/`, live Ollama embed,
3.11 venv build + dry-run + install + **real MPS forward pass**.

| Fact | Value | Source |
|---|---|---|
| Default interpreter | **Python 3.14.5** (PEP 668 externally-managed — no pip) | `python3 --version` |
| Also installed | **Python 3.11.15**, 3.13.13 | `python3.11 --version` |
| Models on disk (weights present) | tiny-bert, distilbert-base-uncased, codebert-base, neobert | `ls models/`, `present_models=4` |
| `.mlpackage` files | **ZERO** (T-ANE still unconverted) | `coreml_packages=0` |
| **T-TORCH** | **ALIVE** — torch 2.12.0 + transformers 5.10.2 in `.venv-models` (3.11); forward pass on **MPS** | tiny-bert→128d, codebert→768d, ~1s |
| T-EYE (Ollama) | **UP**, `qwen3-embedding:8b`, returns 4096-d live | live `embed_one` test |
| T-DET | always-on | by construction |
| coremltools / T-ANE | not installed; **installable on 3.11** (no longer a hard block) | dry-run wheel resolves |

**The divergence — now partly resolved:** the parent PRD's "BERT on-device" (INV-5, §14a)
was non-functional because the default 3.14 interpreter has no torch and forbids pip. It is
**not** a capability block — Python 3.11 is present and torch/coremltools have arm64 wheels.
The fix was a 3.11 venv (`.venv-models`, gitignored). T-TORCH is now real on-device inference
on the Apple GPU. CoreML/ANE (T-ANE) remains an optimization tier, not a requirement.
//why kept honest: §0 previously asserted "torch blocked" — that became false the moment the
venv installed; the doc is corrected rather than left to narrate a stale hole (T2).

## §1 The model inventory (catalog, `lgwks_model_hub._MODEL_CATALOG` — verified)

| Model | Arch | Params/size | License | Role in the harness |
|---|---|---|---|---|
| **tiny-bert** | BERT, 2L, h128 | 16 MB | Apache-2.0 | edge intent classification; smallest viable encoder; CI default |
| **distilbert-base-uncased** | DistilBERT, 6L, h768 | 66 MB | Apache-2.0 | fast STEM gate for crawl ingest (PRD-03) |
| **codebert-base** | RoBERTa, 12L, h768 | 500 MB | MIT | **code embedding/review engine** (PRD-02, PRD-09) — AST-aware |
| **neobert** | BERT, 28L, h768, 4K ctx | 1.2 GB | MIT | research-grade encoder; salience/attention (PRD-06 cortex) |
| qwen3-embedding:8b | (Ollama-served) | ~8B | Apache-2.0 | **current** semantic embeddings; the working tier today |

All licenses are permissive (Apache-2.0/MIT) — INV-5 §competitive "forkable OSS" satisfied.
Weights are repo-resident (git-lfs per `models/.gitattributes`); only setup touches network.

## §2 The tiered runtime (FINALIZED — how they run)

Four tiers, strict degrade order. Every consumer (PRD-01/02/03/04/06) calls one surface
(`embed/score/classify`) and the runtime selects the highest available tier. INV-6: any
consumer must function with ALL model tiers absent (deterministic fallback).

```
T-ANE   CoreML .mlpackage on Apple Neural Engine    ← designed; BLOCKED (Py3.14, no coremltools, no mlpackage)
T-TORCH PyTorch/MPS forward pass (transformers)      ← works if torch present; the realistic on-device tier NOW
T-EYE   Ollama qwen3-embedding:8b @ localhost        ← WORKING TODAY; local server, on-device, not cloud
T-DET   cosine over precomputed centroids / lexical  ← always-on deterministic floor (LGWKS_NO_MODELS=1)
```

//why four not two: the parent's binary (CoreML | nothing) doesn't match reality. T-TORCH
is the honest near-term on-device path (MPS exists on this Mac; coremltools is the only
blocker, and it's a packaging blocker not a capability one). T-EYE is what ships value today.
T-DET guarantees INV-6. **Decision: T-EYE is the supported production tier for v1; T-TORCH
is the on-device upgrade; T-ANE is unblocked only when a ≤3.12 interpreter is provisioned
for the setup/convert step (runtime stays 3.14).** This is a finalized stance, not a TODO.

INV-5 reconciliation: "no runtime cloud inference" holds — Ollama is a localhost process,
no network egress, no API key. T-EYE is on-device by the invariant's intent. The catalog
flags any cloud embedder (`lgwks_openrouter_embed.py`) as **dev-only**, asserted by a test
that fails if it is reachable from a runtime path.

## §3 The lifecycle (setup → convert → load → forward → doctor)

Surfaces verified in `lgwks_model_hub.py`: `list_models`, `load_model`, `convert_to_coreml`,
`train_text_classifier`, `doctor`, `scrub_model_dir`. Setup: `scripts/setup_models.py` (199 lines).

1. **Setup (network, once per dev):** download from HF Hub (Apache/MIT only) → `scrub_model_dir`
   (keeps only config/tokenizer/weights — strips training metadata, INV: no training data
   persists) → place in `models/<name>/`. git-lfs for >100 MB.
2. **Convert (T-ANE only, ≤3.12):** `convert_to_coreml` traces a mean-pooled wrapper →
   `ct.convert` → `.mlpackage` (iOS16 target). **Returns `ok:true, skipped` on 3.14** — the
   degrade is already coded (`_python_coreml_eligible`). FINALIZE: setup runs convert under a
   pinned 3.12 venv (`scripts/setup_models.py` gains a `--convert-venv` path); the artifact,
   not the converter, is what runtime needs.
3. **Load (runtime, any tier):** `load_model` returns `{ok, path}` from repo dir; tier
   selector probes ANE→TORCH→EYE→DET and returns the live one.
4. **Forward:** `embed(texts)→vectors`, `score(pairs)→floats`, `classify(text,labels)→dist`.
5. **Doctor:** `lgwks.model_hub.doctor.v1` (exists) — extended with `active_tier` field so the
   cockpit (PRD-07) shows which tier is live per session.

## §4 The training pipeline (FINALIZED steps)

Two trainable surfaces exist; both fine-tune a small encoder, both target the same export.

### 4a. Generic classifier — `train_text_classifier` (verified, `lgwks_model_hub.py:357`)
Steps (as coded): label-map build → `_TextDS` tokenize (max_len 128) → 80/20 split
(`random_state=42`, deterministic) → HF `Trainer` 3 epochs, batch 8, eval per epoch,
`save_strategy=no` → accuracy on holdout → `save_pretrained` torch dir →
`convert_to_coreml` with `ClassifierConfig(labels)`. **Guards present:** ≥4 rows / ≥2 labels,
path-escape assertion (`_assert_under`). **Gap to fix:** CoreML export is the last step and is
blocked on 3.14 → training currently yields a torch model with no `.mlpackage`. FINALIZE:
split the pipeline — `train` (3.14, produces torch + safetensors) and `export` (3.12 venv,
produces mlpackage) as separate verbs, so training is not coupled to the conversion blocker.

### 4b. Intent classifier — `tools/train_intent_classifier.py` (verified exists) + `lgwks_intent_classifier.py`
Domain: ~20–50 lgwks verb classes, derived live from the manifest (label = verb id, feature
= intent string). PyTorch + MPS. The runtime fast path is cosine over precomputed class
centroids (T-DET/T-EYE); the accurate path is the CoreML encoder (T-ANE, pending). //why
custom not off-the-shelf (from the file's own L5): closed-set, English-only, retrains in
minutes when verbs land, owns its weights, 10–100× smaller than an instruct model.

### 4c. Training data discipline (new — required before any fine-tune ships)
Every fine-tune is an EXP under [SCIENCE.md](SCIENCE.md) §2/§3: frozen labeled corpus,
hash-pinned, held-out test, accuracy reported with the corpus hash. No model enters a
runtime tier without beating the T-DET deterministic baseline on its frozen set (SCIENCE §6).
Retraining triggers: manifest verb-set change (intent classifier), corpus growth from
production errors (SCIENCE §6 loop).

## §5 Units & acceptance (build order)

| Unit | Acceptance |
|---|---|
| 05-a tier selector | `embed/score/classify` route ANE→TORCH→EYE→DET; `doctor.active_tier` correct on this machine (must read `eye` today); test forces each tier present/absent |
| 05-b T-EYE production | qwen3-embedding path benchmarked: throughput tokens/s reported, p95 latency logged; the supported v1 semantic tier |
| 05-c T-TORCH on-device | a real MPS forward pass over codebert on 02-d chunks; golden-input output stable across runs (±tol); proves on-device without CoreML |
| 05-d degrade proof | full consumer suites pass under `LGWKS_NO_MODELS=1`; zero crashes; `tests/test_one_embedder.py` pattern extended to every consumer |
| 05-e split train/export | `model-hub train` (3.14) yields torch+safetensors; `model-hub export` (3.12 venv) yields mlpackage; neither blocks the other |
| 05-f T-ANE unblock | provisioned 3.12 venv converts one model; `convert_to_coreml` returns ok+path (not skipped); a real ANE forward pass matches T-TORCH output within tolerance |
| 05-g registry pinning | weights hash-pinned; doctor fails loud on mismatch; cloud-embedder reachability test fails the build if a runtime path can reach `openrouter_embed` |

## §6 How this fits the PRD family

PRD-05 is the **engine room** — it decides nothing (INV-4), it serves vectors/scores to:
PRD-01 (semantic re-rank, 01-d) · PRD-02/03 (chunk + docs embedding) · PRD-04 (vector leg
of hybrid retrieval) · PRD-06 (salience/attention + classifier heads for flags/intent).
Every one of those names T-DET as its fallback precisely because T-ANE is unproven and
T-EYE depends on a running Ollama. Nothing upstream may *require* a model tier to function.

RISK: the honest finalization surfaces a real constraint — the "ANE/CoreML on-device"
story in the parent PRD is aspirational on Python 3.14; v1 value rides on Ollama (T-EYE),
a 8B model and a separate server, which is heavier and less "baby model" than §4's economic
thesis assumes. If T-EYE's weight undermines the cheap-orchestration argument, the answer is
T-TORCH with a small encoder (codebert/distilbert), and that path (05-c) should be proven
early rather than treated as a fallback.
