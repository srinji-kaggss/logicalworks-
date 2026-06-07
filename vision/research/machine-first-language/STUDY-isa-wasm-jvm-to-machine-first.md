# STUDY — WASM & JVM ISAs → the machine-first translation, and the auto-layering math

Status: GROUNDED STUDY (2026-06-06; next reader is an AI). Grounds the language rebuild in real compute
per Director: "base our math on real compute." Primary sources fetched live (`lgwks fetch`):
- WASM core spec 3.0 (2026-06-04): `webassembly.github.io/spec/core/intro/introduction.html`,
  `…/syntax/instructions.html`.
- JVM spec Java SE 21: `docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html` (structure),
  `…/jvms-4.html#jvms-4.10` (class-file verification).
No claim here is from training memory; the design-goal and execution-model quotes are from the pages above.

## §1 · What the two ISAs actually are (grounded)

**WASM (from the spec's own Design Goals):** "a *safe, portable, low-level code format* … efficient
execution and compact representation." Stated goals: **Fast · Safe** (validated, memory-safe, sandboxed) ·
**Well-defined** ("fully and precisely defines valid programs and their behavior in a way that is easy to
reason about informally *and formally*") · **Hardware-/Language-/Platform-independent · Open.**
Execution model: a **stack machine** — instructions pop/push a typed *operand stack*; some carry static
*immediates* (indices, type annotations); some are **structured** (`block`/`loop`/`if` contain nested
instruction sequences → reducible control flow by construction, no arbitrary jumps).

**JVM (from the structure chapter):** typed data (integral, floating-point, `reference`, `returnAddress`,
`boolean`); run-time data areas (pc register, **JVM stacks**, heap, method area, constant pool). Execution
is per-**frame**: each method invocation gets a frame with its own *operand stack* + *local variables*.
The **class-file verifier** (§4.10) proves type/memory safety **from the artifact alone**, before any code
runs — the producer is not trusted; the consumer re-derives safety.

## §2 · Why they are "great" — and for WHOM (the reframe)

Neither is an ergonomic *authoring* surface; humans rarely hand-write them. Their greatness is that they
let an **untrusted producer's code be safely consumed**. The shared deep pattern, both ISAs:

1. **Static verification from the artifact alone** — the format carries enough information to *prove its
   own safety* before execution (WASM validation / "well-defined"; JVM verifier §4.10). No trust in the
   author. **This is the keystone.**
2. **Stack machine + typed operands** — uniform, minimal instruction model; each instruction's effect on
   the typed stack is *locally* knowable → one-pass checkable.
3. **Structured control flow / no arbitrary jumps** — reducible CFG by construction (WASM structured
   instrs) → formal + informal reasoning stays tractable.
4. **Symbolic / indexed references** — JVM constant pool (late-bound symbolic refs, deduped); WASM typed
   section indices. Indirection by reference, never inlined bytes.
5. **Host-independent semantics + thin embedder** — effects enter only through declared imports (WASM) /
   host+native (JVM); the core is portable. Write-once, run-trusted-anywhere.
6. **Compact, linear, one-pass** — dense binary, streamable.

The realization: **what reads as "legibility" in these ISAs IS formal well-definedness** — reason about a
program without running it or trusting its author. A machine-first language needs this property *more*,
because by design the producer (the LLM) is untrusted. We do **not** trade ISA discipline for "AI freedom";
we inherit the verifier and put the LLM behind it as the untrusted producer. That is precisely the membrane
(free thought, gated action) restated in ISA terms: **untrusted producer → verifying consumer.**

## §3 · The translation (ISA property → machine-first analog in the lgwks language)

| ISA property (great because…) | Toolchain/human value | Machine-first translation (already half-derived in our corpus) |
|---|---|---|
| Static verification from artifact alone | untrusted producer, trusted consumer | **the click/gate**: a Claim runs iff it satisfies its slot-contract (typecheck + capability + test/proof). Validity is in the artifact, never the oracle (translation-chain §4.1). The verifier, restated. |
| Stack machine + typed operands | locally-checkable effect | **proof-carrying term graph**: each node typed by capability + provenance + L; its effect is locally derivable from the term, no global context (ADR-004 atom). |
| Structured control flow (no arbitrary jumps) | reducible CFG → tractable verification | **typed-edge DAG only**: no untyped/dangling edge (`UnanchoredPath`); structured by construction → the gauge is a *pure fold* over the graph (INV-7). |
| Constant pool / symbolic refs | dedup, late binding | **content-addressed substrate**: refs by BLAKE3 hash, never inlined → token-frugality + the data moat. Our constant pool (ADR-068-class fact-log, owned not borrowed). |
| Host-independent + embedder imports | write-once-run-anywhere | **engine envelopes + WASM off-ramp**: the term lowers to WASM (forgetful erasure) or to engine ports; effects via capability-typed imports (engine-v0 §2). |
| Compact, linear, one-pass | streamable | **canonical TLV encoding**: borrow protobuf TLV/varint shape, own the deterministic ordering before hashing (translation-chain §3.1). |

So the four scattered vocabularies collapse onto **one ISA-grade discipline**: a typed, content-addressed,
self-verifying term format whose producer is the (untrusted) AI and whose consumer is a deterministic
verifier. The earlier docs kept re-inventing pieces of this (membrane = click = gate = admission_verifier);
the ISA lens names the *one* thing they all are: **the verifier of a well-defined format.**

## §4 · The auto-layering math (50-node → auto-bin into new layers), grounded in real compute

Director: the 50-node limit is real; the math must **auto-bin into new layers**, not error out.

**Real-compute precedent — limits force decomposition, never a "too big" failure:**
- **JVM** hard frame limits: method `code` ≤ 65535 bytes; `max_stack` and `max_locals` declared per frame;
  constant pool ≤ 65535 entries. Exceeding a method's frame → the *compiler extracts sub-methods*; the
  **method is the binning unit**, and a call is the typed handoff between frames.
- **WASM**: the **function** is the unit; locals/operand-stack validated per function; larger logic = more
  functions + a call graph. Structured nesting bounds each unit.
- Both: when a unit overflows its frame, the least-coupled region is **spilled into a new unit behind a
  typed interface** (method ref / function import). This is register/stack spilling — *automatic,
  structural, never an error surfaced to the author.*

**The math (generalize spilling to the semantic graph).** The 50-node limit is the **comprehension-frame
budget** `B` of one layer — the semantic analog of `max_stack`/`max_locals`, and it must be *calibrated to
a real limit* (the verifier's one-pass working set, or one reasoning frame's token budget), not left as a
magic 50. On a block exceeding `B`:

1. **Detect** the densest separable sub-graph — minimum edge-cut / maximum-cohesion cluster (the
   "independence-first split", `bin_swimlanes`). Cut weight = inter-cluster typed edges.
2. **Extract** it into a new layer `z+1` behind **one typed interface edge** (the call boundary =
   WASM function import / JVM method ref). The interface is the only coupling that survives the cut.
3. **Replace** the sub-graph in the parent with a single node that references the new layer by
   **content-hash** → the parent's active-node count drops below `B`.
4. **Recurse** until every layer ≤ `B`.

**Invariant AUTOLAYER:** no layer exceeds its frame budget `B`; decomposition is **automatic, structural
(a typed interface edge), and content-addressed** — never a truncation, never an error to the human. This
*replaces* the current `TooManyNodes` compile error (COMPILER_FUNCTIONS) with an `AutoLayer` *transform*:
the limit triggers re-layering, exactly as a method/function boundary absorbs frame overflow in real ISAs.

Cut-quality obligation (the keystone risk): an auto-layer is only as sound as the cut is clean. A bad cut
leaks coupling across the interface edge (high residual cut weight). So the binning math must **minimize
interface surface** and refuse a cut whose residual coupling exceeds a threshold → escalate to human
planner (PAN PAN: fork in decomposition). Mirrors a verifier rejecting an ill-typed frame boundary.

## §5 · Consequence for the rebuild spine

The ISA lens *confirms and tightens* the proposed spine rather than replacing it:
- The **spine = a self-verifying, content-addressed, typed term format** (the thing WASM/JVM both are),
  with the translation-chain as its front end (intent→term) and WASM/engines as its back end (term→effect).
- The **gate** is explicitly "the verifier of a well-defined format" — one mechanism, the ISA keystone.
- **Auto-layering (§4)** becomes the compiler's decomposition law — real-compute-grounded, replacing the
  arbitrary 50-node error.
- Still OPEN (Director to confirm): frame budget `B`'s real-compute calibration target, and whether the
  spine doc absorbs §4 as its compiler section or keeps it as a referenced study.
