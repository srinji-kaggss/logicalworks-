# Research Scope — Machine-First Frontend Language (Project: "NodeUI" / codename TBD)

## Foundational thesis
Existing languages are designed for human input. AI code generation today produces "slop" because the target language (Swift, TS, Rust) was never constrained for machine authorship. We need a language that is a **framework for machines** — optimized for AI-to-AI transition, with bounded scope, visual constraints, and node-like structures that map directly to the Canvas substrate node-mesh architecture (#287).

## Primary constraints
1. **Machine-first, human-reviewable** — grammar and type system should make invalid/"sloppy" programs unrepresentable (parse, don't validate at the AI layer).
2. **Scope containment** — language-level mechanisms prevent frontend scope from racing backend (capabilities, effects, bounded contexts à la Canvas broker E2).
3. **Deep SwiftUI integration** — MVP targets Apple systems. Must compile to or deeply embed in SwiftUI, leveraging existing Apple frameworks rather than rewriting them.
4. **Node-like structures** — first-class support for actor/node/graph primitives that align with Canvas envelope routing, broker registry, and widget host patterns.
5. **Visual constraints** — layout and animation are constrained by construction, not freeform imperative code.
6. **AI learnable** — small, orthogonal feature set; minimal syntax; predictable semantics so other AIs can learn the framework and apply it correctly.

## Research tracks

### Track A — SwiftUI integration surface (MVP blocker)
- What is the actual boundary for generating SwiftUI views from another language in 2026?
- Can we emit Swift source? Use Swift Macros? Embed a WASM runtime? LLVM IR?
- What are the App Store / toolchain risks of a non-Swift frontend language?
- ctx7 targets: "SwiftUI", "Swift", "Swift Macro"

### Track B — Machine-first language design precedents
- Languages built for structured generation / constrained authoring: Darklang, Unison, Grain, Roc, Wuffs, F*, Formality
- Effect systems / capability languages: Eff, Koka, Austral, Verse
- Visual / node-textual hybrids: Luna, Lustre, Houdini VEX, Unreal Blueprints
- Search: "machine first programming language", "AI generated code constraints", "effect systems frontend"

### Track C — Node / actor / message-passing primitives
- How do Erlang, Elixir, Pony, Actors model map to a UI language?
- Canvas substrate uses envelope + broker + pattern-match routing. Can the language's execution model BE the broker model?
- Search: "actor model UI framework", "message passing UI language", "node graph programming language"

### Track D — Intermediate representation for machine transition
- Text vs binary AST vs content-addressed IR (Unison hashes, IPFS)
- Fleece, Cap'n Proto, FlatBuffers, WASM, SPIR-V, MLIR as machine-to-machine formats
- Which IR supports diff-friendly, merge-friendly, token-efficient transition?
- Search: "content addressed AST", "binary IR for code generation", "diff friendly intermediate representation"

### Track E — Scope containment mechanisms
- Language-level sandboxing / capability security: WASM capabilities, WebAssembly Component Model, Rust sandbox, Swift strict concurrency
- How to prevent a frontend widget from accessing backend seams (ADR-009 trust levels)?
- Search: "capability based programming language", "language level sandboxing", "effect tracking compiler"

### Track F — Visual constraint systems
- Constraint-based layout: Cassowary, Yoga, SwiftUI layout engine, Auto Layout DSLs
- Animation constraint systems: Reanimated, Motion, Lottie but declarative
- Search: "declarative layout constraint language", "visual constraint programming"

## Blindspots to close
1. **Apple lock-in risk** — If the language generates SwiftUI, Apple toolchain updates can break us. What is the historical stability of SwiftUI ABI?
2. **Compilation target ambiguity** — Do we compile to Swift, to LLVM IR, or run an interpreter on-device? Each has very different 2026 constraints.
3. **Node-graph ↔ text impedance mismatch** — Node graphs are great for machines (DAGs, visual programming) but SwiftUI is textual. How do we bridge without losing both?
4. **Base rate of new languages in 2026** — What is the survival rate of new frontend languages launched since 2020? (Reason, Elm, Grain, Roc, Gleam, etc.)
5. **AI slop reduction — unmeasured** — No existing study proves that a constrained language reduces AI-generated bugs. We must reason from first principles or find analogues.

## Output format
All findings must conform to LW-RS/1 (`~/logicalworks-/vision/LW-RS/1.md`).
- Lightweight notes: `~/logicalworks-/vision/notes/frontend-language.jsonl`
- Distinctive claims: `~/logicalworks-/vision/claims/frontend-language.json`
- Opus synthesis (if warranted): `~/logicalworks-/vision/artifacts/frontend-language.md`
- Blindspots: `~/logicalworks-/vision/notes/blindspots.jsonl` (append)

## Tooling
- Use `ctx7` for library docs: `npx ctx7@latest library <name> "<question>"` then `npx ctx7@latest docs <id> "<question>"`
- Use `firecrawl` CLI for web research (cheaper than MCP). Cache in `.firecrawl/`.
- Never use training memory as fact — every claim needs a source.
