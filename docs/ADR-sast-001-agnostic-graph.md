# ADR-sast-001: Semantic Code Graph (SCG) — Agnostic Vulnerability Substrate

**Status**: PROPOSED 2026-06-13
**Author**: Logic Architect
**Layer**: lgwks toolchain / SAST engine (daemon capability)
**Provenance**: Relocated 2026-06-13 from `logic-os-kernel:laws/design/adr-080-agnostic-graph-sast.md`. SAST is a lgwks concern and the kernel number 080 already names a governance ADR (attestation-engine-build-provenance); this is the lgwks-namespace home. Cross-repo contract refs (ADR-068/078) point at the kernel's State Fabric / routing ADRs.

## 1. Context and The Deficit of AST-Matching
The previous SAST implementation (`lgwks_bot_code_hacker.py`) relied on hardcoded AST (Abstract Syntax Tree) matching specific to Python. This approach suffered from several critical deficits:
1.  **Language Coupling:** Hardcoding `os.system` or `Path.read_text()` works for Python but provides zero protection for Rust, Go, or TypeScript targets.
2.  **Shallow Taint Tracking:** AST walkers struggle with cross-file (interprocedural) taint propagation, global state, and dynamic dispatch.
3.  **Human vs. AI Blindness:** AST matchers look for known bad functions, but they cannot detect *structural* anomalies—such as the statistical differences between poorly written AI boilerplate and human memory mismanagement.

To achieve a "Google/ctx7" scale moat, the daemon must do the heavy lifting. The SAST engine must become an emergent property of the existing multi-tenant data substrate.

## 2. Decision: Graph-Theoretic Vulnerability Analysis
We will deprecate the Python-specific AST walker and implement the **Semantic Code Graph (SCG)**.

The daemon will parse target codebases into the **exact same Entity Graph** format used for documents (`lgwks.engine.schema.v1`), utilizing `trailmark` as the underlying parser for 16+ languages.

### 2.1 The Universal Representation
Instead of querying strings, the daemon queries relations.
*   **Nodes:** Functions, Variables, API Endpoints, Memory Allocations.
*   **Edges (Relations):** `data_flows_to`, `controls_execution_of`, `allocates`, `frees`, `requires_auth`.

### 2.2 Agnostic Threat Detection via Graph Queries
Vulnerabilities become language-agnostic graph traversals:
*   **SSRF:** `Find Path(Source: User_Input) -[data_flows_to]-> (Node) -[calls]-> (Sink: Network_Egress)`
*   **SQLi:** `Find Path(Source: User_Input) -[data_flows_to]-> (Node) -[calls]-> (Sink: Database_Execute)`
*   **LFI / Path Traversal:** `Find Path(Source: User_Input) -[data_flows_to]-> (Node) -[calls]-> (Sink: File_System)`

Because the graph is stored in the Global Fact List (DB2) and Causal Tape (DB1), the daemon can run these traversals across entire microservice boundaries.

## 3. Detecting Human vs. AI Signatures (Statistical Benchmarking)
A world-class SAST must catch what regex cannot. By analyzing the structural topology of the SCG using our existing **Z-eigenpair centrality** math, we can statistically benchmark code quality and origin.

### 3.1 The "Shitty AI" Signature
AI models (especially smaller or unguided ones) exhibit distinct structural anomalies in code graphs:
*   **High Boilerplate, Low Centrality:** AI code often generates massive AST depth (verbose switch statements, repetitive error wrapping) that has exceptionally low centrality in the broader application graph.
*   **The "Just-in-case" Masking:** AI often hallucinates error handlers that swallow exceptions, creating graph nodes with high `in_degree` (caught errors) but zero `out_degree` (no telemetry or bubbling).
*   **Missing Context Boundaries:** AI often assumes authorization happened "elsewhere." The graph will show an `Execution_Path` to a privileged function that completely bypasses the `Auth_Gate` subgraph.

### 3.2 The Human Mistake Signature
Humans make mistakes that AI rarely makes due to context-window fading:
*   **Temporal Separation (Memory Management):** `malloc()` occurs on line 10, but the pointer is passed through 4 layers of indirection, and `free()` is missed. The graph shows an `allocates` edge without a corresponding `frees` path in the execution flow.
*   **Concurrency Deadlocks:** Two human-written threads acquire locks in different orders. The graph detects a cycle in the `acquires_lock` edges.

## 4. Implementation Plan
1.  **Daemon Integration:** Expose `trailmark.preanalysis()` as a daemon capability (`lgwks audit`).
2.  **Substrate Mapping:** Translate Trailmark's IR (Intermediate Representation) into the `lgwks_score` relational matrix.
3.  **Graph Queries:** Implement the vulnerability traversals (SSRF, LFI, SQLi) as subgraph queries (`engine.subgraph("tainted")`).
4.  **Anomaly Detection:** Feed the code graph into `lgwks_rank.py` to highlight nodes with statistically anomalous Z-centrality (flagging AI boilerplate vs. critical human choke points).

## 5. Consequences
*   **Moat:** The Daemon's graph becomes a proprietary vulnerability scanner that learns cross-language patterns.
*   **Performance:** Graph building is computationally heavy (Daemon lifting). We leverage the D4 Storage Gate to deduplicate AST chunking globally.
*   **Deprecation:** `lgwks_bot_code_hacker.py` will be sunset in favor of `lgwks_audit_graph.py`.
