# Model & LLM Strategy — Full Lifecycle Deep Dive

**Date:** 2026-06-14 · **Status:** strategy brief · **Audience:** senior AI/ML engineer
**Scope:** the complete arc from the **Day-0 borrowed-cognition stack we run today** to the
**from-scratch custom model** (the *Personal Digital Overseer*) trained on our own framework.

> **One-line thesis.** We do **not** build another autoregressive LLM with a bigger context
> window. We build a *persistent, bounded, action-conditioned latent world model* over an
> effectively unbounded personal event stream — and we use frontier LLMs only as a delegated,
> peripheral tongue while we get there. Language is a **lossy ingress**, not the ontology.

Cross-references (existing canonical surfaces this brief extends, do not supersede):
- `docs/jepa-program-map-2026-06-06.md` — program build-down map
- `docs/jepa-scientific-approach-2026-06-06.md` — research doctrine / falsifiable theses
- `docs/jepa-logic-os-alignment-2026-06-06.md` — kernel governance ↔ world-model layer mapping
- `docs/plan-jepa-deployment-path-2026-06-06.md` — deployment path
- `docs/SPEC-tier-e-machine-model-v1.md` — historical Tier-E draft (superseded where it disagrees)
- Source spec for the custom model: `personal_digital_overseer_condensed.json`

---

## 0. The two-sentence positioning

The Personal Digital Overseer is **not a chatbot and not an LLM wrapper**. It is a local-first
latent digital-world overseer whose **native output is ranked future chains and bounded machine
options** — language generation is optional and delegated.

The core research question it answers:

> *How can a tiny persistent model learn what matters, forget what does not, detect dangerous
> chains, simulate possible futures, and improve over time **without rereading a person's entire
> digital history**?*

Everything below is the engineering lifecycle that gets us from "we borrow cognition from
frontier models" (today) to "we own a trained latent world model" (the moat).

---

## 1. Why the obvious approach is architecturally wrong

A senior engineer's first instinct is "long-context LLM + RAG + tools." We reject that as the
*core*, for a measurable reason.

| Dimension | Conventional LLM framing | Our framing |
|---|---|---|
| Mental model | person's life as a **giant prompt** | person's life as an **evolving environment** |
| Context scale | fit history into a window | continuous state over an unbounded stream |
| Est. human-equivalent tokens/month | — | **2B–5B** |
| Cost curve | full self-attention ≈ **O(n²)** in active context | bounded latent state update ≈ **O(1)** per event |
| Native output | text | **ranked future chains + bounded machine options** |

At 2B–5B tokens/month, a Transformer context window is not "expensive" — it is *architecturally
the wrong object*. You cannot pay your way out of O(n²) over a lifelong stream. The shift from
**prompt** to **environment** is the entire bet.

---

## 2. Day 0 — the model strategy we run *today* (borrowed cognition)

Day 0 is deliberately **two AI layers plus a deterministic spine**, and only one of those AI
layers is allowed near the decision math. This is the *sensor-vs-math doctrine* and it is load-
bearing for everything that follows.

```
        ┌──────────────────────── Day-0 stack (2026-06-14) ────────────────────────┐
        │                                                                           │
  text  │   ① Qwen embedding sensor        ② deterministic math engine             │
 ─────────▶  (FROZEN AI, text→vectors)  ─────▶ (calculator-test layer)  ──▶ gate    │
        │        │                              cosine / scoring / I1·I5·I6·I7      │
        │        │                              §6 C/G/N/P → calibrated decision    │
        │        ▼                                                                  │
        │   ③ The "Tongue" — FREE harnessed frontier models (Opus/Sonnet/etc.)     │
        │      peripheral: parse intent · explain · draft · creative overflow      │
        │      insight-or-silence membrane; never invents state                    │
        └───────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Layer ① — the embedding sensor (frozen AI)
- A pretrained **Qwen embedding model** turns text into vectors. It is a **frozen sensor**: we do
  not train it, we do not let it make decisions. It is exempt from the determinism bar precisely
  *because* it is treated as a measuring instrument, not a judge.
- Analogy for the reviewer: this is the camera, not the pilot.

### 2.2 Layer ② — the deterministic math engine (the spine)
- Consumes the sensor's vectors and produces every runtime decision: cosine similarity (normalized,
  clamped, finite-guarded), the invariant scores (I1/I5/I6/I7), the §6 C/G/N/P signals, and a
  **calibrated gate** that bottoms out in *human / default*, never "mandatory AI."
- Held to the **Calculator Test**: every runtime value must be reconstructable by a human with the
  data, a calculator, and zero internet. This bars magic constants, LLM-distilled weights, and
  non-deterministic scoring from the decision path. (The embedding layer is the *only* exemption.)

### 2.3 Layer ③ — the Tongue (delegated frontier language)
- Language generation is **peripheral and delegated** to FREE harnessed frontier models. Its only
  jobs: parse human intent when required, explain a decision, draft/communicate through an external
  model, and absorb creative or broad-reasoning overflow.
- **Non-goal:** recreate frontier text generation locally. We will never out-pretrain a frontier
  lab on web text, and we don't try.
- Governed by an *insight-or-silence* membrane: the Tongue may narrate only cited, already-proven
  facts; it never invents state. (Same discipline that makes `solve_git` abstain rather than
  hallucinate.)

### 2.4 What "Day 0" honestly means
Today we **borrow cognition**. The intelligence in the loop is mostly the frozen embedder plus a
rented frontier model. We own the *math spine, the gate, the governance, and the data pipeline* —
but not a single proprietary trained world-model weight. The rest of this document is the plan to
change that without ever betting the product on a single giant model.

---

## 3. The target — the Personal Digital Overseer (from-scratch model)

### 3.1 The native loop (this is the product, not a feature)
```
observe_event → encode_event → update_bounded_latent_state → estimate_surprise
   → selectively_write_or_retrieve_memory → simulate_candidate_future_chains
   → rank_options → emit_bounded_machine_decision → delegate_language_only_when_needed
```

### 3.2 Core architecture pipeline
```
typed_event_stream
  → domain_event_encoders
  → persistent_bounded_latent_state
  → selective_state_space_or_recurrent_update
  → prediction_error_estimator
  → surprise_driven_memory_router
  → episodic_causal_chain_memory
  → candidate_action_simulator
  → future_state_scorer
  → option_ranker
  → bounded_machine_output
```

State dynamics (the two equations a reviewer should hold onto):

- **State update:** `z_{t+1} = F(z_t, e_t, optional a_t)` — bounded latent state, one event at a time.
- **Action-conditioned rollout:** `z_{t+k} ≈ G(z_t, a_t, a_{t+1}, …, a_{t+k-1})` — simulate
  futures under candidate action sequences.

Native output is **ranked future chains**, e.g.:

| option | predicted_state_delta | confidence |
|---|---|---|
| `restrict_scope` | lower_risk | 0.91 |
| `allow` | uncertain_exfiltration_path | 0.66 |
| `deny` | feature_breakage | 0.97 |

The model **ranks and predicts**; it does not execute. (See §4 authority split.)

### 3.3 Memory hierarchy (how it forgets on purpose)
| Layer | Retention | Content |
|---|---|---|
| immediate scratchpad | seconds–minutes | recent high-resolution events |
| active latent world state | continuous | current beliefs, risks, open loops, user context |
| compressed episodic memory | selective | anomalies, corrections, meaningful chains |
| slow personal adaptation | days–weeks | validated recurring patterns, micro-learnings |
| encrypted raw event archive | policy-controlled | forensic retrieval only, **not** live context |

**Retention policy:** low-surprise → compress aggressively; high-surprise → retain trace, inspect
chain, consider an episode write; **slow-burn risk → track combinations of individually-normal
events** (the class of threat a stateless model structurally cannot see).

### 3.4 The three model roles
- **Guardian** — observe OS/app events, detect malicious/unexpected chains, propose scope
  reduction / block / escalation.
- **Steward** — maintain private personal state, recognize relevant context, select tools/actions
  *within grants*, preserve unresolved loops.
- **Learner** — extract private micro-learnings, validate local behavior changes, submit opt-in,
  privacy-safe modules to the cooperative pipeline.

### 3.5 Authority split (non-negotiable seam)
| Actor | May |
|---|---|
| **model** | infer, predict, rank, recommend, learn |
| **runtime** | grant, constrain, execute, revoke, record |
| **human** | authorize constitution, approve sensitive actions, override or revoke |

The model never executes and never widens its own authority. This is the same kernel discipline as
`adr-072` (constitutional intent transformer): *the learned layer proposes alignment; deterministic
control remains final.*

---

## 4. Security & governance (hard rules the architecture must enforce)

Enforcement pattern: `event_emitter → local_state_update → model_detects_suspicious_chain →
deterministic_policy_runtime_checks_grants → allow/narrow/approve/block/revoke → append_only_receipt`.

Capability grant fields: `actor, capability, scope, duration, onward_transfer, network_export`.

**Hard rules (the model physically cannot):**
- widen its own permissions
- alter audit receipts
- silently upload private state
- infer consent from inactivity
- escalate to cloud invisibly or un-scoped (escalation must be visible *and* scoped)
- block the user from export / delete / revoke

These map 1:1 onto the existing Logic OS capability-port / receipt model — this is *why* lgwks and
the kernel converge rather than compete.

---

## 5. Device tiers — "more compute expands depth, not authority"

Every tier shares the **same contract**: event language, latent-state contract, memory format,
capability runtime, receipt schema, delegation protocol, privacy boundary.

| Tier | Active params | Responsibilities |
|---|---|---|
| **phone floor** | 100M–1B | continuous state, event compression, salience, lightweight anomaly detection, routing/delegation |
| **local deeper module** | 1B–4B | complex chain simulation, heavier retrieval, micro-learning consolidation, sandboxed reasoning |
| **laptop / home server** | — | richer memory graph, larger working set, adapter training, complex personal analysis |
| **cooperative / cloud** | — | aggregate opt-in modules, validate shared updates, train shared backbone / distilled variants, large-scale adversarial eval |

The phone floor (100M–1B active params) is the design constraint everything else negotiates
against. A reviewer should read the tiers as *the same model contract at different depths*, not as
four different models.

---

## 6. The learning system — four timescales, no uncontrolled online weight mutation

| Timescale | What changes |
|---|---|
| ms–seconds | latent state update (`F`) |
| minutes–days | episodic memory write |
| days–weeks | personal micro-learning consolidation |
| weeks–months | cooperative model improvement |

**Micro-learning flow:**
`episode → candidate_micro_learning → local_validation → attach_bounded_adapter_or_memory_rule →
evaluate → retain/quarantine/discard → optional_privacy_safe_submission → cooperative_review_and_aggregation → signed_shared_update`

**Share classes:** `private` (stays local) · `shareable_abstract` (generalized causal pattern,
post-consent) · `safety_critical` (minimal reproducible signal for fast review + distribution).

The key engineering stance: adaptation happens via **bounded adapters and memory rules with a
validate/quarantine gate**, never by mutating the backbone weights online. This is what keeps a
self-improving personal model from drifting or being poisoned.

---

## 7. Research positioning — what we borrow, what is novel

**Adjacent work we stand on:** JEPA-style latent prediction (I-JEPA), LLM-JEPA, Mamba (selective
state spaces), RWKV (recurrent inference), Transformer-XL (segment recurrence), Titans (test-time
memory), MuZero (latent planning), Dreamer (world models), V-JEPA 2 (action-conditioned prediction).

**Core claim:** a personal digital intelligence should be trained as an *action-conditioned
recurrent latent world model with selective surprise-driven memory and focused local attention*,
**not** as an autoregressive LM with a gigantic context window.

**Novelty boundary (state this precisely to the reviewer):** the new core is **not** "LLM +
retrieval + tools." It is trained to *update and predict a bounded digital-world state over an
effectively unbounded event stream.* None of the adjacent systems solves the full personal digital
overseer problem — we are composing them toward a target none of them targets.

**Candidate research contributions:**
- bounded persistent latent state for lifelong digital streams
- surprise-driven memory that catches slow-burn chains
- learned causal-chain representation without full-history attention
- action-conditioned future simulation
- stable modular micro-learning without uncontrolled online weight mutation
- cross-device binning under one latent-state contract
- privacy-preserving cooperative module aggregation

**Attention's role is deliberately small:** a *focused local tool* over a small retrieved working
set (comparing recent causal chains, precise anomaly explanation) — **never** full-history attention.

---

## 8. Training the from-scratch model

### 8.1 Curriculum (staged; each stage gated on beating the prior baseline)
1. train typed event encoders
2. train recurrent / selective-state-space state updates
3. train prediction-error & surprise scoring
4. train action-conditioned future-state prediction
5. train option ranking (safety, usefulness, reversibility, uncertainty-reduction, user prefs)
6. train memory consolidation & retrieval
7. train cross-device delegation
8. train local micro-learning validation
9. aggregate opt-in cooperative modules
10. **scale only after ablation beats simpler baselines**

### 8.2 The data moat (this is the actual competitive asset)
Start with a **small controlled synthetic digital universe**, then graduate to validated real
trajectories. Event domains: OS events, app permissions, file mutations, calendar, email, browser,
network patterns, identity events, tool invocations, plus **benign / malicious / ambiguous chains**
and **human overrides**.

Trajectory schema: `initial_state, event_sequence, candidate_actions, observed_outcomes,
preferred_action, prediction_error, causal_chain_label`.

> **Key data moat:** *clean, privacy-safe, causally-grounded digital trajectories — not generic web
> text.* This is the asset a frontier lab does **not** have and cannot scrape. It is also exactly
> what the Day-0 lgwks stack already produces as a byproduct (see §10).

### 8.3 Feasibility — what we can build *without* a cluster
**Feasible on owned/modest hardware:**
- 10M–100M param architecture experiments
- 100M–1B phone-class core
- 1B–4B selectively-invoked reasoning modules
- event encoders, memory router, anomaly heads, future-state heads, option ranker, simulator
- LoRA / QLoRA adaptation, distillation

**Requires cluster-class compute (rent / cooperative / academic / grant / partner — ownership not
required):**
- competitive 20B–50B pretraining from random init
- large-scale multimodal pretraining
- massive event-corpus backbone training
- broad ecosystem-scale shared updates

The honest framing for the reviewer: **the entire core thesis is testable without a cluster.** A
cluster only buys the commodity (large pretraining), and that is rentable, not foundational.

### 8.4 Ablation ladder (the experiment that proves/refutes the bet)
```
A  rules only
B  A + small anomaly model
C  B + recurrent latent state
D  C + episodic retrieval
E  D + action-conditioned future-state head
F  E + option ranking
G  F + personal micro-learning
H  G + cooperative aggregation
I  H + hybrid focused-attention planner
```
We do not get to claim the world-model wins until each rung beats the rung below it on the metrics
in §8.5. Rung A (rules only) is the skeptic's baseline and must be beaten honestly.

### 8.5 Success metrics
future-state prediction accuracy · anomaly precision/recall · **slow-burn chain detection rate** ·
false-positive rate · memory-retention efficiency · future-chain ranking quality · **energy/event**
· **latency/event** · **phone-class memory footprint** · delegation quality · privacy-leakage rate ·
poisoning resistance · cross-device state consistency.

(Note how many metrics are *systems* metrics — energy, latency, footprint. This is a systems-first
program, not a leaderboard-first one.)

### 8.6 Build order (engineering sequence)
```
define typed event protocol → build simulated digital environment → train tiny recurrent baseline
→ test state retention WITHOUT history replay → add surprise memory → add chain retrieval
→ add action-conditioned prediction → add option ranking → benchmark under phone constraints
→ add device tiers → collect validated trajectories → scale only after measured gain
```

---

## 9. Open-source posture & external data

Distinguish three things precisely (reviewers conflate them constantly):
- **open weights** = downloadable trained parameters
- **open training data** = redistributable corpus
- **open recipe** = data pipeline + architecture code + checkpoints + logs + evals + post-training flow

For any web-text component (only ever feeding the *peripheral* language path, never the core world
model), the raw source is **Common Crawl** (WARC = raw HTTP; WAT = metadata/links; WET = plaintext).
Recommendation: WET for text-encoder experiments, WARC for document-structure research, WAT for
graph/trust research; download small subsets first, never full crawls.

The data-pipeline cost is real and is *the* hard part of any web-text use: HTML extraction, spam
filtering, exact + fuzzy dedup, quality scoring, language/domain balancing, **benchmark-
contamination removal**, privacy/safety filtering, tokenization, sharding, high-throughput
distributed loading. Open references to copy from rather than reinvent: **FineWeb / FineWeb2, Dolma,
OLMo** (OLMo is the model to study for a fully-open recipe).

---

## 10. The bridge — how Day-0 feeds the from-scratch model

This is the part most strategy docs miss, and the part a senior engineer will probe hardest: *how
do you get from borrowed cognition to a trained world model without a chicken-and-egg data problem?*

1. **The Day-0 stack is the trajectory factory.** Every time lgwks observes events, scores them
   with the deterministic spine, asks the Tongue to narrate, and a human approves/overrides, it
   emits exactly the trajectory schema in §8.2 — `event_sequence + candidate_actions +
   preferred_action + causal_chain_label + human_overrides`. We are *already* logging the data moat
   as a byproduct of normal operation (dogfooding).
2. **The frozen embedder bootstraps the event encoders.** Stage-1 typed event encoders can be
   distilled from / initialized against the Qwen sensor's representations, then specialized — we do
   not start the encoder from random init.
3. **The Tongue becomes the teacher, then the fallback.** Frontier models supply labels, intent
   parses, and explanations during early stages (distillation targets). As the local model wins
   rungs on the ablation ladder, the Tongue recedes to its non-goal-bounded role: overflow and
   communication only.
4. **The governance seam never moves.** The deterministic gate, capability runtime, and receipts in
   §4 are identical Day-0 and Day-N. We swap *what proposes* (Tongue → trained overseer) without
   touching *what authorizes* (runtime + human). That is what makes the migration safe and
   incremental rather than a rewrite.

In short: **Day 0 is not a throwaway prototype — it is the labeled-data generator, the encoder
bootstrap, and the teacher for the model that eventually replaces its borrowed cognition.**

---

## 11. Lifecycle timeline (anchored to relevant dates)

| Date / phase | Milestone |
|---|---|
| **2026-06-06** | JEPA program established — program map, scientific approach, kernel alignment, deployment path docs (the research scaffold this brief sits on) |
| **2026-06-14 (Day 0, today)** | Borrowed-cognition stack in production: frozen Qwen sensor + deterministic math spine + delegated Tongue; `lgwks_jepa` package surface executable; trajectory logging begins as byproduct |
| **Near term (build order §8.6)** | typed event protocol → simulated digital universe → tiny recurrent baseline → **prove state retention without history replay** (the make-or-break early experiment) |
| **Then (ablation A→F)** | rules-only baseline → anomaly model → recurrent latent state → episodic retrieval → action-conditioned future head → option ranking; benchmark under phone constraints (100M–1B) |
| **Mid term (ablation G→H, learning §6)** | personal micro-learning (days–weeks), cooperative aggregation (weeks–months), device tiers under one contract |
| **Long term (ablation I + §8.3 cluster work)** | hybrid focused-attention planner; cluster-class workloads (20B–50B from-scratch pretrain, multimodal, ecosystem-scale shared updates) — **only after measured gain**, on rented/cooperative/grant compute |

The timeline is **gated, not calendared**: every transition is conditioned on an ablation rung
beating the one below it (§8.4) on the §8.5 metrics. We do not promise dates we cannot earn with
evidence; "scale only after measured gain" is the governing clause.

---

## 12. What to push back on (pre-empting the reviewer's hardest questions)

- *"Why not just use a long-context LLM?"* → §1. O(n²) over 2B–5B tokens/month is the wrong object,
  not an expensive one.
- *"Isn't a tiny model just worse?"* → We are not competing on open-ended generation. On the native
  task (bounded state prediction + chain ranking + anomaly detection over a personal stream) the
  ablation ladder (§8.4) is the proof obligation, and rung A (rules only) keeps us honest.
- *"Where's the training data?"* → §8.2 + §10. The moat is clean causally-grounded trajectories the
  Day-0 stack already generates; not scraped web text.
- *"Can you afford to train this?"* → §8.3. The full thesis is testable without a cluster; cluster
  work is the rentable commodity tail, not the foundation.
- *"How is self-improvement not a safety/poisoning disaster?"* → §6. Bounded adapters + memory rules
  + validate/quarantine gate, never online backbone mutation; §4 hard rules are runtime-enforced.

---

## Sources

| Title | URL |
|---|---|
| Mamba: Linear-Time Sequence Modeling with Selective State Spaces | https://arxiv.org/abs/2312.00752 |
| RWKV: Reinventing RNNs for the Transformer Era | https://arxiv.org/abs/2305.13048 |
| Transformer-XL | https://arxiv.org/abs/1901.02860 |
| Titans: Learning to Memorize at Test Time | https://arxiv.org/abs/2501.00663 |
| I-JEPA | https://arxiv.org/abs/2301.08243 |
| LLM-JEPA | https://arxiv.org/abs/2509.14252 |
| MuZero | https://arxiv.org/abs/1911.08265 |
| DreamerV3 | https://arxiv.org/abs/2301.04104 |
| V-JEPA 2 | https://arxiv.org/abs/2506.09985 |
| LoRA | https://arxiv.org/abs/2106.09685 |
| Common Crawl Get Started | https://commoncrawl.org/get-started |
| FineWeb | https://huggingface.co/datasets/HuggingFaceFW/fineweb |
| FineWeb2 | https://huggingface.co/datasets/HuggingFaceFW/fineweb-2 |
| Dolma | https://allenai.org/dolma |
| OLMo | https://allenai.org/olmo |

*Source spec: `personal_digital_overseer_condensed.json`. This brief extends the 2026-06-06 JEPA
program docs; on any conflict, the JEPA program map and the Logic OS kernel governance ADRs win for
control-plane semantics, and this document governs the model-strategy narrative only.*
