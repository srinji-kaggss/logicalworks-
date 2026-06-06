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
`proves cap:` = the **declared** capability (author layer); the gate refuses a capsule whose needed caps
aren't carried up its `on[]` lineage — **least-privilege as a graph property.** At L0, effects hit the system
**only through WASI handles** (grounded: WASI = capability-based, no ambient authority); the clicked capsule's
`cap:` lower to WASI imports. Can't *claim* a cap the base lacked; can't *exercise* one WASI didn't grant.

**§5.1 · The grant root (resolves AUDIT F-03 — Director 2026-06-06: signed genesis).** Capabilities are NOT
free attacker-writable fields. A capability exists only if it descends from a **cryptographically-signed
genesis capsule**:
- **Genesis** — a signed capsule whose signature verifies against a trusted key; it is the ONLY origin of
  authority. `grants` on a non-genesis capsule are valid only if `grants ⊆ needs` (you may re-grant only what
  you legitimately hold and the lineage carried to you).
- The `by:"ai+human:<cap>"` **string self-grant path is REMOVED** — a string prefix is not authority.
  Authority is a verified signature, never a substring (T0: trust is cryptographic, not stringly).
- v0 stdlib stand-in: keyed **HMAC** attestation (matches constitution L5 `tag=HMAC_key(...)`); production
  upgrade = ed25519 asymmetric signatures. The CONTRACT (grants trace to a verified genesis) is unchanged.
- Holes carry `grants = ∅` and contribute nothing to the lineage union (resolves AUDIT F-02).

## §5.2 · CID integrity (resolves AUDIT F-01/F-05/F-09)
The CID is verified, not trusted: every store and every base read MUST assert `capsule.cid() == key` and
reject mismatch (no decorative content-addressing). Encoding is a **strict canonical codec** (canonical
CBOR/JCS): one number type, ±0 normalized, NaN/±Inf rejected, fixed float serialization — hash over canonical
*bytes*, never a language-native JSON round-trip. Digest = **BLAKE3-256** (no 128-bit). These are build
mandates for the `axiom/` package, not options.

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

## §14 · The git/Google-Drive model — immutable DAG + checkout refs (resolves AUDIT F-04/F-06; Director 2026-06-06)
Nodes are **immutable + content-addressed, NEVER deleted.** This is git semantics on the Merkle-DAG
(translation-chain §4.5: "git IS the Merkle-DAG core"), and it dissolves the cascade-vs-quarantine fork:
- **Immutable objects:** a capsule, once stored under its CID, is permanent. There is no `del` (kills AUDIT
  F-06 structurally). "Change" = append a new version (new CID via `sup`); the old CID still exists forever.
- **Checkout refs (the working set):** each actor (human or AI) has a **checkout** = the files/nodes they
  are working on (the bounded live set). A "revert" is **moving your checkout ref to an earlier snapshot** —
  it never destroys anything; divergent work persists by CID, just off your current ref.
- **Dependents pin to a specific base CID** (immutable) → **nothing is ever stranded** (the old base always
  resolves by hash). A child built on `K` stays valid even after `K` is superseded, because `K` is permanent.
- **Clean traceback + snapshot diff:** the hash-chained log + the DAG let you bisect to *exactly where it
  diverged* and **diff any two snapshots** — e.g., between two Director prompts. The history IS the diagnostic.
- **Monotonic time (kills AUDIT F-04):** commit/order uses a **monotonic logical clock** (log length / a
  high-water mark the core refuses to go below), never a caller-supplied wall-clock; reject `window ≤ 0`.
  COMMITTED is monotone — you cannot rewind to un-commit.
PENDING (on your checkout, freely abandonable) → COMMITTED (in shared history, change only by `sup`) →
superseded (new version appended; old persists). //why git-model: an immutable content-addressed DAG makes
"never strand, never lose, always trace" a property of the data structure, not a policy bolted on revert.

## §15 · The weight/gauge math (Director: "nodes become mathematical weights of health")
A node is a **capsule that carries a weight** — two complementary layers: **validity** (discrete, the click,
§4) and **health** (continuous, this section). Every node `n` carries a measured **weight vector**
`w(n) ∈ ℝ^d` = `[test_health, debt, slop_risk, coverage, intent_align, coupling, …]`, each dimension a pure
function of observed facts (test exit codes, complexity, click-log, divergence gauge) — strict math, 0-AI.

**Physics frame:** the codebase is an energy landscape; energy = badness (debt + slop + missing coverage +
misalignment); **health = low energy.** A **gauge** is a parameterized projection of that field:
`γ(field; criterion c, scope S, end_user u) → (value, trajectory, next_step)` where
- `value = Σ_{n∈S} αc · w(n)` — `αc` = criterion weighting over dimensions, **end-user-dependent** (designer
  vs AI weight differently → different gauges over ONE field; this is the human-layer ⟷ AI-layer).
- `trajectory = dV/dt` over the time-machine log — the field's evolution along commit history (computed, not drawn).
- `next_step = argmax_n` (n's contribution to the worst criterion gap) — deterministic sensitivity = gradient
  descent on badness-energy = the unique actionable next step. 0-AI (argmax over measured weights).
Equilibrium = local minimum; an edit that raises energy = "that was wrong" → time-machine roll-back.
Edits (human or AI) = operators on the field; the click gates *validity*, the weight-update measures *health*.
**Human⟷AI comms-diagnostic:** divergence between the human-gauge trajectory and AI-gauge trajectory over
the same field = where the two minds disagree on health/direction = where comms broke (JEPA framing, literal).

**Honesty constraint:** the 0-AI claim holds only for fact-derived dimensions (tests, complexity, coverage);
judgment-derived dimensions (slop_risk, intent_align) MUST be flagged as such in `w(n)` or the gradient is
theater over a guess. OPEN: `αc` **declared** (designer sets weights; pure 0-AI, static) vs **learned** (fit
from time-machine reverts via frozen Tier-E evaluator; adaptive but reintroduces a model). Instinct: declared
first; learned as opt-in that only *proposes* a criterion the human ratifies, so the 0-AI floor never depends on it.

## Hardening status (see AUDIT-axiom-byte-framework-adversarial.md — pen-test FAIL at first-pass)
RESOLVED this session: **F-01/F-05/F-09** → §5.2 (verify CID on read, strict canonical codec, BLAKE3-256);
**F-02** → §5.1 (hole `grants=∅`, no lineage contribution); **F-03** → §5.1 (signed genesis grant root, kill
self-grant); **F-04/F-06** → §14 (immutable git-model DAG, monotonic clock, reject `window≤0`, never delete);
**`cap:node-at-runtime` granter** → §5.1 (it is just another cap that must descend from genesis). F-07 (reorder
supersede) + F-08 (gauge rank by weight) are build mandates. F-10: stop asserting unimplemented invariants.
These are MANDATES for the `axiom/` build, enforced by negative tests mirroring the audit's exploits.

## OPEN forks (still for the Director)
- **The primitive itself** (Director: "idk if node is correct"): node-first vs relation-first vs cell/triple;
  how to stay granular and avoid binning. The verifier is agnostic, but the authoring model depends on this.
- **Gauge budget**: confirm ≤5 *live gauges* (not nodes) as the cognitive limit; the 50-node figure is dead.
- **Syntax flavor**: text projection defaulted to S-expr/WAT-like (homogeneous, no whitespace-significance).
