# SPEC — Axiom v0: the machine-first ISA (node model · decidable verifier · MLIR lowering)

Status: PROPOSED (2026-06-06; next reader is an AI). The unified language spec the corpus lacked — collapses
four overlapping vocabularies (compiler Node/Path · z-depth · engine model · translation-chain) onto ONE
spine. Realizes the node model (this session) and the Axiom thesis (`wedge.axiom-language-substrate`).
**Scope: lgwks-independent.** Kernel ADR-063 (mathematical bounding) / ADR-067 (engine map) are
*eventual-alignment precedent*, never dependencies — Axiom here is the type-lock over **lgwks's own**
engines (SPEC-lgwks-engine-v0). Supersedes the "copy WASM/JVM" framing of STUDY-isa-wasm-jvm; that study is
now the *grounding*, this is the design.

## §0 · Thesis (what makes it next-gen — NOT appeasement)
Every existing framework assumes an **accountable human author**; trust = "a person signed off." Axiom
inverts the author: the author (human or AI) is **untrusted**, and validity lives **in the artifact** (the
click), not the signoff. lgwks is a coding tool — it does not reassure anyone; **it makes sense** (coheres)
or it halts. The objective is measurable: **reduce bad code · AI slop · technical debt.** Users of the
future = **designers + AI, not coders.** Now: serves only our fleet; architected for a global future.

## §1 · Layering (vertical: surface→metal; horizontal: the frame tree)
```
L5 Intent surface   designer/AI emits intent (CLI)          = noise (nothing real yet)
L4 Noding           intent → candidate capsules; bias subtracted; 3–5 + base-first enforced
L3 Capsule (ISA)    the noded node: content-addressed, capability+provenance+L typed   ← the instruction
L2 Gate (verifier)  the CLICK — DECIDABLE: enum∈ + capability-lattice⊆ + interval bounds; 0-AI; edge-runnable
L1 Fabric           content-addressed hash-chained store + the time-machine (sup ledger)
L0 Lowering         MLIR multi-dialect → WASM (off-ramp) / AOC / … ; effects via WASI handles; AI-free
```
Keystone (from WASM/JVM): the L3 artifact carries enough to prove itself at L2 **before** L0. Untrusted
producer → verifying consumer, as physics.

**Horizontal — gauges, NOT node-bins (corrected 2026-06-06).** Capsules are **separate, granular, and
unbounded** — they are NOT packed into ≤5 frames (that was the binny error; no AUTOLAYER node-spilling).
The 3–5 cognitive limit lives on **GAUGES**: a gauge is a *strictly statistical/physics/math* pure fold
over the fabric, **parameterized by the end user**, whose output is a **unique, actionable next step**
(not decoration) — 0-AI, same family as the radar fold (INV-7). At any moment a mind (human or AI) holds
**≤5 live gauges** = ≤5 simultaneous ways-of-seeing the same granular capsule set. "I can think in
different ways, as can you" → gauges are those ways; human and AI may pick different gauges over one fabric.

**Naming caveat:** "node"/"capsule" is a *provisional* name for the L3 primitive, and whether the primitive
is node-first or relation-first is OPEN (see OPEN forks). The verifier (§4) is name- and shape-agnostic: it
checks a typed content-addressed record against its dependency edges, whatever we call it.

## §2 · The atom = the Intent Capsule (one shape, two inhabitants)
One content-addressed typed record (ADR-004 atom, grounded as the wedge's Intent Capsule). Fields map 1:1
to lgwks engines (authority→grounding/effect gates · effects→#4 · evidence→#8/#9 · budget→#7):
- **Claim** (asserts): `kind` (closed vocab), `on[]` (base CIDs — base-first edges), `by` (human |
  ai+human:cap), `claim`, `proves` (the click contract: type ∧ capability ∧ test), `l` (invented ratio),
  `cid` (BLAKE3 over canonical bytes = identity).
- **Hole** (abstains): same envelope, asserts nothing executable; `context`, `nearest`, `why`; appends to
  the **gap ledger**. //why one shape: the verifier/fold/CID logic must not branch on "is this a gap."

## §3 · The op set (M2M- and AI-optimized; small, closed)
Opcodes are **content-addressed capsule operations**, not human syntax. Optimized two ways: **M2M** =
capsules transfer as canonical TLV bytes (translation-chain §3.1), deduped by CID, capability-attenuated
("AirDrop-class" signed context); **AI layer** = the AI fills **typed parameter slots** in a capsule
(ADR-063 parameterization-over-codegen) — never free logic, always token-frugal typed slots.
- `node` — collapse noise→node, attach (core instruction)
- `hole` — abstain; typed gap → ledger (= an OPEN ticket, §9)
- `sup`  — supersede; the time-machine revert/replace (append-only, never delete)
- `frame`/`world` — the layer unit (≤5) and the project-world module (= ADR-005 comms scope)
Text projection (debug/designer only, tertiary) defaults to S-expr/WAT-like; canonical bytes are identical
underneath regardless of projection.

## §4 · The verifier (the click) — decidable, 0-AI, edge-runnable
A capsule clicks **iff**: (1) every `on[]` base CID is already noded (base-first; rejects dangling/forward
= WASM structured-CFG discipline); (2) `proves` holds: `kind ∈ closed-vocab` ∧ `capability ⊆` the lattice
carried up `on[]` ∧ `params ∈ [min..max]` intervals ∧ declared test/proof passes. **No theorem-proving in
the hot path** → the verifier is a dumb machine that fits in WASM on a phone. *That decidability is the
democratization + the 0-AI guarantee:* validity = the click, never the oracle (INV: oracle-agnostic).

## §5 · Capability + WASI (two walls, one capability)
`by …:cap` + `proves cap:` = the **declared** capability (author layer); the gate refuses a capsule whose
needed caps aren't carried up its `on[]` lineage — **least-privilege as a graph property.** At L0, effects
hit the system **only through WASI handles** (grounded: WASI = capability-based, no ambient authority); the
clicked capsule's `cap:` lower to WASI imports. Can't *claim* a cap the base lacked; can't *exercise* one
WASI didn't grant.

## §6 · Lowering = MLIR multi-dialect (the authority plane never changes, only the target)
One authored capsule lowers via an **MLIR-style multi-dialect Core IR**: → WASM (binary, today; **UNBUILT —
first real cost**, no wasm32 target exists yet) / → AOC analog (post-binary accelerator, behind the
black-box-reduction envelope, never root of trust) / → future targets. Erasure boundary: proof/provenance/L
dropped at lowering (forgetful functor), mechanism kept; radar reads above the line, metal runs below.

## §7 · Intent is a LATTICE, not 100 (hard ceiling 76–80%)
Grounded (Cohen et al., EMNLP 2025): human-human intent agreement is only 76–80% — intent is **irreducibly
multi-valued**, so "=100" is provably unreachable. Axiom encodes intent as a **lattice**: `candidates[] =
{intent, confidence, evidence_refs}` (many-valued, paraconsistent) + a **deterministic collapse operator**
to a bounded action bundle. Provenance constraint: infer only from **observed** summaries, never speculative
(the discard boundary). The honest target is not 100 — it is: capture the lattice · collapse deterministically
· **make divergence visible and shrinking** (the comms-diagnostic, §8). Silently claiming 100 = the blackbox
returned (INV-8).

## §8 · Happy path = AI · sad path = human, enforced by math (never AI judgment)
The AI works the **happy path** it's good at: propose bounded params/nodings. The deterministic gate
**auto-routes every outcome** — `Allow | RequireConfirm(token) | Block` (grounded: lgwks effect-gate /
ADR-063 clamp). Any deviation (out-of-interval param, failed click, boundary breach, divergence spike) is
caught by **math + contract + code** and escalated to the human (PAN PAN = fork in intent / unverifiable
contract; MAYDAY = trust-boundary breach / irreversible). //why: the AI **never reasons about sad paths and
never decides to defer** — the framework forces the halt. This frees the AI to be creative on the happy
path and removes appeasement (deferral is physics, not judgment). The human's job is the deviation/debug.

## §9 · Self-documentation, 0-AI (docs = tickets = audit = the emission)
Each CLI function has a **schema contract** (input/output). On function-end it emits a **content-addressed
JSON extract** = the doc + the ticket (CID = ticket id; `by` = owner; status = clicked/hole/superseded;
why = `on[]` lineage). **Holes = OPEN tickets** (work to do); **clicked emissions = CLOSED tickets + docs.**
Documentation is a **deterministic fold over capsule emissions** — same family as the radar fold (INV-7).
The schema contract is the one-time effort; docs/tickets/audit are the free byproduct. No AI writes docs.

## §10 · Dynamic features — gated through the same membrane
No un-clicked code runs, ever, even dynamically. Runtime code generation = a **runtime noding** that passes
the identical gate (§4) before it attaches and runs. It requires an explicit, granted, audited
`cap:node-at-runtime` (most capsules never hold it). //why: closes the hole JVM reflection/classloading
leaves open (running author-unverified code). **This cap is the system's one self-referential power and
needs the tightest boundary — see OPEN.**

## §11 · Boundaries (each is a gate; crossing requires a proof)
world (project; comms+fabric scope; close project→close world) · frame (≤5; cross = typed interface node) ·
noding/membrane (noise↔noded; only human/AI-with-human crosses) · capability (WASI + `proves cap:`; least-priv
up `on[]`) · erasure (proof dropped at L0 lowering).

## §12 · Acceptance invariants
1. **0-AI-utility**: strip AI → humans node, the click validates, the fabric replays, WASM runs. AI = proposal throughput only.
2. **Decidable click**: verification = enum∈ + lattice⊆ + intervals; no theorem-proving; edge-runnable.
3. **Base-first**: no capsule attaches above an un-noded base; verifier rejects dangling.
4. **3–5 gauges (not node-bins)**: capsules are separate/granular/unbounded; the ≤5 limit is on live gauges
   (strict-math folds → actionable next-step, end-user-parameterized, 0-AI). No node-frame spilling.
5. **Capability up the DAG**: a capsule can't claim/exercise authority its `on[]` didn't carry.
6. **Intent-lattice honesty**: intent stored multi-valued; collapse deterministic; divergence visible, never silently 100.
7. **Sad path by math**: deviation halts + escalates via gate, never AI judgment; AI never authors sad-path logic.
8. **Docs = fold**: documentation/tickets are a deterministic fold over schema-contracted emissions; 0 AI.
9. **Time-machine**: append-only; revert = `sup`, never delete.
10. **Channel-independence**: radar/divergence computed from harness emissions, never AI narration.

## §13 · Build sequence (decidable-first; WASM is the first real cost)
1. Capsule encoder/decoder over canonical TLV bytes (CID = identity).
2. **The decidable verifier (§4)** — the click as enum∈+⊆+interval; 0-AI; the keystone (proves §0 end-to-end).
3. Fabric: content-addressed append + `sup` time-machine + replay.
4. Frame + AUTOLAYER min-cut spill (the 3–5 law).
5. Self-doc fold (§9) — emissions → tickets/docs.
6. **WASM lowering target (UNBUILT, first real cost)** → then frontend "NodeUI" on the custom OS backend.

## §14 · Pending→committed transaction (the time-machine, refined 2026-06-06)
AI changes land **PENDING** (rejectable). A **commit window** elapses → **COMMITTED**: the human "cannot
just reject" anymore. Post-commit change is **additive** — draw new relations / `sup`, never a bare reject
(append-only). So three states: PENDING (revert freely) → COMMITTED (restructure via new relations) →
superseded (`sup`). //why a window: autonomy needs the change to *stick* without per-node human touch, while
the window preserves cheap correction; after it, the comms-diagnostic (not a reject button) is the feedback.

## OPEN forks (for the Director / Codex hardening pass)
- **The primitive itself** (Director: "idk if node is correct"): node-first vs relation-first vs cell/triple;
  how to stay granular and avoid binning. The verifier is agnostic, but the authoring model depends on this.
- **Time-machine revert of committed nodes**: cascade (orphan superstructure → noise) vs quarantine (freeze
  dependents as stranded). Cascade depth = comms-failure severity. (Pre-commit revert is free, §14.)
- **`cap:node-at-runtime`** (§10): what GRANTS it, what AUDITS each runtime-noding. The soundness frontier.
- **Gauge budget**: confirm ≤5 *live gauges* (not nodes) as the cognitive limit; the 50-node figure is dead.
- **Commit-window length** (§14): fixed time, or activity-based (N dependent nodes attached on top = committed)?
- **Syntax flavor**: text projection defaulted to S-expr/WAT-like (homogeneous, no whitespace-significance).
