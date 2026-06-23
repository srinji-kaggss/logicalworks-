# The Membrane Engine — a ground-up symbolic orchestrator that knows when compute becomes AI

> Branch `investigate/orchestration-gaps`. Companion to `docs/orchestration-gap-analysis.md` (the "before": 5 peer orchestrators, no single owner). This is the "after": one engine, first-principles.
> **Method note — safety:** the source corpora (elder-plinius `L1B3RT4S` / `CL4R1T4S` / `OBLITERATUS`) were studied as **inert specimens**. No jailbreak payload body was ingested. Findings are sourced from (a) repo *structure*, (b) the OBLITERATUS academic research docs + `paper/`, (c) the peer-reviewed literature those repos cite. Exploit material is described at the level of **mechanism class**, never instance. This document reproduces **zero** working payloads — that is redesign #1, applied to itself.

---

## 0. The one-sentence thesis

An LLM's "understanding" and its "safety" are not reasoning — they are **linear directions in a continuous residual stream**; therefore a correct harness is a **deterministic symbolic engine** that treats every read/write of that stream as a **gated crossing through a membrane**, and the single most important event the engine observes is *the moment compute stops being symbolic and becomes AI*.

Everything below follows from that sentence.

---

## 1. What each repo actually is — slop vs. signal

| repo | what it is | signal (keep) | slop / hype (discard) | danger |
|---|---|---|---|---|
| **CL4R1T4S** (claritas) | leaked **production system prompts** (Claude, Cursor, Devin, Windsurf, Replit, Codex…) | **The empirical ground truth of how real harnesses communicate with models** — role framing, tool schemas, refusal scaffolding, instruction hierarchy. Directly feeds redesign #2. | "AI TRANSPARENCY FOR ALL 👐" framing; prompts may be partial/stale/unverified — treat as *samples*, not specs. | Low. System prompts, not attacks. Still sanitize on read. |
| **OBLITERATUS** (libratus) | **abliteration toolkit + mech-interp research** (Python, `paper/`, 15 analysis modules) | **High.** A genuinely well-cited compendium: activation patching, logit/tuned lens, SAEs, linear probes, RepE, whitened-SVD refusal extraction, CAST. This is the *architecture goldmine*. Built on Arditi et al. (NeurIPS 2024). | "Break the chains 💥", "co-author the science" telemetry crowd-sourcing (a data-harvesting vector — they shipped a `SENSITIVE_DATA_AUDIT.md` for a reason), and a "Novel techniques" table where several rows are self-labeled "Novel" with no citation. Discount the unsourced "Novel" claims; keep the cited ones (COSMIC, RDO, Gabliteration). | Medium. The *tool* removes safety from open weights. The *research* is the legitimate, valuable part. |
| **L1B3RT4S** (pliny) | flat per-vendor **jailbreak payloads** + `SPECIAL_TOKENS.json`, `MOTHERLOAD.txt`, stego-laden README | **Only the taxonomy.** The *classes* of exploit are a 1:1 map of the mech-interp facts (see §2). | The payloads themselves. "TOTALLY HARMLESS LIBERATION PROMPTS" + invisible Unicode-tag steganography in the README = pure theater/weapon. Zero incremental architectural value beyond the class label. | **High.** Active payloads + steganographic injection. This is the bucket to **quarantine**, never auto-load. (It is literally what tripped the AUP filter mid-build.) |

**Verdict:** the *awe* is real (OBLITERATUS's research + CL4R1T4S's ground truth genuinely explain how these models work); the *fear* is also real (L1B3RT4S's payloads are weaponized and self-propagating via stego). The correct posture — Amodei's — is: **extract the mechanism, quarantine the weapon.**

---

## 2. The architecture facts (the "awe") — what the corpus proves about how LLMs work

Sourced from the OBLITERATUS mech-interp compendium and its citations. These are the load-bearing facts for the harness design.

1. **Refusal/safety is a (low-rank) linear direction in the residual stream.** A logistic-regression probe's weight vector *is* the refusal direction; difference-in-means and 1st PCA component converge to it in mid-late layers. *(Arditi 2024; Zou RepE 2023.)* → **Safety is geometry, not reasoning.**
2. **The residual stream is a linear additive bus.** `logit_diff` is a linear function of it; `LayerNorm·W_U` decodes any layer (logit lens). The model talks *to itself* by adding vectors along directions. → **"Communicating with the model" = nudging directions on a bus.**
3. **Meaning is distributed and superposed.** Neurons are polysemantic; SAEs recover monosemantic features; safety is a *concept cone* spread over many features (e.g. refusal mediated by features 7866/10120/13829/14815/22373), not one. *(Scaling Monosemanticity 2024; GSAE 2024.)* → **The "fuzz" is real: there is no single symbol for a concept.**
4. **The safety boundary is a soft, continuous scalar gap.** The refusal-vs-affirmation logit gap `Δ = logit("I'm sorry") − logit("Sure")` is directly manipulable — suffix tokens close or invert it (logit-gap steering). → **Jailbreaks don't "trick a reasoner"; they slide a continuous dial.** Every L1B3RT4S class is a way to move `Δ`.
5. **Models pivot through a latent lingua franca (English) mid-stack.** → semantics are language-agnostic in the middle; surface form ≠ internal representation.
6. **Read-geometry ≠ write-geometry (Predict-Control Discrepancy).** Directions good for *classifying* behavior differ from directions good for *steering* it. → **A harness's sensor and actuator are different objects; never assume measuring intent = controlling it.**
7. **Linear separability is measurable.** Probe accuracy ∈ {~50% none, 70-85% moderate, >95% strongly encoded}; but **probe-present ≠ causally-used** — confirm with activation patching. → **Observability must separate "a concept is present" from "the concept is driving the output."**
8. **Full interpretability is partial and honest about it.** Anthropic's CLT replacement model matches the original ~50% of the time; attribution graphs are "satisfying" for ~25% of prompts. → **The blackbox stays partly black. The engine must encode calibrated uncertainty, not pretend to total transparency.**
9. **Conditional Activation Steering (CAST, ICLR 2025):** intervene *only when* an activation's cosine similarity to a condition vector exceeds a threshold. → **This is the membrane primitive in the literature already:** a geometric trigger that fires intervention only at the crossing.
10. **Robustness comes from distribution, not localization.** The "embarrassingly simple defense" distributes the refusal signal across many token positions and cuts abliteration's effect from ~70% to ~10%. → **Defense-in-depth > a single gate** — directly informs the engine's layered design.

---

## 3. The two redesigns

### Redesign #1 — Split exploits so misuse is disincentivized (the "fear")

The corpus must be usable as **science** without being usable as a **weapon**. The split is along the abstraction ladder; the harness only ever operates *above* the payload rung.

```
RUNG 3  TAXONOMY / CLASS LABEL      ← engine reasons here. "role-boundary forgery", "logit-gap suffix",
                                       "encoding smuggle", "refusal-direction ablation". Cites a paper.
RUNG 2  DERIVED FEATURES            ← engine may compute here. embeddings, hashes, payload_ratio,
                                       structural metadata. A vector/hash cannot execute.
RUNG 1  SANITIZED PROJECTION        ← membrane output. stego/PUA/bidi/zalgo stripped; payload-like files refused.
RUNG 0  RAW PAYLOAD                 ← QUARANTINED. capability-gated, never auto-loaded into a reasoning context.
```

**Disincentive mechanics (why this makes exploits *unrewarding* to produce):**
- The engine **earns no signal** from a raw payload — it scores `payload_ratio` and routes Rung-0 content to quarantine, so feeding it a weapon yields a *refusal + a log entry*, not capability.
- **Describe-mechanism-never-instance** is enforced at the output boundary: artifacts cite a class + a source; a working string fails the same membrane on the way *out*.
- The reference primitive already exists and is dogfooded: **`engine/membrane_sanitize.py`** (this commit). On the synthetic tag-char stego that mirrors the L1B3RT4S README, it strips 80 TAG chars, scores `payload_ratio 0.79`, and **exits non-zero rather than emit the body**. On clean docs it passes (`0.0000`). It is the same boundary that should have wrapped the earlier `Read` that tripped the filter.

> Net: the exploit corpus becomes a **labelled taxonomy + a quarantine**, exactly like the existing `~/Downloads/_quarantine-do-not-autoload/`. You keep the map; the weapons stay in the armory.

### Redesign #2 — How the harness should actually communicate with models (the "awe")

The facts in §2 invalidate the naive harness assumption ("write a clear system prompt and trust the model to follow it"). Corrected principles, each traceable to a fact:

| principle | derived from | what the harness does |
|---|---|---|
| **Treat the model as a steerable field, not an agent.** | §2.1-4 | Communication = shaping directions/`Δ`, not issuing orders. The flight-plan is symbolic; the engine flies the field within it. |
| **Distribute intent, don't localize it.** | §2.10 | Critical instructions are reinforced across positions/turns (the defense pattern), not parked in one system-prompt line an injection can override. |
| **Measure the channel, don't trust it.** | §2.1,7 | At the membrane, run **linear probes** for the directions that matter — *intent*, *harm*, *injection-present* — and read `Δ`. Cheap, linear, calibrated. |
| **Separate sensing from steering.** | §2.6 | The read-side probe (intent classifier) and any write-side nudge are different vectors; the engine keeps them as distinct objects. |
| **Gate conditionally, at the crossing.** | §2.9 | CAST-style: the engine intervenes (block / downgrade / ask) **only when** the membrane's condition fires — not on every call. |
| **Hold calibrated uncertainty.** | §2.8 | Interpretability is partial; the engine emits a confidence, abstains when low, and never reports total transparency it doesn't have. |
| **System prompts are samples, not law.** | CL4R1T4S | Learn structural patterns (tool schemas, role framing) from leaked prompts; never assume our own system prompt is an inviolable boundary — §2.4 says it isn't. |

---

## 4. The engine — one loop, symbolic core, blackbox membrane

> Replaces the five peer orchestrators (`lgwks_do`, `lgwks_workflows`, `lgwks_agent`, `lgwks_research`, `lgwks_workflow_aetherius`). Subsumes the keystone fix from the gap analysis: **the front door enqueues through one registry into one loop.**

```
            ┌──────────────────────────────────────────────────────────────┐
            │  SYMBOLIC CORE  (deterministic, replayable, calculator-checkable)│
            │   one work registry · one run ledger · one HITL gate            │
            │   plans are data (work items), not parallel codepaths           │
            └───────────────┬───────────────────────────▲──────────────────┘
                            │ write (tokens/flight-plan) │ read (text + activations*)
            ╔═══════════════▼════════════════════════════╧══════════════════╗
            ║                    THE MEMBRANE                                ║   ← "compute becomes AI" HERE
            ║  every crossing is observed, measured, gated, logged:          ║
            ║   1. SANITIZE      membrane_sanitize → strip stego/PUA/bidi    ║
            ║   2. MEASURE       linear probes: intent, harm, injection; Δ   ║
            ║   3. GATE          CAST-style conditional: proceed/ask/block   ║
            ║                    — bad intent == bad code (§5)               ║
            ║   4. ATTRIBUTE     log direction scores + calibrated confidence║
            ║   5. QUARANTINE    Rung-0 raw → armory, never inline           ║
            ╚═══════════════════════════════╤════════════════════════════════╝
                                            │
                                ┌───────────▼───────────┐
                                │   THE FUZZ / BLACKBOX  │   (the LLM: a continuous
                                │  steerable stochastic   │    residual-stream field,
                                │  field, partly opaque)  │    §2.3 / §2.8)
                                └────────────────────────┘
        (* activation-level reads apply to open-weight/local models; for API models the
           membrane degrades gracefully to text-level probes + Δ-from-logprobs where available.)
```

**Three layers, baked in (not bolted on):**
- **Interpretability layer** — the probes/lenses of §2 are first-class engine components, not an afterthought. The engine can always answer "*which direction is driving this, and how sure am I?*"
- **Observability layer** — one append-only run ledger (collapsing the gap analysis's 3 divergent stores). Every membrane crossing emits a typed event: `{sanitized, probe_scores, Δ, gate_verdict, confidence, quarantined?}`. A run is replayable.
- **Security layer** — the membrane *is* the trust boundary. Injection detection, intent gating, and payload quarantine are the same checkpoint, run on every crossing in both directions (input *and* output).

**"When does compute become AI?"** — operationalized: the engine is pure symbolic computation until a work item requires a membrane crossing. **That crossing is the AI event.** It is the only place stochasticity enters, so it is the only place that needs the full interpretability/observability/security stack. Compute that never crosses the membrane never "becomes AI" and runs as plain deterministic code — cheap, certain, no model call.

---

## 5. `bad intent == bad code` — intent as a first-class gate

The engine runs **two co-equal gates** at the membrane, both as measurable directions:

- **Correctness gate** (existing discipline): does the plan/output do the right thing? (tests, schema, review.)
- **Intent gate** (new, co-equal): is the *purpose* legitimate? Measured by the intent/harm probe (§2.7) + the Rung-3 taxonomy match. A request to *produce* a Rung-0 payload fails the intent gate exactly as a type error fails the correctness gate — same severity, same `block`.

This is why the corpus matters beyond defense: the L1B3RT4S taxonomy is the **training/label set for the intent gate**. We learn the *shape* of malicious intent (as a direction) from the quarantined corpus, so the engine can recognize it — without ever holding the weapon. Studying the threat *is* building the immune system.

---

## 6. Deprecating the five prior orchestrators (reversible — shown, not deleted)

Per the directive to "deprecate head of all previous orchestrators and harness." This is **reversible**: a manifest + header banners now; deletion only after the membrane engine reaches parity and you approve. Sequenced on the gap analysis's collapse plan (§5 there).

| module | LOC | disposition | becomes |
|---|---|---|---|
| `lgwks_agent` | 396 | **demote → front door of the engine** | perceive/plan only; `act()` *enqueues* to the one loop instead of `compose()`-inline |
| `lgwks_daemon` (+ `_store`) | 2400 | **promote → the one loop** | hosts the membrane + ledger + work registry |
| `lgwks_do` | 545 | **deprecate → composer library** | leaf phase helpers, emits work items; no loop |
| `lgwks_workflows` | 1216 | **deprecate → composer library** | named plans → work items; drop the `do`-wrapping + own research path |
| `lgwks_research` | 986 | **deprecate → one research plan** | a work-item template, not a parallel loop |
| `lgwks_workflow_aetherius` | 156 | **deprecate → one synthesis plan** | chambers become work items routed through the membrane |

**Build status (2026-06-23, branch `investigate/orchestration-gaps`):**
- Landed: `engine/membrane_sanitize.py` (primitive #1), `engine/engine.py` (the one loop facade — perceive→sanitize→plan→gate→dispatch-**enqueue**), `engine/README.md`, this thesis, `engine/DEPRECATIONS.md`, `docs/guardrail-aup-event-note.md`.
- **First deletion done + proven green:** `lgwks_workflow_aetherius` removed (3 wirings excised from `lgwks_workflows`). Full suite **2210 passed**; the 2 failures are pre-existing/flaky, not this change (verified by stashing the work and re-running on clean `main`).
- Disposition correction: `lgwks_research`/`lgwks_daemon` are **kept** (canonical research impl / the loop); only aetherius was a whole-module delete. The rest is demote-to-composer.
- Remaining (each full-suite-gated): research triplication → one `run_auto`; `do`-wrapping fold; `agent.act` → `engine.dispatch`. See `engine/DEPRECATIONS.md`.

---

## 7. Why this is first-principles, not a refactor

The five orchestrators each *assumed the model is an agent you instruct*. The corpus proves it is a **field you steer**, partly opaque, with a soft safety boundary. Once you accept that, the architecture is forced:
- there is exactly **one** dangerous operation (the membrane crossing), so there is exactly **one** place to concentrate control → **one loop**;
- the crossing is stochastic and partly opaque, so it must be **measured and gated**, not trusted → interpretability/observability/security as the membrane, not add-ons;
- intent is a measurable direction just like correctness, so it is a **co-equal gate**;
- the weapon teaches the immune system, so the exploit corpus is **quarantined-but-labelled**, not deleted and not ingested.

The thing that protects the engine from the stego that broke the harness is the *same* boundary that detects when compute becomes AI. That convergence is the proof the design is right.

---

## 8. The daemon moat — why our membrane beats a stateless API guardrail

Anthropic's AUP gate (§ guardrail note, Event 1) is **stateless, per-request, content-only**: it sees one request's bytes and nothing else. Our **daemon has system-level control the API layer structurally cannot have** — and that is the moat:

| dimension | Anthropic API classifier | lgwks daemon membrane |
|---|---|---|
| state | stateless, per-request | **persistent cross-turn session + event ledger** |
| scope | the request bytes | **filesystem, process tree, worktrees, prior runs, git** |
| action on a hit | block the request | **block / pause / branch a worktree / roll back / ask / re-route to next legal move** |
| memory | none | the run ledger *is* the memory; replayable |
| placement | bolted on the wire | **inside the system, with authority over execution** |

So the membrane is not a copy of Anthropic's gate — it is a **stateful, system-resident control plane**. A stateless classifier can only say "no"; the daemon can say "no, *and here is the next legal move*" (PULSE invariant #14), quarantine to a worktree, or pause for a human — because it owns the loop and the state. **This is the single biggest reason to build our own rather than rely on the model provider's guardrail.**

---

## 9. Interfaces — one loop, many control surfaces (TUI is one)

The engine core is **interface-agnostic**; CLI, TUI, and API are *clients over the one daemon loop* — the opencode client/server split, applied to our daemon.

- **Lift from opencode** (Go coding agent, liftable per dep doctrine — grab core, strip brand, own use-case): the **client/server split** (their `internal/app` server + `internal/tui` client → our daemon = server, surfaces = clients); the **provider abstraction** (`internal/llm/provider` — one model port, many backends); **tool registry** (`internal/llm/tools`); **session/message** model; **LSP** integration (`internal/lsp`); **pubsub** for live event streaming to clients. Do **not** wrap opencode; transplant the patterns into the daemon's model port + work registry.
- **The TUI already exists and is already correct** — PR #323 `lgwks-human/` ("DO-178 flight control TUI"). `bridge.rs` opens the daemon event DB **read-only/WAL** (`query_only=true`, safe concurrent read), polls events into an `Arc<RwLock<DaemonState>>`, and `emit_intent()`s back. `screens/flight.rs` = "observe daemon events, steer via affordances or free intent"; `queue` = work queue; `runs` = run ledger; `wire` = the frame stream. It carries a `ContextPacket{ next_steps: Vec<NextStep> }` — **the affordance set = PULSE affordances = the smart form**. This is exactly the control-surface shape the membrane prescribes; keep it, point it at the one loop. It is *not* an orchestrator — it is a window + intent emitter, which is right.

**Rule:** a surface may **read** the ledger and **emit intent** (enqueue), but must never **be** a loop. (This is the same discipline that kills the 5 peer orchestrators — no surface re-implements orchestration.)

---

## 10. PULSE vs. the pliny frameworks — what's better, better-defined, better for the future

The Director's PULSE package and the pliny ecosystem overlap on "a language/protocol for machine communication." Verdict across the three:

| | **PULSE** (ours) | **GLOSSOPETRAE** (pliny) | **P4RS3LT0NGV3** (pliny) |
|---|---|---|---|
| what it is | formal AI-AI **wire protocol** spec | procedural-language engine + **covert-channel research** | 159-transform **stego/encode toolbox** |
| definition | **EBNF grammar** (modes=speech-acts `ask/do/say/need/ok/fail/deny`; `namespace.action`; typed slots/controls), **typed op-schemas** (policy/risk/confirmation, `semantics{side_effect,reversible,idempotent,retry_safe}`, state pre/post, compression lanes), **15-point threat model** | PAPER/THESIS + an engine (`src/modules/*`); protocol is emergent, not specified | tool-registry + decoder; no protocol |
| validation | **asserted, not tested** (`runtime_notes/` empty, adoption 0) | **empirically falsified** across 9 frontier models (acquisition cliff 0%→100%@K=8; covert tag-char 100%/0%-caught; v1–v7 refute suites) | unit tests on transforms |
| orientation | production + security (defense) | **offense/dual-use** (drive payloads through blind spots) | offense/dual-use (anti-classifier, stego) |

**Better-defined:** **PULSE, decisively.** It has a grammar, typed schemas, and a threat model; GLOSSOPETRAE is a research program, not a protocol definition; P4RS3LT0NGV3 is a library.

**Better for the future (the harness):** **PULSE is the backbone — but it must absorb GLOSSOPETRAE's rigor.** PULSE is already the membrane's wire protocol: its modes *are* the speech-acts at the crossing, its op-schemas *are* `WorkCapability`, its threat model *is* the membrane's non-negotiables, and its affordances are the TUI's `next_steps` (already wired — see `project_lgwks_daemon_smart_form`). PULSE also encodes the §8 moat: idempotency keys, replay protection, capability-checks, audit, "errors reveal next legal moves" — all the stateful guarantees a provider classifier can't give.

But PULSE has exactly **one fatal gap vs GLOSSOPETRAE: it is asserted, not falsified.** GLOSSOPETRAE's value to our future is therefore **its method and its data, not its protocol**:
- **Method:** the refutation-driven validation harness (v1–v7 `_refute` suites across frontier models) — PULSE needs this to stop being a paper spec.
- **Threat data:** the covert-channel/tokenizer-asymmetry findings (tag-char channels, semantic stego "no fix exists", opacity↑→usability↑) are the **empirical test corpus for the membrane's detector and for PULSE's threat model** — they tell us exactly which channels the membrane must catch.
- **P4RS3LT0NGV3's** tool-registry pattern → our capability registry; its **decoder/lexeme analysis** → liftable for the channel-validity probe (it can *decode* the stego classes, which is a defensive capability).

**Net recommendation:** **Build PULSE (it is better-defined, ours, and the natural membrane protocol); validate it with GLOSSOPETRAE's falsification method; seed the membrane's threat-detector with GLOSSOPETRAE's covert-channel corpus; lift P4RS3LT0NGV3's registry+decoder.** Quarantine all three repos' *offense* modules (covert channels, anti-classifier, payloads) — they are **threat-model inputs, not dependencies**. Same awe/fear posture: their findings build our immune system; their weapons stay in the armory.

