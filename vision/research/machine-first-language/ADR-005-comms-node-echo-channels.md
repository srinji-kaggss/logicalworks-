# ADR-005 — The comms node: overhear channels, the frame, and the echo rule

Status: PROPOSED (drafted 2026-06-06; echo rule ratified by Director this session). Settles the comms
sub-node left open in HANDOFF-2026-06-06 §comms. Adopts (never forks) ADR-068 (content-addressed
hash-chained fact-log / Causal Tape), ADR-073 (closed capability vocabulary), ADR-078 (cryptographic group
isolation), ADR-079 (metadata-ping) from logic-os-kernel. This is the node **between** plane (agent) ↔ radar
(ADR-002 harness gauge) ↔ peers. Everything here is ADOPT, not invent.

## D-scope · Comms is PROJECT-world, not life (Director, 2026-06-06)
Every channel/echo/"global" tier below is scoped to **one shared project-world** — the bounded node-graph
the agents collaborate in. "Global" means *global-within-this-project*, never a life-wide or cross-project
persistent social layer. Agents overhear each other across the world they share *for that project*; close
the project, the world closes. This is not the fleet's life-comms; it is one project's shared senses.

## D0 · The model is OVERHEAR, not address (Director: "eyes and ears through echoing")

Agents are decoupled — they do not work *for* or *with* each other on a fixed wire. Comms is the sense
organ: an agent hears the fleet by overhearing **echoes**, not by being addressed. There is no recipient
field, no routing table, no request/response. A message is emitted to a channel; hearing is subscription,
not delivery.

//why overhear not address — addressing re-introduces coupling (sender must know receiver) and a routing
authority (a hive coordinator). Overhear keeps the fleet a relational democracy: every agent is a peer that
chooses what it attends to. This is ADS-B, not TCP — broadcast position, let listeners decide.

## D1 · Channel topology: individual → team → global, by union of echoes

Three tiers, each a set of the one below:
- **individual** — the agent's own per-agent hash-chained log (ADR-068 Causal Tape). The ground truth.
- **team** — a keyed set of agents sharing a channel ("my AIs, same channel"). The "teams chat" desire —
  NOT a literal Slack; a channel is a cryptographic membership set (D3), not a server.
- **global** — the **union feed of all echoes**. Not a separate store: it is the merge of every channel's
  promoted metadata. The fleet's shared senses = the set of everything anyone chose to echo up.

//why global = union, not a top-level log — a distinct global store would be a single point of authority and
a binning of "the fleet" into one entity. The global feed is derived (a fold over channel echoes), so it
cannot diverge from its members and has no owner.

## D2 · Echo = metadata relays UP, cargo stays sealed (this IS ADR-079 metadata-ping)

Promotion up the tiers carries **metadata only**; the payload (cargo) stays sealed at its origin tier unless
explicitly promoted (D4·c). An echo is a ping — "a fact of this shape occurred here" — addressable by its
content_hash, fetchable by a capability holder. The union feed is therefore cheap and leak-resistant: you
overhear *that* something happened and its frame-class, not its contents.

## D3 · Membership & audit are cryptographic, not stringly (T0)

- **Admission** to a channel = signature by an existing member key + a channel capability (ADR-073) +
  cryptographic group isolation (ADR-078). No `if member == "internal"`.
- **Audit** = the hash-chain **is** the proof. This fixes raw ADS-B's spoofability: auditability is the
  Causal Tape's content-addressed chain (ADR-068), not "we wrote a log line." Tamper breaks the chain.

## D4 · The echo rule — RATIFIED (a)+(c); (b) deferred

The promotion rule (individual→global) was the open fork. Resolved this session:

- **(a) always-echo-metadata — ADOPTED as the spine.** Every frame relays its metadata up automatically.
  The union feed is complete by construction; salience is a *reader-side* concern, never a substrate filter.
- **(c) explicit-promote — ADOPTED for cargo.** Sealed payloads cross a tier only on the agent's explicit
  promote, gated by capability (D3). Required regardless of (a) because (a) never moves cargo.
- **(b) deterministic-salience — DEFERRED, not rejected.** Filtering echoes by salience is legal *only* if
  salience is a **non-AI frame-class** (Axiom 2: substrate stays non-AI; AI is the gated exception). No such
  frame-class is specified yet. Adopting (b) now would smuggle an AI judgment into the transport. (b) stays a
  goal contingent on first specifying that non-AI salience frame-class.

//why (a)+(c) and not (b) — a salience filter that calls a model puts AI inside the comms substrate, the
exact inversion of the standing axiom (project_non_ai_comms_substrate). Always-echo keeps the substrate dumb
and deterministic; if the feed is noisy, that is a reader's problem to fold, not the wire's to pre-judge.

## D5 · The frame (closed, versioned vocabulary)

```
{ channel_id, agent_id, seq, causal_parent, payload_type, payload, capability_proof, sig }
content_hash = CID over canonical bytes (ADR-004 D3 encoding)  // == message ID
```
- `payload_type` ∈ a **closed, versioned vocabulary** (terminology = cut tech-debt + optimize the machine).
- `causal_parent` = prior content_hash in this agent's chain → the Causal Tape edge (ADR-068).
- `capability_proof` = ADR-073 term authorizing this emission on this channel.
- `content_hash` is the identity, dedup key, and the thing an echo pings (D2).

//why closed vocabulary — an open payload_type string is an un-auditable surface and a binning hazard
(two agents inventing divergent types for one meaning). Closed + versioned makes the wire machine-checkable.

## INV (the invariants this node must not violate)
- **INV-C1 channel-independence preserved** — an echo's metadata is harness/transport-captured, never the
  emitting model's self-report (continues ADR-004 D-correction #3; the radar's B-channel stays clean).
- **INV-C2 no address field** — the frame has no recipient; a build that adds routing has left the overhear model.
- **INV-C3 cargo sealed by default** — payload crosses a tier only via D4·c explicit-promote + capability.
- **INV-C4 chain-or-it-didn't-happen** — every frame has a valid `causal_parent`; a broken chain is a dropped
  message, never a silent accept.

## Build sequence (continues HANDOFF §build, after the divergence gauge)
1. frame encoder/decoder over ADR-004 D3 canonical bytes (content_hash = message ID).
2. per-agent Causal Tape append + chain-verify (ADR-068 port).
3. always-echo emitter (D4·a) → union feed fold (the global "senses").
4. channel membership/admission (D3) + explicit-promote path (D4·c).
OPEN (Director deferred, wants it after this): **transport posture** — hosted relay vs P2P gossip vs shared
append-log. The topology + echo model (this ADR) had to settle first; transport is now the next decision.
