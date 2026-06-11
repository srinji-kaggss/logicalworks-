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

Fields: `cid` (blake2b of canonical bytes) · `modality` (text\|image\|video) · `embedding` (BLOB, float32[d] big-endian, L2-normalized) · `norm` f32 (pre-norm audit) · `dim` u16 · `space_id` str · `tenant` str · `source_cid` str.
Invariants: ‖ê‖ = 1 ± 1e-6; same inputs → same cid (dedup); cross-space compare raises `SpaceMismatchError`.
Proof fixture: `~/ingestion_results/code_embeddings_v1.db` — 4100 rows migrated from JSON-TEXT, 659 deduped (cid-dedup working on real data).
**Supersedes:** `vector_json TEXT` column in `lgwks_substrate_db.py:85` + `fact_vectors.vector_json` (gap G-11).

`lgwks.substrate.{run,query,baseline,map,vector_query,crawl_map,error}.v0` (`lgwks_substrate_run.py`,
`lgwks_substrate_vector.py`, `lgwks_substrate_crawl.py`) · `lgwks.ingest.v1` (`lgwks_ingest.py:284`) ·
SQLite DDL: `lgwks_substrate_db.py:43-98` (sources/documents/chunks/facts/vectors/frontier + FTS5),
`lgwks_entity_graph.py:111-138` (nodes/edges/chunks).
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
| `lgwks.inbound.v1` | 1 | live (**I7**) — reflex pack: `handles[]`, `scores{}`, `budget{limit_tokens,used_tokens,truncated_count,truncated[]}` (count exact, cid list bounded ≤64), `depth_handles[{id,est_tokens,kind}]` | `lgwks_inbound.py` |
| `lgwks.waste.ledger.v1` | 1 | **live** (**I11**) — per-session waste ledger: `session_id`, `window_turns`, `items[{cid,tokens,used_within_n,first_use_turn}]`, `totals{tokens_injected,tokens_used,waste_rate}` | `lgwks_waste.py`; JSON-Schema: `docs/schemas/lgwks.waste.ledger.v1.json` |
| `lgwks.admission.v1` | 1 | **live** (**I8**) — token-bucket admission result envelope: `cid`, `status` (`admitted`/`rejected_429`), `reason`, `retry_after` | `lgwks_admission.py` (`Admitted`, `Rejected429`) |
| `lgwks.capability.v1` | 1 | **live** (**I8**) — capability-token tenant isolation: `tenant`, `nonce`, `sig` (hmac-sha256) | `lgwks_capability.py` (`CapabilityToken`) |
| `lgwks.crdt.state.v1` | 1 | **live** (**I9**) — CRDT state envelope: `type` (`gset`/`orset`/`lww`) + type-specific fields; SEC proof in `tests/test_crdt.py` | `lgwks_crdt.py`; JSON-Schema: `docs/schemas/lgwks.crdt.state.v1.json` |
| `lgwks.navmap.v1` | 1 | **live** — generated module atlas for AI navigation: `totals`, `index{by_subsystem,by_staleness,by_issue,by_packet}`, `modules{<name>:{purpose,loc,deps,used_by,subsystem,staleness,integration,owning_issue,packet,last_commit_days,has_cli,has_tests}}`. Regenerate via `scripts/gen_navmap.py`; read `docs/NAVMAP.md` first | `scripts/gen_navmap.py`; output `docs/navmap.json`; JSON-Schema: `docs/schemas/lgwks.navmap.v1.json` |
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
| `lgwks.schema.relations.v2` | 2 | **live** (I5.1) — directional operators active: `R_k = P_k·diag(d_k) + N_k`, antisymmetric `N_k` paired so `Σ_k N_k = 0` ⇒ `(1/m)Σ R_k = I` exact (§4.2 proof holds) while directed relations score asymmetrically. `FactoredRelation.antisym`. | `lgwks_score.py` (`build_operators`) | dataclass + `lgwks_schema` |
| `lgwks.score.record.v1` | 1 | **live** (I5) — RESCAL factored score + MDL conformance + content cid | `lgwks_score.py` (`ScoreRecord`) | dataclass; canonical CBOR + zstd |

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
`lgwks.sast.flow.v1` (`lgwks_sast.py`) · `lgwks.model_hub.doctor.v1` (`lgwks_model_hub.py`) ·
`lgwks.workflow.run.v1` (`lgwks_workflows.py`).
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
