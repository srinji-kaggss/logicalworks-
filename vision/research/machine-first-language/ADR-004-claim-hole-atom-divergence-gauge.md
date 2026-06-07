# ADR-004 — The Claim + Hole atom, canonical encoding, and the divergence gauge

Status: PROPOSED (drafted 2026-06-06; pending Director ratification). Realizes
SPEC-translation-chain-bytecode-semantics §3/§3.1/§4/§4.4 and its open fork #1. Adopts (never forks)
ADR-068 (content-addressed E2EE fact-log) and ADR-073 (closed capability vocabulary) from logic-os-kernel.
This is the **meaning layer** the CLI-gap log named as the real bottleneck — not the tooling.

## D1 · The atom is one shape with two inhabitants: Claim (asserts) and Hole (abstains)

The proof-carrying term graph (SPEC §3) is built from **one** content-addressed record type with two
inhabitants — the conjugate pair. Same envelope so the graph is homogeneous, the verifier walks one shape,
and an abstention is a first-class node, never an absence.

- **Claim** — asserts a meaning at a node of the chain (H0…A2). Carries: `objective|content`, `basis[]`
  (the content-hashes it derives from — the provenance edges), `origin_type ∈ {grounded, inferred, invented}`,
  `capability` (the ADR-073 vocabulary term it commits to, or `none` above the compile boundary),
  `l_contribution` (this node's invented-share numerator), `content_hash` (CID over canonical bytes, D3).
- **Hole** — abstains where the closed vocabulary cannot yet express the input (SPEC §4, Hazel typed holes).
  Same envelope, but asserts nothing executable: `context`, `nearest_known` (discriminator's nearest-bin),
  `why_unmatched`, `content_hash`. **Data, not instruction (ADR-065): a Hole cannot widen its own scope.**
  Appends to the gap ledger → the unforeseen becomes a worklist, never a silent admit (INV-5).

//why one shape, two inhabitants — not two types: the verifier, the fold, and the CID logic must not branch
on "is this a gap." A Hole is a Claim whose `origin_type` is `abstained` and whose capability is `⊥`. Binning
them as distinct records would re-introduce the context-loss sin at the atom level.

## D2 · Provenance is structural, not annotated — `basis[]` is the only edge

A node's trust is its transitive closure over `basis[]` down to `origin_type:grounded` leaves (the H0
utterances). There is no separate provenance side-channel: the DAG of `basis` content-hashes **is** the
provenance. Consequences enforced by construction:
- A Claim whose `basis` does not reach a grounded leaf is `invented` by definition — the type cannot lie.
- `desire` (SPEC H1) may travel as a preference signal but **may never appear in a `basis`** (INV-3): taste
  is not evidence. The encoder rejects a `basis` entry whose source record is a `Desire`.
- Capability flows **up** the DAG: a node cannot claim authority its `basis` did not carry (least-privilege
  as a graph property, not a check) — aligns ADR-073's capability port.

## D3 · Canonical encoding — borrow the wire, own the determinism (SPEC §3.1)

The CID is load-bearing (it is the identity, the dedup key, the replay anchor), so encoding is a *decision*,
not a default:
- **Borrow** protobuf-style TLV + base-128 varint shape: `tag=(field<<3)|wire_type`; unknown fields are
  **preserved and skipped**, never crashed on → a Hole and a forward-compatible unknown field are the same
  idea at two layers.
- **Own** canonical ordering: protobuf is NOT canonical by default (field/map order, unknown placement vary
  → same message, different bytes → broken CID). We impose deterministic ordering (JCS / canonical-CBOR
  shape) **before** hashing. Borrow extensibility; own determinism (INV-1).
- **Hash over canonical bytes, never a string round-trip** (not all bytes are valid UTF-8; byte→string→byte
  is lossy → a corrupted CID). `content_hash = BLAKE3(canonical_bytes)` — byte-identical input → same CID.
  This is exactly an ADR-068 fact: append-only, hash-chained, natively ingestible by the OS substrate.

//why this is the single most reversible-if-wrong / irreversible-if-shipped decision in the atom: every
downstream CID, dedup, and replay inherits it. Spend here.

## D4 · L and R are recomputed by an independent verifier — never self-reported (INV-4)

`l_score` and `R` are **audits**, so the audited party cannot compute them:
- **L verifier** walks the `basis` DAG of a finished term and recomputes, per hop, `L = invented_claims /
  total_claims` from `origin_type` — it does not read the agent's claimed `l_score`; it derives it from the
  structure and overwrites. A node tagged `grounded` whose `basis` does not reach a grounded leaf is
  **reclassified `invented`** and the divergence is logged. Spikes are expected and audited at the compile
  boundary (H2→A0) and at A1 (the AI's own L_rep / sycophancy), per SPEC §2.
- **R-meter** splits a run's tokens into `recovery` (re-deriving context already known) + `invention` +
  `judgment` (= total − recovery − invention). `R = judgment / total`. This is the lgwks-gap feature idea
  (`--meter`) made structural: `R=0.87, L=0.04` is peer-review-grade, agent-checkable evidence the substrate
  earns its tokens. Recovery is read from the cognition-log cache-miss trace, not narrated.

//why no self-report: a verifier the proposer feeds is the sycophancy hole one layer down. L/R must be a
fold over emitted structure (D5's independence law), or they measure nothing.

## D5 · The divergence gauge is the first radar instrument — and the independence law that makes it real

The killer gauge (SPEC §4.4): **DIVERGENCE = narrated plan vs actual emissions.** Built first because it is
the one that catches me lying.

> **CORRECTION (2026-06-06, post-review):** the divergence gauge is NOT an AI-native instrument — it is a
> generic agreement/similarity score. Its only real property is **channel-independence** (B never fed by A),
> which is a P-property, not an A-property. Separately, D2/D4 must add the **claimed-vs-observed provenance
> split**: a `basis` edge counts only if the retrieval/tool-call was *harness-observed*, not LLM-asserted —
> otherwise the L metric still has the LLM inside its own measurement. See HANDOFF-2026-06-06.

- **Channel A (cockpit/narration):** what my CLI words claim I did — the plan, the "done."
- **Channel B (radar):** computed **only** from harness-captured emissions — real test exit codes, real
  diffs, real tool-call log, the click-log, the graph, `gh state`. **LAW (INV-8): the radar is never fed by
  my narration.** The instant it renders what I *say*, the blackbox returns and the gauge measures nothing.
- **Gauge = agreement(A, B); divergence = the alarm.** A claimed "tests pass" with no test exit code in B,
  a "refactored X" with no diff touching X, an `origin_type:grounded` the L-verifier reclassified — each is a
  divergence event → PAN PAN (SPEC §4.3). Sycophancy and hallucination are caught **by construction**, not by
  a human re-reading my prose.
- **Source-independence caveat (the trap):** Channel B's facts must be **harness-captured**, not records I
  author — else it is a sensor the pilot wired to himself. The emitter (D6 below / SPEC §4.5) must stamp
  provenance of *capture*, distinct from provenance of *content*.

## D6 · Open obligations seeded here (the build sequence this ADR commits to)

1. **Atom + canonical encoder first** (D1–D3): one record type, the borrow-wire/own-canonical codec, BLAKE3
   CID as an ADR-068 fact. Nothing downstream is real until the CID is stable. Verification: byte-identical
   input → identical CID across two processes (INV-1 test).
2. **L verifier + R-meter** (D4) over the atom DAG — independent recompute, reclassify-and-log, no self-report.
   Verification: a deliberately mis-tagged `grounded` node is reclassified `invented` (INV-4 test).
3. **Divergence gauge** (D5) — Channel B reads only the harness emission log; a narrated claim with no
   matching emission raises divergence. Verification: a "tests pass" with no captured exit code alarms (INV-8 test).
4. The global emitter as content-addressed git objects (SPEC §4.5, INV-9) is the substrate all three write
   to; GitHub stays a disposable projection. Deferred behind #1–#3 but it is the home for the capture-provenance
   of D5's caveat.

## What this ADR does NOT decide (held open, per scope discipline)
- The executable off-ramp VM shape (register vs stack) — SPEC §6 fork 3, deferred, not on the critical path.
- The canonical vector space for substrate recall (deterministic-hash vs qwen3) — that is issue #41 / the
  hybrid-LPM decision, a *different* axis from the atom's CID. Do not bin them.
- The discriminator/binning gate's internal model — D1 consumes its `nearest_known` output; how it ranks bins
  is its own spec.
