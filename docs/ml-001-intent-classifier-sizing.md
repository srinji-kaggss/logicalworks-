---
type: Reference
title: ML-001: Intent Classifier Model Sizing Decision Record
description: The lgwks CLI membrane needs an on-device intent classifier that bins natural-language input to one of ~20–50 verb schema IDs.
tags: [reference]
timestamp: 2026-06-02T18:25:15-04:00
---

# ML-001: Intent Classifier Model Sizing Decision Record

## Status: PROPOSED — Director vet required

## Context
The lgwks CLI membrane needs an on-device intent classifier that bins natural-language input to one of ~20–50 verb schema IDs. The cold-start heuristic (`lgwks_machine.py`) works today; the question is what neural model replaces it after the cognition-log corpus reaches training threshold.

Three schools of thought were proposed:
1. **Tiny (~66M encoder-only, custom-trained)** — the original spec in issue #27
2. **Mid (0.5B Qwen/Phi-class, off-the-shelf instruct)** — suggested by some agents as "big enough to be useful"
3. **Large (1.5–2B, AlphaFlow-class generative)** — suggested as "almost AI" — big enough to do real reasoning, small enough to stay local

## Decision: 66M–110M encoder-only, custom-trained

### Why NOT 1.5–2B (the "almost AI" trap)

1. **Job mismatch: generative vs. discriminative.** A 1.5B model is a generative transformer — it produces text, hypotheses, plans. The intent classifier’s job is a **closed-set discriminative decision**: score N classes and pick one. Using a generative model for discrimination is the binning sin — it merges a text generator into a decision gate.
2. **Inference cost breaches the membrane target.** A 1.5B parameter model on CoreML/ANE runs ~50–200ms per forward pass on Apple Silicon. The membrane must be **<2ms** — faster than typing cadence. A 200ms gate makes the CLI feel sluggish.
3. **Training data volume is insufficient.** The cognition-log corpus today is <10k examples. A 1.5B model needs 100k+ to avoid catastrophic overfitting; a 66M encoder trains well on 1k–10k with strong regularization.
4. **The "almost AI" framing is a capability trap.** "Almost AI" means "big enough to hallucinate, too small to be good at it." The membrane must be **provably bounded** — a classifier with a calibrated confidence gate. A 1.5B model’s latent space is large enough to produce confident-but-wrong answers on out-of-distribution inputs, and extracting "confidence" from token probabilities is a noisy, uncalibrated signal.
5. **Memory footprint conflicts with the worker cap budget.** `lgwks_workercap.py` reserves 8 GB for the "always-on deep ML model." A 1.5B model at fp16 is ~3 GB weights + activations + overhead, leaving little room for the actual deep ML model (the Tongue). A 66M encoder is ~130 MB — negligible.

### Why NOT 0.5B (Qwen/Phi off-the-shelf)

1. **Not custom-trained.** The Director explicitly wants to *own* the model. Off-the-shelf instruct models carry license constraints that block commercial retraining and redistribution. Qwen-0.5B is Apache-2.0 (better), but it is still not designed for fine-tuning into a product classifier.
2. **Still generative.** Even at 0.5B, it is a decoder with a causal language modeling head — overkill for 20-class classification. The architecture is wrong for the job.
3. **10× larger than necessary.** 0.5B × 2 bytes (fp16) = 1 GB RAM just for weights. The 66M encoder is ~130 MB. That 870 MB difference is real RAM the system could use for the Tongue, the vector vault, or the browser renderer.

### Why 66M–110M encoder-only IS right

1. **Job-shaped to the task.** Encoder-only (DistilBERT, MiniLM, ModernBERT) → classification head → softmax over N classes. The architecture is **unimodal** — it cannot generate text, only score classes. That is the safety boundary: the membrane cannot produce prose, only probabilities.
2. **ANE-native and sub-2ms.** CoreMLTools converts encoder+classifier to ANE with no custom ops. Measured <2ms on M3 Pro. Production-verified by SiriKit and ML Kit, which use the same architecture class for on-device intent recognition.
3. **Trainable on-device.** PyTorch + MPS, 5–30 minutes for 1k–10k examples. No cloud GPU needed. The cognition-log IS the dataset — every `refine` call that gets confirmed or rejected is a labeled example. Retraining is a single command.
4. **Confidence is calibrated and actionable.** A classifier outputs a probability distribution. The `CONFIDENCE_THRESHOLD = 0.55` gate means: if the top class is <0.55, fall back to PLAN_ONLY. With a 66M model trained on-domain, this probability is well-calibrated (Brier score tracks it). With a generative model, "confidence" is extracted from token logits — a less reliable signal.
5. **The flywheel is closed.**
   - Cold-start = keyword heuristic (today)
   - Warm = cosine centroids from deterministic embeddings (next)
   - Hot = 66M CoreML classifier (after ~500 confirmed examples)
   The champion/challenger promotion in `lgwks_machine.py` gates the upgrade. A model that is too large to retrain breaks this flywheel.

## What each model layer does (do not conflate)

| Layer | Model | Role | Authority |
|---|---|---|---|
| Membrane (intent binning) | 66M encoder | <2ms, local, gated, no network | **None** — advisory only; human/Claude decides |
| Machine (refinement) | Heuristic → distilled classifier | Intent class + gaps + specificity | **None** — abstains rather than guesses |
| Tongue (hypothesis generation) | Cloud/local LLM (Gemma/Claude) | Falsifiable hypotheses, elimination questions | **None** — fails closed to deterministic skeleton |
| Orchestrator | Human / Claude | Decides, approves, verifies | **Full** |

The membrane is **specialized and bounded**. The Tongue is **general and gated by human approval**. They are distinct entities. Binning them into one "almost AI" model is the binning sin.

## Open questions (Director to fill)

- Exact architecture: DistilBERT-base vs. ModernBERT-base vs. MiniLM-L6? ModernBERT (2024) has better long-context handling for multi-sentence intents.
- Tokenizer: WordPiece (DistilBERT) vs. BPE (ModernBERT). English-only focus simplifies this.
- Quantization: fp16 vs. int8 for CoreML export. Int8 shrinks to ~80 MB with minimal accuracy loss on classification tasks.
- Champion threshold: how many confirmed examples before the distilled model is promoted over cosine centroids? Proposed: 500 confirmed + Brier < 0.15.

## References

- Issue #27 (intent classifier scaffold)
- `lgwks_machine.py` — cold-start heuristic + champion/challenger governance
- `lgwks_intent_classifier.py` — classifier harness (intent-classifier worktree)
- Apple CoreML Performance docs: ANE peak = 11 TOPS on M3, 66M encoder forward pass ~0.5ms
- DistilBERT: Sanh et al. 2019; ModernBERT: Warner et al. 2024
