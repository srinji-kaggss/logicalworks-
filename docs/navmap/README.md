# NAVMAP — lgwks module atlas (generated; do not hand-edit)

> `scripts/gen_navmap.py` from source — re-run to refresh. **167 modules · 57,086 LOC.** This is the canonical repo map: if someone says "review the map" or "check the navmap", they mean this file unless another map is explicitly named. Read/query this FIRST. Strict machine-readable contract: `docs/navmap/index.json` (`lgwks.navmap.v1`).

**Staleness:** `active` 165 · `orphan` 1 · `staling` 1

Rules — `active`: referenced by another module/dispatcher (static or dynamic), or a tested CLI verb <180d · `scaffolding`: no caller, owned by an open issue · `staling`: no caller anywhere, but built/tested or has a CLI verb, no issue (wire or retire) · `orphan`: no caller, no tests, no CLI, no issue (deletion candidate).

Row legend: `cli` `test` · `←N` imported by N · `→N` imports N · `Nd` days since last commit · `🧠` Cognition · `📡` Events · `👁️` UI.

## Per-issue rollup (open canonical issues → owned modules + staleness)

| issue | packet | modules (staleness) |
|---|---|---|
| #72 | I8 | `lgwks_admission` (active), `lgwks_capability` (active) |
| #73 | I9 | `lgwks_crdt` (active) |
| #74 | I10 | `lgwks_viz_project` (active) |
| #75 | I11 | `lgwks_waste` (active) |

## Ingestion spine (I1–I12)  ·  17 mod · 7,308 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_admission` | token-bucket admission + idempotent queue (I8 / I8-hardening L3). | 487 | active |  | cli test ←3 →3 1d |
| `lgwks_admission_store` | durable cross-process admission queue (I8-hardening L4). | 312 | active |  | ←1 →4 1d |
| `lgwks_capability` | capability-token tenant isolation boundary (I8). | 306 | active |  | cli test ←7 1d |
| `lgwks_capability_action` | the execution boundary (#120). | 232 | staling | 📡 | test →3 4d |
| `lgwks_crdt` | CRDT state: G-Set, OR-Set, LWW-Register (I9). | 409 | active | 🧠 | cli test ←5 5d |
| `lgwks_embed_port` | embedder runtime (lgwks.embed.port.v1). | 687 | active |  | test ←5 →3 1d |
| `lgwks_extract` | ingest every file format → text. The "read anything" port. | 318 | active |  | test ←6 →6 1d |
| `lgwks_inbound` | L5 consumer pack: RRF fusion + token-budgeted reflex envelope (I7). | 371 | active |  | cli test ←3 →4 5d |
| `lgwks_input` | universal input handler (lgwks.modality.item.v1). | 530 | active |  | ←1 →2 3d |
| `lgwks_pipeline` | unified ingestion and ranking spine. | 1328 | active |  | cli test ←1 →17 1d |
| `lgwks_promote` | audited tenant→world promotion (ARCH L5, I8-hardening #89). | 146 | active | 🧠 | ←3 →3 5d |
| `lgwks_rank` | cubic node centrality (Z-eigenpair) + AI-discrepancy δ (I6). | 541 | active |  | cli test ←3 →1 1d |
| `lgwks_score` | deterministic schema scoring: RESCAL order-3 · R_k · MDL (I5). | 382 | active |  | cli test ←2 1d |
| `lgwks_vector` | vector-space + cid contract (lgwks.vector.record.v1). | 546 | active |  | ←11 →3 1d |
| `lgwks_viz_project` | deterministic 3-D viz projection, decoupled from semantic space (I10). | 297 | active |  | cli test ←2 1d |
| `lgwks_waste` | waste ledger: the proof context-optimisation works (I11). | 339 | active | 🧠 | cli test ←3 →1 6d |
| `scripts.build_capability_idf` | freeze the I8 demand-weight table (stdlib only, no AI). | 77 | active |  | ←4 →2 5d |

## Research / web acquisition / extract  ·  13 mod · 5,177 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_auth_runtime` | read-only auth resolver for crawler fetches. | 225 | active |  | ←3 1d |
| `lgwks_browser` | bot-resilient, JS-rendering fetch via a real browser (playwright). The eyes for pages | 637 | active |  | test ←6 →3 1d |
| `lgwks_crawl` | unified crawler dispatcher. | 110 | active |  | cli test ←2 →3 1d |
| `lgwks_expression` | - lgwks-expression/1 parser and resolver. | 768 | active |  | ←1 →2 1d |
| `lgwks_files` | the `extract` and `convert` verbs: the read-anything port made into CLI surface. | 101 | active |  | ←1 →1 1d |
| `lgwks_geoexpr` | deterministic geometric-CLI compiler (SPEC-geometric-cli-translator-v1). | 402 | active |  | cli ←1 →7 1d |
| `lgwks_html` | robust, deterministic HTML-to-Markdown and semantic link/table parser. | 352 | active |  | test ←3 →1 4d |
| `lgwks_jarvis` | legacy deterministic research graph crawler. | 1139 | active |  | cli ←1 →2 1d |
| `lgwks_public` | open-license public source layer. | 189 | active |  | cli ←1 1d |
| `lgwks_search` | the missing primitive: a zero-key, free web + news search provider. | 525 | active |  | test ←5 →4 2d |
| `lgwks_site_profile` | site configuration profile manager. | 100 | active |  | ←1 2d |
| `lgwks_sites` | site-aware extractors for high-value platforms. | 195 | active |  | test ←1 1d |
| `lgwks_substrate_crawl` | web crawl engine, auth-gate detection, and frontier management. | 434 | active |  | ←2 →4 3d |

## Bots / detection / static analysis  ·  7 mod · 2,991 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `graphify.cluster` | graphify.cluster — Leiden community detection with no silent fallback. | 220 | active |  | ←2 3d |
| `lgwks_bot_code_hacker` | U5 build #2: enterprise-grade static security analyzer. | 800 | active |  | test ←2 →4 1d |
| `lgwks_bot_optimizer` | U7: deterministic optimization static analyzer. | 398 | active |  | test ←1 →1 1d |
| `lgwks_bot_slop_math` | U6: deterministic structural slop-detection bots (S1–S6). | 586 | active |  | test ←1 →2 1d |
| `lgwks_bot_stress` | U8: Concurrent Stress Bot. | 307 | active |  | test ←1 →1 1d |
| `lgwks_cohere` | Coherence Engine pipeline (spec-00). | 170 | active | 🧠 | cli test ←1 →5 1d |
| `lgwks_debug` | automated debugging: turn "it's broken" into "here's why + next step." | 510 | active | 👁️ | cli test ←1 →2 2d |

## Axiom byte framework  ·  8 mod · 1,757 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `axiom.__init__` | the standalone byte framework for the Axiom machine-first ISA. | 20 | active |  | ←17 11d |
| `axiom.capsule` | The Capsule — one typed, content-addressed record. Claim asserts; Hole abstains. The unit the verifier | 171 | active |  | ←17 10d |
| `axiom.cid` | Content identity (CID) — the address of a node over its CANONICAL bytes. | 52 | active |  | ←17 11d |
| `axiom.fabric` | The fabric — immutable content-addressed DAG + hash-chained append-only log + the pending→committed | 144 | active |  | ←17 10d |
| `axiom.varint` | LEB128 base-128 varints — the lowest byte-layer primitive (WASM uses these for all lengths/indices). | 92 | active |  | ←17 11d |
| `axiom.verify` | The decidable click — the trust core. A capsule attaches IFF this returns ok. Pure, decidable, 0-AI, | 112 | active |  | ←17 11d |
| `axiom.wire` | Canonical TLV wire — tag-length-value over LEB128 (the WASM section / protobuf TLV shape, but we OWN the | 106 | active |  | ←17 10d |
| `lgwks_axiom` | CLI harness over the standalone Axiom byte framework. | 1060 | active |  | cli ←1 →5 1d |

## Graph / AST / code intelligence  ·  9 mod · 6,264 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `graphify.__init__` | — | 4 | active |  | ←2 7d |
| `lgwks_audit_graph` | U5 Build #5: The Liquid Brain (ADR-sast-003). | 215 | active |  | test ←1 →2 4d |
| `lgwks_codebase` | semantic codebase database for AI-native code understanding. | 756 | active |  | cli test ←1 →3 1d |
| `lgwks_entity_graph` | offline document entity graph builder. | 731 | active |  | cli test ←7 →4 1d |
| `lgwks_graph` | functional, traversable codebase graph with query engine and persistence. | 1570 | active |  | test ←8 →2 1d |
| `lgwks_graph_viz` | simple localhost graph visualization. | 1205 | active | 👁️ | test ←4 →3 6d |
| `lgwks_refactor` | deterministic AST-based refactoring engine. | 362 | active | 👁️ | cli test ←1 →2 1d |
| `lgwks_repo` | repo lifecycle commands: audit, recover, cleanup, merge, handoff, graph. | 756 | active | 👁️ | cli test ←7 →7 1d |
| `lgwks_review` | graph-aware, spec-bound code review. | 665 | active | 👁️ | cli test ←3 →10 1d |

## Harness / daemon / orchestration  ·  36 mod · 12,038 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `hooks.claude_stop_hook` | Claude Stop hook — reads JSONL transcript tail and emits transcript_turn events. | 88 | active | 📡 | test ←8 →3 5d |
| `hooks.claude_tool_hook` | Claude PostToolUse hook — emits tool_call events to the daemon store. | 77 | active | 📡 | test ←8 →2 4d |
| `hooks.codex_inbound` | Codex ingress adapter — thin daemon event emitter for OpenAI Codex CLI hooks. | 70 | active | 📡 | test ←8 →2 4d |
| `hooks.gemini_inbound` | Gemini ingress adapter — thin daemon event emitter for Google Gemini CLI hooks. | 77 | active | 📡 | test ←8 →2 5d |
| `hooks.subconscious_inbound` | Second-harness U7 — subconscious inbound tap (UserPromptSubmit hook). | 115 | active | 📡 | test ←8 →3 4d |
| `lgwks_agent_os` | fleet startup/bootstrap helpers for the Logical Works prompt layer (#1). | 544 | active |  | cli test ←2 →2 3d |
| `lgwks_algorithms` | L4 narrow-ML catalog (semantic-escalation-harness stage L4). | 190 | active |  | test ←1 3d |
| `lgwks_capabilities` | the resolver that fixes "the tool isn't where it should be." | 268 | active |  | ←5 11d |
| `lgwks_context` | graduated-resolution (LOD) context pack for the next spawn (#9 harness layer). | 193 | active |  | cli ←2 1d |
| `lgwks_cycle` | project deploy cycle ledger. | 143 | active |  | ←4 →4 1d |
| `lgwks_daemon` | minimal background lifecycle shell for the referee runtime. | 1042 | active | 📡 | cli test ←3 →8 2d |
| `lgwks_daemon_event` | normalized daemon event envelope for shared referee runtime. | 373 | active | 📡 | cli test ←5 →3 1d |
| `lgwks_daemon_export` | content-addressed archive/export tier for daemon runs. | 158 | active |  | test ←1 →1 3d |
| `lgwks_daemon_store` | durable event log + work queue for the daemon referee runtime. | 918 | active | 📡 | test ←3 →3 2d |
| `lgwks_do` | unified orchestrator: code, research, govern, cleanup, ship. | 424 | active | 👁️ | cli ←3 →10 1d |
| `lgwks_dsl` | lightweight Ruby-like DSL for workflow orchestration. | 127 | active |  | cli ←1 →1 1d |
| `lgwks_engine` | U6: Subconscious Engine (deterministic first slice). | 509 | active |  | cli test ←4 →7 1d |
| `lgwks_ground` | fused live grounding for the research loop (#9 / harness layer). | 165 | active |  | ←2 →4 13d |
| `lgwks_had` | Human Assumption Decoder (consultant semantic-escalation-harness, intent math). | 446 | active |  | test ←1 →5 1d |
| `lgwks_hooks` | audit-first hook system for lgwks. (hardened v2) | 891 | active |  | cli test ←1 →2 3d |
| `lgwks_map` | U1 Capability Map (second-harness PRD §12). | 106 | active |  | cli ←4 →2 1d |
| `lgwks_portal` | deterministic portal packets for coding-agent re-entry. | 279 | active |  | cli test ←2 →3 1d |
| `lgwks_project` | one-prompt project orchestrator front door (re-export shim). | 125 | active |  | cli ←5 →5 1d |
| `lgwks_project_deploy` | `lgwks project deploy` verb. | 433 | active |  | ←3 →7 1d |
| `lgwks_project_plan` | `lgwks project plan` verb. | 120 | active |  | ←3 →2 16d |
| `lgwks_project_review` | `lgwks project review` verb. | 122 | active |  | ←2 →3 16d |
| `lgwks_repl` | interactive readline harness for lgwks. | 457 | active | 👁️ | test ←3 →4 1d |
| `lgwks_session` | session boundary analyzer (begin / end / summary). | 556 | active | 👁️ | cli test ←4 →5 3d |
| `lgwks_solve` | the first real-world experience: "I have this mess / this thought — prove what happened." | 392 | active | 👁️ | test ←5 →5 1d |
| `lgwks_spawn` | AI-AI handoff packet assembler (#9 harness layer). | 207 | active |  | cli test ←2 →2 8d |
| `lgwks_substrate_run` | build, query, and baseline orchestration for substrate runs. | 786 | active |  | cli ←4 →11 2d |
| `lgwks_synthesizer` | U9/U9A: LLM reasoning layer & Apple-native/cloud synthesis seam. | 222 | active |  | test ←1 →3 2d |
| `lgwks_tongue` | the Tongue: an optional OpenRouter LLM compiles hypotheses + the elimination | 236 | active |  | ←2 →1 2d |
| `lgwks_workercap` | computed worker-slot ceiling from a probed host profile. | 99 | active |  | ←4 16d |
| `lgwks_workflow_aetherius` | the autonomous intelligence kernel. | 156 | active | 🧠👁️ | cli ←1 →5 3d |
| `lgwks_workflows` | unified AI workflow harness. | 924 | active | 👁️ | cli ←3 →16 1d |

## Membrane / intent / steering  ·  9 mod · 2,873 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_concept` | deterministic concept extraction and activation steering. | 624 | active |  | test ←1 →2 1d |
| `lgwks_intent` | schema-driven intent router. A 10-line declaration drives automation. | 556 | active | 👁️ | cli test ←2 →3 2d |
| `lgwks_intent_classifier` | custom English intent classifier for the CLI membrane. | 490 | active |  | test ←5 →5 1d |
| `lgwks_machine` | the Tier-E MACHINE (build #3, z1). The intent/goal engine — NOT AI. It scores and | 273 | active | 🧠 | test ←2 →2 3d |
| `lgwks_multiply` | the `x` verb: multiply intent instead of issuing it N times. | 204 | active | 👁️ | ←4 →1 16d |
| `lgwks_route` | unified intent routing. | 49 | active |  | cli ←1 →3 1d |
| `lgwks_steering` | the adjustable control surface, both sides of the membrane. | 101 | active |  | ←4 16d |
| `lgwks_vault` | hardened INTENT-VAULT store (build #3, enterprise grade). | 422 | active |  | test ←2 →2 2d |
| `tools.train_intent_classifier` | train_intent_classifier.py — training script for the custom English intent classifier. | 154 | active |  | ←6 →1 15d |

## Governance / gates / refusal / auth  ·  15 mod · 4,650 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_aup` | AUP runtime gate with Defense-in-Depth. | 720 | active |  | cli test ←4 →4 1d |
| `lgwks_comprehend` | the Comprehension Gate (spec-01). | 203 | active |  | cli test ←1 →2 1d |
| `lgwks_embed` | deterministic local folder embedding vault. | 207 | active |  | cli ←6 →7 1d |
| `lgwks_gate` | unified safety and governance gate router. | 95 | active |  | cli ←1 →5 1d |
| `lgwks_gate_arch` | G1 Architecture gate (spec-00). | 263 | active |  | test ←1 →1 11d |
| `lgwks_gate_framework` | G3 Framework-Reality gate (spec-00). | 267 | active |  | test ←1 →1 2d |
| `lgwks_gate_idiom` | G2 Idiom gate (spec-00). | 150 | active |  | test ←1 →4 1d |
| `lgwks_keyvault` | macOS Keychain-backed secret resolver for runtime API keys (Issue #7). | 132 | active |  | cli ←6 8d |
| `lgwks_model_port` | the one runtime gateway every cognition request flows through. | 300 | active |  | test ←10 →6 1d |
| `lgwks_run` | the post-gate execution spine (Issue #7, ADR-001). | 855 | active |  | cli ←11 →13 1d |
| `lgwks_sign` | keyed integrity for the run log, the vault chain, and gate verdicts (Issue #7). | 53 | active |  | ←9 16d |
| `lgwks_storage` | D4 Three-Syscall Storage Gate (ADR-068). | 837 | active |  | test ←6 →8 2d |
| `lgwks_urlrisk` | G3 scope curator (Issue #7, ADR-001 §5, constitution L9). | 244 | active |  | ←1 →1 3d |
| `lgwks_verify` | the Verifier oracle (spec-01), hardened with provenance tracking. | 253 | active |  | test ←5 9d |
| `scripts.check_schema_registry` | Registry conformance gate (governance/README.md + docs/schemas/REGISTRY.md rule 4). | 71 | active |  | ←4 7d |

## CLI / home / membrane surface  ·  5 mod · 3,488 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_foundation` | T3 structured extraction via Apple Foundation Models (macOS 26+, on-device). | 200 | active |  | cli ←2 8d |
| `lgwks_gh` | GitHub surface: issues, PRs, state maps, hardening, deterministic "what's next". | 899 | active | 👁️ | cli test ←2 →3 2d |
| `lgwks_home` | the launcher. Type `lgwks` (bare) and the whole thing pops up. | 964 | active | 👁️ | test ←4 →9 1d |
| `lgwks_manifest` | the machine-first contract. `lgwks manifest` → one JSON blob an AGENT reads instead | 1308 | active | 👁️ | ←5 →5 2d |
| `lgwks_ui` | our own terminal visual language. Deliberately NOT Claude Code. | 117 | active | 👁️ | ←21 11d |

## Substrate / storage / schema  ·  14 mod · 3,774 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_batch` | schema-validated batch execution for real shell commands. | 288 | active | 👁️ | cli ←1 →2 2d |
| `lgwks_cache` | the UNTRUSTED-CACHE store (build #2, z2 evidence / z4 quarantine). | 114 | active | 🧠 | ←2 →1 3d |
| `lgwks_capture` | unified operator-facing capture compiler over substrate + portal. | 183 | active |  | cli test ←1 →3 3d |
| `lgwks_cognition` | the COGNITION-LOG store (build #2, z4 core). | 190 | active | 🧠 | ←9 →3 1d |
| `lgwks_memory` | deterministic project memory chain (hardened, build #3). | 272 | active |  | cli test ←3 →6 1d |
| `lgwks_project_artifacts` | shared schemas, JSONL writers, record builders, | 1120 | active |  | ←11 →3 1d |
| `lgwks_schema` | schema registry for next-agent discovery. | 283 | active |  | cli test ←7 4d |
| `lgwks_sqlite` | Shared SQLite connection hardening for lgwks durable stores. | 299 | active | 📡 | ←12 2d |
| `lgwks_substrate` | thin facade re-exporting all substrate sub-modules. | 191 | active |  | test ←7 →11 2d |
| `lgwks_substrate_config` | constants, paths, regexes, and shared types for substrate runs. | 109 | active |  | ←22 2d |
| `lgwks_substrate_io` | file system I/O, JSONL/JSON emission, and manifest loading. | 145 | active |  | ←11 →2 2d |
| `lgwks_substrate_text` | text processing: chunking, scoring, stemming, fact extraction. | 137 | active |  | ←4 →1 9d |
| `lgwks_substrate_vector` | vector search, vector space identity, and cross-space guards. | 253 | active |  | ←2 →3 9d |
| `lgwks_tokenizer_registry` | tokenizer/analyzer identity registry. | 190 | active |  | test ←2 →1 2d |

## Models / runtime (opaque dep)  ·  9 mod · 2,186 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_apple` | Apple-local embedding provider seam. | 146 | active |  | ←2 10d |
| `lgwks_coreml` | local text classification via CoreML. | 142 | active |  | ←1 14d |
| `lgwks_jepa` | first executable multi-view JEPA package surface. | 307 | active |  | cli test ←1 →6 1d |
| `lgwks_model_hub` | repo-resident model loading + developer setup for local CoreML use. | 642 | active |  | cli test ←3 →3 2d |
| `lgwks_model_mesh` | model law rendered as a single queryable manifest (#119). | 291 | active |  | test ←3 1d |
| `lgwks_multimodal` | image extraction + multimodal embedding seam. | 350 | active |  | ←3 →2 1d |
| `lgwks_openrouter` | cloud Tongue via OpenRouter (Issue #7). | 140 | active |  | ←4 →2 1d |
| `lgwks_openrouter_embed` | optional remote embedding seam via OpenRouter. | 66 | active |  | test ←1 →3 1d |
| `scripts.build_capability_embeddings` | freeze the Qwen verb-embedding matrix (U6.2 #85). | 102 | active |  | ←4 →2 5d |

## Dev tooling / scripts  ·  2 mod · 615 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `scripts.gen_navmap` | relational + staleness module atlas for AI navigation (stdlib only). | 367 | active | 🧠📡👁️ | cli ←4 5d |
| `scripts.setup_models` | setup_models.py — one-time developer script to download and convert models. | 248 | active |  | ←4 →1 2d |

## Unclassified (triage)  ·  23 mod · 3,965 LOC

| module | purpose | loc | stale | obs | rel |
|---|---|---|---|---|---|
| `lgwks_access` | CapabilityPort interface and HMAC impl (#98 / #97 seam). | 518 | active | 👁️ | cli test ←4 →5 1d |
| `lgwks_artifact_tokenized` | canonical tokenized artifact envelope. | 186 | active |  | test ←3 →1 2d |
| `lgwks_cli_introspect` | one source of truth for live CLI parser introspection + the | 144 | active |  | ←2 1d |
| `lgwks_clock` | the single source of truth for timestamps. | 28 | active |  | ←14 3d |
| `lgwks_config` | validated YAML config surface (lgwks.config.v1). | 133 | active |  | test ←3 2d |
| `lgwks_cortex` | the Transcript Cortex (PRD-06 U5). | 195 | orphan |  | →7 2d |
| `lgwks_fabric_projection` | the universal projection seam for the State Fabric. | 122 | active |  | ←1 →2 2d |
| `lgwks_fabric_reader` | the unified read surface over the State Fabric. | 88 | active |  | test ←1 →2 2d |
| `lgwks_hashing` | the single source of truth for content hashing. | 88 | active |  | test ←38 3d |
| `lgwks_inline` | unified payload-inlining resolver. | 136 | active |  | test ←8 2d |
| `lgwks_jailbreak` | entrypoint injection-risk sensor + abstention verdict. | 174 | active |  | ←2 →1 1d |
| `lgwks_lexicon` | the one canonical LEXICAL analyzer (word / identifier tokenisation). | 66 | active |  | ←7 →1 1d |
| `lgwks_ops` | consolidated operations and lifecycle workflows. | 208 | active | 🧠👁️ | cli ←2 →9 |
| `lgwks_oriented` | the basement seam for the Structural Inference Framework (#172). | 186 | active |  | test ←1 2d |
| `lgwks_phase` | canonical phase-result type and exit-code→verdict policy. | 43 | active |  | ←4 1d |
| `lgwks_proc` | the single source of truth for safe subprocess invocation. | 41 | active |  | ←3 3d |
| `lgwks_reasoning_port` | runtime-neutral DEEP-REASONING seam. | 150 | active |  | test ←2 →1 1d |
| `lgwks_redact` | the single source of truth for credential redaction. | 33 | active |  | ←3 3d |
| `lgwks_research` | autonomous deep-research loop (Issue #9, parent #7). | 938 | active | 👁️ | cli ←5 →13 1d |
| `lgwks_tokenizer` | the Aetherius Neural Tokenizer (ANT). | 217 | active |  | ←2 →1 2d |
| `lgwks_transcript` | tail-reader utility for Claude Code JSONL transcript files. | 144 | active |  | ←2 2d |
| `lgwks_vecmath` | the single source of truth for vector similarity math. | 82 | active |  | ←14 1d |
| `scripts.build_model_mesh` | freeze the model law as a queryable manifest (#119). | 45 | active |  | ←4 →1 4d |
