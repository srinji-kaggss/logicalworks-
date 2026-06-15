# Schema Registry (lgwks) — all contracts, one index

**Status:** live registry, created 2026-06-10 from a full-repo contract inventory.
**Authority:** this file is the index + repurposing policy. The *defining file* named in each row is
the shape authority — verify it before reuse (rows record where truth lives, they are not the truth).
**Live scanner:** `lgwks_schema.py` (`lgwks.schema.registry.v0`) machine-builds a registry by scanning
`lgwks_*.py`; this document is the curated layer on top: families, status, and repurpose rules.

## Minting rules (factory discipline)
1. **Check this registry before minting.** A new cross-module dict/struct that duplicates an existing
   family member is a defect, not a new schema.
2. Every cross-module payload carries `schema: "lgwks.<domain>.<name>.v<N>"`. `v0` = research
   (breakable without ceremony), `v1+` = stable (breaking change ⇒ bump + registry row update; old
   version marked `superseded-by`).
3. A contract that crosses a **process boundary** (CLI JSON, Rust↔Python, hook stdin/stdout, file
   handoff) requires a JSON-Schema file in `docs/schemas/` once it reaches v1.
4. New/bumped contracts land with a row here in the SAME commit (the INGESTION-PLAN packets carry
   explicit `Register:` lines).
5. Repurpose > extend > mint, in that order — see per-family rules.

## Families and repurpose rules

### 1. axiom byte framework (`axiom/`) — frozen primitives
varint (LEB128, bomb-rejecting) · wire (canonical TLV) · cid (`b2b256:<hex>`) · capsule (frozen
Claim/Hole record) · fabric (content-addressed DAG + hash-chained log). Stdlib-only, no upward imports.
**Repurpose when:** you need deterministic bytes, content addressing, or append-only audit anywhere in
the stack — build ON these, never reimplement hashing/encoding locally.
**Never:** fork a second cid scheme or a second canonical encoding. One byte-truth.
**Version note:** versionless by design (protocol-embedded); any change is a new module, not an edit.

### 2. crawl family
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.crawl.v2` | 2 | **live** (I3, 2026-06-10) — v1→v2 bump | `crawler/src/schema.rs` (serde) | serde + JSON-Schema |
| `lgwks.crawl.v1` | 1 | **superseded-by: v2** (on I3 landing) | `crawler/src/schema.rs` (serde) | serde |
| `lgwks.crawl.v0` | 0 | **deprecated** — python-side near-duplicate; retire callers | `lgwks_substrate_crawl.py` | dict |
| `lgwks.crawl.artifacts.v1` | 1 | **live** (I3) | `docs/schemas/lgwks.crawl.artifacts.v1.json` | jsonschema |
| `lgwks.lfm2_extract.v1` | 1 | **live** (I3) — LFM2-Extract fill component; emits `lgwks.crawl.artifacts.v1` | `lgwks_lfm2_extract.py` (`SCHEMA_VERSION`) | jsonschema |
| chunk record | — | live, versionless ⚠ | `crawler/src/chunk.rs:11` `{cid,position,text,word_count,simhash}` | serde |

**v2 additions over v1:** `Page.media: Vec<MediaItem{cid,modality,url,mime,byte_count,fetch_status}>` (fetched bytes, not URLs); `Page.artifacts: Option<JSON>` (LFM2-Extract fill); `Modality` enum (image\|video); schema bumped to `lgwks.crawl.v2`. LFM2-Extract fills `lgwks.crawl.artifacts.v1`; non-conformant fills rejected by `lgwks_lfm2_extract.fill_schema()`.
**Repurpose when:** any fetch-and-structure job — point at v2, do not write ad-hoc scrapers with private output shapes. v0 callers must be retired.

### 3. substrate / ingestion family

#### lgwks.vector.record.v1 — landed I1 (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.vector.record.v1` | 1 | **live** (20 tests) | `lgwks_vector.py` | decode_record + require_cid |

Fields: `cid` (blake2b of canonical bytes) · `modality` (text\|image\|video) · `embedding` (BLOB, float32[d] big-endian, L2-normalized) · `norm` f32 (pre-norm audit) · `dim` u16 · `space_id` str · `tenant` str · `source_cid` str · **v2:** `tokenization_id` str · `artifact_cid` str.
Invariants: ‖ê‖ = 1 ± 1e-6; same inputs → same cid (dedup); cross-space compare raises `SpaceMismatchError`. v2 metadata columns do NOT affect the cid — identical embeddings dedup regardless of which tokenizer named them.
Proof fixture: `~/ingestion_results/code_embeddings_v1.db` — 4100 rows migrated from JSON-TEXT, 659 deduped (cid-dedup working on real data).
**Supersedes:** `vector_json TEXT` column in `lgwks_substrate_db.py:85` + `fact_vectors.vector_json` (gap G-11).

`lgwks.substrate.{run,query,baseline,map,vector_query,crawl_map,error}.v0` (`lgwks_substrate_run.py`,
`lgwks_substrate_vector.py`, `lgwks_substrate_crawl.py`) · `lgwks.ingest.v1` (`lgwks_ingest.py:284`) ·
SQLite DDL: `lgwks_substrate_db.py:43-98` (sources/documents/chunks/facts/vectors/frontier + FTS5),
`lgwks_entity_graph.py:111-138` (nodes/edges/chunks).
#### lgwks.artifact.tokenized.v1 — landed Phase 1 (2026-06-15)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.artifact.tokenized.v1` | 1 | **live** | `lgwks_artifact_tokenized.py` | `build_artifact()` + JSON-Schema |

Fields: `artifact_cid` (content-addressed canonical bytes) · `tenant_id` · `source` (research/run/ingest/substrate/daemon_event/project_artifact) · `run_id`/`session_id` · `modality` (text/image/video/audio/terminal/reasoning) · `tokenization_id` (FK to tokenizer registry) · `token_stream` · `payload_cid` (raw bytes) · `payload_meta` · `capability_id` · `timestamp` · `prev_hash`.
Invariants: deterministic `artifact_cid` over canonical JSON; one artifact = one row on the Causal Tape; all projections derive from it.
**Supersedes/retires:** ad-hoc file-tree rows as source of truth in `lgwks_substrate_run.py`, `lgwks_ingest.py`, `lgwks_research.py`, `lgwks_run.py`.

#### lgwks.tokenizer.registry.v1 — landed Phase 1 (2026-06-15)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.tokenizer.registry.v1` | 1 | **live** | `lgwks_tokenizer_registry.py` | JSON-Schema |

Fields: `tokenizer_id` · `kind` · `version` · `config_json` · `vocab_cid` · `modality_anchors` · `created_at`.
Invariants: registration is idempotent (first definition wins); default entries `word_regex:v1` and `aetherius:v0` are auto-seeded.
**Why:** attaches tokenizer/analyzer identity to every stored unit so FTS, vector, graph, and relational projections are tokenizer-aware and auditable.

#### lgwks.modality.item.v1 — landed I2 (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.modality.item.v1` | 1 | **live** (73 tests) | `lgwks_input.py` | handle() + extract() |

**Fields** (every item has all of these):

| field | type | what it holds |
|-------|------|--------------|
| `schema` | str | always `"lgwks.modality.item.v1"` |
| `modality` | str | `"text"` · `"image"` · `"video"` · `"quarantine"` |
| `parsed_unit` | str or None | decoded text — set for text items; `None` for image/video/quarantine |
| `raw_bytes` | bytes or None | raw file bytes — set for image/video/quarantine; `None` for text |
| `mime` | str | MIME type from magic bytes |
| `origin` | str | file path or identifier passed to `handle()` |
| `extraction_strategy` | str | `"text_direct"` · `"ocr_image"` · `"visual_embed"` · `"video_embed"` · `"none"` |
| `frame_index` | int | always `-1` (reserved) |
| `source_fingerprint` | str | blake2b-8 hex over first 64KB — for dedup |
| `quarantine_reason` | str | non-empty only when `modality="quarantine"` |

**Invariants:** text → `raw_bytes=None`; image/video/quarantine → `parsed_unit=None`; `extraction_strategy` always set; `handle()` and `extract()` never raise; `needs_extraction()` is `True` only for `"ocr_image"`.

**Two-phase:** `handle(bytes, origin)` = classify fast (hook-safe). `extract(item)` = OCR only — returns item unchanged for all other strategies.

**Video path:** `handle()` sets `extraction_strategy="video_embed"`, `raw_bytes=<file bytes>`. `extract()` is a no-op. I4 (`lgwks_embed_port.EmbedPort`) opens the bytes, extracts frames, and calls the VL model — one 4096-d vector out. I2 never touches video content.

#### lgwks.embed.port.v1 — landed I4 (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.embed.port.v1` | 1 | **live** (59 tests) | `lgwks_embed_port.py` | EmbedPort |

**What it does:** takes any `lgwks.modality.item.v1` item → produces a `lgwks.vector.record.v1` blob.

**Quick start** (self-contained — no assumed context):
```python
from lgwks_input import handle          # I2: classify any file
from lgwks_embed_port import EmbedPort  # I4: embed it

items = handle(file_bytes, "myfile.mp4")
with EmbedPort() as port:              # auto-selects mlx or transformers
    for item in items:
        vec    = port.embed_from_item(item)
        record = port.embed_to_record(vec, modality=item.modality,
                                      source_cid="b2b256:...", tenant="myproject")
        # pass record to I1 (lgwks_vector.upsert_record)
```

**Model:** `Qwen3-VL-Embedding-8B` — local only, no HuggingFace at runtime (Zscaler-safe).
Weights in `store/models/Qwen3-VL-Embedding-8B-mlx` (mlx) or `store/models/Qwen3-VL-Embedding-8B` (transformers). Fetch once via `make download-models` (pulls from GitHub Release, not HF).

**Tiers** (same model, same `space_id` — auto-selected):

| tier | when active |
|------|------------|
| `mlx` | `store/models/Qwen3-VL-Embedding-8B-mlx` exists + `mlx_vlm` importable |
| `transformers` | `store/models/Qwen3-VL-Embedding-8B` exists |

**`embed_from_item(item)` routing:**

| modality | extraction_strategy | calls |
|----------|---------------------|-------|
| `text` | `text_direct` | `embed_text(parsed_unit)` |
| `image` | `visual_embed` | `embed_image(raw_bytes)` |
| `video` | `video_embed` | `embed_video(raw_bytes)` — N frames extracted here, native VL |
| `quarantine` | any | raises `ValueError` |

**space_id:** `"qwen3-vl-embedding-8b:d{k}"` — identical for both tiers. Pass `dim=k` (k ≤ 4096) for MRL truncation; port slices and re-normalises. I1 cross-space guard refuses any comparison against a different space_id.


**Repurpose when:** storing or querying ingested content — extend the substrate DDL, never mint a
side-database (the external `~/ingestion_results/*.db` stores are exactly the lossy pattern I1 retires).
**Rule:** all `.v0` here are research-grade; promote to v1 only through an INGESTION-PLAN packet.

### 4. harness / orchestrator family
| id | ver | status | defined in |
|----|-----|--------|-----------|
| `lgwks.actor.v1` | 1 | **live** — THE composition envelope | `lgwks_actor.py:79` |
| `lgwks.do.run.v1` | 1 | live | `lgwks_do.py:51` |
| `lgwks.spawn.v1` | 1 | live | `lgwks_spawn.py:~70` |
| `lgwks.pipeline.manifest.v1` | 1 | live | `lgwks_pipeline.py:52` |
| `lgwks.manifest.v0` / `lgwks.intent.v0` / `lgwks.hooks.v0` / `lgwks.audit.v0` / `lgwks.gh.v0` / `lgwks.session.summary.v0` | 0 | live, research-grade | `lgwks_schema.py:66-133`, `lgwks_gh.py:82` |
| `lgwks.intent.centroids.v1` | 1 | live (cache) | `lgwks_intent_classifier.py:68` |
| `lgwks.config.v1` | 1 | **live** (Issue 158) — validated YAML config | `lgwks_config.py` | jsonschema |
| `lgwks.inbound.v1` | 1 | live (**I7**) — reflex pack: `handles[]`, `scores{}`, `budget{limit_tokens,used_tokens,truncated_count,truncated[]}` (count exact, cid list bounded ≤64), `depth_handles[{id,est_tokens,kind}]` | `lgwks_inbound.py` |
| `lgwks.aetherius.v1` | 1 | **live** (Issue 163) — core foundation model representation and artifact emission schema | `lgwks_aetherius.py` | jsonschema |
| `lgwks.cortex.v1` | 1 | **live** (Issue 163) — transcript cortex and cognitive log schema | `lgwks_cortex.py` | jsonschema |
| `lgwks.waste.ledger.v1` | 1 | **live** (**I11**) — per-session waste ledger: `session_id`, `window_turns`, `items[{cid,tokens,used_within_n,first_use_turn}]`, `totals{tokens_injected,tokens_used,waste_rate}` | `lgwks_waste.py`; JSON-Schema: `docs/schemas/lgwks.waste.ledger.v1.json` |
| `lgwks.admission.v1` | 1 | **live** (**I8**) — token-bucket admission result envelope: `cid`, `status` (`admitted`/`rejected_429`), `reason`, `retry_after` | `lgwks_admission.py` (`Admitted`, `Rejected429`) |
| `lgwks.admission_queue.v1` | 1 | **live** (**I8-hardening L4 #89**) — durable cross-process admission queue row: `tenant`, `cid`, `item` (opaque handle, never raw content — §1-INV), `state` (`queued`/`leased`/`done`), `enqueued_at`, `leased_at`, `lease_owner`, `lease_deadline`, `retry_count`; PK `(tenant,cid)` idempotent dedup. WAL table; crash-durable lease/reap; fair leasing ≤ c from the DB COUNT. Capability-gated (tenant:rw) | `lgwks_admission_store.py` (`DurableAdmissionQueue`) |
| `lgwks.capability.v2` | 2 | **live** (**I8-hardening #89**) — tier-scoped capability token: `tenant`, `nonce`, `sig` (hmac-sha256 over `tenant:nonce:scopes`), `scopes` (`tenant:rw`/`world:r`/`world:promote`). Scopes signed → no client-side escalation (ARCH L7). Read path: `get_record_for_tenant`/`query_for_tenant` (own ⊕ world) | `lgwks_capability.py` (`CapabilityToken`) |
| `lgwks.capability.v1` | 1 | **superseded-by: v2** (on I8-hardening landing) — `tenant`, `nonce`, `sig`; no tier scopes | `lgwks_capability.py` (`CapabilityToken`) |
| `lgwks.capability.action.v1` | 1 | **live** (**#120 — the execution boundary**) — the ONLY contract the daemon's Hand executes; a model proposes, execution is typed validated code. `verb` (member of the `lgwks.map.v1` catalog — unknown→reject), `subject{kind,id\|cid,tenant}`, `effect_class` (`read`/`write`/`network`/`spawn`/`delete`/`external_publish` — declared not inferred), `reversibility` (`reversible`/`compensatable`/`irreversible`), `required_authority{scopes}` (reuses `lgwks.capability.v2` tier scopes), `provenance{proposing_event_id,proposer,trust}` (trust rides from the #118 event), `preconditions[]`, `postconditions[]`, `undo`, `replay{deterministic,idempotency_key}`, `confirmed`. Gate `validate_action` rejects unknown verb/effect, missing authority, and `irreversible` without `confirmed:true`; the Hand (`execute_action`) runs only validated actions. **Distinct from** the `lgwks.capability.v2` auth token. `verb`+`effect_class`+`reversibility`+`required_authority` are the locked interface #121 lowers into and #122 lists as `allowed_capabilities` | `lgwks_capability_action.py` (`build_action`/`validate_action`/`execute_action`/`lower_do_ship`); JSON-Schema: `docs/schemas/lgwks.capability.action.v1.json` |
| `lgwks.crdt.state.v1` | 1 | **live** (**I9**) — CRDT state envelope: `type` (`gset`/`orset`/`lww`) + type-specific fields; SEC proof in `tests/test_crdt.py` | `lgwks_crdt.py`; JSON-Schema: `docs/schemas/lgwks.crdt.state.v1.json` |
| `lgwks.navmap.v1` | 1 | **live** — generated module atlas for AI navigation: `totals`, `index{by_subsystem,by_staleness,by_issue,by_packet}`, `modules{<name>:{purpose,loc,deps,used_by,subsystem,staleness,integration,owning_issue,packet,last_commit_days,has_cli,has_tests}}`. Regenerate via `scripts/gen_navmap.py`; read `docs/navmap/README.md` first | `scripts/gen_navmap.py`; output `docs/navmap/index.json`; JSON-Schema: `docs/schemas/lgwks.navmap.v1.json` |
| `lgwks.daemon.event.v1` | 1 | **superseded-by: v2** (on #118 landing) — original normalized daemon event envelope: `tenant_id`, `agent_id`, `session_id`, `actor`, `client`, `lane` (`ingress`/`telemetry`/`workflow`/`control`), `kind` (`human_message`/`transcript_turn`/`tool_call`/`file_change`/`workflow_event`), `scope` (`agent_local`/`shared_referee`), optional `causal_parent_id`, `refs{}`, `payload{}`. Deterministic `event_id` when omitted. v1 records still validate (`validate_event` accepts v1 ⊕ v2) and project into v2 via `upgrade_v1_to_v2` | `lgwks_daemon_event.py`; JSON-Schema: `docs/schemas/lgwks.daemon.event.v1.json` |
| `lgwks.daemon.event.v2` | 2 | **live** (**#118 — "event_envelope"**) — additive superset of v1; the unified causal event envelope every sensory/runtime source emits. All v1 fields retained; new fields OPTIONAL, `kind` widened as a superset (adds `browser_action`/`repo_diff`/`terminal_output`/`model_output`/`artifact_emit`). Adds: `source` (`speech`/`text`/`browser`/`repo`/`terminal`/`model`/`workflow`/`artifact` — WHERE it entered, orthogonal to `kind`), `payload_cid` (out-of-band payload content-address, axiom CID `b2b256:<hex>`), `trust` (`human_confirmed`/`deterministic`/`model_proposed`/`untrusted`), `provenance` (`{derived_from,producer,producer_version}`), `replay` (`{seq,deterministic,schema_from}`). `source`+`trust` are the locked join keys for #120/#121/#122/#124. Deterministic `event_id` includes present optional fields; `upgrade_v1_to_v2` projects historical v1 events without recomputing their id | `lgwks_daemon_event.py` (`SCHEMA`, `build_event`, `upgrade_v1_to_v2`); JSON-Schema: `docs/schemas/lgwks.daemon.event.v2.json` |
| `lgwks.voice.event.v1` | 1 | **live** (**#123 — speech ingress, never a gate bypass**) — the Ear's output, NOT authority: `audio_source{kind(mic\|file\|stream),device\|path,sample_rate,codec}`, `transcript_span{start_ms,end_ms}`, `confidence`, `speaker{speaker_id,session_id,agent_id}`, `raw_text` (verbatim ASR — **immutable**), `normalized_text` (cleanup), `raw_ref` (`raw:b2b256:<hex>` pointer normalized→raw; verified to resolve to `raw_text`), `cleanup_provenance{model(null=open slot),method,changed}`, `final` (streaming interim/final). `to_daemon_event` lowers into the #118 envelope with **`source:speech`, `trust:untrusted`** (voice can never arrive pre-trusted) + `payload_cid`=cid(raw_text) + `provenance.derived_from=[raw_ref]`. Does NOT select an ASR/VAD/cleanup model (open slots). Distinct from `lgwks_tongue` (the next hop) | `lgwks_voice_event.py` (`build_voice_event`/`validate_voice_event`/`to_daemon_event`); JSON-Schema: `docs/schemas/lgwks.voice.event.v1.json` |
| `lgwks.daemon.events.query.v0` | 0 | **live, research-grade** — daemon event-log query result: `count`, `items[]` where each item is `lgwks.daemon.event.v1`/`v2` | `lgwks_daemon_store.py` |
| `lgwks.daemon.query.v1` | 1 | **live** (**#124 — unified query request**) — one filter envelope over the federated read surface: `{schema, q\|null, filters{tenant(required), session, project, source, type, freshness, trust}, limit, order}`. `source`/`trust` reuse the #118 v2 axes; `freshness` is an ISO watermark cutoff; `order` is fixed to `score_desc` (the one stable order). Unifies `lgwks.daemon.events.query.v0` / `lgwks.substrate.*` / `lgwks.graph.*` / vector recall as backend adapters — does not replace them | `lgwks_query.py` (`build_request`/`validate_request`/`query`); JSON-Schema: `docs/schemas/lgwks.daemon.query.v1.json` |
| `lgwks.daemon.query.result.v1` | 1 | **live** (**#124 — unified query result**) — `{schema, count, hits[]}` where each `Hit` = `{cid (b2b256), projection (`graph`/`vector`/`transcript`/`artifact`/`fact`/`symbol`), score (normalised [0,1]), provenance{event_id\|artifact_cid, source}, snippet, ts, trust}`. Stable total order `(score desc, cid asc)`; cross-projection scores normalised to [0,1] before merge (documented, reproducible). Every hit traces back to a #118 event or artifact CID. The `Hit` shape is the interface #122's `retrieval` section consumes | `lgwks_query.py` (`make_hit`/`query`); JSON-Schema: `docs/schemas/lgwks.daemon.query.result.v1.json` |
| `lgwks.daemon.sessions.query.v0` | 0 | **live, research-grade** — tenant session-head query result: `count`, `items[{tenant_id,agent_id,session_id,first_event_id,last_event_id,event_count,last_ts,last_lane,last_kind,last_scope}]` | `lgwks_daemon_store.py` |
| `lgwks.daemon.status.v0` | 0 | **live, research-grade** — daemon lifecycle status envelope: `repo_root`, `daemon_root`, `db_path`, `lock_present`, `state_present`, `pid`, `alive`, `transcript_path`, `heartbeat_at`, `status`, `stale_lock_reaped` | `lgwks_daemon.py` |
| `lgwks.daemon.doctor.v0` | 0 | **live, research-grade** — daemon doctor report: `checks[]` for daemon root, event-store parent, transcript env; includes `stale_lock_reaped` and aggregate `ok` | `lgwks_daemon.py` |
| `lgwks.daemon.bus.event.v1` | 1 | **live** (Issue 160) — single typed event bus emitted by daemon for TUI/CLI tailing: `id`, `kind`, `state` (`queued`/`processed`), `processed_at`, `payload` | `lgwks_daemon.py` | jsonschema |
| `lgwks.daemon.work_item.v0` | 0 | **live (2026-06-12), research-grade** — dequeued work-queue item: `schema`, `item_id`, `tenant_id`, `session_id`, `agent_id`, `kind` (`research_run`/`ingest_file`/`workflow`/`index_run`/`custom`/`worktree_open`/`worktree_close`), `priority` (int, higher = sooner), `payload{}`, `enqueued_at`, `started_at`, `status` (`running`). Dequeue is atomic via `BEGIN IMMEDIATE`; idempotent by `item_id` on enqueue | `lgwks_daemon_store.py` (`WORK_ITEM_SCHEMA`) |
| `lgwks.daemon.queue.v0` | 0 | **live (2026-06-12), research-grade** — per-tenant queue depth snapshot: `schema`, `tenant_id`, `queued`, `running`, `done`, `failed`, `total` | `lgwks_daemon_store.py` (`QUEUE_SCHEMA`) |
| `lgwks.daemon.packet.v0` | 0 | **superseded-by: lgwks.context.packet.v1** (on #122 landing) — original deterministic session context packet: `schema`, `tenant_id`, `session_id`, `agent_id`, `session_head`, `queue`, `recent_events[]`, `event_count`. Promoted (not a peer mint) to the context packet below | `lgwks_daemon_store.py` (`PACKET_SCHEMA`) |
| `lgwks.context.packet.v1` | 1 | **live** (**#122 — the shared subconscious briefing**) — the ONE canonical daemon briefing read by every agent (Claude/Codex/Gemini) and the human cockpit; a derived read-only projection reproducible from {event log @ watermark, stores @ watermark} with no hidden mutation. Promoted from `lgwks.daemon.packet.v0`. Keeps the v0 core (`session_head`, `queue`, `recent_events[]` now #118 v2 events, `event_count`) and adds the **locked section set**: `active_task`, `retrieval` (#124 graph/vector hits), `known_failures` (filtered #118 events), `commitments`, `constraints`, `allowed_capabilities` (#120 verbs), `provenance{watermark_event_id, store_versions}`. Sections depending on other contracts degrade to empty-but-shaped (provider-fed) — packet stays valid + deterministic under partial availability. Same inputs → byte-identical packet | `lgwks_daemon_store.py` (`PACKET_SCHEMA`, `get_packet`, `validate_context_packet`); JSON-Schema: `docs/schemas/lgwks.context.packet.v1.json` |
| `lgwks.daemon.worktree.v0` | 0 | **live (P2, 2026-06-12), research-grade** — daemon-owned git worktree record: `schema`, `worktree_id`, `tenant_id`, `session_id`, `agent_id`, `repo_path`, `worktree_path`, `branch` (`daemon/<worktree_id>`), `base_sha`, `status` (`active`/`closed`/`error`), `created_at`, `closed_at`. Persisted in `daemon_worktrees` SQLite table (migration v4). Also reflected in per-tenant CRDT ORSet at `store/daemon/crdt/<tenant>.json` for auditable merge state | `lgwks_daemon_store.py` (`WORKTREE_SCHEMA`); lifecycle: `lgwks_daemon.WorktreeManager` |
| `lgwks.daemon.export.v0` | 0 | **live (P5, 2026-06-12), research-grade** — content-addressed export record: `schema`, `run_id`/`session_id` (depending on export target), `export_path`, `export_hash` (sha256 hex), `verified` bool. Run exports produce `.tar.gz`; session exports produce `.jsonl`. Hash is stored in `daemon_runs.export_hash` column (migration v5); `verify_export` re-hashes to confirm integrity | `lgwks_daemon_export.py` (`EXPORT_SCHEMA`); `lgwks_daemon_store.mark_run_exported` |
| `lgwks.daemon.cleanup.v0` | 0 | **live (P5, 2026-06-12), research-grade** — safe local cleanup result: `schema`, `run_id`, `cleaned` bool, `removed_dir`, `dir_existed`, `force` bool. Cleanup is blocked (`cleaned=false`) unless `verify_export` passes; `force=true` skips verification and logs the override. Local-only tier; cloud export is additive (extend `ExportManager`, not a new schema) | `lgwks_daemon_export.py` (`CLEANUP_SCHEMA`); CLI: `daemon cleanup <run_id>` |
| `lgwks.map.v1` | 1 | **live** (**U1**) — capability map result: `schema`, `query`, `query_tokens`, `verb_count`, `matched`, `matches[{verb,intent,args,score}]`, `note`; deterministic token-match, <1s | `lgwks_map.py` (`map_intent`) |
| `lgwks.engine.schema.v1` | 1 | **live** (**U6/U6.1 #83; U6.2/U6.3 #85,#86**) — §6 subconscious schema: `prompt`, `attention`(null, Qwen layer pending), `retrieval[]`, `last_state{}`, `insights{scores{coverage_C,gap_G(nullable),decisiveness_d,confidence_P,grounding_status,coverage_mode},selections[],flags[],actions_taken[]}`, `pathways[]`, `meta{verb_count,query_tokens,graph_hits}`; **independent axes** (capability / graph / margin), **constant-free P** (geometric mean over available axes); `coverage_mode`∈`lexical`/`lexical+demand`/`qwen` (I8 demand-weighting + Qwen-cosine seam, additive); deterministic, <1s, non-generative | `lgwks_engine.py` (`run_engine`) |
| `lgwks.reasoning.result.v0` | 0 | **live (session 15, 2026-06-13), research-grade** — runtime-neutral deep-reasoning result (parallel of `embed_port`): `{schema, persona, backend(olmo_mlx\|agent_handoff), mode(local\|agent_handoff\|deferred), ok, model\|null}` + one of `text` / `handoff{to,reason,request{prompt,framing,context}}` / `deferred{to,why}`. Port resolves backend by tier: owned OLMo-3-32B (MLX, store/models) when present → hand off to the working agent (Claude/Codex/Gemini, operator's pick) → defer to human; **never fabricates** (INV-3). Personas (`co_scientist`) are harness framing, not weights. Honors LGWKS_NO_MODELS / LGWKS_REASONING_BACKEND | `lgwks_reasoning_port.py` (`reason`/`resolve_backend`) |
| `lgwks.capability_idf.v1` | 1 | **live** (**U6.3/I8 #86**) — frozen demand-weight table for padding-invariant coverage: `corpus`, `n_documents`, `n_tokens`, `idf{token:weight}`; smoothed IDF over the capability vocabulary (pure counting, no AI — Calculator Test); optional artifact, runtime recomputes from the live verb catalog when absent | `scripts/build_capability_idf.py`; output `.lgwks/capability_idf.json` |
| `lgwks.capability_vectors.v1` | 1 | **live** (**U6.2 #85**) — frozen Qwen verb-embedding matrix for cosine coverage: `space_id`, `dim`, `n_verbs`, `verbs[{verb,intent,vec}]`; vectors are the Qwen sensor layer (exempt — runtime cosine over them is in-bounds arithmetic). Optional artifact + needs the model present; absent OR embed port unavailable → engine degrades to the lexical+demand floor | `scripts/build_capability_embeddings.py`; output `.lgwks/capability_vectors.json` |
| `lgwks.risk.assessment.v1` | 1 | **live (#143, 2026-06-14)** — unified abstention-gate verdict over ALL risk signals (the gate the U6 engine calls; `lgwks_jailbreak.assess` is retained as the injection-only view / back-compat shim, sharing the same thresholds): `{schema, verdict(proceed\|attenuate\|confirm\|block), risk_score, injection_risk, signals[], receipt, injection{verdict,score,signals,receipt}, components[{name,score,weight,contribution,signals,evidence}]}`. ONE gate composes injection (attacker — can reach BLOCK) · assumption (accidental self-injection; HAD over the intent classifier; capped at CONFIRM) · anomaly (z fraud/drift seam, unfed until a request series exists; capped at CONFIRM — evidence for a human gate, not an autonomous block). `composed = max(weight·score)`, all weights 1.0 (no magic; authority differences expressed as per-signal CAPS), thresholds shared with the injection sensor (single source); assumption gated behind `assume`/`classify_fn` so a cold classifier load never blows the engine's <1s budget (INV-7); self-caps input at 16k chars; deterministic, calculator-derivable. Back-compat superset of the old injection dict; the `injection` sub-view is injection-only (never mislabels other signals' tells) | `lgwks_had.py` (`assess`/`compose_verdict`/`RiskSignal`) |
**Repurpose when:** any new capability → wrap as an actor (`ActorSpec` + `lgwks.actor.v1` envelope)
instead of a bare function with a private dict. Actor-calls-actor is the sanctioned composition path.

### 5. bot fabric family — the only fully formalized family (the model to copy)
`lgwks.bot.record.v1` + `lgwks.bot.plan.v1` — defined `lgwks_project_artifacts.py:291-292`, **formal
JSON Schemas** in `docs/schemas/lgwks-bot-{record,plan}-v1.schema.json`, validated at runtime.
**Repurpose when:** any finding/plan-shaped artifact (review findings, audit results, scan output) —
emit `bot.record.v1` with a new `kind` rather than minting a new findings schema.

### 6. scoring / graph family
`lgwks.graph.v2` (live; `lgwks.graph.v1` deprecated) + `lgwks.repo.graph.v0` (graph-over-repo bridge,
`lgwks_graph.py`/`lgwks_repo.py`) + `lgwks.graph.{query,impact,complexity,path,neighbors,patterns}.v0`
(`lgwks_schema.py:102-109`) · `lgwks.graph.cache.v1` (`.lgwks/graph.cache.json`).
**Repurpose when:** any code-structure question — query `graph.v2`; do not parse source ad-hoc.

#### I6 cubic node centrality — landed (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.rank.record.v1` | 1 | **live** (I6) — Z-eigenpair cubic centrality + AI-discrepancy δ; top-decile δ → human lane | `lgwks_rank.py` (`RankRecord`) | frozen dataclass; power-iter convergence + seed-stability tests |

**v1 note:** ranking is batch/offline (INV-3, no AI in path). Conformance weight = edge `confidence_score`. δ threshold = top 10% pre-registered as `DELTA_HUMAN_PERCENTILE`. Relation weights uniform 1.0.

#### I5 deterministic scoring — landed (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.schema.relations.v1` | 1 | superseded-by **v2** (I5) — D0: 8 typed-triple relations; operators identity, directional Pₖ deferred | `lgwks_score.py` (`RELATIONS`) | dataclass + `lgwks_schema` |
| `lgwks.schema.relations.v2` | 2 | **live** (I5.1) — directional operators active: `R_k = P_k·diag(d_k) + N_k`, antisymmetric `N_k` paired so `Σ_k N_k = 0` ⇒ `(1/m)Σ R_k = I` exact (§4.2 proof holds) while directed relations score asymmetrically. 10 relations paired: calls, case_of, contains, image, imports_from, inherits, method, rationale_for, uses, video. | `lgwks_score.py` (`build_operators`) | dataclass + `lgwks_schema` |
| `lgwks.score.record.v1` | 1 | **live** (I5) — RESCAL factored score + MDL conformance + content cid | `lgwks_score.py` (`ScoreRecord`) | dataclass; canonical CBOR + zstd |
| `lgwks.oriented.objective.v1` | 1 | **hypothesis-basement** (Structural Inference #172; harness #180) — three-term oriented objective `L = description_length + prediction_error + intent_divergence`, all in **bits**, weights 1 by construction (no magic constants). Nested limits: flat intent ⇒ `intent_divergence=0` ⇒ #172 structural limit; +frozen structure ⇒ Bayes. `mode`∈`bayes`/`structural`/`oriented`. `vertex_birth_justified` is the `Phi_V` economic gate (#174); `tau`=encoding bits of the proposed vertex, derived not tuned. Final seam — proof/`Phi_V`/capsules fill terms, no reshape. | `lgwks_oriented.py` (`oriented_loss`) | calculator-pure (surprisal + KL bits); no AI, no deps |

**v1 note:** scoring is batch/offline (INV-3, no AI in path). MDL + cid + factored-operator mechanism are active; per-relation directional `Pₖ` is identity in v1 so the §4.2 marginal-identity proof holds exactly — directional activation is I5.1.

#### lgwks.graphify.cluster.v1 — landed I12 (2026-06-10)
| id | ver | status | defined in | validation |
|----|-----|--------|-----------|------------|
| `lgwks.graphify.cluster.v1` | 1 | **live** | `graphify/cluster.py` | `ClusterResult` dataclass |

Fields: `schema` · `algorithm` (leiden\|louvain — which actually ran) · `communities` (list of node-id lists) · `community_count` · `modularity` · `resolution` · `seed` · `metadata{leidenalg_available, py_version, forced}`.
**Invariant:** Leiden→Louvain silent substitution is never permitted. `LeidenUnavailableError` raised when Leiden is requested on py≥3.13. Louvain only via `force_louvain=True` (sets `metadata.forced=True`).

### 7. portal / capture / JEPA / synthesis family
`lgwks.portal.v1` + `lgwks.portal.code.v1` (`lgwks_portal.py:25-26`) · `lgwks.capture.v1`
(`lgwks_capture.py:19`) · `lgwks.jepa.{package,doctor}.v1` (`lgwks_jepa.py`) ·
`lgwks.synth.{input,output,meter}.v1` (`lgwks_synthesizer.py`) · `lgwks.artifact.strength.v1`
(`lgwks_project_artifacts.py:1061`).
**Repurpose when:** intent→artifact binding or multi-view packaging — these are the seams; extend
fields, don't fork the envelope.

### 8. axiom harness / review / solve (research tier, all v0)
`lgwks.axiom.{harness,run_index,test_matrix,narration,doctor,divergence,replay,replay_all}.v0`
(`lgwks_axiom.py`) · `lgwks.review.v0` → planned `v1` · `lgwks.review.packet.v1` ·
`lgwks.solve.v0` / `lgwks.thought.v0` (`lgwks_solve.py`).
**Repurpose when:** deterministic replay/verification jobs — reuse the axiom harness records.

### 9. PRD candidates (planned, spec-only — do not cite as existing)
`lgwks.state.v1` · `lgwks.engine.v1` · `lgwks.detect.v1` · `lgwks.docs.v1` · `lgwks.depthpack.v1` ·
`lgwks.codegraph.v1` · `lgwks.map.v1` · `lgwks.had.intent.v1` (spec/second-harness/prd/).
**Rule:** a planned schema becomes real only via its packet/PRD unit + a status flip here.

### 10. CLI / repo-ops family (v0 research — gate-registered 2026-06-10)
`lgwks.repo.{audit,cleanup,handoff,merge,recover,sync}.v0` (`lgwks_repo.py`) ·
`lgwks.run_index.v0` (`lgwks_run.py`) · `lgwks.codebase.v0` (`lgwks_codebase.py`) ·
`lgwks.manifest.for_agent.v0` (`lgwks_manifest.py`) · `lgwks.jarvis.substrate_crawl.v0`
(jarvis↔crawler bridge) · `lgwks.debug.v0` (`lgwks_debug.py`) · `lgwks.algebra.v0` (`lgwks_math.py`).
**Repurpose when:** machine-readable CLI output — reuse the verb's existing envelope before minting.

### 11. model-stack family (W-track, live)
`lgwks.algorithms.catalog.v1` (`lgwks_algorithms.py`, W2 catalog) · `lgwks.sast.catalog.v1` +
`lgwks.sast.flow.v1` (`lgwks_sast.py`) · `lgwks.audit.graph.v2` (`lgwks_audit_graph.py` — U5 Build #5
"Liquid Brain" SAST result envelope, ADR-sast-003: `schema` + graph-flow audit findings over
caller/callee/guard/escape edges) · `lgwks.model_hub.doctor.v1` (`lgwks_model_hub.py`) ·
`lgwks.workflow.run.v1` (`lgwks_workflows.py`).

**`lgwks.workflow.trigger.v1`** (**#121** — event-chain grammar; `lgwks_workflow_trigger.py`,
`evaluate_triggers`; JSON-Schema: `docs/schemas/lgwks.workflow.trigger.v1.json`): a pure predicate
over the append-only #118 event log that emits a #120 `lgwks.capability.action.v1` **proposal** when
matched — never a direct execution. `{schema, trigger_id, pattern[EventMatcher over #118
source/kind/refs/subject], required_evidence[], confidence{score,basis (rule floor; scorer model an
open slot)}, preconditions[], cooldown{window,max_fires}, policy(ask\|act), lowers_to(#120 action
template)}`. Replayable (same slice → same proposals) and non-executing (only sink is the proposal
list; never calls `lgwks_do`/`lgwks_workflows`). The multi-event generalisation of the single-prompt
`_workflow_for_intent` (left intact). **Repurpose when:** any cross-event/latent-workflow detection —
add a trigger, do not hard-code a new classifier branch.

**`lgwks.model.mesh.v1`** (**#119** — model law as data; `lgwks_model_mesh.py`, builder
`scripts/build_model_mesh.py` → `.lgwks/model_mesh.json`; JSON-Schema:
`docs/schemas/lgwks.model.mesh.v1.json`): single queryable manifest of the model-stack law
(spec MODEL-RUNTIME-FINALIZATION §3.1 current law + §3.2 open slots). `{schema, generated_at,
models[]}` where each entry = `{name, runtime, locality, role, input_schema, output_schema,
trust_class, fallback, health{status,latency_ms_p50,last_checked}, eval_gate, status
(current_law/open_slot/candidate_reference), notes?}`. **Records inventory; does not change it**
— no new default, no selection, loads no model. `role`+`trust_class`+`input/output_schema`+
`eval_gate` are the locked join keys for #120/#122 + the future LogicGPT-1 eval path. Doctor
(`lgwks_model_hub._model_mesh_status`) reads the artifact, degrading to the in-code law when absent.
**Repurpose when:** any deterministic scorer/detector → a CATALOG entry + these envelopes, not a new shape.

### 12. JEPA manifest-level ids (live, supplement family 7)
`lgwks.jepa.v1` (manifest verb envelope) · `lgwks.machine.packet.v1` · `lgwks.human.summary.v1` ·
`lgwks.links.index.v1` (all `lgwks_project_artifacts.py`) · `lgwks.concept.graph.v0` (`lgwks_spawn.py`).

### 13. Documentation fixtures (NOT contracts — listed so the gate distinguishes them)
`lgwks.foo.v0`, `lgwks.foo.v1` — example ids inside `lgwks_schema.py` docs/scanner strings only.

## Mechanical enforcement
`scripts/check_schema_registry.py` (run: `make check-registry` or directly) fails CI when a
`lgwks.*.v<N>` literal in src lacks a registry row. Scope: `*.py/*.rs/*.sh`, excluding tests/,
worktrees, caches. This section's rule 4 is therefore enforced, not advisory.

## Known debts (flagged 2026-06-10)
1. **Validation asymmetry:** ~45 contracts are manual-dict validated; only bot fabric has formal
   JSON Schemas + enforcement. Rule 3 above ratchets this: every v1 process-boundary contract gets a
   schema file on next touch.
2. **`lgwks.crawl.v0` vs `v1`** — near-duplicate pair; retire v0 at I3.
3. **Versionless chunk record** (`crawler/src/chunk.rs`) — version it at the I3 bump.
4. **External side-stores** (`~/ingestion_results/*.db`, incl. `lessons_compressed.db` and
   `code_embeddings.db` with JSON-TEXT embeddings) — outside the substrate DDL, lossy, unregistered.
   I1 migrates `code_embeddings.db` as its proof fixture; register or retire the rest as they're touched.
5. **Doc inconsistency:** gemini-embedding-2 dimensionality stated as both 4096-d and 3072-d in
   BUILDLOG-model-stack.md (noted there, unresolved — resolve at I4 eval).
