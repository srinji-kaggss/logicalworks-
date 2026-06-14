# Model Runtime Finalization - 2026-06-13

Status: decision log and packaging direction.

This note records the final model/runtime read after reconciling the existing daemon, PRD surface,
model stack, ingestion stack, and Logic OS direction. It supersedes the shallow reading that treated
the model layer as a future add-on. The model is already built into the graph; the missing work is
turning the built pieces into a governed model mesh inside the daemon.

Important correction: this document does not change model inventory, model law, runtime code, or
deployment defaults. Existing repo-pinned models remain authoritative. Any model named outside the
current repo law is an open slot or candidate reference, not a decision.

## 1. Runtime thesis

The daemon should be packaged as a local AI runtime, not as a single chatbot model.

The shape is:

```text
speech/text/browser/repo/event
  -> daemon event envelope
  -> intent and context compiler
  -> small model or deterministic engine
  -> typed capability proposal
  -> governance gate
  -> action/result event
  -> updated graph, memory, packet, and workflow state
```

That means "Logic AI" is a model system: several small foundational models plus deterministic
runtime layers, storage, event graph, capability gates, and user-facing voice/text ingress.

## 1.1 Why one architecture works, but one transformer is the wrong v1 target

One architecture is the right target because all major parts can share the same runtime invariants:

- every input becomes an event;
- every model has a typed input/output contract;
- every action becomes a capability proposal before it can mutate state;
- every derived fact carries provenance back to source events;
- every agent/client consumes the same context packet shape.

That is what makes the daemon feel like one system even when several models and deterministic engines
are involved. The unity is the protocol and event graph, not a single weight file.

A single transformer is the wrong v1 target because these layers do different jobs with different
trust semantics:

| Layer | Why it should not collapse into one model |
|---|---|
| Storage/event log | Needs hashes, replay, migrations, tenant isolation, and exact causality. A model cannot be the source of truth. |
| Capability execution | Needs explicit effects, reversibility, permissions, and audit. A model can propose, but execution must be typed code. |
| Retrieval/vector space | Needs stable embeddings and space IDs. Changing a generator should not invalidate the whole memory graph. |
| Extraction | Needs schema-valid facts with provenance. Generation quality is not enough; invalid output must fail closed. |
| Voice | ASR is a streaming audio problem. It should feed the daemon, not become the daemon. |
| Code/security review | Static analysis, taint, CFG, tests, and exact call matching are deterministic evidence. LLMs can explain or prioritize, not replace them. |
| Human control | Pause, inspect, undo, approve, and delegate are product/runtime controls, not model weights. |

So the package can be one architecture, one daemon, one install, one HF collection, or one app bundle.
It should not pretend to be one universal model until there is enough event/capability/outcome data to
train a genuine Logic event model. Even then, that model predicts and proposes; the daemon executes.

## 2. Built function gap table with model column

| Built function | What exists | True gap | Model slot and current plug-in |
|---|---|---|---|
| Daemon lifecycle/state | `lgwks_daemon*`, event store, queue, emit, export, packet, adapters | The daemon is still more service/process than mandatory runtime referee. It needs to own ingress, egress, state, and next-agent packets. | No generative model should own this layer. Deterministic state engine plus small classifiers only: `tiny-bert`/intent centroid model for event labels; anomaly/statistical models for failure/stuckness. |
| Transcript cortex | Transcript normalization, session handling, run/query surfaces | Transcript events are captured but not fully converted into live cognition: intent drift, repeated failure, unresolved commitments, useful discoveries. | Current catalog has `neobert` as a research-grade encoder slot for salience/attention. Any summarizer/proposal model is unselected and must be added through model mesh policy. |
| Sensory/input layer | `lgwks_input`, `lgwks_browser`, `lgwks_crawl`, `lgwks_search`, `lgwks_substrate_crawl`, HTML/site tooling | Inputs are tool-shaped. Need one event envelope for browser action, file read, repo diff, CLI output, crawl, user instruction, model output, workflow result. | `LFM2-1.2B-Extract` for schema filling on crawled/unstructured pages; `Qwen3-VL-Embedding-8B` through `lgwks_embed_port` for text/image/video embedding. |
| Code intelligence / IDE graph | `lgwks_codebase`, `lgwks_graph`, `lgwks_entity_graph`, `lgwks_review`, `lgwks_refactor`, repo tooling | The graph exists, but it is not yet a live IDE subconscious continuously updated from edits, tests, imports, ownership, and task state. | Current catalog has `codebert-base` for code embeddings/review features. No coder LLM is selected here; deterministic AST/SAST remains authoritative. |
| Capability map/routing | `lgwks_map`, `lgwks_capability`, capability embeddings, admission, routing pieces | The map is not yet the mandatory execution vocabulary. Runtime action must flow through capability IDs, effects, trust, context, replay, and audit metadata. | Current path: `tiny-bert`/intent classifier plus existing semantic embedder path (`qwen3-embedding:8b` in model-stack law, and/or `Qwen3-VL-Embedding-8B` where the embed port owns the space). Output is route candidates, not actions. |
| Intent/membrane | `lgwks_intent`, `lgwks_intent_classifier`, `lgwks_intent_router`, `lgwks_concept`, `lgwks_machine`, `lgwks_steering`, `lgwks_vault`, HAD | Intent is still too request-local. Missing event-chain intent: sequences across apps that imply latent workflows. | HAD + centroid classifier for closed verbs; graph/sequence models later for event chains. Small LLM may paraphrase intent, but typed IR is deterministic and gated. |
| Workflow/action layer | `lgwks_do`, `lgwks_workflows`, `lgwks_run`, `lgwks_project_*`, `lgwks_spawn`, `lgwks_portal` | Workflows are callable but not compiled from causal patterns. Need App-Intents-like verbs, effects, reversibility, preconditions, event-triggered DAGs. | No foundational LLM in control. Use event-chain scorer, rules, and verifier. A small planner model can propose DAGs; daemon compiles and validates. |
| Model runtime | `lgwks_model_hub`, `lgwks_coreml`, `lgwks_apple`, `lgwks_ollama`, `lgwks_openrouter`, `lgwks_multimodal`, `lgwks_jepa`, `lgwks_lfm2_extract`, `lgwks_embed_port` | The model pieces exist. Missing is the model mesh: contracts, health, routing policy, eval promotion, trust class, and mutation boundaries. | Current model law only: `Qwen3-VL-Embedding-8B`/embed port, catalog encoders (`tiny-bert`, `distilbert`, `codebert`, `neobert`), `LFM2-Extract`, and existing optional provider seams. New models require explicit selection. |
| Embedding/vector/rank | `lgwks_embed_port`, `lgwks_vector`, `lgwks_score`, `lgwks_rank`, capability embeddings | Search primitives exist. Need one query API over text, code, transcripts, events, symbols, facts, and runs. | `Qwen3-VL-Embedding-8B` remains the primary shared vector space where `lgwks_embed_port` owns the contract. Reranker is an unselected slot, not a decided model. |
| Substrate/storage | `lgwks_substrate*`, `lgwks_sqlite`, `lgwks_memory`, `lgwks_cache`, `lgwks_project_artifacts`, CRDT/storage gate | Storage is strong. Missing projection governance: canonical vs derived facts, freshness, invalidation, causal links for every artifact. | No model owns storage. Models may suggest fact extraction; only schema validators, hashes, provenance, and daemon gates promote facts. |
| Governance/security | `lgwks_aup`, gates, `lgwks_sign`, `lgwks_verify`, `lgwks_keyvault`, admission, OWASP/SAST tooling | Authority is not fully unified. Every model suggestion, tool call, browser/session action, repo mutation, and workflow effect should use one capability/effect/provenance gate. | Deterministic gates first. Classifiers/risk models provide evidence. LLM output is untrusted data until converted to typed action and verified. |
| Review/attenuation | `lgwks_review`, `lgwks_verify`, detection algorithms, graph SAST work | Review exists as analysis. Need runtime attenuation: lower trust, require confirmation, route to verifier, sandbox, or block. | Python CFG/SAST engine is authority. `codebert-base`/coder model can help prioritize and explain. Reranker helps triage, not decide. |
| Agent adapters | Codex/Gemini adapters, request context seams, hooks | Adapters exist, but the daemon is not yet the agent substrate. Every agent needs the same canonical packet. | Context packet compiler uses retrieval models plus deterministic budget/waste logic. Optional small LLM compresses packet text; packet schema remains deterministic. |
| Browser/research | search/crawl/browser/public/substrate research tooling | Close to "Google for agents," but needs durable query memory, source trust, TTL, contradictions, already-searched paths, and provenance summaries. | Current slots: `Qwen3-VL-Embedding-8B` for retrieval; `LFM2-Extract` for structured extraction; `lgwks_tongue` for hypothesis/question generation through its existing provider seam. |
| Axiom/WASM bridge | Axiom byte framework, machine language experiments, Logic OS ADR capability-port direction | Need shared event/action ABI. lgwks intent/workflow graph should lower into typed WASM/capability actions with proofs and replay metadata. | No model in the WASM authority path. Model proposals lower to typed IR; WASM executes only validated capability actions. |
| Human uplift/safety | Local-first direction, provider-blind posture, gates, small-model philosophy | Users need inspect, explain, undo, pause, delegate, constrain, and audit. Without that, small models can still become opaque automation. | Voice/text "Tongue" plus cockpit are the human control surface. ASR and small LLMs make it natural; gates make it accountable. |

## 3. Base model architecture slots v1

This is not a replacement model list. It is the architecture slot map. "Current model" means it is
already present in repo docs/code or current model law. "Open" means no model is selected.

| Layer | Current model law / slot | Runtime | Open decision |
|---|---|---|---|
| Universal semantic space | `Qwen/Qwen3-VL-Embedding-8B` via `lgwks_embed_port` | MLX primary, transformers fallback, local weights in `store/models/` | None if we keep current ingestion law; only eval dimensions/space policy remain. |
| Lightweight text intent | `tiny-bert` plus cached intent centroids; current semantic eye law also names local Ollama `qwen3-embedding:8b` | `lgwks_model_hub`, intent classifier, Ollama local where used | Which path becomes product-default vs dev-default. |
| General classifier/gate | `distilbert-base-uncased` | `lgwks_model_hub` | Exact gate tasks and eval corpus. |
| Code intelligence | `codebert-base` | `lgwks_model_hub` | Whether to add a separate code proposal model later; not selected here. |
| Transcript/cortex salience | `neobert` catalog slot | `lgwks_model_hub` research tier | Whether `neobert` is promoted or replaced after eval. |
| Structured extraction | `LiquidAI/LFM2-1.2B-Extract`; optional VL extractor per ingestion docs | llama.cpp/GGUF local worker | Exact local worker packaging. |
| Retrieval rerank | Open slot | Rerank port, local-only | Model not selected. |
| Natural-language proposal/summarizer | Open slot | Local worker or existing provider seam | Model not selected. |
| Code proposal helper | Open slot | Local worker or existing provider seam | Model not selected. |
| Voice ingress | Open ASR slot | MLX, CoreML/WhisperKit, or another local ASR sidecar | Model not selected; only event contract is decided. |

Decision: MLX should be a first-class runtime option for Apple Silicon, especially where existing
model law already points there or where a new local sidecar is explicitly selected later. CoreML/ANE
remains valuable for tiny stable encoders and app-like packaging, but it should not block the daemon.
Ollama remains acceptable where current code/model law already uses it. The product target should
expose runtime-neutral contracts so model choices can change without changing daemon architecture.

## 3.1 Current model surfaces already listed in the repo

This is the inventory this note must not silently replace.

| Surface | Already listed model/runtime | Where it belongs |
|---|---|---|
| Repo-resident encoder catalog | `tiny-bert`, `distilbert-base-uncased`, `codebert-base`, `neobert` | `lgwks_model_hub` local model catalog. |
| Semantic eye / intent path | local Ollama `qwen3-embedding:8b` in the model-stack law | Intent classifier / semantic capability matching where that law applies. |
| Unified multimodal embed port | `Qwen/Qwen3-VL-Embedding-8B`; MLX primary, transformers fallback | `lgwks_embed_port`; shared text/image/video vector space. |
| Extraction | `LiquidAI/LFM2-1.2B-Extract`; optional `LFM2.5-VL-1.6B-Extract` | Crawler/schema extraction, not authority. |
| Apple local seam | `mlx-community/all-MiniLM-L6-v2-4bit` default in `lgwks_apple` | Existing Apple-local embedding seam. |
| CoreML seam | `.mlpackage` text classifier path | Optional local classifier runtime. |
| Tongue provider seam | `lgwks_tongue` through existing provider configuration | Research-language compiler: hypotheses, questions, reason, contrarian. |
| Media/cloud legacy path | OpenRouter/Gemini media embedding paths where current docs/code still name them | Existing seam only; not expanded by this note. |

## 3.2 Model slots missing from the expanded architecture

These are missing slots, not selected models.

| Missing slot | Why the expanded runtime needs it | Current stance |
|---|---|---|
| Voice ASR / Ear | Wispr/Siri-like speech input needs audio -> transcript events with confidence and time spans. | Open slot. Define `lgwks.voice.event.v1` first. |
| Voice activity / command segmentation | Continuous speech needs turn boundaries, pause detection, and command-vs-dictation segmentation. | Open slot; may be deterministic first. |
| Punctuation/cleanup for dictated text | ASR output must become usable daemon text without changing user intent. | Open slot; must preserve raw transcript. |
| Speaker/session attribution | Subconscious/IDE mode needs to know who spoke and which session/task it belongs to. | Open slot; likely runtime metadata before model. |
| Local Tongue replacement | Current Tongue is provider-seamed. A local proposal/summarizer may be needed for fully local runtime. | Open slot; no model selected. |
| Event-chain intent model | Cross-app sequences need latent workflow detection over time, not single-prompt classification. | Open slot; contract before model. |
| Workflow trigger scorer | Event patterns need confidence, preconditions, and "ask vs act" scores. | Open slot; deterministic/rules baseline first. |
| Runtime risk/attenuation scorer | Review findings need to affect authority: block, sandbox, ask human, or downgrade. | Open slot; deterministic gates remain authority. |
| Retrieval reranker | Shared vector recall needs a second-stage ranker for source/query quality. | Open slot; deferred in current model-stack ledger. |
| Context compressor | Agent packets need compact summaries with cited provenance and no hidden mutation. | Open slot; packet schema first. |
| Code proposal helper | IDE mode may need code explanation/proposal beyond embeddings/static analysis. | Open slot; no direct write authority. |
| GUI/browser action grounding | Browser/IDE actions need screen/DOM/action grounding beyond retrieval embeddings. | Open slot; must lower to typed capabilities. |
| Preference/persona memory model | "Subconscious" needs stable user/project preference recall without becoming opaque personalization. | Open slot; storage/provenance first. |
| Eval/distillation model path | Future LogicGPT-1 needs event/capability/outcome traces and held-out evals. | Dataset and eval harness missing before model selection. |

## 4. Tongue layer

The repo already has `lgwks_tongue.py`, but that file is a research-language compiler: hypotheses,
questions, reason-over-findings, contrarian. For voice, the runtime should distinguish:

| Layer | Name | Job | Model |
|---|---|---|---|
| Ear | Speech ingress | Audio -> timestamped transcript event | Open local ASR slot; model not selected in this note |
| Tongue | Natural language compiler | Text/speech -> intent IR, hypotheses, questions, summaries | Existing `lgwks_tongue` provider seam; local replacement not selected |
| Mouth | Spoken response, optional | Daemon state -> short speech/audio | OS TTS first; model TTS later only if needed |
| Hand | Action executor | Typed capability action -> effect | No LLM; deterministic runtime/gates |

So the daemon's "Siri" is not a personified assistant. It is:

```text
microphone/transcript
  -> Ear
  -> daemon event
  -> Tongue compiler
  -> intent/capability proposal
  -> gate/confirmation
  -> action or packet
```

Wispr Flow-like input is achievable as a local sidecar: continuous ASR, punctuation/cleanup,
speaker/session metadata, and command segmentation feeding daemon events. The dangerous part is not
ASR; it is letting natural language bypass capability gates. That must never happen.

## 5. Can this be packaged as "one model"?

Yes as one product artifact. No as one honest HuggingFace transformer in v1.

Possible package shapes:

1. `logic-ai-runtime` Python/CLI package: daemon, event schemas, ports, gates, workflows.
2. `logic-ai-model-pack-v1` HuggingFace collection: pinned model references, configs, checksums,
   small classifier heads, adapters, model cards, eval reports.
3. `logic-ai-daemon-space` or Docker/MLX bundle: demo/runtime packaging with local weights.
4. `logic-ai-event-corpus` dataset: anonymized/synthetic event envelopes, capability actions,
   transcript cortex labels, workflow traces.
5. Later: a distilled "LogicGPT-1" model trained on daemon event traces to predict next intent,
   route, packet summary, or workflow proposal.

The honest v1 is a runtime-plus-model-pack. A future foundational model becomes possible only after
the daemon has produced enough high-quality event traces:

```text
events + capabilities + outcomes + human corrections
  -> train small route/intent/context models
  -> evaluate against deterministic baselines
  -> distill into LogicGPT-1 / Logic Event Model
```

That future model should still not execute. It should predict:

- next likely intent
- relevant context slice
- missing evidence
- candidate capability/action
- risk/confirmation need
- packet summary

The daemon remains the operating system around it.

## 6. Immediate implementation contracts

To finalize this in code, the next contracts should be:

| Contract | Purpose |
|---|---|
| `lgwks.daemon.event_envelope.v1` | One event schema for speech, text, browser, repo, terminal, model, workflow, and artifact events. |
| `lgwks.model.mesh.v1` | Registry of model name, runtime, role, input/output schema, trust class, latency, local/cloud status, and eval gates. |
| `lgwks.context.packet.v1` | Canonical packet consumed by Codex/Gemini/agents/human cockpit. |
| `lgwks.capability.action.v1` | Only executable action contract: verb, subject, effect, reversibility, authority, provenance. |
| `lgwks.workflow.trigger.v1` | Event-chain pattern grammar for latent cross-app workflows. |
| `lgwks.voice.event.v1` | ASR transcript event with audio source, time span, confidence, speaker/session, cleanup provenance. |

## 7. External model/runtime references checked 2026-06-13

These links were checked as runtime feasibility references only. They are not selected model changes.

- MLX Community hosts Apple Silicon-ready model weights: https://huggingface.co/mlx-community
- MLX local server paths exist for some small language/code models.
- MLX embedding variants exist for experimentation.
- MLX and WhisperKit/CoreML ASR packaging exists for future voice-ingress evaluation.

## 8. FINALIZED MODEL PACK v1 — LOCKED 2026-06-13

This is the lockfile for the Director's session-15 finalization (decisions logged in
`BUILDLOG-model-stack.md`). "Locked" = the pinned reference is authoritative; weights are env
artifacts (small ones committed under `models/`; big ones live in gitignored `store/models/` and are
fetched per-machine; gated ones need the operator's HF license + token). We do NOT commit multi-GB
weights to git history. Status legend: `committed` (in `models/`), `store-fetch` (gitignored, setup
step), `gated` (operator must accept license), `pinned` (reference only, not yet fetched).

| Slot | Finalized model | Repo / source | ~Size | Runtime | Trust | Status |
|---|---|---|---|---|---|---|
| Embed / semantic space | Qwen3-Embedding-8B (0.6B phone tier) | `Qwen/Qwen3-Embedding-8B` | ~16GB | mlx→transformers | sensor | store-fetch |
| Rerank | Qwen3-Reranker (0.6/4B) | `Qwen/Qwen3-Reranker-0.6B` | ~1.2GB | mlx/gguf | sensor | pinned |
| Code understanding | codebert-base (live) + Qwen3-Coder (opt) | `microsoft/codebert-base` | ~0.5GB | transformers | sensor | committed |
| Intent / classify | tiny-bert + distilbert (centroids) | repo catalog | ~0.5GB | mlx/transformers | det.-fed | committed |
| Salience / cortex | neobert (research slot) | repo catalog | ~0.9GB | transformers | sensor | committed |
| Extract | LFM2-1.2B-Extract | `LiquidAI/LFM2-1.2B-Extract` | ~1.2GB | llama.cpp | sensor | pinned |
| Ear (ASR) | WhisperKit lg-v3-turbo / Parakeet-TDT-0.6B-v3 | WhisperKit / NeMo Parakeet | ~0.6GB | ANE/MLX | sensor·untrusted | pinned |
| Tongue (translator) | Qwen3-VL (text+vision) — composed, deferring, non-generative | `Qwen/Qwen3-VL-*-Instruct` | tier | mlx | generative·proposal | pinned |
| Mouth (TTS) | Kokoro-82M | `hexgrad/Kokoro-82M` | ~0.3GB | mlx-audio | output | pinned |
| Voice upgrade (Mac) | Moshi (full-duplex) | `kyutai/moshika-*` | tier | local | generative·proposal | pinned |
| Injection guard | det. floor (LIVE) + Llama-Prompt-Guard-2-86M | `meta-llama/Llama-Prompt-Guard-2-86M` | ~0.35GB | transformers | sensor | gated |
| Context-state (learned) | Titans/MIRAS target (det. JSONL+I7 is the live floor) | research target | — | — | deterministic engine | pinned |
| Deep reasoning (owned core) | OLMo-3-32B (4-bit, thinking) — Mac-tier only; hands off to the working agent on weaker devices | `mlx-community/Olmo-3-1125-32B-4bit` | ~18GB | mlx | generative·proposal | pinned (store-fetch, ~32GB+ Mac) |
| Multimodal owned (opt) | Molmo 2 (open recipe) | `allenai/Molmo-2-*` | tier | transformers/mlx | sensor/generative | pinned |
| Reasoning escalation (frontier) | **the working agent** — Claude / Codex / Gemini (operator's pick), the daemon's own client | adapter + context packet path | n/a | agent handoff | conscious layer | live |

Notes: the injection-guard DETERMINISTIC floor is implemented + tested NOW (`lgwks_jailbreak.assess`); the
Prompt-Guard ML layer is the gated upgrade behind the `_ml_injection_score` seam. Big Qwen/OLMo/Moshi
weights are pinned references — run a setup step on each machine to populate `store/models/`. MESH_LAW
(`lgwks_model_mesh.py`) + §3.1/§3.2 promotion of these into formal law is the tracked follow-up.
