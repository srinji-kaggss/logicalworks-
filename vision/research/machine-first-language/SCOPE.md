# Research Scope - Machine-First OS Language

## Working thesis

The language is not primarily a nicer syntax for humans. It is a constrained operating substrate for AI-authored software: Go-like simplicity and deployment, Swift-like UI ergonomics and safety, Rust-grade systems integration, and TSX/Swift/Rust source generation as target surfaces.

The first deploy should behave like a frontend framework that can run above existing operating systems, including ChromeOS. The long-term target is an AI-native OS/world layer where agents author, inspect, verify, and revise code with less syntax debt, less hidden auth debt, and explicit entity relationship flows.

## MVP frame

- Ship as a frontend framework first: TSX/PWA + WASM-capable runtime, with a bridge path to SwiftUI and Rust.
- Keep source generation boring and reviewable: no JIT and no downloadable executable code for Apple targets.
- Put Rust at the kernel boundary: broker, capability/effect gate, canonical schema, crypto, tape, and high-risk analysis.
- Treat Swift and TSX as host render targets, not the semantic source of truth.
- Treat every UI action as an envelope moving through an entity graph, not as callback soup.

## Required feature set

- Vulnerability protection: capability-based effects, no ambient authority, typed auth/session/entity flows, ASVS/CWE/OWASP mappings, unsafe isolation.
- Speed: small grammar, AOT source generation, Rust core, zero-copy canonical wire where measured, incremental graph compilation.
- Neural networks: embeddings over nodes/edges/claims, blindspot scoring, active-learning feedback from human correction, retrieval-ranking improvement.
- Privacy: local-first memory, PII taint types, scoped credentials, encrypted append-only tape, data minimization by compiler rule.
- Machine-first: canonical AST/graph IR is the primary artifact; human syntax is a projection.

## Design constraints

1. Invalid programs should be unrepresentable by grammar/type/effect construction.
2. A generated program must declare entity relationships before implementation logic.
3. Every function-like unit needs a bounded branch/complexity budget.
4. Auth must be modeled as subject -> capability -> object -> action -> verdict, never as ad hoc middleware.
5. The frontend cannot reach backend state except through declared effects and broker envelopes.
6. Generated code must preserve a trace from user intent -> AST node -> target source lines -> test/proof/check.
7. AI feedback must be recorded as training signal, not just chat history.

## Near-term research tracks

### Track A - Frontend deploy surface

ChromeOS-compatible PWA/TSX host, WASM sandbox for untrusted widgets, source-generated TypeScript bindings, and a static visualization layer that reads graph JSON.

### Track B - Rust kernel integration

Rust broker/effect engine, canonical schema compiler, unsafe boundary audit, C ABI/Swift bridge, and WASM Component Model adapter.

### Track C - Swift target

SwiftUI source generation, result-builder compatible host components, strict concurrency alignment, and App Store-safe compilation pipeline.

### Track D - Machine-first IR

Content-addressed AST/graph IR, typed edge semantics, entity relationship declarations, and source projections to TSX/Swift/Rust.

### Track E - Debt prevention

Cyclomatic/cognitive complexity caps, comprehension-budget scoring, entity-flow coverage, auth-flow coverage, generated-test coverage, and schema-drift detection.

### Track F - Blindspot detector bot

A Python service that consumes graph artifacts, notes, claims, source files, tests, and user feedback. It emits blindspots, directives, and visualization-ready graph deltas.

