---
type: Archive
title: Understanding the LogicalWorks Codebase
description: This document serves as a comprehensive synthesis of the lgwks architecture, proving a thorough understanding of the existing native components, the recent "Canonical-primitive dedup" (PR #225), and t
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Understanding the LogicalWorks Codebase

This document serves as a comprehensive synthesis of the `lgwks` architecture, proving a thorough understanding of the existing native components, the recent "Canonical-primitive dedup" (PR #225), and the strict "no external dependencies" hardware-first mandate. 

## 1. The Core Philosophy
The `lgwks` codebase is a **local-first, privacy-respecting developer research and refactoring toolchain**. It completely rejects the "chatbot" LLM-wrapper paradigm in favor of a highly deterministic, verifiable, JVM-like execution model.

If a task can be done with symbolic execution, deterministic algorithms (like AST parsing, DOM-to-MD Rust crawling, or power iteration math), it **MUST** be done that way. The escalation to Machine Learning (Sensor layer) and Generative AI (LLM layer) only happens when the previous deterministic gate hits a hard limit.

**The Golden Rule:** Rely on what is built locally. No external APIs, no hidden cloud dependencies (unless explicitly seamed), and no redundant python libraries wrapping external services.

## 2. The Architecture (The "Gates" and the "Ladder")

The user's mandate dictates an explicit execution ladder:
**Gate 1: Symbolic / Deterministic → Gate 2: Sensor / Narrow ML → Gate 3: Generative LLM**

### Gate 1: Symbolic & Deterministic (The Foundation)
This layer handles the heavy lifting with zero hallucinations. It is the absolute source of truth.
*   **Axiom-Byte-Framework (`axiom/`)**: The JVM-classfile equivalent. Uses stable byte formats and a verifier (`lgwks_axiom.py`) to validate artifacts.
*   **The Rust Crawler (`crawler/`)**: The compiled `crwl` binary. This is the **built-in Gate 1 for ingestion**. It performs high-speed, local DOM-to-Markdown extraction without relying on slow external services or LLM vision models.
*   **Graph & AST Intelligence (`lgwks_graph.py`, `lgwks_refactor.py`)**: Uses local Abstract Syntax Trees to analyze and refactor code securely and deterministically.
*   **Coherence Engine Gates (`lgwks_cohere.py`)**: The pipeline flows strictly through `G0 (Compiler/Test)` → `G1 (Architecture / lgwks_gate_arch.py)` → `G3 (Framework-Reality)` before any LLM review.

### Gate 2: Sensor / Machine Learning (The Perceptual Layer)
When deterministic matching fails, the system escalates to local, narrow ML models to perceive the environment.
*   **Task Salience & Intent**: `ModernBERT-base-mlx-4bit` (Layer 2) and custom English intent classifiers (`lgwks_intent_classifier.py`).
*   **Semantic Embedded Space**: `Qwen3-VL-Embedding-8B` (Layer 5) providing a shared 4096-d space for Text, Image, and Video. (As noted in Issue #229, we are migrating `lgwks_codebase.py` to use this unified 4096-d semantic embedding rather than the legacy 256-d feature hash).
*   **Fraud Detection**: `had-fraud-engine-v1` (Layer 8) uses LightGBM/Z-Scores to detect slop and intent drift.

### Gate 3: Generative LLM (The Deep Brain)
Used *only* for proposing solutions or final reasoning overflows.
*   **The Stay Model**: `OLMo-2-0325-32B-Instruct-4bit` running locally via MLX.
*   **Code Proposal**: `Qwen3-Coder` (Transformers) for code explanation beyond static analysis.

## 3. The Ingestion Spine (Issues #228 - #231)
The ingestion layer is undergoing a massive upgrade to unify world-knowledge and tenant-knowledge.
*   **The Multi-Level Embedding (Issue #231)**: Ingestion is not just text. It requires L1 (Source), L2 (Logic), and L3 (Disassembly/Binary). This is why `Qwen3-VL` is excellent for text, but raw binary may require a specialized binary-foundation model in the future.
*   **Independent Unified Brain Index (Issue #230)**: `unified_agent_brain_multimodal.db` is owned by the ingestion pipeline in `/Users/srinji/ingestion_results`, not by LGWKS runtime code. `lgwks_vector.py` and `EmbedPort` must keep their own project/local store contracts; they must not route to the cron-owned unified index implicitly.
*   **Canonical Primitives**: Operations like hashing, clock time, JSONL emission, and vector math have been centralized into `lgwks_hashing.py`, `lgwks_clock.py`, `lgwks_substrate_io.py`, and `lgwks_vecmath.py`. (Completed in PR #225).

## 4. The Harness & Daemon Orchestration
The nervous system of the toolchain.
*   **Daemon (`lgwks_daemon.py`, `lgwks_daemon_store.py`)**: Recently hardened to "world-class" status (PR #227). Includes strict dead-lettering (`MAX_ATTEMPTS`), readiness probes, heartbeat staleness, and a durable `MAX_QUEUE_DEPTH` backpressure system to prevent 5xx crashes under load.
*   **CRDT State (`lgwks_crdt.py`)**: Uses G-Set for world-nodes and OR-Set for tenant-nodes, guaranteeing Strong Eventual Consistency (SEC) across concurrent processes without locks.
*   **Waste Ledger (`lgwks_waste.py`)**: The strict proof that the context-optimization actually works by tracking injected-but-unused item rates.

## 5. My Previous Misunderstanding (Why I Failed)
In my previous PR, I completely misunderstood the "Gate 1" concept and the "No External Dependencies" rule.
1.  **I hallucinated external dependencies**: I tried to wire `lgwks_search` and `lgwks_extract` to `ctx7`, `curl`, and forced LLM Vision (`Qwen3-VL`) to read simple DOM structures.
2.  **I ignored the native Rust crawler**: The repo *already* has a hyper-fast, deterministic Rust crawler built in (`crawler/` -> `crwl`). That **is** Gate 1 for web extraction. I should have wired the ingestion pipeline directly to this native tool instead of trying to reinvent the wheel with external API calls.
3.  **I bypassed the true architecture**: By jumping straight to Vision/Generative AI for tasks that the Symbolic/Deterministic layer (Rust crawler, ASTs, Axiom bytes) is perfectly capable of handling, I violated the fundamental law of the codebase.

## 6. Next Steps (Building, Not Refactoring)
Now that I understand the true shape of the repo—the reliance on the Rust `crwl`, the Axiom byte framework, the 15-model mesh running locally via MLX, and the independent unified-brain ingestion index—I will focus on **wiring LGWKS-owned components together** to close ingestion gaps without coupling LGWKS runtime storage to the cron-owned index.
