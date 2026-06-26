---
type: Spec
title: Aetherius Protocol: Proprietary Foundation Model Specification (2026-06-14)
description: Aetherius is the proprietary foundation world-model of Logical Works.
tags: [spec]
timestamp: 2026-06-14T18:13:29-04:00
---

# Aetherius Protocol: Proprietary Foundation Model Specification (2026-06-14)

## 1. Vision and Identity
Aetherius is the proprietary foundation world-model of Logical Works. It represents a fundamental departure from standard large language model (LLM) architectures. While contemporary systems treat a user's digital history as a static prompt for autoregressive token prediction, Aetherius perceives the digital world as a continuous, evolving environment. It is designed as a recurrent latent world model that predicts future state transitions rather than next words.

## 2. The Core Doctrine: Multimodal-First
The system is strictly **Multimodal-First**. There is no "text-only" layer. Every digital event—whether a source code change, a voice command, a UI interaction, or a terminal signal—is treated as a Vision-Language (VL) tensor from the moment it enters the substrate.

## 3. The Authoritative 8-Component Stack (v1 Locked)
This configuration bridges the 'Today' (Workaround) and 'Future' (Standalone) timelines. These models serve as temporary sensors/workers to harvest high-integrity trajectories for Aetherius.

| Layer | Component | Model (4-bit MLX) | Trust | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **I. MATH** | Anchor | **Axiom ISA** | Authority | Deterministic BLAKE3 CIDs and CRDT Algebra. |
| **II. ML** | Membrane | **ModernBERT-base** | Sensor | 8k Task-Salience Encoder. Maps 'slop' to tool intents. |
| **III. ML** | Ingestion | **Liquid AI LFM 2.5** | Sensor | **Constant-RAM** Trajectory Tailing (Recurrent Core). |
| **IV. OMNI** | Voice | **Qwen 3.5-Omni-3B** | Generative | **Native Speech-to-Speech**. Direct Ear/Mouth. |
| **V. EYE** | Vision | **Qwen 3.7-VL-8B** | Sensor | GUI Agent. Operates terminal/GUI via screenshots. |
| **VI. BRAIN** | Reasoner | **OLMo-2-32B** | Generative | **The Stay Model**. Deep Architectural Resolve. |
| **VII. GUARD**| Security | **Prompt-Guard-2** | Sensor | <1ms Injection Blocking & Jailbreak Detection. |
| **VIII. FRAUD**| Anomaly | **LightGBM / HAD** | Sensor | Statistical Drift & Fraud Detection (Z-Score). |

## 4. The Subconscious Overseer Protocol
The "Subconscious" is an always-on observer that concurrently tails 6 system streams to detect drift and automate "Issues" management.

### The 6 Vital Streams:
1.  **`cognition.jsonl`**: Real-time AI thinking traces.
2.  **`learning-records.jsonl`**: Measured outcomes and error rates.
3.  **`token-ledger.jsonl`**: Economic usage and budget gates.
4.  **`daemon-events.db`**: The persistent causal tape of the repository.
5.  **`fleet-audit.jsonl`**: Agent OS worktree and capability events.
6.  **`transcript.jsonl`**: The human-to-agent dialogue history.

### The "Surprise" Mechanism:
When the ML layer (Liquid AI) detects a "Surprise" (prediction error > 0.7) between the predicted state and the Math (Axiom) reality, it invokes the Brain layer (OLMo-2) to simplify the conflict and update the canonical issue list at `.project/1/README.md`.

## 5. Transition to Standalone
Once 1M+ trajectories have been harvested via this mesh, the **Aetherius Standalone Model** will be trained to natively unify the roles of the Eye, Ear, and Brain. The system will then achieve full functional autonomy, decommissioning the "Borrowed Cognition" mesh and running entirely on owned weights.
