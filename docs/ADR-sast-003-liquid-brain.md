---
type: ADR
title: ADR-sast-003: The Liquid Brain SAST — Biological Flow-Based Vulnerability Detection
description: Traditional SAST is a "Solid Brain" (centralized, rule-based, rigid).
tags: [adr]
timestamp: 2026-06-13T00:02:26-04:00
---

# ADR-sast-003: The Liquid Brain SAST — Biological Flow-Based Vulnerability Detection

**Status**: PROPOSED 2026-06-13
**Author**: Logic Architect
**Layer**: lgwks toolchain / audit-graph engine
**Provenance**: Relocated 2026-06-13 from `logic-os-kernel:laws/design/adr-082-liquid-brain-sast.md`. SAST is a lgwks concern and the kernel number 082 already names a governance ADR (egress-gate-interim-clip-budget); this is the lgwks-namespace home. Implemented by `lgwks_audit_graph.py`.

## 1. Context: The "Solid Brain" Deficit
Traditional SAST is a "Solid Brain" (centralized, rule-based, rigid). It fails because it tries to think like a human rather than flow like a system. Humans and AI both exhibit distinct "flow signatures" in code. Humans struggle with long-distance temporal coupling (e.g. `malloc` ... `free`); AI struggles with structural "hollowness" (high verbosity but zero centrality in the application's liquid memory).

## 2. Decision: Biological Flow-Based Detection (MATH-ML-LLM)
We will implement the "Liquid Brain" architecture, strictly separating deterministic gates from statistical intuition and blackbox reasoning.

### Tier 1: The Math Substrate (The Reflex / Liquid Memory)
*   **Mechanism:** `Z-eigenpair Centrality` over the `Semantic Code Graph`.
*   **Logic:** Inspired by *Physarum polycephalum* (Slime Mold). Code nodes are "tubules." Edges are "flow." If a node has high flow (centrality) but low weight (MDL conformance), it is a structural anomaly.
*   **Role:** The 0-trust gate. It owns the "Aversion Stimulus" (SSRF/SQLi blocks). If the math detects a tainted flow path, the system reacts with "Behavioral Aversion" (instantly denying execution).

### Tier 2: The ML Reflex (The Habituation / Anomaly Detection)
*   **Mechanism:** Statistical origin benchmarking (AI vs Human).
*   **Logic:** Habituation (learning to ignore noise).
    *   **AI Signature:** "High Sclerotium Density" — massive code blocks that contribute zero flow to the system graph. It looks like "dead weight" intended to distract or mask intent.
    *   **Human Signature:** "Synaptic Tagging Mismatch" — high local complexity (e.g. nested manual memory management) that fails to converge globally (e.g. missing `free` edge).
*   **Role:** Escalation engine. It flags nodes for the LLM that "look wrong" but didn't trigger a Tier 1 Aversion.

### Tier 3: The LLM Subconscious (The "Anti-Thinker" / Edge Case Reasoning)
*   **Mechanism:** High-level adversarial reasoning.
*   **Isolation (Day -1 Protocol):**
    1.  **Desensitization:** The LLM never sees raw code. It only sees the `CID-indexed Fact Log` and the `Abstract Topology`.
    2.  **Strict Gating:** LLM output is an "Intent Proposal," not a command.
    3.  **Injection Guard:** Prompt injection is neutralized because the LLM is "blind" to the system's actual execution handles.
*   **Role:** The final escalation. It only wakes up when Tier 1/2 are "Uncertain" (high Delta-discrepancy).

> **Implementation status (2026-06-13):** Tier 1 (Math Gate) and Tier 2 (ML Reflex) are wired in `lgwks_audit_graph.py`. Tier 3 escalation is a SEAM only — when requested it reports `summary.tier3_status="adapter_not_configured"` until a Host Adapter exists. It does not emit an analysis finding unless real analysis occurred.

## 3. Specific Implementation: wget and Auth Sinks
*   **wget/curl:** These are "External Slime Trails" (stigmergy). They must be strictly tagged as `UNTRUSTED` at the Math layer. Any data flowing back from a `wget` sink must be re-journaled into the **Causal Tape** with an `INBOUND_RISK` tag.
*   **Auths:** Auth gates are "Sodium Ion Channels." If a flow path exists from a public source to a sensitive sink without crossing a "High Potential" (Sodium/Auth) node, the "Liquid Brain" halts.

## 4. Consequences
*   **Agnosticism:** Because we treat code as biological flow (tubules and edges), the language doesn't matter. A Rust `Arc::clone` and a C `malloc` create the same "Reinforced Path" in the graph.
*   **Resilience:** Prompt injection in the LLM cannot bypass the Math Gate because the Math Gate doesn't even know the LLM exists—it only sees the resulting graph-state.
