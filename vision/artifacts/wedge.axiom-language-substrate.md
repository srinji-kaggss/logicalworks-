---
id: wedge.axiom-language-substrate
track: wedge
title: Axiom — Capability-Native Language as the Type-Lock over the Eleven Engines
model: claude
confidence: 0.78
provenance: elicited
grounding:
  - "/Users/srinji/sales-landing-page/CODEBOOK.md"
  - "/Users/srinji/sales-landing-page/LOGIC_OS_AI_FIRST_LANGUAGE_STATE_FABRIC_SECURITY_RESEARCH_BASELINE.md"
  - "/Users/srinji/sales-landing-page/kernel/crates/canvas-protocol/src/lib.rs (Capability enum :9-40)"
  - "/Users/srinji/sales-landing-page/kernel/crates/canvas-backend/src/effect_gate.rs (RiskThresholdGate :108-167)"
  - "/Users/srinji/sales-landing-page/kernel/crates/canvas-backend/src/policy/engine.rs (DefaultPolicyEngine stub :40-65)"
  - "/Users/srinji/sales-landing-page/kernel/crates/canvas-backend/src/boundary/mod.rs (CrossBoundaryCall :104-127)"
  - "/Users/srinji/sales-landing-page/laws/governance/adr-063-mathematical-bounding.md"
  - "/Users/srinji/sales-landing-page/laws/governance/adr-062-intent-outcome-gating.md"
  - "/Users/srinji/sales-landing-page/laws/governance/adr-067-logic-os-kernel-engine-map.md"
  - "/Users/srinji/sales-landing-page/blueprints/arch-320/ (language-kernel pack)"
  - "https://arxiv.org/abs/2509.12423 (Cohen et al., EMNLP 2025, decomposed intent extraction)"
  - "https://www.microsoft.com/en-us/research/project/aoc/ (Analog Optical Computer)"
  - "https://component-model.bytecodealliance.org/design/why-component-model.html"
  - "https://mlir.llvm.org/"
  - "https://www.unison-lang.org/docs/the-big-idea/"
grounding_tool: "crwl (crawl4ai) for external sources + Explore subagent backend map"
source_tiers: {primary: 7, secondary: 1, tertiary: 1}
adjudicated_by: logical-claude
convergence: stable
maps_to_vision: [gate, sovereignty, ml, scale, tape]
feeds: [decision, build]
expand_axes:
  - "axiom-core-ir-mlir-dialect-model"
  - "intent-lattice-many-valued-collapse-operator"
  - "content-addressed-capsule-airdrop-protocol"
  - "dumb-machine-verifier-decidability-proof"
  - "effect-class-shared-protocol-type"
---

## TL;DR

- **Axiom is not a greenfield language.** Logic OS already has the eleven engines (ADR-067); what is missing is the **type-lock that composes them.** Axiom v0 = the shared capability/effect/intent type system that wires them together.
- The backend's #1 defect, **ARCH-02 (stranded trust)**, *is* the language-shaped gap: `canvas_protocol::Capability` (lib.rs:9-40) is defined but `kernel/Cargo.toml` has zero dependency on it, so `DefaultPolicyEngine.evaluate()` (policy/engine.rs:40-65) string-checks identity and ignores `scope`/`rights`/`revocation_epoch`.
- Axiom's safety core is **decidable and dumb-machine-compilable**: verification = enum membership + capability-lattice ⊆-check + interval arithmetic. No theorem-proving in the hot path → the verifier runs on a phone or edge box. *That decidability is the democratization mechanism.*
- **ADR-063 already ships Axiom's thesis** in one domain: AI emits bounded parameters, Rust math clamps them. Axiom generalizes parameterization-over-codegen from motion to every effect class.
- Adopt an **MLIR-style multi-dialect Core IR** so one authored intent lowers to a CPU binary today, an **AOC** analog circuit tomorrow, or a quantum-inspired optimizer later — *the deterministic authority plane never changes, only the lowering target.*

## MAP

### What Axiom is, grounded in what is built
The accepted architecture (ADR-067) names eleven engines. The Explore backend map found they exist but are **uncomposed** — the capability type is stranded (ARCH-02), the policy engine is a stub (policy/engine.rs:40-65), the journal/replay engine is spec-only (arch-261), the cost arbiter is local-rate-limit-only (rate_limit.rs, L1-01). The mature one is the **effect gate**: `RiskThresholdGate` (effect_gate.rs:108-167), `Allow | RequireConfirm(token) | Block`, confirm≥5 / block≥8, ~40 tests. Trust is already a non-comparable lattice: `TrustBin` (canvas_model.rs:55-69), `CrossBoundaryCall<Caller,Callee>` fails closed when `caller_trust < required_caller_trust` (boundary/mod.rs:104-127).

**Axiom's job is to be the single typed unit — the Intent Capsule — that every one of those engines reads, so authority composes instead of leaking at the seams.** Capsule fields map 1:1 to engines: `authority`→#2/#3, `effects`→#4, `reads/writes`+tenant→#5, IPC envelope→#6, `budget`→#7, `evidence`→#8/#9, key ops→#10.

### Already-shipping proof: ADR-063
ADR-063 (mathematical bounding) is Axiom's core thesis live in production: AI agents emit *constrained parameters only* (e.g. `tension=170`), never executable logic; the Rust motion-core integrates (RK4) and **clamps** out-of-bounds values; Zod rejects NaN/negative. Axiom is the generalization: replace "motion parameters" with "any effect," replace "motion-core clamp" with "the effect/capability/outcome envelope `O ⊆ E = Compile(I,C,Policy)`."

### Intent capture, grounded in Cohen et al. (EMNLP 2025)
On-device small models beat a large MLLM when intent is **decomposed**: stage-1 produces a structured per-interaction summary with three fields — `screen_context`, `user_action`, and `speculative_intent` **which is discarded** before stage-2; stage-2 aggregates summaries into intent. Human-human intent agreement is only 76–80% — the empirical ceiling, and proof that intent is **irreducibly multi-valued**. This maps onto the fabric: stage-1 summaries are observations on the Causal Tape; the discard of `speculative_intent` is the observed-vs-speculative trust boundary; stage-2 populates the **Intent Lattice** (candidates + confidence + evidence-refs); the deterministic plane is the collapse to a bounded action bundle. Axiom must encode "infer only from observed summaries" as a *provenance constraint*, not a style note (the paper shows training otherwise teaches the model to embellish).

## SCALE & CONSTRAINTS

- **Decidability is the budget.** Keep the safety core to closed enums + ⊆-checks + interval bounds and a verifier fits in WASM on commodity/edge hardware. Admit Turing-complete elaboration *above* the gate (probabilistic plane) only.
- **No WASM target exists yet** (Rust edition 2021; `no_std`-capable crates not compiled to `wasm32`). The portable-component story is unbuilt — first real cost.
- **Substrate honesty (baseline §22.8):** quantum stays horizon-scan, not MVP (IBM hardware still cryo + capital-heavy). **AOC** (room-temp commodity optics, continuous+binary data, ~100× on inference/optimization) is the *democratizable* post-binary substrate — but it belongs behind the Black-Box Reduction Envelope as an accelerator, never the root of trust.
- The hard cap on confidence here: this is elicited synthesis over primary internal code + primary external standards; not yet validated by a built Axiom verifier.

## TOUCHES US

- **Aligns to the core app idea directly:** Logic OS = "intent-native, capability-constrained, binary-first work substrate." Axiom is the *expression layer* of that sentence — it makes "capability-constrained" a compile-time fact and "intent-native" a typed lattice.
- **Closes the FE-exposure risk** (CODEBOOK §4): business rules/permissions move from string checks into a typed capability the backend enforces — ARCH-02 closure is the first brick.
- **Makes the AI-coding doctrine enforceable:** the review object becomes a *capability/effect/data-flow/manifest diff* (baseline §19.3), not a text diff — the 9-gate verification suite (verification/mod.rs) is already eBPF-shaped to host it.
- **Gives white-label / arch-320 its enforcement spine:** the language-kernel pack's overlay-policy and provenance contracts become capsule-level invariants.
- **AirDrop-class fast context:** signed, content-addressed, capability-attenuated capsules over the existing mutual-auth IPC (sidecar/ipc.rs — shared-memory forbidden, schema-validated).

## BUILD-NOW

1. **Close ARCH-02 (keystone).** Add `canvas-protocol` as a `kernel/Cargo.toml` workspace dependency; replace the `DefaultPolicyEngine` string-check (policy/engine.rs:40-65) with `Capability` enum membership + `scope` + `revocation_epoch` evaluation. This is Axiom's literal first atom; decidable; issue-backed against `sales-landing-page`.
2. **Promote the effect-class enum** (baseline §9.1) into `canvas-protocol` as a shared type, bound to `RiskThresholdGate` — generalizes ADR-063 past motion.
3. **Type the Intent Lattice** as a `canvas-protocol` record (candidates[]: {intent, confidence, evidence_refs, model_manifest}) — encodes the Cohen schema; many-valued + paraconsistent by construction; deterministic collapse operator separate.
4. **Add `accelerator_target` + `determinism_class`** to the artifact manifest — the MLIR-dialect hook so admission applies the right envelope per substrate (binary deterministic vs analog/quantum stochastic).
5. **Write the ADR** "Axiom v0 — Language Constitution & Compiler Contract" (baseline §26.4) seeding grammar/effect-calculus/capability-model/IR/CLI, scoped as an arch-pack with the four above as its first units.

## SKEPTICISM

- **WASM Component Model + WASI** already deliver typed, capability-based, message-passing components — *better resourced than us.* Our delta is narrow but real: WASI caps are coarse (fs/socket); Axiom caps are domain-semantic + effect-classed + risk-tiered + **intent×outcome-gated** (ADR-062). If we cannot articulate that delta in shipping code, Axiom is reinvented WIT.
- **Unison** solves distribution via content-addressing and *eliminates builds* — we should borrow the hash-addressing for airdrop but we deliberately keep the signed-manifest admission verifier (Unison trusts the hash; we trust hash + signature + capability envelope). If we copy Unison wholesale we lose the authority story.
- **MLIR** is a decade-deep ecosystem; building our own dialect stack is expensive. The bet only pays if substrate-agnostic lowering (CPU→AOC→quantum) is a genuine product axis, not a slide.
- **Where we cannot afford to be wrong:** the decidability claim. If the safety core needs undecidable analysis to be sound, "dumb-machine compilable" collapses and the democratization thesis with it.
- **Genuinely novel vs all four:** none model the AI black box as a first-class *bounded advisor* with a reduction envelope. The probabilistic-above / deterministic-below split, made into language structure, is the contribution — or it is nothing.

## DIALECTIC

- **thesis:** Axiom should be specified as a new capability-native language with its own grammar and compiler.
- **antithesis:** the engines already exist; a new language is inflationary until the existing capability type is even wired into the kernel (ARCH-02). The gap is composition, not vocabulary.
- **synthesis:** ship Axiom as a *type-lock first* — the shared capability/effect/intent types that compose the built engines — and let grammar/IR/CLI accrete on top once the lock holds. The language is discovered from the backend, not imposed on it.
- **residual_disagreement:** whether the MLIR-style multi-dialect IR is worth its cost now, or only after one substrate beyond binary (AOC) is physically reachable.

## ML-FEED

```json
{
  "entities": [
    {"id": "ax-capsule", "type": "IntentCapsule"},
    {"id": "ax-capability", "type": "Capability"},
    {"id": "ax-effect-class", "type": "EffectClass"},
    {"id": "ax-intent-lattice", "type": "IntentLattice"},
    {"id": "ax-core-ir", "type": "CoreIR"},
    {"id": "ax-verifier", "type": "AdmissionVerifier"},
    {"id": "eng-effect-gate", "type": "RiskThresholdGate"},
    {"id": "eng-policy", "type": "DefaultPolicyEngine"}
  ],
  "relations": [
    ["ax-capsule", "declares", "ax-capability"],
    ["ax-capsule", "declares", "ax-effect-class"],
    ["ax-capability", "evaluated_by", "eng-policy"],
    ["ax-effect-class", "gated_by", "eng-effect-gate"],
    ["ax-intent-lattice", "collapses_to", "ax-capsule"],
    ["ax-capsule", "lowers_through", "ax-core-ir"],
    ["ax-core-ir", "admitted_by", "ax-verifier"]
  ],
  "metrics": [
    "stranded_capability_string_check_count",
    "capsule_effect_classes_unenforced_count",
    "verifier_decidable_pass_ratio",
    "intent_lattice_candidate_count",
    "accelerator_targets_supported"
  ]
}
```
