# PRD-04 — Context Synthesis & Token Economy

Parent: [PRD.md](../PRD.md) §6 schema + L5 channels · Status: draft v0.2 · absorbs YAML `context_stream_synthesis_engine`
Replaces: **token waste itself** — the tax every other vendor monetizes around.

## Problem — and what economy is NOT

This PRD kills **waste, not thinking**. Token economy ≠ token minimization. The doctrine
mantra governs: *depth is the economy — spend 40k now to kill 200k of rework in two days.*
A 40k-token grounded read that prevents a wrong build is the cheapest context ever bought;
500 tokens of redundant annotation Opus never uses is pure waste. The design session that
produced the parent PRD burned ~1M tokens reaching ground-0 — the waste was not the volume,
it was the *yield*: tokens spent re-deriving, re-discovering, re-reading what an owned
index could have served in one pass.

**Waste, operationally**: injected/retrieved tokens that are never used downstream —
never cited, never acted on, redundant with what's already in context, or answerable
deterministically without entering the window at all. That is the thing to measure and
drive toward zero. Depth-when-needed is never waste.

## Two channels, two laws (//why: the previous draft's single hard cap rationed thinking)

1. **Reflex channel** — the unsolicited per-prompt injection (§6 schema via PRD-07).
   Opus didn't ask for it; it interrupts every prompt; here a terse hard cap is correct
   (default 1.5k tokens, INV-8). Its job is salience, not depth: scores, flags, pointers.
2. **Depth channel** — context assembled because the intent demands it (a retrieval pull,
   a task's dependency closure, a grounding read). **No fixed ceiling.** Sized by need,
   governed by yield: pruning removes the *valueless* (redundant, off-closure, stale),
   never truncates the load-bearing to hit a number. The reflex channel carries *pointers*
   into depth ("the closure is 12k tokens, assembled, here's the handle") so Opus chooses
   the spend consciously.

## Thesis

Token economy is a *routing, pruning, and yield-measurement* problem over owned indexes:
hybrid retrieval (deterministic graph walk + semantic rank), fusion, pruning of the
valueless — with waste-rate as the governing metric, not byte-count. The YAML's synthesis
engine is correct in shape; we bind it to our invariants (deterministic-first,
non-generative, waste-measured).

## Absorbed from the input YAML — with deviations

| YAML proposal | Verdict | //why |
|---|---|---|
| hybrid retrieval router (dense vectors for concepts + graph walk for dependencies) | ADOPT | matches INV-4: graph decides membership, vectors rank order |
| Reciprocal Rank Fusion over vector+graph scores | ADOPT | deterministic given inputs; cheap; no model judgment call |
| modified PageRank over the graph | ADOPT (phase 2) | static centrality is precomputable by the daemon; useful prior, must prove lift on eval first |
| dynamic token budgeting, drop low-priority defs, keep foundational interfaces | ADOPT, reflex channel only | becomes INV-8: hard cap + deterministic truncation order on the unsolicited injection; the depth channel prunes by value, never by ceiling |

## Scope

- IN: the `lgwks.inbound.v1` schema (parent §6) — versioned, reflex-capped, with
  deterministic truncation order: `flags > scores > selections > retrieval > pathways >
  last_state`; carries depth-handles (size + content summary by selection, not generation).
- IN: the depth channel: assemble the full needed closure on demand (dependency closure,
  grounding pack, docs pack) — yield-governed, no ceiling.
- IN: hybrid retrieval over PRD-02 code graph + PRD-03 web/docs + PRD-01 capability map.
- IN: **waste accounting** (the governing ledger): every injection/pack logs tokens to
  PRD-08 db AND its downstream yield — was it cited/used in subsequent turns (measurable
  from the transcript the daemon already tails). Cockpit shows waste-rate, not just spend.
- IN: pruning: chunk-level (AST chunks from 02-d), interface-first retention, redundancy
  vs current-window content.
- OUT: generation (INV-3). OUT: deciding what Opus does with the context. OUT: capping
  thinking — no mechanism in this PRD may truncate demanded depth to meet a number.

## Builds on (candidates — verify at unit start)

`lgwks_context.py`, `lgwks_search.py`, `lgwks_substrate_vector.py`, `lgwks_embed.py`,
`lgwks_concept.py`, `lgwks_graph.py` · shipped consumers: `hooks/subconscious_inbound.py`.

## Contract

Emits `lgwks.inbound.v1` (reflex): parent §6 fields + `schema`, `budget {limit_tokens,
used_tokens, truncated[]}`, `depth_handles[{id, est_tokens, kind}]`. Reflex cap default
**1500 tokens** (tunable, never absent). Emits `lgwks.depthpack.v1` (depth): `{handle,
tokens, sources[], pruned[{what, why}]}` — pruned list visible, no silent drops.
Consumers: PRD-07 taps. Producers consumed: PRD-01/02/03 retrieval surfaces, PRD-06 scores.

## Units & acceptance

| Unit | Acceptance |
|---|---|
| 04-a reflex schema v1 | versioned envelope + budget block; property test: NO input can produce a reflex injection over cap; truncation order proven by forcing overflow; depth-handles survive truncation (they ARE the economy — a pointer is never dropped for bulk) |
| 04-b hybrid router | given a query touching a known graph region: graph-walk returns the dependency closure, vector rank orders it; RRF fusion deterministic (same inputs → same order, tested) |
| 04-c waste ledger | per-session ledger in db: tokens injected/packed AND downstream-use signal per item (cited/acted-on within N turns, from transcript); cockpit shows waste-rate; sums verified against transcript |
| 04-d pruning yield | on the eval corpus (SCIENCE §4): pruned depth-pack preserves 100% of answer-bearing chunks while cutting measured dead weight vs naive closure — yield up, never coverage down |
| 04-e pagerank prior | precomputed centrality improves retrieval metrics on eval, else REJECTED and removed (pre-registered, SCIENCE §2) |
| 04-f depth-pack assembly | for 5 frozen intents needing depth: pack contains the full needed closure (audited vs ground truth), regardless of size; nothing load-bearing pruned to satisfy any number |

## Open questions → SCIENCE.md

Reflex-cap sizing (marginal salience per token — §4, knee-finding applies to the reflex
channel ONLY); waste-rate definition window (cited within how many turns?); whether
last_state retrieval needs recency decay; RRF k-constant tuning (pre-register, don't fiddle).

RISK: the failure modes are now two and opposite — an unbounded reflex channel becomes
noise tax, and a capped depth channel becomes starved thinking (the defect this v0.2
corrects). The waste ledger (04-c) is the instrument that catches both: high waste-rate
indicts the reflex channel; rework-after-shallow-context indicts depth starvation.
