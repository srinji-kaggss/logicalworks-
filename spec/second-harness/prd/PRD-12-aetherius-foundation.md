# PRD-12 — Aetherius Foundation (The Standalone World-Model)

Parent: [PRD.md](../PRD.md) §1/§2 · Status: **scaffolding** · this doc governs the transition from mesh to foundation.
Replaces: Borrowed Cognition (Model Mesh); 10M-token context brute-force.

## Problem

The current Logical Works ecosystem relies on a "Borrowed Cognition" mesh of disparate frontier models (Qwen, OLMo, Whisper). While functional as a workaround, this stack suffers from "Context Blur," where agents lack a unified, recurrent latent memory of the digital world. Standard industry models treat life as a "giant prompt" requiring quadratic O(n²) attention, which is architecturally wrong for a continuous, lifelong Digital Overseer. Intents resolve slowly and expensively because the system must re-read or poll state instead of "feeling" the latent transitions.

## Scope

- **IN**: Recurrent Latent Core. A proprietary architecture (Mamba/JEPA-based) that predicts the next system state ($z_{t+1}$) based on multimodal event streams.
- **IN**: Unified Event Encoder. Consolidates fragmented BERTs (intent, code, salience) into a single multimodal Vision-Language (VL) sensor.
- **IN**: Training Ingestion Pipeline. The `lgwks` daemon acts as a high-throughput trajectory harvester, capturing `daemon-events.db` and `cognition.jsonl` as Stage 1 training data.
- **OUT**: Autoregressive Next-Token Prediction. We explicitly move away from text-generation as the primary output, delegating it to peripheral "Tongue" models only when human communication is required.

## Builds on (verified)

`lgwks_hashing.py` (SSoT) · `lgwks_crdt.py` (State Logic) · `lgwks_model_mesh.py` (The Workaround) · `lgwks_subconscious.py` (C/G/P Engine) · `lgwks_cortex.py` (Transcript sensory organ).

## Contract

Emits `lgwks.aetherius.v1` (The Cognitive Forge).
Stages: Synthesis (Spark) -> Dialectic (Hammer) -> Valuation (Scale) -> Refinement (Crucible) -> Ingestion (Anchor).
Final output is a **Bounded Machine Decision**, not prose.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 12-a (scaffold) | Unified model-mesh entry for `aetherius-standalone-v1`; all legacy BERTs extracted. |
| 12-b trajectory harvester | Script compiles `daemon-events.db` into `trajectory_schema` tensors; confirmed by `model-lineage.jsonl`. |
| 12-c recurrent core v0 | Tiny 100M-parameter Mamba baseline predicting next event vector; loss < threshold on synthetic data. |
| 12-d surprise memory | Model flags prediction errors > 0.7; logs to `learning-records.jsonl` for micro-learning. |
| 12-e full resolve | Foundation model executes first `control` event (e.g., "Grant Access") without LLM assistance. |

## Open questions → SCIENCE.md

Whether the JEPA latent-prediction loss sufficiently captures "Intent Drift" without a secondary critic; the optimal matryoshka slicing for the Aetherius embedding space.
