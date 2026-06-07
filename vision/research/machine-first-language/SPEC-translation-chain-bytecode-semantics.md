# SPEC — Translation-Chain Bytecode Semantics (lgwks language layer)

**Status:** PROPOSED (draft for lgwks ADR-004) · 2026-06-06 · machine-first artifact (next reader is an AI)
**Scope:** lgwks is the **forge/infrastructure**; this is its *semantic* layer for authoring highway terms.
It **adopts** OS contracts (ADR-068 content-addressed fact-log, ADR-073 capability vocabulary, ADR-069
WASM off-ramp) and **borrows** all byte-*encoding* tactics. We own the model; we borrow the engine.

## §0 The frame — we replace the front end, type the IR, borrow the back end
The bytecode canon (LuaJIT, Ball's Monkey, bernstein, CPython) is one pipeline:
`source → lex → parse → AST → bytecode → VM`. Ours is that pipeline, front-end replaced + IR typed:
```
CANON:  source ─lex─ parse ─→ AST ──compile──→ bytecode ──→ VM ──→ output
OURS:   human-ease → intent+desire → (subtract bias) → AI-goal → PROOF-CARRYING TERM → WASM/engines
        └────── the meaning compiler (OURS) ──────┘          └ typed IR (OURS) ┘  └ borrowed ┘
```
Front end (intent-extraction + bias subtraction) = ours. IR (capability+provenance+L typed) = ours/moat.
Back end (encoding + VM) = borrowed wholesale. The canon carries no provenance/capability/L — that gap is the product.

## §1 Decision — semantics-first, encoding-borrowed
The load-bearing, ownable thing is **meaning**: the translation chain + the proof-carrying term.
Byte encoding (stack-vs-register, dispatch, instruction layout) is the *engine* — borrowed from the
canon (Nystrom *Crafting Interpreters*; *Implementation of Lua 5.0* = register VM; JVM spec; CPython
`ceval`; Forth/Smalltalk threaded code). None of the canon carries provenance/capability/L; that is ours.

## §2 The translation chain — the semantic spine
A pipeline of typed meaning-transforms from human to AI. **Bias is a first-class node**, not silent noise:
it is extracted, represented, and *subtracted at the grounding boundary with the subtraction logged*.

| Node | What it is | Representation | L / bias / provenance |
|---|---|---|---|
| **H0 Human Ease** | zero-discipline emission (ramble, draw.io box, "make it work") | `Utterance{raw, content_hash, actor:human}` (SAID, ADR-001) | origin_type:grounded; max human compression |
| **H1 Intent + Desire** | intent = directional goal (checkable); desire = taste/values (NOT fully mathematizable, ADR-069 D6) | `Intent{objective,constraints min..max}` + `Desire{prefs,taste_vec}` (MEANT) | desire travels as preference signal, never laundered into fact |
| **H2 Human Bias** | unexamined assumptions inside H1: lazy bins, anthropocentric framing, sycophancy pressure, desire-as-fact | `Bias{kind,evidence,content_hash}` annotation on intent | the node the binning gate + anti-sycophancy gate inspect; said↔meant divergence is a bias signal |
| **— COMPILE BOUNDARY —** | grounding: subtract bias, keep grounded intent (the tollbooth) | logged transform: removed bin B (condition P, human-ratified) | **L spikes here** = invented-to-fill-gap ÷ grounded |
| **A0 AI Goal** | bias-subtracted typed objective the AI commits to (the Claim root) | `Goal{objective,basis[],subtracted_bias[],l_score,content_hash}` | proof-carrying term root; full provenance → H0 |
| **A1 AI Intent** | AI's own plan/decomposition into core verbs; the AI has its OWN bias (L_rep, sycophancy) → re-gated | term graph `Step{verb_composition,basis,l_contribution}` | validate vs closed vocabulary (ADR-073); unforeseen → typed hole (Hazel) |
| **A2 AI Ease** | execute at max R (reasoning ratio): context loaded, not re-derived | the loaded continuation packet / bytecode | **the telos** — the whole chain exists to deliver A2 a clean grounded term |

**Duality (backward = projection out):** when the AI emits to the human, the chain runs in reverse —
A2→A1→A0→[re-inject human frame for *legibility*, not contamination]→H1→H0 (the compressed receipt).
Forward = comprehension (compile human→AI, **strip** bias). Backward = explanation (project AI→human,
**re-add** frame). Same chain, opposite functor. Compression-for-humans happens only on the backward pass.

## §3 The term (the highway)
Content-addressed, **capability + provenance + L typed** term graph = Proof-Carrying Code (Necula) +
Typed Assembly (Morrisett) + content-addressed AST (Unison). Lowers two ways from one source:
- **off-ramp → WASM** (country road; ADR-069): forgetful-functor erasure — drop the proof, keep mechanism.
- **on-ramp → engine envelopes**: the term *is* the typed input each of ADR-067's 11 engines gates on
  (capability #2, authority #3, tenant #5, effect #4, journal #8, audit #9), as one linear lineage.

## §3.1 Encoding — borrowed, grounded 2026-06-06 (LuaJIT · bernstein · protobuf · bits/bytes · SO)
The reading-list canon proves the engine layer is mature → **borrow, don't build**:
- **Wire envelope = protobuf-style TLV + base-128 varint — borrow the SHAPE, NOT the canonicality.**
  `tag=(field<<3)|wire_type`; old readers **skip unknown fields** → forward-compatible (the unforeseen,
  §4, becomes a *wire-level preserved unknown field*, not a parse crash — typed-Hole and protobuf
  forward-compat are the SAME idea, two layers). **CAVEAT (machine-correctness):** protobuf serialization
  is NOT canonical by default (field/map ordering, unknown-field placement vary → same logical message,
  different bytes → broken CID, violates INV-1). We borrow TLV/varint/unknown-field-skip and **impose our
  own deterministic canonical ordering** (JCS/canonical-CBOR shape) before hashing. Borrow the idea; own the determinism.
- **Content-hash over canonical BYTES, never a string round-trip** (not all bytes are valid UTF-8 →
  byte→string→byte is lossy → a corrupted round-trip = a broken CID). Aligns ADR-068 BLAKE3.
- **Execution off-ramp = WASM / LuaJIT-class** (interpreter-in-asm + trace-JIT + SSA; DynASM). The fast
  path is solved; deferred, not on the critical path. Construction recipe = bernstein/CPython stack ISA.
- We own ONLY the *meaning in the fields*: capability + provenance + L. The canon gives speed,
  extensibility, and the metal; none of it gives capability/provenance/L typing — that is the whole moat.

## §4 The unforeseen (CLI: syntax/potholes we didn't think of)
**Soundness via closure; growth via typed holes.** Closed vocabulary (ADR-073 pen) = sound, can't run
the unknown. The unknown is never rejected or guessed — it is **captured as a typed, content-addressed
hole** `Hole(content_hash,context,nearest_known,why_unmatched)` (Hazel typed holes; gradual-typing `?`):
data not instruction (ADR-065), cannot widen its own scope. Discriminator gate proposes nearest-bin +
split condition → human ceremony decomposes to cores (L=0) or mints a new term through the pen. Every
hole appends to a **gap ledger** → the unforeseen becomes a worklist, never a silent swallow.

## §4.1 Static-regenerative & 0-LLM — oracle/click model
LLM = **oracle, not author.** System maps the typed topology; each hole has a complete contract
(interface+type+capability+test = puzzle-shape). Oracle *proposes* a fill; accepted **iff it CLICKS**
(typecheck+capability+test/proof). **Validity = the click, never the oracle**; provenance records who
proposed (origin_type). → NOT "AI-generated code"; system-generated, oracle-proposed, click-validated.
Linguistics live only at propose-time (above erasure boundary); run layer = AI-free validator output
(ADR-069 D6). **Static** = clicked program runs LLM-free. **Regenerative** = replay the content-addressed
fill-and-click log (no oracle at replay). **0-LLM:** run ✓, replay ✓, new-fill degrades
LLM→small-model→reuse-search→human (click is oracle-agnostic; LLM = throughput not validity); novel
topology → human planner. **OPEN KEYSTONE:** the click is only as sound as the slot-contract is complete.

## §4.2 The self-play game & RLVR reward
The system is a game: **Cities-Skylines** (construct; prerequisites — data/capability/IPC wired before a
node clicks = ADR-067 fail-closed order as physics) × **air-traffic-control** (orchestrate flows; multiple
sector controllers) × **Football-Manager** (manage over time: debt/regression/architecture). Reward =
deterministic city-health (clicks + flow-balance + low-L + high-R + coherence) read from the fact-log =
**RLVR** (ADR-069 D6), NOT human approval → no sycophancy; true feedback = the game's physics. Self-play
traces = the **machine-only training corpus** → evolves the models (AlphaZero champion/challenger, ADR-003
D3). Risks: reward-hacking (Sycophancy-to-Subterfuge — reward must be unhackable = contract completeness);
mode-collapse (need EIG exploration); garbage-rules→garbage-skill (city-physics must be sound first).

## §4.3 Cockpit & graded escalation
Two parallel streams: **place-blocks** (build) + **manage-alerts** (operate). Graded escalation to
ground-control (human): **PAN PAN** (urgency: abstain / unverifiable contract / fork in human intent →
confirm before proceeding); **MAYDAY** (emergency: trust-boundary breach / irreversible / critical alerts
→ stop, hand over) = T0 + effect-gate RequireConfirm/Block, made legible. Three human meeting points:
Build (planner sets zoning/contracts), Operate (ground control), Review (post-flight replay audit).
Build-while-flying is bounded: **never fly an un-clicked node** — flown surface = the verified subset.

## §4.4 Two-channel radar — independence is everything
Two **independent epistemic channels**, not two renders: (1) pilot's narration (my CLI words — possibly
appeasing); (2) the **radar** (lgwks tab — computed from observable emissions: real test exit codes, real
diffs, real tool-calls, the click-log, the graph, gh state). **LAW: radar derived from facts, NEVER fed by
my narration** (the instant it renders what I say, the blackbox returns) = INV-3 as UI. Trust =
agreement(narration, radar); **divergence = the alarm** → sycophancy/hallucination caught by construction.
Cockpit (AI operate) vs radar (human supervise) resolves "different planes for AI vs human." **Killer gauge
to build first: DIVERGENCE = narrated plan vs actual diffs/tool-calls.** Source-independence caveat: facts
must be harness-captured emissions, not records I author, else it's a sensor the pilot wired himself.

## §4.5 ISA → gauges · 0-AI utility · global emitter
**ISA opportunity:** compile on our framework → bytecode → the gauges are a **deterministic FOLD over the
execution trace.** Opcodes typed by gauge-effect; instrument panel = `reduce(trace)`. AI may propose only
**operands inside a node**, never an opcode and never the fold → **system-health is AI-free by construction.**
**0-AI-utility invariant:** strip AI out and the system keeps ~same utility (less convenience) — fold + run
layer + clicked nodes stand; only new-fill throughput drops. **WASM/wasmtime** is optimized for
execution-speed+sandbox, NOT token/size-minimal → borrow as the execution off-ramp; do NOT chase
token-efficiency there (wrong layer; R is won in the meaning layer above). Concrete tweak: carry erasable
proof/gauge/provenance in WASM **custom sections** (radar-readable, erased at execution). **Global emitter
(bypass GitHub):** emit facts as **content-addressed git objects** (git IS the Merkle-DAG core; GitHub is
the map); ID = content-hash; sync peer-to-peer (iroh/R2/CRDT, ADR-068 D5); GitHub demoted to a disposable
projection. Decentralized-tracker precedents to ground: Radicle, git-bug, Fossil, Pijul.

## §5 Invariants (testable)
- INV-1 every node carries origin_type + basis + content_hash; encoded as ADR-068 facts (byte-identical → same CID).
- INV-2 bias subtracted at the compile boundary is **logged** (a transform record), never silently dropped.
- INV-3 desire never enters a `basis` as fact; it is a preference signal only.
- INV-4 L is recomputable per-hop by an independent verifier (no self-report); spikes audited at H2→A0 and A1.
- INV-5 unforeseen input → a typed Hole, never a crash and never a silent admit.
- INV-6 the highway term always degrades to plain WASM (fail-open-to-dumb, ADR-068 D9; "crawl out", ADR-069 D10).
- INV-7 system-health is a pure fold over the execution trace; no AI in the fold (0-AI-utility) — strip AI, utility holds.
- INV-8 radar gauges are computed from harness-captured emissions, never from the agent's narration or self-authored records.
- INV-9 the global emitter is content-addressed (git/BLAKE3); GitHub is a projection, never the source of truth.

## §6 Open forks / next
1. Claim atom + Hole record together as lgwks ADR-004 (same shape: content-addressed typed record; one asserts, one abstains).
2. Tollbooth-first (open conformance/attestation gate) before the guarded byte framework.
3. Borrow register-VM (Lua) or stack-VM (Crafting Interpreters) shape for the *executable* off-ramp — deferred, not on the critical path.
