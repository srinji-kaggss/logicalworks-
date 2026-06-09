# PRD Index — Second Harness, decomposed

Status: draft v0.1 · 2026-06-09 · children of [../PRD.md](../PRD.md) (frozen v1.0 — end-state authority)
Audience: machine-first. Each child PRD is independently implementable; this index holds the seams.

## Why decomposed

The parent PRD is the end-state. The mission restated operationally: **lgwks is Claude Code
for Claude Code** — the harness's own harness. Every external subscription the harness leans
on is replaced by an owned, local, non-generative function. The decomposition cuts along
*replacement targets* and *interface seams*, so each child can ship, be measured, and fail
independently.

## Replacement matrix (what dies, which PRD kills it)

| External dependency | What it actually sells | Owned replacement | Child PRD |
|---|---|---|---|
| Greptile | code graph + PR review context | code world-graph + review attenuation | PRD-02, PRD-09 |
| Serena | LSP-backed semantic code toolkit (MCP) | AST/LSP code intelligence over owned graph | PRD-02 |
| Firecrawl | crawl/scrape/extract APIs | `lgwks crawl/ingest` + frontier ladder | PRD-03 |
| Context7 (ctx7) | current library docs on demand | docs ingest → world-graph, versioned | PRD-03 |
| Token waste (the tax, not a vendor) | — | context synthesis + budgeted injection | PRD-04 |
| LangChain-class orchestration | routing/chains | capability map + actors + baby models | PRD-01, parent §4 |
| Observability/governance SaaS | audit, traces | daemon side-effect capture | PRD-08 |

## Children

| PRD | Title | Parent units | Replaces |
|---|---|---|---|
| [PRD-01](PRD-01-capability-map.md) | Capability Map & Routing | U1 | tool-discovery waste; LangChain routing |
| [PRD-02](PRD-02-code-intelligence.md) | Code Intelligence (code world-graph) | U3 (code half) | Greptile, Serena |
| [PRD-03](PRD-03-web-docs-ingest.md) | Web & Docs Ingest | U11 + L0 (web half) | Firecrawl, Context7 |
| [PRD-04](PRD-04-context-economy.md) | Context Synthesis & Token Economy | §6 schema + retrieval | token waste itself |
| [PRD-05](PRD-05-model-runtime.md) | Local Model Runtime | U4 | cloud inference |
| [PRD-06](PRD-06-subconscious-engine.md) | Transcript Cortex & Engine (C/G/P) | U5, U6 | — (the novel core) |
| [PRD-07](PRD-07-taps-channels.md) | Taps & Channels (hooks, cockpit) | U7, U8, U9 | — (the delivery layer) |
| [PRD-08](PRD-08-daemon-state-governance.md) | Daemon, State & Governance | U10 + §14 risks | observability SaaS |
| [PRD-09](PRD-09-review-attenuation.md) | Review & Nitpick Attenuation | (new — from input YAML) | Greptile review, CodeRabbit-class |
| [PRD-10](PRD-10-detection-algorithms.md) | Detection Algorithms (SAST + fraud-engine) | (new — from SAST blueprints) | Semgrep/CodeQL/Snyk rules, CodeRabbit |
| [SCIENCE](SCIENCE.md) | Scientific method for the messy parts | §7 + detectors + ranking | — |

PRD-05 is **finalized** (v1.0): model architecture, the tiered runtime (ANE→Torch→Ollama→
deterministic), and the training pipeline — grounded against verified repo state, with the
honest finding that CoreML is blocked on Python 3.14 and Ollama (T-EYE) is the live tier.
PRD-10 is **finalized** (v1.0): the detection substrate (SAST + fraud-engine scoring), folding
the 7 cited research blueprints onto the existing `lgwks_bot_code_hacker.py` 5-layer analyzer.

External inputs (preserved for provenance, volatile in Downloads):
- [inputs/gemini-code-graph-rag.yaml](inputs/gemini-code-graph-rag.yaml) — Gemini code-graph-RAG
  spec; absorbed into PRD-02/04/09 (Kafka/Kinesis + cloud embedders rejected per INV-5).
- [inputs/sast-engine-blueprints.json](inputs/sast-engine-blueprints.json) — 7 fully-cited
  frontier SAST pattern blueprints; absorbed into PRD-10 as the v1 pattern set.

## Interface seams (the contracts between children)

```
PRD-03 web/docs ─┐
                 ├→ World-Graph (one store: deterministic edges + semantic attrs) ─→ PRD-04 retrieval
PRD-02 code ─────┘            ↑ writes governed by PRD-08 (single-writer db)
PRD-01 map ──────→ ranked capabilities ─→ PRD-04 (a retrieval source) + PRD-06 (a C input)
PRD-05 runtime ──→ embed/score fns consumed by PRD-02/03/04/06 (never decide; INV-4)
PRD-06 engine ───→ {C,G,P,flags,selections} ─→ PRD-07 channels (two projections, INV-1)
PRD-09 review ───→ findings ─→ PRD-07 cockpit (Director) — never injected to Opus unproven
PRD-08 daemon ───→ lifecycle/state for all of the above
```

Schema contracts are versioned (`lgwks.<name>.v1`); a child may not consume another child's
internals — only its published schema. Cross-child changes bump the schema version.

## Invariants (inherited by every child; restated once)

INV-1 independent projections · INV-2 closed-model · INV-3 non-generative meta-layer ·
INV-4 deterministic-first, embeddings rank never decide · INV-5 repo-resident models, no
runtime cloud inference · INV-6 never-block, never impersonate · INV-7 inbound latency cap.
New (v1.1 hardening, adopted by children): INV-8 the unsolicited reflex injection is
hard-capped + schema-versioned; demanded depth is never capped — economy kills waste
(unused tokens), never thinking (PRD-04 two-channel law) · INV-9 swallowed failures are
logged to cockpit-side, never invisible · INV-10 one kill switch (`LGWKS_SUBCONSCIOUS=0`)
disables every tap.

## Build order (revised first slices)

1. PRD-01 (shipped: U1) → PRD-07 inbound-minimal (shipped: U7) — the loop exists.
2. PRD-04 reflex schema v1 + waste ledger (small; protects everything downstream).
3. PRD-02 code-graph slice (tree-sitter over this repo) ∥ PRD-03 docs-ingest slice.
4. PRD-05 CoreML forward pass → PRD-06 engine (gated on SCIENCE.md pre-registration).
5. PRD-09 review attenuation ∥ PRD-08 daemon hardening.
6. PRD-07 cockpit last among channels (web surface; auth spec in PRD-08 first).
