# HANDOFF — LogicalWorks Language workstream (read this first)

> **Last updated:** 2026-05-28. **Owner role:** Opus integrator/synthesizer.
> **This is the language workstream** (distinct from the top-level `vision/HANDOFF.md`, which is the
> world-map research *system*). Goal: design a new AI-native, general-purpose programming language.

---

## 0. What this is (identity — LOCKED)

A **real, standalone, general-purpose language** (Go/Swift/Rust class). The *only* justification for
our own: optimized for (a) how our app is AI-generated and (b) writing code for our ecosystem/OS
(Canvas). Built **for us AND to contribute to the world.** Security = **blast-radius-zero**, built in.
NOT a control-plane product, NOT a translation service, NOT a frontend DSL, NOT an exec substrate.
Full statement: `RECONCILE.md` §1. Canonical compressed design: memory `synetheier-language.md`.

---

## 1. Progress log (what exists, verified)

| Artifact | Path | State |
|---|---|---|
| Reconcile-first design doc | `vision/research/language/RECONCILE.md` | ✅ Complete §1–§7, §5 bound to real Canvas code |
| Spec ladder step 0 (Physics/Ontology) | `vision/research/language/spec/00-physics.md` | ✅ Complete |
| Spec ladder steps 1–6 | `vision/research/language/spec/01..06` | ⬜ Not started |
| Prior-art research fan-out | (subagents) | 🔴 BLOCKED — see §4 |

**Session timeline (2026-05-28):**
1. Read all of `~/Downloads/Claude Research/` (5 artifacts) + the two prior SCOPE.md research dirs.
2. Director decisions: identity = standalone language; deliverable = reconcile-first; grounding =
   bind to real code.
3. Wrote `RECONCILE.md` — artifact inventory + verdicts (§2), 9-row contradiction ledger (§3),
   unified design (§4), and dispatched **3 Explore agents** over `~/sales-landing-page @ 2e4d09d`
   to fill §5 with real `file:line` anchors. All 3 returned; §5 fully filled.
4. Director ask: surface concerning trends → §6 (report's P0 list + 5 NEW holes the code-read found).
5. Director reframed **security** → §4.5 keystone (blast-radius-zero via decomposition +
   ephemerality; IR/WASM = enforcement floor; "can't be hacked" → "blast-radius-zero + recoverable").
6. Director: build **bottom-up, creator-of-the-world, one step at a time** → defined the 7-rung
   ladder; wrote step 0 (`spec/00-physics.md`).
7. Director: explore topologies / synaptic binding / plasticity / temporal+parallel sync / concurrency
   / securitization+containerization, "look into existing frameworks," under the hard constraint
   below. Launched 2 of 4 research agents → **blocked** (no web access). Interrupted before C/D.

---

## 2. The design (pointers, don't relitigate without reason)

- **Two ideas:** (1) ONE substance = linear non-duplicable resource (capability=ownership=no-cloning,
  authority only shrinks); (2) ONE law = proof obligation (refinement types + SMT/Z3; "done"
  unreachable without discharged proof). `RECONCILE.md` §4.0, `spec/00-physics.md`.
- **Three layers:** language-semantics / AI-semantics (absorbs the control-plane YAML) / core-DB.
  `RECONCILE.md` §4.1–§4.3.
- **§4.5 security keystone:** decompose→no-amplify→ephemeral/reset-to-seed→traced; WASM floor.
- **Core thesis (proven by the Canvas code-read):** the substrate already reaches for every right
  shape but enforces at *runtime convention*; the language **lifts these to compile-time invariants**
  so the holes become unspellable. Anchors in `RECONCILE.md` §5.
- **The 7-rung spec ladder (bottom-up):** 0 Physics ✅ → 1 Alphabet (legal symbols/closed move-set;
  answers "which values are linear?") → 2 Morphology (bonds/attenuation/effect-inference) → 3 Syntax
  (content-addressed IR + Swift/Rust surface projection) → 4 Static semantics (linearity, refinement
  +SMT, proof discharge, capability-as-type) → 5 Dynamic semantics (run, reset-to-seed, effect/
  envelope model, concurrency) → 6 Pragmatics (lower to Rust→WASM, sandbox floor, AI-authoring layer).

---

## 3. Decisions: locked vs pending

**Locked:** identity (§0); the two ideas; lower-to-Rust→WASM day-1 + own typed IR day-2; security =
§4.5 model built in from line 1; the **hard constraint** (see §4); P0 holes are *proof targets*, not
this stream's work ("they're for me" — director).

**Pending (director steers):**
- Day-1 lowering form: emit Rust source-text vs proc-macro/library DSL.
- Is the typed IR literally Canvas's `#236` kernel-ABI / `MotionGraph` node-graph? (§5.2 leans yes.)
- Day-1 surface: web-only vs web+macOS.
- The **name** (still TBD; "Synetheier" was a typo).
- Spec entry point after step 1 (director chose bottom-up; worked-example-vs-spine deferred).
- The neural/connectionist question (§4): how much neural *structure* to adopt while keeping
  deterministic/decodable semantics.

---

## 4. 🔴 BLOCKER: prior-art research needs web access

The director's exploration ask (topologies, synaptic binding, backprop/plasticity, temporal+parallel
sync, math-driven dev, securitization/containerization, concurrency, "existing frameworks") was
split into a **4-cluster fan-out**:
- **A — Topology & synaptic binding** (mesh/fat-tree/small-world; binding-by-synchrony; interaction
  nets HVM/Bend; neuromorphic Loihi2/SpiNNaker2; GNNs). *Launched → blocked.*
- **B — Plasticity & math-driven dynamics** (backprop opacity critique; Hebbian/STDP/predictive-
  coding/Forward-Forward/EqProp; autodiff JAX/Dex/Enzyme; reversible computing Janus). *Launched → blocked.*
- **C — Temporal/parallel sync & concurrency** (synchronous reactive: Lustre/Esterel/Signal/SCADE;
  Lamport/vector clocks, CRDTs, deterministic parallelism; BSP; CSP/π-calculus). *NOT launched.*
- **D — Securitization, containerization & formal foundations** (WASM Component Model/WASI; microVMs
  Firecracker/gVisor; seL4; object-capabilities; Austral/Unison; verified compilation CompCert/
  CakeML; total/terminating langs for the decodability constraint). *NOT launched.*

**THE HARD CONSTRAINT (the lens for all 4):** machine-first, but **a human with NO AI must be able to
encode AND decode programs by hand, even if it needs enormous compute.** → core must be DETERMINISTIC,
fully formally specified, NO opaque/learned/black-box components.

**Why blocked:** every egress tool (`WebSearch`, `WebFetch`, firecrawl MCP, `Bash`→`ctx7`/`firecrawl`
CLI) is permission-denied in this environment. (The top-level `vision/HANDOFF.md` notes firecrawl was
unavailable in prior sessions too — recurring.) Agents correctly refused to fabricate citations.

**To unblock (pick one):** (1) grant ANY one egress tool (`WebSearch` is enough); OR (2) point agents
at LOCAL corpus — the vault already holds relevant research: `vision/notes/*.jsonl` (esp. `ai-layer`,
`stack`, `ecosystems-frameworks-sdks`), `vision/claims/*.json`, and artifacts
`wedge.language-kernel-substrate.md` (the OLD translation framing — rejected as identity but useful),
`Competing_OS_Framework_Map.md`, `canvas-architecture-recommendation.md`; OR (3) explicitly waive the
live-citation rule for a clearly-labeled training-memory synthesis (knowledge cutoff Jan 2026).

**Going-in hypothesis to test when unblocked:** borrow neural *structure & local dynamics* (topology,
synchrony-binding, explicit local update *formulae*) but keep *semantics* deterministic/formal/proof-
bound ("neuromorphic structure, formal semantics"). Sweet spots likely: **synchronous reactive langs
(Lustre/Esterel)** for math-driven+deterministic+temporal, **interaction combinators (HVM/Bend)** for
hand-traceable parallel reduction. Backprop/plasticity → opacity → fights the constraint + the
proof-law; adaptation, if any, must be explicit-formula, not hidden weights.

---

## 5. Next actions (ordered)
1. **Resolve §4 blocker** (director: grant web / use local corpus / waive). Then run clusters A–D and
   synthesize into `vision/research/language/EXPLORE-substrate.md`, each finding tagged with the spec
   layer it informs + compatibility verdict vs the hard constraint.
2. Fold A–D findings back to confirm/adjust the ladder, then **take step 1 (the Alphabet)** —
   enumerate the closed legal move-set (realizing `00-physics.md` §0.5) and answer Q0.1 (linear vs
   freely-copyable values).
3. Continue ladder steps 2→6, one at a time, each grounded in real frameworks + Canvas anchors.
4. Eventually: name the language; resume/retire the old `wedge.language-kernel-substrate` axes.

## 6. Director steering profile (from memory)
Postures over jargon. Be honest on conflict-layers (flag "finance-major-asserted" tensions with a
concrete alternative). Don't be path-dependent or "binny" (no over-binning / fixed-slot ceremony;
infer, surface only exceptions). Don't hardcode every path — define valence, let structures assemble.
Bottom-up, one step at a time. Accuracy over speed; no MVP shortcuts; production bar.
