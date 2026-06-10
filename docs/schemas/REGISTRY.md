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
| `lgwks.crawl.v1` | 1 | **live** (30 tests) | `crawler/src/schema.rs:7` (serde) | serde |
| `lgwks.crawl.v0` | 0 | **deprecated** — python-side near-duplicate of v1 | `lgwks_substrate_crawl.py` | dict |
| `lgwks.crawl.v2` | 2 | **planned** (INGESTION-PLAN **I3**) | spec only | JSON-Schema required |
| chunk record | — | live, versionless ⚠ | `crawler/src/chunk.rs:11` `{cid,position,text,word_count,simhash}` | serde |
**Repurpose when:** any fetch-and-structure job — point at v1/v2, do not write ad-hoc scrapers with
private output shapes. **Flagged:** v0/v1 duplication — retire v0 callers during I3.

### 3. substrate / ingestion family
`lgwks.substrate.{run,query,baseline,map,vector_query,crawl_map,error}.v0` (`lgwks_substrate_run.py`,
`lgwks_substrate_vector.py`, `lgwks_substrate_crawl.py`) · `lgwks.ingest.v1` (`lgwks_ingest.py:284`) ·
SQLite DDL: `lgwks_substrate_db.py:43-98` (sources/documents/chunks/facts/vectors/frontier + FTS5),
`lgwks_entity_graph.py:111-138` (nodes/edges/chunks).
**Planned successors (INGESTION-PLAN):** `lgwks.vector.record.v1` (**I1** — replaces JSON-TEXT vector
storage, gap G-11), `lgwks.modality.item.v1` (**I2**), `space_id` scheme (**I4**).
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
| `lgwks.inbound.v1` | 1 | **planned** (PRD; extended by **I7**) | spec only |
| `lgwks.waste.ledger.v1` | 1 | **planned** (**I11**) | spec only |
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
**Planned:** `lgwks.score.record.v1` (**I5**), `lgwks.rank.record.v1` (**I6**).
**Repurpose when:** any code-structure question — query `graph.v2`; do not parse source ad-hoc.

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
