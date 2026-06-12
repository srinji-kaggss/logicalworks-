# NAVMAP — lgwks module atlas (generated; do not hand-edit)

> `scripts/gen_navmap.py` from source — re-run to refresh. **134 modules · 48,955 LOC.** This is the canonical repo map: if someone says "review the map" or "check the navmap", they mean this file unless another map is explicitly named. Read/query this FIRST. Strict machine-readable contract: `docs/navmap/index.json` (`lgwks.navmap.v1`).

**Staleness:** `active` 133 · `orphan` 1

Rules — `active`: referenced by another module/dispatcher (static or dynamic), or a tested CLI verb <180d · `scaffolding`: no caller, owned by an open issue · `staling`: no caller anywhere, but built/tested or has a CLI verb, no issue (wire or retire) · `orphan`: no caller, no tests, no CLI, no issue (deletion candidate).

Row legend: `cli` `test` · `←N` imported by N · `→N` imports N · `Nd` days since last commit.

## Per-issue rollup (open canonical issues → owned modules + staleness)

| issue | packet | modules (staleness) |
|---|---|---|
| #72 | I8 | `lgwks_admission` (active), `lgwks_capability` (active) |
| #73 | I9 | `lgwks_crdt` (active) |
| #74 | I10 | `lgwks_viz_project` (active) |
| #75 | I11 | `lgwks_waste` (active) |

## Ingestion spine (I1–I12)  ·  16 mod · 6,999 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_admission` | token-bucket admission + idempotent queue (I8 / I8-hardening L3). | 464 | active | cli test ←3 →3 0d |
| `lgwks_admission_store` | durable cross-process admission queue (I8-hardening L4). | 315 | active | ←1 →4 0d |
| `lgwks_capability` | capability-token tenant isolation boundary (I8). | 295 | active | cli test ←7 0d |
| `lgwks_crdt` | CRDT state: G-Set, OR-Set, LWW-Register (I9). | 409 | active | cli test ←4 0d |
| `lgwks_embed_port` | embedder runtime (lgwks.embed.port.v1). | 654 | active | test ←2 →2 0d |
| `lgwks_extract` | ingest every file format → text. The "read anything" port. | 277 | active | test ←4 →4 9d |
| `lgwks_inbound` | L5 consumer pack: RRF fusion + token-budgeted reflex envelope (I7). | 358 | active | cli test ←4 →3 0d |
| `lgwks_input` | universal input handler (lgwks.modality.item.v1). | 530 | active | ←1 →1 1d |
| `lgwks_pipeline` | unified ingestion and ranking spine. | 1492 | active | cli test ←1 →12 0d |
| `lgwks_promote` | audited tenant→world promotion (ARCH L5, I8-hardening #89). | 146 | active | ←3 →3 0d |
| `lgwks_rank` | cubic node centrality (Z-eigenpair) + AI-discrepancy δ (I6). | 537 | active | cli test ←3 1d |
| `lgwks_score` | deterministic schema scoring: RESCAL order-3 · R_k · MDL (I5). | 344 | active | cli test ←3 1d |
| `lgwks_vector` | vector-space + cid contract (lgwks.vector.record.v1). | 500 | active | ←7 →2 0d |
| `lgwks_viz_project` | deterministic 3-D viz projection, decoupled from semantic space (I10). | 262 | active | cli test ←3 1d |
| `lgwks_waste` | waste ledger: the proof context-optimisation works (I11). | 339 | active | cli test ←4 →1 1d |
| `scripts.build_capability_idf` | freeze the I8 demand-weight table (stdlib only, no AI). | 77 | active | ←5 →2 0d |

## Research / web acquisition / extract  ·  14 mod · 4,481 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_auth_runtime` | read-only auth resolver for crawler fetches. | 200 | active | ←3 8d |
| `lgwks_browser` | bot-resilient, JS-rendering fetch via a real browser (playwright). The eyes for pages | 571 | active | test ←8 →2 2d |
| `lgwks_crawl` | single-page fetch shim: delegates to lgwks_substrate.build_run(max_pages=1). | 204 | active | cli test ←2 →4 3d |
| `lgwks_expression` | - lgwks-expression/1 parser and resolver. | 768 | active | ←1 →1 6d |
| `lgwks_files` | the `extract` and `convert` verbs: the read-anything port made into CLI surface. | 62 | active | ←2 →1 11d |
| `lgwks_geoexpr` | deterministic geometric-CLI compiler (SPEC-geometric-cli-translator-v1). | 388 | active | cli ←3 →4 9d |
| `lgwks_html` | robust, deterministic HTML-to-Markdown and semantic link/table parser. | 318 | active | test ←4 →1 8d |
| `lgwks_ingest` | the advanced web-crawler workflow, as ONE function an AI agent runs. | 338 | orphan | →8 2d |
| `lgwks_preview` | the safe sibling of `lgwks x`. Same brace math, no execution, human rendering. | 214 | active | cli ←1 →3 10d |
| `lgwks_public` | open-license public source layer. | 183 | active | cli ←2 6d |
| `lgwks_search` | the missing primitive: a zero-key, free web + news search provider. | 522 | active | test ←3 →3 6d |
| `lgwks_site_profile` | site configuration profile manager. | 88 | active | ←1 8d |
| `lgwks_sites` | site-aware extractors for high-value platforms. | 195 | active | test ←1 9d |
| `lgwks_substrate_crawl` | web crawl engine, auth-gate detection, and frontier management. | 430 | active | ←3 →4 2d |

## Bots / detection / static analysis  ·  7 mod · 2,843 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `graphify.cluster` | graphify.cluster — Leiden community detection with no silent fallback. | 215 | active | ←2 1d |
| `lgwks_bot_code_hacker` | U5 build #2: enterprise-grade static security analyzer. | 594 | active | test ←1 →1 2d |
| `lgwks_bot_optimizer` | U7: deterministic optimization static analyzer. | 420 | active | test ←1 →1 4d |
| `lgwks_bot_slop_math` | U6: deterministic structural slop-detection bots (S1–S6). | 601 | active | test ←1 →1 3d |
| `lgwks_bot_stress` | U8: Concurrent Stress Bot. | 329 | active | test ←1 →1 4d |
| `lgwks_cohere` | Coherence Engine pipeline (spec-00). | 170 | active | cli test ←1 →5 9d |
| `lgwks_debug` | automated debugging: turn "it's broken" into "here's why + next step." | 514 | active | cli test ←1 →1 8d |

## Axiom byte framework  ·  8 mod · 1,757 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `axiom.__init__` | the standalone byte framework for the Axiom machine-first ISA. | 20 | active | ←12 5d |
| `axiom.capsule` | The Capsule — one typed, content-addressed record. Claim asserts; Hole abstains. The unit the verifier | 171 | active | ←12 5d |
| `axiom.cid` | Content identity (CID) — the address of a node over its CANONICAL bytes. | 52 | active | ←12 5d |
| `axiom.fabric` | The fabric — immutable content-addressed DAG + hash-chained append-only log + the pending→committed | 144 | active | ←12 5d |
| `axiom.varint` | LEB128 base-128 varints — the lowest byte-layer primitive (WASM uses these for all lengths/indices). | 92 | active | ←12 5d |
| `axiom.verify` | The decidable click — the trust core. A capsule attaches IFF this returns ok. Pure, decidable, 0-AI, | 112 | active | ←12 5d |
| `axiom.wire` | Canonical TLV wire — tag-length-value over LEB128 (the WASM section / protobuf TLV shape, but we OWN the | 106 | active | ←12 5d |
| `lgwks_axiom` | CLI harness over the standalone Axiom byte framework. | 1060 | active | cli ←1 →2 5d |

## Graph / AST / code intelligence  ·  8 mod · 5,789 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `graphify.__init__` | — | 4 | active | ←2 1d |
| `lgwks_codebase` | semantic codebase database for AI-native code understanding. | 563 | active | cli test ←1 →1 3d |
| `lgwks_entity_graph` | offline document entity graph builder. | 705 | active | cli test ←7 →4 0d |
| `lgwks_graph` | functional, traversable codebase graph with query engine and persistence. | 1570 | active | test ←7 →1 4d |
| `lgwks_graph_viz` | simple localhost graph visualization. | 1205 | active | test ←4 →3 1d |
| `lgwks_refactor` | deterministic AST-based refactoring engine. | 337 | active | cli test ←2 →1 8d |
| `lgwks_repo` | repo lifecycle commands: audit, recover, cleanup, merge, handoff, graph. | 740 | active | cli test ←5 →4 7d |
| `lgwks_review` | graph-aware, spec-bound code review. | 665 | active | cli test ←3 →9 3d |

## Harness / daemon / orchestration  ·  27 mod · 9,506 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `hooks.subconscious_inbound` | Second-harness U7 — subconscious inbound tap (UserPromptSubmit hook). | 81 | active | test ←9 →1 0d |
| `lgwks_agent_os` | fleet startup/bootstrap helpers for the Logical Works prompt layer (#1). | 554 | active | cli test ←1 3d |
| `lgwks_capabilities` | the resolver that fixes "the tool isn't where it should be." | 268 | active | ←5 6d |
| `lgwks_context` | graduated-resolution (LOD) context pack for the next spawn (#9 harness layer). | 187 | active | cli ←2 3d |
| `lgwks_cycle` | project deploy cycle ledger. | 145 | active | ←4 →1 10d |
| `lgwks_daemon` | minimal background lifecycle shell for the referee runtime. | 387 | active | cli test ←1 →2 |
| `lgwks_daemon_event` | normalized daemon event envelope for shared referee runtime. | 217 | active | cli test ←2 0d |
| `lgwks_daemon_store` | durable event log for the daemon referee runtime. | 306 | active | test ←1 →2 0d |
| `lgwks_do` | unified orchestrator: code, research, govern, cleanup, ship. | 512 | active | cli ←2 →6 3d |
| `lgwks_engine` | U6: Subconscious Engine (deterministic first slice). | 438 | active | cli test ←3 →3 0d |
| `lgwks_ground` | fused live grounding for the research loop (#9 / harness layer). | 165 | active | ←2 →4 8d |
| `lgwks_hooks` | audit-first hook system for lgwks. (hardened v2) | 896 | active | cli test ←1 4d |
| `lgwks_map` | U1 Capability Map (second-harness PRD §12). | 104 | active | cli ←3 0d |
| `lgwks_portal` | deterministic portal packets for coding-agent re-entry. | 276 | active | cli test ←3 →1 6d |
| `lgwks_project` | one-prompt project orchestrator front door (re-export shim). | 122 | active | cli ←6 →5 8d |
| `lgwks_project_deploy` | `lgwks project deploy` verb. | 564 | active | ←3 →7 8d |
| `lgwks_project_plan` | `lgwks project plan` verb. | 120 | active | ←3 →2 10d |
| `lgwks_project_review` | `lgwks project review` verb. | 122 | active | ←2 →3 10d |
| `lgwks_repl` | interactive readline harness for lgwks. | 497 | active | test ←2 →3 3d |
| `lgwks_session` | session boundary analyzer (begin / end / summary). | 506 | active | cli test ←2 →4 0d |
| `lgwks_solve` | the first real-world experience: "I have this mess / this thought — prove what happened." | 417 | active | test ←4 →4 8d |
| `lgwks_spawn` | AI-AI handoff packet assembler (#9 harness layer). | 207 | active | cli test ←2 →2 3d |
| `lgwks_substrate_run` | build, query, and baseline orchestration for substrate runs. | 726 | active | cli ←2 →11 2d |
| `lgwks_synthesizer` | U9/U9A: LLM reasoning layer & Apple-native/cloud synthesis seam. | 213 | active | test ←1 →2 4d |
| `lgwks_tongue` | the Tongue: an optional OpenRouter LLM compiles hypotheses + the elimination | 228 | active | ←2 →1 5d |
| `lgwks_workercap` | computed worker-slot ceiling from a probed host profile. | 99 | active | ←4 10d |
| `lgwks_workflows` | unified AI workflow harness. | 1149 | active | cli ←2 →13 3d |

## Membrane / intent / steering  ·  9 mod · 3,084 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_concept` | deterministic concept extraction and activation steering. | 624 | active | test ←1 3d |
| `lgwks_intent` | schema-driven intent router. A 10-line declaration drives automation. | 567 | active | cli test ←2 →1 8d |
| `lgwks_intent_classifier` | custom English intent classifier for the CLI membrane. | 486 | active | test ←3 →2 2d |
| `lgwks_intent_router` | deterministic intent routing with tiny-bert. | 275 | active | cli test ←1 →2 3d |
| `lgwks_machine` | the Tier-E MACHINE (build #3, z1). The intent/goal engine — NOT AI. It scores and | 271 | active | test ←2 →1 4d |
| `lgwks_multiply` | the `x` verb: multiply intent instead of issuing it N times. | 204 | active | ←5 →1 10d |
| `lgwks_steering` | the adjustable control surface, both sides of the membrane. | 101 | active | ←4 11d |
| `lgwks_vault` | hardened INTENT-VAULT store (build #3, enterprise grade). | 402 | active | test ←3 →1 3d |
| `tools.train_intent_classifier` | train_intent_classifier.py — training script for the custom English intent classifier. | 154 | active | ←7 →1 9d |

## Governance / gates / refusal / auth  ·  12 mod · 3,359 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_aup` | AUP runtime gate with Defense-in-Depth. | 710 | active | cli test ←3 →1 3d |
| `lgwks_comprehend` | the Comprehension Gate (spec-01). | 199 | active | cli test ←1 →1 9d |
| `lgwks_embed` | deterministic local folder embedding vault. | 237 | active | cli ←6 →1 10d |
| `lgwks_gate_arch` | G1 Architecture gate (spec-00). | 263 | active | test ←1 →1 6d |
| `lgwks_gate_framework` | G3 Framework-Reality gate (spec-00). | 255 | active | test ←1 →1 4d |
| `lgwks_gate_idiom` | G2 Idiom gate (spec-00). | 149 | active | test ←1 →2 3d |
| `lgwks_keyvault` | macOS Keychain-backed secret resolver for runtime API keys (Issue #7). | 132 | active | cli ←7 3d |
| `lgwks_run` | the post-gate execution spine (Issue #7, ADR-001). | 787 | active | cli ←9 →7 2d |
| `lgwks_sign` | keyed integrity for the run log, the vault chain, and gate verdicts (Issue #7). | 53 | active | ←9 11d |
| `lgwks_urlrisk` | G3 scope curator (Issue #7, ADR-001 §5, constitution L9). | 250 | active | ←1 11d |
| `lgwks_verify` | the Verifier oracle (spec-01), hardened with provenance tracking. | 253 | active | test ←5 4d |
| `scripts.check_schema_registry` | Registry conformance gate (governance/README.md + docs/schemas/REGISTRY.md rule 4). | 71 | active | ←5 2d |

## CLI / home / membrane surface  ·  5 mod · 3,540 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_foundation` | T3 structured extraction via Apple Foundation Models (macOS 26+, on-device). | 200 | active | cli ←3 3d |
| `lgwks_gh` | GitHub surface: issues, PRs, state maps, hardening, deterministic "what's next". | 880 | active | cli test ←1 →1 5d |
| `lgwks_home` | the launcher. Type `lgwks` (bare) and the whole thing pops up. | 1043 | active | test ←4 →8 0d |
| `lgwks_manifest` | the machine-first contract. `lgwks manifest` → one JSON blob an AGENT reads instead | 1300 | active | ←6 →4 0d |
| `lgwks_ui` | our own terminal visual language. Deliberately NOT Claude Code. | 117 | active | ←19 6d |

## Substrate / storage / schema  ·  15 mod · 3,858 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_batch` | schema-validated batch execution for real shell commands. | 287 | active | cli ←1 →1 9d |
| `lgwks_cache` | the UNTRUSTED-CACHE store (build #2, z2 evidence / z4 quarantine). | 116 | active | ←3 10d |
| `lgwks_capture` | unified operator-facing capture compiler over substrate + portal. | 196 | active | cli test ←2 →2 5d |
| `lgwks_cognition` | the COGNITION-LOG store (build #2, z4 core). | 139 | active | ←7 →1 0d |
| `lgwks_lfm2_extract` | lgwks_lfm2_extract — strict schema fill via LFM2-1.2B-Extract (GGUF, llama.cpp). | 209 | active | test ←1 1d |
| `lgwks_memory` | deterministic project memory chain (hardened, build #3). | 277 | active | cli test ←4 →1 4d |
| `lgwks_project_artifacts` | shared schemas, JSONL writers, record builders, | 1068 | active | ←11 →1 4d |
| `lgwks_schema` | schema registry for next-agent discovery. | 283 | active | cli test ←8 0d |
| `lgwks_sqlite` | Shared SQLite connection hardening for lgwks durable stores. | 276 | active | ←9 3d |
| `lgwks_substrate` | thin facade re-exporting all substrate sub-modules. | 200 | active | test ←7 →12 3d |
| `lgwks_substrate_config` | constants, paths, regexes, and shared types for substrate runs. | 102 | active | ←7 3d |
| `lgwks_substrate_db` | SQLite substrate index DB and global fact vector upserts. | 218 | active | ←2 →2 3d |
| `lgwks_substrate_io` | file system I/O, JSONL/JSON emission, and manifest loading. | 97 | active | ←6 →1 3d |
| `lgwks_substrate_text` | text processing: chunking, scoring, stemming, fact extraction. | 137 | active | ←3 →1 3d |
| `lgwks_substrate_vector` | vector search, vector space identity, and cross-space guards. | 253 | active | ←2 →3 3d |

## Models / runtime (opaque dep)  ·  9 mod · 1,969 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_apple` | Apple-local embedding provider seam. | 146 | active | ←2 5d |
| `lgwks_coreml` | local text classification via CoreML. | 142 | active | ←1 8d |
| `lgwks_jepa` | first executable multi-view JEPA package surface. | 335 | active | cli test ←2 →4 5d |
| `lgwks_model_hub` | repo-resident model loading + developer setup for local CoreML use. | 577 | active | cli test ←4 →3 3d |
| `lgwks_multimodal` | image extraction + multimodal embedding seam. | 354 | active | ←4 →1 2d |
| `lgwks_ollama` | local Ollama provider for the Eye (embeddings), Issue #7. | 108 | active | ←5 4d |
| `lgwks_openrouter` | cloud Tongue via OpenRouter (Issue #7). | 138 | active | ←4 →1 5d |
| `lgwks_openrouter_embed` | optional remote embedding seam via OpenRouter. | 67 | active | test ←1 →1 7d |
| `scripts.build_capability_embeddings` | freeze the Qwen verb-embedding matrix (U6.2 #85). | 102 | active | ←5 →2 0d |

## Dev tooling / scripts  ·  2 mod · 554 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `scripts.gen_navmap` | relational + staleness module atlas for AI navigation (stdlib only). | 354 | active | cli ←5 0d |
| `scripts.setup_models` | setup_models.py — one-time developer script to download and convert models. | 200 | active | ←5 →1 3d |

## Unclassified (triage)  ·  2 mod · 1,216 LOC

| module | purpose | loc | stale | rel |
|---|---|---|---|---|
| `lgwks_access` | CapabilityPort interface and HMAC impl (#98 / #97 seam). | 459 | active | cli test ←4 →4 0d |
| `lgwks_research` | autonomous deep-research loop (Issue #9, parent #7). | 757 | active | ←2 →5 8d |
