---
type: ADR
title: ADR-sast-002: Zero-Trust Multi-Layer Execution Pipeline (Math-ML-LLM)
description: We are building a system where LLMs are part of the "Subconscious" (Layer 3), but they are fundamentally untrusted and prone to injection.
tags: [adr]
timestamp: 2026-06-12T23:10:49-04:00
---

# ADR-sast-002: Zero-Trust Multi-Layer Execution Pipeline (Math-ML-LLM)

**Status**: PROPOSED 2026-06-13
**Author**: Logic Architect
**Layer**: lgwks toolchain / execution sandbox
**Provenance**: Relocated 2026-06-13 from `logic-os-kernel:laws/design/adr-081-zero-trust-execution-pipeline.md`. SAST is a lgwks concern and the kernel number 081 already names a governance ADR (grant-axes-sync-scope); this is the lgwks-namespace home. Cross-repo contract refs (ADR-068/078) point at the kernel's State Fabric / routing ADRs.

## 1. Context: The "Anti-Thinker" Problem
We are building a system where LLMs are part of the "Subconscious" (Layer 3), but they are fundamentally untrusted and prone to injection. Traditional security assumes a single execution boundary. We must assume the LLM *will* be compromised by prompt injection or "weird" edge cases.

## 2. Decision: The Strict Layered Gate (DiD)
We will implement a 0-trust execution pipeline where each layer is strictly isolated from the next by a **unidirectional data flow**.

### Layer 1: The Math Gate (Deterministic / World Class)
*   **Role:** The absolute boundary. Owns all ACLs, File System I/O, Network Sinks, and Substrate Gates.
*   **Primitive:** Frozen Python/Rust stdlib only. No ML, no AI.
*   **Invariant:** If Layer 1 says "Deny", the request dies. Layer 3 (LLM) cannot see or influence Layer 1's decision logic.

### Layer 2: The ML Reflex (Statistical Anomaly Detection)
*   **Role:** Identifies patterns that look "wrong" based on global benchmarks.
*   **Primitive:** Z-eigenpair centrality (SCG), Cosine similarity, ε-DP patterns.
*   **Moat:** Detects "Shitty AI" code signatures (low-centrality boilerplate) and "Human Mistake" signatures (resource leaks like malloc/free mismatch) by statistical divergence.

### Layer 3: The LLM Subconscious (Edge Case Reasoning)
*   **Role:** The "Anti-Thinker." Reserved for high-level edge cases and red-teaming.
*   **Isolation:** The LLM never sees raw system primitives. It only sees the **Semantic Code Graph (SCG)** or **Fact Log** emitted by Layer 2.
*   **Injection Guard:** The LLM's output is NEVER executed. It is only parsed for *intents*, which are then re-validated by Layer 1.

## 3. Specific Hardening: wget and Auth Sinks
*   **wget/curl/Network:** Hardened via Layer 1 active DNS resolution and per-request routing validation (ADR-068/078).
*   **Auth Gates:** Hardened via SCG Taint Analysis. If the graph shows a path from a Public Endpoint to a Secret Sink that doesn't cross an `Auth_Gate` node, it's flagged as a critical flaw.

## 4. Proprietary SAST: Statistical Origin Benchmarking
We will benchmark code origin based on graph topology:
*   **AI Origin:** High node count, deep AST depth, but "Hollow" centrality (meaning the code is verbose but doesn't actually bind into the system state).
*   **Human Origin:** High "Local Cluster" complexity (e.g. manual memory management patterns like `malloc` without `free`) and non-standard logic branches that AI avoids for "safer" common paths.

## 5. Implementation Roadmap
1.  **Harden `lgwks_engine.py`**: Inject a "Layer 1" gate that sanitizes all prompts before they even reach the lexical/embedding stage.
2.  **Integrate SCG Taint**: Use `trailmark` to detect "Auth-Bypass" paths in the code graph.
3.  **Deploy Anomaly Scorer**: Use `lgwks_rank` to flag nodes with anomalous Z-centrality as "Boilerplate Risk."
