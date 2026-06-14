# PRD — lgwks as a Second Harness (the Subconscious)

Status: **authoritative · final · source of truth for end-state** · v1.0 · 2026-06-09
Owners: Director + Logical Claude. This document governs; code conforms to it.
Audience: machine-first. The next reader is an AI implementing or operating this.

---

## 1. Problem & thesis

**Problem (this conversation is the evidence).** An AI operating across 1284 skills, 15 MCPs, 60+ lgwks verbs, 5 embedders cannot quickly (a) grasp the *scale of what already exists* for an intent, or (b) see a *predictive read of its own outcome-vs-gap* before spending tokens. So intents resolve slowly, blindly, expensively — this design session alone burned ~1M tokens reaching ground-0. There is no compressed, shared channel of understanding between Director and AI.

**Thesis.** The sprawl already brute-forced the key functions that the "millions of AI wrappers" sell as subscriptions. The win is **good routing over owned functions + cheap local models** — not subscriptions. The expensive frontier model (Opus) is **rationed to reasoning**; cheap baby models (BERTs) do all orchestration. lgwks becomes the AI's **subconscious**: the parallel substrate that perceives, contextualizes, and surfaces — so the conscious model is never lost and the Director sees where its reasoning is heading before it commits.

## 2. Philosophy — subconscious, NOT activation steering

Two distinct minds, never fused:
- **Consciousness** = Opus. Generative, serial, expensive, the thing that decides and writes.
- **Subconscious** = lgwks. Non-generative, parallel, always-on, cheap, the thing that builds "thoughts of everything" and surfaces the salient ones.

This is explicitly **NOT** ActAdd / activation steering (arXiv:2308.10248 — injects a vector into the residual stream to suppress/redirect behavior). We reject it on two grounds: (1) Opus is a closed API — its internals are unreachable, so steering it is *impossible*; (2) we don't want to neuter behavior, we want to *augment* it. The subconscious **surfaces to awareness, never overrides** — like a human gut feeling that catches a mistake mid-thought. The activation-engineering *mechanism* (representations as coordinates → "where am I / nearby branches") is legitimate and **relocated to a model we own** (the local BERTs), used for *positioning*, not control.

It is the structural cure for the operating-loop defect — *fragment → premature "done" → deleted verification → confident narration over a hole.* That defect IS a conscious mind with no subconscious.

## 3. The independence invariant (hard requirement)

The subconscious serves **both** Director and Opus, but their **experiences are permanently independent**:
- one **engine + state (db)** = common source;
- **two projections, never merged, never mirrored**: the **Director cockpit** (human oversight) and the **Opus schema** (machine context), each tuned to its reader.
- Opus's projection is tuned to *its* cognition and must not be polluted by the human view; the Director's is tuned to *oversight* and is not Opus's raw schema.

> **INV-1 (non-negotiable): the AI's experience is always independent of the Director's.** Common well, decoupled streams. Violating this couples the two minds wrongly and breaks both.

## 4. Division of labor (machine-first)

| Layer | Who | Does | Cost |
|---|---|---|---|
| Orchestration / routing / analysis / retrieval / scoring / simulation | **BERTs + baby models** (add as many as needed) | everything mechanical | cheap, local |
| Reasoning / generation / decisions | **Opus** | only its best thing | rationed |

Opus's **marginal footprint for the whole meta-layer ≈ zero extra actions**: it reads an injected schema (like it already reads the operating-loop block) and is steered by terse signals. No extra tool calls, no output tee — the daemon reads the transcript directly.

## 5. Mechanism — continuous + bidirectional (the loop)

**Daemon (always-on, pre-warmed).** Tails the live transcript `~/.claude/projects/<slug>/*.jsonl` — which already logs Opus's output *and* every tool call — and continuously runs analysis, simulation, retrieval, and research on it. No Stop-hook tee needed; the transcript is the canonical stream.

**Three taps (all via Claude Code hooks, verified live):**

1. **Inbound — `UserPromptSubmit`** (fires on the Director's prompt, before Opus; ≤30s hard cap). Injects the **non-generative schema** (§6) into Opus's context. Heavy work (live framework checks, crawls) does NOT block here — it runs in the daemon and surfaces via tap 2 or next inbound. *"Intercept the human's input, not the AI's output"* — the cheap early signal, same head-start Opus gets.
2. **Mid-turn — `PostToolBatch`** (fires between reasoning steps). Refreshes the steer **every ~3 reasoning steps OR immediately on a critical-fact hit** — a terse non-generative signal Opus reads fast (the practical form of "steer me in vectors"). Can also `block` to halt a bad trajectory before the next model call.
3. **Side-effects (free) — `PostToolUse` · `FileChanged` · `TaskCreated/Completed` · `ConfigChange` · `SessionStart/End`.** The daemon observes every action → auto-updates governance/audit/work-tracking and fires **independent static review** — surfaced in the **cockpit**, flagging the Director directly (not through Opus). Some can `block` (e.g. gate a task-complete or a destructive config change).

**Outbound** is not a tap — the daemon already has Opus's output and tool calls from the transcript, analyzing continuously.

## 6. The inbound schema (the data contract) — NON-GENERATIVE

Injected to Opus each prompt. **No generated prose** — scores, selections, retrieved facts, non-gen actions. This *is* the anti-slop guard (§8).

```jsonc
{
  "prompt": "<raw director text>",
  "attention":  { /* BERT salience over prompt tokens — what matters most */ },
  "retrieval":  [ /* top-k deterministic+semantic hits from the world-graph/db */ ],
  "last_state": { /* relevant prior decisions/work/run-artifacts for this prompt */ },
  "insights": {
    "scores":     { "coverage_C": 0.0, "gap_G": 0.0, "confidence_P": 0.0 },   // §7
    "selections": [ /* candidate paths/files/actors the subconscious pre-picked */ ],
    "flags":      [ /* "slop" | "sycophancy" | "dredge" | "intent-drift" | "unverified-claim" */ ],
    "actions_taken": [ /* non-generative work the daemon already ran (cached results) */ ]
  },
  "pathways":   [ /* retrieved (not generated) next-step suggestions — subsequent workflow */ ]
}
```

## 7. The three equations (the compressed read)

> ⚠️ **DRIFT (2026-06-14):** the shipped engine computes deterministic *proxies* that differ from these
> equations (capability-coverage C, grounding-gap G, geometric-mean P). The design below (grounded/required
> nodes, trust-weighted G, Bayesian P) is the **target, not what runs**. See the `PRD-06` DRIFT banner +
> `Desktop/LogicOS-Conflict-Ledger-2026-06-14.md` C-01. Canonical choice pending PI.

Surfaced in both projections (cockpit visual + schema scores):
- **Coverage** `C = grounded_nodes / required_nodes` — how much of the intent's required context is grounded vs assumed.
- **Gap/Risk** `G = Σ(unverified_claim_i · trust_weight_i)` — the predicted hole, weighted by trust tier.
- **Outcome confidence** `P(success) = f(C, evidence_tier, prior_similarity)` — Bayesian estimate from world-graph + transcript history.

Low C / high G → Opus must ground more before acting; the Director sees the same numbers and can **pause** Opus from the cockpit.

## 8. Anti-slop / sycophancy / dredge (first-class)

- The meta-layer is **non-generative by construction** — it cannot emit slop because it does not generate prose.
- The subconscious **detects and flags** these in Opus's output (cockpit + next-turn schema `flags`):
  - **slop** = low-information filler / hedging;
  - **sycophancy** = agreement without grounding;
  - **dredge** = recycled/padded restatement.
- Design lens for every unit: **machine-first principles + downstream-impact analysis.**

## 9. Architecture layers

```
L5  CHANNELS          inbound schema (Opus) · mid-turn steer (Opus) · cockpit (Director) — INDEPENDENT projections (INV-1)
L4  SUBCONSCIOUS ENGINE  non-gen: scores {C,G,P} · simulate outcomes-vs-gaps · route · detect slop/sycophancy/dredge
L3  TRANSCRIPT CORTEX  BERT (CoreML, on-device) tails *.jsonl → live task state, attention/salience
L2  CAPABILITY MAP     queryable index of every verb/skill/MCP/run → "scale of stuff" in a few commands
L1  ACTORS            one contract: typed input → run → dataset+manifest; composable; pre-wired super-tools
L0  SUBSTRATE         ingest(web+code+files) → World-Graph (deterministic edges + semantic attrs) + artifact tree
```

## 10. Non-negotiables (invariants)

- **INV-1** independence of Opus's and Director's experience (§3).
- **INV-2** closed-model: never assume access to Opus internals; all "steering" is context injection / terse signal.
- **INV-3** non-generative meta-layer; generation is reserved for Opus.
- **INV-4** deterministic-first; embeddings rank, never decide.
- **INV-5** repo-resident models, **no runtime cloud inference** (BERT via CoreML on-device).
- **INV-6** never-block degrade; **the conscious channel (Director↔Opus) is never replaced or impersonated** — the subconscious annotates, never answers as Opus.
- **INV-7** 30s inbound cap; heavy work is async via the daemon.

## 11. Competitive coverage (own, don't subscribe)

| They sell | We own via |
|---|---|
| Greptile (graph code context) | L0 World-Graph (web+code) + L2 |
| Apify (actor platform) | L1 Actor contract |
| Cursor/Copilot (code context) | L0 + L3 cortex |
| LangChain/orchestration | baby-model routing (L4) |
| Observability/governance SaaS | §5 free side-effects |
| Anti-detect scraping APIs | frontier crawl (Camoufox ladder) |

## 12. Factory spec — units, acceptance, order

> Build on **existing functions first**. Each unit ships independently with evidence. Cockpit is a web app (acknowledged) — **core functions first.**

| Unit | Builds on | Acceptance | Order |
|---|---|---|---|
| **U1 Capability Map** | `lgwks manifest`, verb registry, skills/MCP lists | `lgwks map "<intent>"` → ranked verbs/skills/MCPs/runs, deterministic, <1s | seed |
| **U2 Actor contract** | `lgwks_ingest`, `lgwks_workflows`, `spawn.json` | one schema; ingest + 2 conform; actor-calls-actor; `lgwks run <actor> --input json` | after U1 |
| **U3 World-Graph query** | `lgwks_entity_graph`, `concepts`, `vectors` | deterministic-edge traversal returns complete neighborhood (not top-k) | ∥ U2 |
| **U4 BERT runtime** | `lgwks_model_hub`, CoreML convert | `model-hub load neobert` runs a real on-device forward pass; doctor green | ∥ U2/U3 |
| **U5 Transcript Cortex** | U4 + `*.jsonl` | tails live session → `{intent_class, phase, entities, attention}` per turn | after U4 |
| **U6 Subconscious Engine** | U3 + U5 | emits `{C,G,P}` + flags + selections, reproducibly; the §6 schema | after U5 |
| **U7 Inbound hook** | `UserPromptSubmit` + U6 | injects §6 schema (non-gen) within 30s; partial-on-timeout | after U6 |
| **U8 Mid-turn steer** | `PostToolBatch` + U6 | refresh every ~3 steps / critical-fact; terse signal; can block | after U7 |
| **U9 Cockpit (web)** | U6 state/db | non-gen dashboard: C/G/P, flags, plan/task analysis, **pause Opus** | after U6 |
| **U10 Side-effect capture** | hooks §5 + governance/review modules | auto governance/audit/work-track + independent review, no Opus action | ∥ U7+ |
| **U11 Frontier crawl** | `lgwks_ingest` + Camoufox | passes a Cloudflare/DataDome page honest-first; human-auth only on true exhaustion | ∥ anytime |

## 13. First slice (build first, end-to-end)

**U1 + U7-minimal: the loop, with deterministic signals.** `lgwks map "<intent>"` (capability map + world-graph retrieval + deterministic C/G — no BERT yet) wired into the `UserPromptSubmit` hook so a real prompt produces a real injected schema in Opus's context, end-to-end. Proves the subconscious loop today from existing functions; BERT attention (U4/U5) upgrades the `attention` field once CoreML conversion lands. Definition of done: a prompt → hook → non-gen schema visible in context, <1s, tested, with evidence.

## 14. Complexity (honest)

This turns a stateless CLI into a **stateful, concurrent** system (daemon + db + live model runtime). The genuinely-new hard parts are narrow: **(a) BERT runtime (CoreML), (b) the state db, (c) daemon lifecycle/concurrency.** Everything else is *wiring of existing modules* (retrieval, review, governance, ingest, graph). Risk concentrates in statefulness/concurrency (idempotent writes, single-writer db, per-session daemon keying, stale-result guards) — managed by the never-block/degrade discipline (every unit optional until present; `if db exists`). Crucially, the complexity lives in the **cheap baby-model layer, isolated from Opus's loop** — Opus stays simple.
