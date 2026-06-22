# NAVMAP — lgwks module atlas (generated; do not hand-edit)

> `scripts/gen_navmap.py` from source — re-run to refresh. **174 modules · 60,873 LOC.** This is the canonical repo map: if someone says "review the map" or "check the navmap", they mean this file unless another map is explicitly named. Read/query this FIRST. Strict machine-readable contract: `docs/navmap/index.json` (`lgwks.navmap.v1`).

**Staleness:** `active` 173 · `staling` 1

Rules — `active`: referenced by another module/dispatcher (static or dynamic), or a tested CLI verb <180d · `scaffolding`: no caller, owned by an open issue · `staling`: no caller anywhere, but built/tested or has a CLI verb, no issue (wire or retire) · `orphan`: no caller, no tests, no CLI, no issue (deletion candidate).

Row legend: `cli` `test` · `←N` imported by N · `→N` imports N · `Nd` days since last commit.

## Per-issue rollup (open canonical issues → owned modules + staleness)

| issue | packet | modules (staleness) |
|---|---|---|
| #72 | I8 | `lgwks_admission` (active), `lgwks_capability` (active) |
| #73 | I9 | `lgwks_crdt` (active) |
| #74 | I10 | `lgwks_viz_project` (active) |
| #75 | I11 | `lgwks_waste` (active) |

## Ingestion spine (I1–I12)  ·  17 mod · 7,364 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_admission` | token-bucket admission + idempotent queue (I8 / I8-hardening L3). | 487 | active | cli test ←3 →3 5d |
| `lgwks_admission_store` | durable cross-process admission queue (I8-hardening L4). | 312 | active | ←1 →4 5d |
| `lgwks_capability` | capability-token tenant isolation boundary (I8). | 306 | active | cli test ←8 5d |
| `lgwks_capability_action` | the execution boundary (#120). | 232 | staling | test →3 8d |
| `lgwks_crdt` | CRDT state: G-Set, OR-Set, LWW-Register (I9). | 409 | active | cli test ←5 9d |
| `lgwks_embed_port` | embedder runtime (lgwks.embed.port.v1). | 726 | active | test ←5 →4 0d |
| `lgwks_extract` | ingest every file format → text. The "read anything" port. | 328 | active | test ←6 →6 0d |
| `lgwks_inbound` | L5 consumer pack: RRF fusion + token-budgeted reflex envelope (I7). | 371 | active | cli test ←3 →4 9d |
| `lgwks_input` | universal input handler (lgwks.modality.item.v1). | 530 | active | ←1 →2 7d |
| `lgwks_pipeline` | unified ingestion and ranking spine. | 1328 | active | cli test ←2 →18 0d |
| `lgwks_promote` | audited tenant→world promotion (ARCH L5, I8-hardening #89). | 146 | active | ←3 →3 9d |
| `lgwks_rank` | cubic node centrality (Z-eigenpair) + AI-discrepancy δ (I6). | 541 | active | cli test ←3 →1 6d |
| `lgwks_score` | deterministic schema scoring: RESCAL order-3 · R_k · MDL (I5). | 382 | active | cli test ←2 6d |
| `lgwks_vector` | vector-space + cid contract (lgwks.vector.record.v1). | 553 | active | ←12 →3 0d |
| `lgwks_viz_project` | deterministic 3-D viz projection, decoupled from semantic space (I10). | 297 | active | cli test ←2 6d |
| `lgwks_waste` | waste ledger: the proof context-optimisation works (I11). | 339 | active | cli test ←3 →1 10d |
| `scripts.build_capability_idf` | freeze the I8 demand-weight table (stdlib only, no AI). | 77 | active | ←5 →2 10d |

## Research / web acquisition / extract  ·  14 mod · 5,463 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_auth_runtime` | read-only auth resolver for crawler fetches. | 225 | active | ←3 6d |
| `lgwks_browser` | bot-resilient, JS-rendering fetch via a real browser (playwright). The eyes for pages | 692 | active | test ←7 →4 0d |
| `lgwks_crawl` | unified crawler dispatcher. | 220 | active | cli test ←2 →5 0d |
| `lgwks_expression` | - lgwks-expression/1 parser and resolver. | 768 | active | ←1 →2 5d |
| `lgwks_files` | the `extract` and `convert` verbs: the read-anything port made into CLI surface. | 121 | active | cli ←1 →1 2d |
| `lgwks_geoexpr` | deterministic geometric-CLI compiler (SPEC-geometric-cli-translator-v1). | 402 | active | cli ←1 →7 5d |
| `lgwks_html` | robust, deterministic HTML-to-Markdown and semantic link/table parser. | 352 | active | test ←5 →1 9d |
| `lgwks_jarvis` | legacy deterministic research graph crawler. | 1116 | active | cli ←2 →11 0d |
| `lgwks_public` | open-license public source layer. | 187 | active | cli ←1 5d |
| `lgwks_search` | the missing primitive: a zero-key, free web + news search provider. | 525 | active | test ←6 →4 7d |
| `lgwks_search_engine` | the 'Web Browser for AIs'. | 126 | active | ←2 →6 4d |
| `lgwks_site_profile` | site configuration profile manager. | 100 | active | ←1 6d |
| `lgwks_sites` | site-aware extractors for high-value platforms. | 195 | active | test ←1 6d |
| `lgwks_substrate_crawl` | web crawl engine, auth-gate detection, and frontier management. | 434 | active | ←2 →4 7d |

## Bots / detection / static analysis  ·  7 mod · 3,080 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `graphify.cluster` | graphify.cluster — Leiden community detection with no silent fallback. | 220 | active | ←2 7d |
| `lgwks_bot_code_hacker` | U5 build #2: enterprise-grade static security analyzer. | 891 | active | test ←2 →4 2d |
| `lgwks_bot_optimizer` | U7: deterministic optimization static analyzer. | 398 | active | test ←1 →1 5d |
| `lgwks_bot_slop_math` | U6: deterministic structural slop-detection bots (S1–S6). | 586 | active | test ←1 →2 5d |
| `lgwks_bot_stress` | U8: Concurrent Stress Bot. | 307 | active | test ←1 →1 5d |
| `lgwks_cohere` | Coherence Engine pipeline (spec-00). | 170 | active | cli test ←1 →5 6d |
| `lgwks_debug` | automated debugging: turn "it's broken" into "here's why + next step." | 508 | active | cli test ←1 →3 0d |

## Axiom byte framework  ·  8 mod · 1,757 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `axiom.__init__` | the standalone byte framework for the Axiom machine-first ISA. | 20 | active | ←17 15d |
| `axiom.capsule` | The Capsule — one typed, content-addressed record. Claim asserts; Hole abstains. The unit the verifier | 171 | active | ←17 15d |
| `axiom.cid` | Content identity (CID) — the address of a node over its CANONICAL bytes. | 52 | active | ←17 15d |
| `axiom.fabric` | The fabric — immutable content-addressed DAG + hash-chained append-only log + the pending→committed | 144 | active | ←17 15d |
| `axiom.varint` | LEB128 base-128 varints — the lowest byte-layer primitive (WASM uses these for all lengths/indices). | 92 | active | ←17 15d |
| `axiom.verify` | The decidable click — the trust core. A capsule attaches IFF this returns ok. Pure, decidable, 0-AI, | 112 | active | ←17 15d |
| `axiom.wire` | Canonical TLV wire — tag-length-value over LEB128 (the WASM section / protobuf TLV shape, but we OWN the | 106 | active | ←17 15d |
| `lgwks_axiom` | CLI harness over the standalone Axiom byte framework. | 1060 | active | cli ←1 →5 5d |

## Graph / AST / code intelligence  ·  9 mod · 6,491 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `graphify.__init__` | — | 4 | active | ←2 11d |
| `lgwks_audit_graph` | U5 Build #5: The Liquid Brain (ADR-sast-003). | 215 | active | test ←1 →2 9d |
| `lgwks_codebase` | semantic codebase database for AI-native code understanding. | 801 | active | cli test ←2 →4 0d |
| `lgwks_entity_graph` | offline document entity graph builder. | 861 | active | cli test ←7 →5 0d |
| `lgwks_graph` | functional, traversable codebase graph with query engine and persistence. | 1619 | active | test ←8 →2 4d |
| `lgwks_graph_viz` | simple localhost graph visualization. | 1207 | active | test ←4 →3 3d |
| `lgwks_refactor` | deterministic AST-based refactoring engine. | 362 | active | cli test ←1 →2 6d |
| `lgwks_repo` | repo lifecycle commands: audit, recover, cleanup, merge, handoff, graph. | 756 | active | cli test ←6 →7 5d |
| `lgwks_review` | graph-aware, spec-bound code review. | 666 | active | cli test ←3 →11 0d |

## Harness / daemon / orchestration  ·  39 mod · 13,396 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `hooks.claude_scope_guard_hook` | Claude PreToolUse hook — blocks scope creep. | 126 | active | test ←8 →2 4d |
| `hooks.claude_stop_hook` | Claude Stop hook — reads JSONL transcript tail and emits transcript_turn events. | 88 | active | test ←8 →3 9d |
| `hooks.claude_tool_hook` | Claude PostToolUse hook — emits tool_call events to the daemon store. | 77 | active | test ←8 →2 8d |
| `hooks.claude_why_hook` | Claude PostToolUse hook — nudges for //why annotations. | 85 | active | test ←8 →2 4d |
| `hooks.codex_inbound` | Codex ingress adapter — thin daemon event emitter for OpenAI Codex CLI hooks. | 70 | active | test ←8 →2 8d |
| `hooks.gemini_inbound` | Gemini ingress adapter — thin daemon event emitter for Google Gemini CLI hooks. | 77 | active | test ←8 →2 9d |
| `hooks.lgwks_subconscious_hook` | vendor-agnostic agent observer. | 146 | active | test ←8 →2 4d |
| `hooks.subconscious_inbound` | Second-harness U7 — subconscious inbound tap (UserPromptSubmit hook). | 115 | active | test ←8 →3 8d |
| `lgwks_agent_os` | fleet startup/bootstrap helpers for the Logical Works prompt layer (#1). | 546 | active | cli test ←2 →3 0d |
| `lgwks_algorithms` | L4 narrow-ML catalog (semantic-escalation-harness stage L4). | 190 | active | test ←1 7d |
| `lgwks_capabilities` | the resolver that fixes "the tool isn't where it should be." | 268 | active | ←6 15d |
| `lgwks_context` | graduated-resolution (LOD) context pack for the next spawn (#9 harness layer). | 199 | active | cli ←2 3d |
| `lgwks_cycle` | project deploy cycle ledger. | 143 | active | ←4 →4 5d |
| `lgwks_daemon` | minimal background lifecycle shell for the referee runtime. | 1344 | active | cli test ←3 →9 0d |
| `lgwks_daemon_event` | normalized daemon event envelope for shared referee runtime. | 373 | active | cli test ←4 →3 5d |
| `lgwks_daemon_export` | content-addressed archive/export tier for daemon runs. | 158 | active | test ←1 →1 7d |
| `lgwks_daemon_store` | durable event log + work queue for the daemon referee runtime. | 1039 | active | test ←3 →3 4d |
| `lgwks_do` | unified orchestrator: code, research, govern, cleanup, ship. | 546 | active | cli ←4 →11 2d |
| `lgwks_dsl` | lightweight Ruby-like DSL for workflow orchestration. | 141 | active | cli ←1 →1 2d |
| `lgwks_engine` | U6: Subconscious Engine (deterministic first slice). | 509 | active | cli test ←4 →7 6d |
| `lgwks_ground` | fused live grounding for the research loop (#9 / harness layer). | 144 | active | ←2 →3 4d |
| `lgwks_had` | Human Assumption Decoder (consultant semantic-escalation-harness, intent math). | 454 | active | test ←1 →5 4d |
| `lgwks_hooks` | audit-first hook system for lgwks. (hardened v2) | 891 | active | cli test ←1 →2 7d |
| `lgwks_map` | U1 Capability Map (second-harness PRD §12). | 106 | active | cli ←4 →2 6d |
| `lgwks_portal` | deterministic portal packets for coding-agent re-entry. | 279 | active | cli test ←2 →3 6d |
| `lgwks_project` | one-prompt project orchestrator front door (re-export shim). | 125 | active | cli ←5 →5 6d |
| `lgwks_project_deploy` | `lgwks project deploy` verb. | 470 | active | ←3 →7 4d |
| `lgwks_project_plan` | `lgwks project plan` verb. | 121 | active | ←3 →2 4d |
| `lgwks_project_review` | `lgwks project review` verb. | 122 | active | ←2 →3 4d |
| `lgwks_repl` | interactive readline harness for lgwks. | 457 | active | test ←3 →4 5d |
| `lgwks_session` | session boundary analyzer (begin / end / summary). | 556 | active | cli test ←4 →5 7d |
| `lgwks_solve` | the first real-world experience: "I have this mess / this thought — prove what happened." | 432 | active | cli test ←5 →6 0d |
| `lgwks_spawn` | AI-AI handoff packet assembler (#9 harness layer). | 207 | active | cli test ←2 →2 12d |
| `lgwks_substrate_run` | build, query, and baseline orchestration for substrate runs. | 862 | active | cli ←5 →12 0d |
| `lgwks_synthesizer` | U9/U9A: LLM reasoning layer & Apple-native/cloud synthesis seam. | 222 | active | test ←1 →3 6d |
| `lgwks_tongue` | the Tongue: an optional OpenRouter LLM compiles hypotheses + the elimination | 236 | active | ←2 →1 6d |
| `lgwks_workercap` | computed worker-slot ceiling from a probed host profile. | 99 | active | ←4 20d |
| `lgwks_workflow_aetherius` | the autonomous intelligence kernel. | 156 | active | cli ←1 →5 7d |
| `lgwks_workflows` | unified AI workflow harness. | 1217 | active | cli ←2 →19 0d |

## Membrane / intent / steering  ·  10 mod · 3,195 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_concept` | deterministic concept extraction and activation steering. | 625 | active | test ←3 →3 0d |
| `lgwks_intent` | schema-driven intent router. A 10-line declaration drives automation. | 554 | active | cli test ←2 →4 0d |
| `lgwks_intent_classifier` | custom English intent classifier for the CLI membrane. | 498 | active | test ←5 →5 4d |
| `lgwks_machine` | the Tier-E MACHINE (build #3, z1). The intent/goal engine — NOT AI. It scores and | 273 | active | test ←2 →2 7d |
| `lgwks_multiply` | the `x` verb: multiply intent instead of issuing it N times. | 204 | active | ←4 →1 20d |
| `lgwks_route` | unified intent routing. | 266 | active | cli ←1 →6 0d |
| `lgwks_steering` | the adjustable control surface, both sides of the membrane. | 101 | active | ←4 20d |
| `lgwks_vault` | hardened INTENT-VAULT store (build #3, enterprise grade). | 403 | active | test ←3 →3 0d |
| `tools.calibrate_intent_thresholds` | calibrate_intent_thresholds.py — validate and calibrate authority thresholds | 117 | active | ←7 →2 4d |
| `tools.train_intent_classifier` | train_intent_classifier.py — training script for the custom English intent classifier. | 154 | active | ←7 →1 19d |

## Governance / gates / refusal / auth  ·  15 mod · 5,025 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_aup` | AUP runtime gate with Defense-in-Depth. | 720 | active | cli test ←3 →4 5d |
| `lgwks_comprehend` | the Comprehension Gate (spec-01). | 203 | active | cli test ←1 →2 6d |
| `lgwks_embed` | deterministic local folder embedding vault. | 201 | active | cli ←6 →7 0d |
| `lgwks_gate` | unified safety and governance gate router. | 95 | active | cli ←1 →5 6d |
| `lgwks_gate_arch` | G1 Architecture gate (spec-00). | 263 | active | test ←1 →1 15d |
| `lgwks_gate_framework` | G3 Framework-Reality gate (spec-00). | 267 | active | test ←1 →1 7d |
| `lgwks_gate_idiom` | G2 Idiom gate (spec-00). | 150 | active | test ←1 →4 5d |
| `lgwks_keyvault` | macOS Keychain-backed secret resolver for runtime API keys (Issue #7). | 132 | active | cli ←6 13d |
| `lgwks_model_port` | the one runtime gateway every cognition request flows through. | 319 | active | test ←11 →6 0d |
| `lgwks_run` | the post-gate execution spine (Issue #7, ADR-001). | 925 | active | cli ←15 →16 0d |
| `lgwks_sign` | keyed integrity for the run log, the vault chain, and gate verdicts (Issue #7). | 53 | active | ←9 21d |
| `lgwks_storage` | D4 Three-Syscall Storage Gate (ADR-068). | 1038 | active | test ←10 →9 0d |
| `lgwks_urlrisk` | G3 scope curator (Issue #7, ADR-001 §5, constitution L9). | 244 | active | ←2 →1 7d |
| `lgwks_verify` | the Verifier oracle (spec-01), hardened with provenance tracking. | 344 | active | cli test ←6 0d |
| `scripts.check_schema_registry` | Registry conformance gate (governance/README.md + docs/schemas/REGISTRY.md rule 4). | 71 | active | ←5 11d |

## CLI / home / membrane surface  ·  5 mod · 3,527 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_foundation` | T3 structured extraction via Apple Foundation Models (macOS 26+, on-device). | 200 | active | cli ←2 13d |
| `lgwks_gh` | GitHub surface: issues, PRs, state maps, hardening, deterministic "what's next". | 900 | active | cli test ←2 →5 0d |
| `lgwks_home` | the launcher. Type `lgwks` (bare) and the whole thing pops up. | 964 | active | test ←4 →9 0d |
| `lgwks_manifest` | the machine-first contract. `lgwks manifest` → one JSON blob an AGENT reads instead | 1346 | active | cli ←6 →5 0d |
| `lgwks_ui` | our own terminal visual language. Deliberately NOT Claude Code. | 117 | active | ←19 16d |

## Substrate / storage / schema  ·  14 mod · 3,895 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_batch` | schema-validated batch execution for real shell commands. | 288 | active | cli ←1 →2 7d |
| `lgwks_cache` | the UNTRUSTED-CACHE store (build #2, z2 evidence / z4 quarantine). | 114 | active | ←2 →1 7d |
| `lgwks_capture` | unified operator-facing capture compiler over substrate + portal. | 183 | active | cli test ←1 →4 0d |
| `lgwks_cognition` | the COGNITION-LOG store (build #2, z4 core). | 190 | active | ←7 →3 5d |
| `lgwks_memory` | deterministic project memory chain (hardened, build #3). | 267 | active | cli test ←3 →6 0d |
| `lgwks_project_artifacts` | shared schemas, JSONL writers, record builders, | 1156 | active | ←11 →5 0d |
| `lgwks_schema` | schema registry for next-agent discovery. | 283 | active | cli test ←7 9d |
| `lgwks_sqlite` | Shared SQLite connection hardening for lgwks durable stores. | 299 | active | ←13 6d |
| `lgwks_substrate` | thin facade re-exporting all substrate sub-modules. | 223 | active | test ←7 →11 3d |
| `lgwks_substrate_config` | constants, paths, regexes, and shared types for substrate runs. | 140 | active | ←23 0d |
| `lgwks_substrate_io` | file system I/O, JSONL/JSON emission, and manifest loading. | 179 | active | ←16 →2 0d |
| `lgwks_substrate_text` | text processing: chunking, scoring, stemming, fact extraction. | 130 | active | ←6 →2 0d |
| `lgwks_substrate_vector` | vector search, vector space identity, and cross-space guards. | 253 | active | ←2 →3 13d |
| `lgwks_tokenizer_registry` | tokenizer/analyzer identity registry. | 190 | active | test ←2 →1 6d |

## Models / runtime (opaque dep)  ·  9 mod · 2,249 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_apple` | Apple-local embedding provider seam. | 153 | active | ←3 →1 0d |
| `lgwks_coreml` | local text classification via CoreML. | 142 | active | ←1 18d |
| `lgwks_jepa` | first executable multi-view JEPA package surface. | 307 | active | cli test ←1 →7 0d |
| `lgwks_model_hub` | repo-resident model loading + developer setup for local CoreML use. | 642 | active | cli test ←4 →3 7d |
| `lgwks_model_mesh` | model law rendered as a single queryable manifest (#119). | 339 | active | test ←4 3d |
| `lgwks_multimodal` | image extraction + multimodal embedding seam. | 350 | active | ←3 →2 5d |
| `lgwks_openrouter` | cloud Tongue via OpenRouter (Issue #7). | 140 | active | ←4 →2 5d |
| `lgwks_openrouter_embed` | optional remote embedding seam via OpenRouter. | 74 | active | test ←2 →3 0d |
| `scripts.build_capability_embeddings` | freeze the Qwen verb-embedding matrix (U6.2 #85). | 102 | active | ←5 →2 10d |

## Dev tooling / scripts  ·  2 mod · 602 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `scripts.gen_navmap` | relational + staleness module atlas for AI navigation (stdlib only). | 354 | active | cli ←5 9d |
| `scripts.setup_models` | setup_models.py — one-time developer script to download and convert models. | 248 | active | ←5 →1 6d |

## Unclassified (triage)  ·  25 mod · 4,829 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_access` | CapabilityPort interface and HMAC impl (#98 / #97 seam). | 558 | active | cli test ←4 →5 0d |
| `lgwks_artifact_tokenized` | canonical tokenized artifact envelope. | 186 | active | test ←4 →1 6d |
| `lgwks_audit` | the one canonical hardened audit-append primitive (#223 family 1). | 94 | active | test ←5 →1 0d |
| `lgwks_chunking` | canonical text chunking strategies. | 262 | active | test ←3 0d |
| `lgwks_cli_introspect` | one source of truth for live CLI parser introspection + the | 144 | active | ←2 0d |
| `lgwks_clock` | the single source of truth for timestamps. | 53 | active | ←22 0d |
| `lgwks_config` | validated YAML config surface (lgwks.config.v1). | 133 | active | test ←3 7d |
| `lgwks_content_extract` | boilerplate-pruning HTML → clean-text extractor. | 353 | active | test ←2 →2 0d |
| `lgwks_cortex` | the Transcript Cortex (PRD-06 U5). | 250 | active | cli ←2 →7 0d |
| `lgwks_fabric_projection` | the universal projection seam for the State Fabric. | 122 | active | ←1 →2 6d |
| `lgwks_fabric_reader` | the unified read surface over the State Fabric. | 241 | active | cli test ←2 →3 0d |
| `lgwks_hashing` | the single source of truth for content hashing. | 88 | active | test ←39 7d |
| `lgwks_inline` | unified payload-inlining resolver. | 136 | active | test ←8 7d |
| `lgwks_jailbreak` | entrypoint injection-risk sensor + abstention verdict. | 174 | active | ←2 →1 5d |
| `lgwks_lexicon` | the one canonical LEXICAL analyzer (word / identifier tokenisation). | 85 | active | ←9 →1 0d |
| `lgwks_oriented` | the basement seam for the Structural Inference Framework (#172). | 186 | active | test ←1 6d |
| `lgwks_phase` | canonical phase-result type and exit-code→verdict policy. | 43 | active | ←2 5d |
| `lgwks_proc` | the single source of truth for safe subprocess invocation. | 41 | active | ←3 7d |
| `lgwks_reasoning_port` | runtime-neutral DEEP-REASONING seam. | 150 | active | test ←2 →1 5d |
| `lgwks_redact` | the single source of truth for credential redaction. | 33 | active | ←4 7d |
| `lgwks_research` | autonomous deep-research loop (Issue #9, parent #7). | 863 | active | cli ←3 →10 0d |
| `lgwks_tokenizer` | the Aetherius Neural Tokenizer (ANT). | 217 | active | ←2 →1 6d |
| `lgwks_transcript` | tail-reader utility for Claude Code JSONL transcript files. | 234 | active | test ←2 0d |
| `lgwks_vecmath` | the single source of truth for vector similarity math. | 138 | active | ←16 0d |
| `scripts.build_model_mesh` | freeze the model law as a queryable manifest (#119). | 45 | active | ←5 →1 8d |
