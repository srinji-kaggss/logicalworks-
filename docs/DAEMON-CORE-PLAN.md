# Daemon Core Plan

Status: active plan · scope: the vendor-neutral daemon core plus the first research experience

This is the cohesive plan after the current architecture cut:

- defer human projection
- keep ingress headstart
- use transcript/history tail as the simpler outbound truth
- treat daemon and ingest as one runtime
- make clients adapters, not product centers
- build concurrency and referee behavior in from day 1

One important correction:

- the daemon is **not already a Rust core**
- Rust exists today in the crawler and Axiom islands
- a Rust daemon is a likely target seam once contracts stabilize

## 1. Core node to finish

Finish this node first:

```text
ingress adapter
-> daemon queue/session
-> workflow/retrieval runtime
-> shared state substrate
-> packet response
-> transcript tail continues state updates
```

If this node works, Claude/Codex/Gemini become adapters instead of architecture forks.

Additional hard requirement:

> one tenant may run multiple frontier agents concurrently, and the daemon is the referee across them

The day-1 bar is at least:

- Claude
- Codex
- Gemini

running at the same time within one tenant.

## 2. What is done

Built enough to rely on:

- ingress/reflex pieces
  - `lgwks_map.py`
  - `lgwks_engine.py`
  - `lgwks_inbound.py`
  - `hooks/subconscious_inbound.py`

- ingestion/retrieval substrate
  - `lgwks_input.py`
  - `lgwks_lfm2_extract.py`
  - `lgwks_embed_port.py`
  - `lgwks_vector.py`
  - `lgwks_score.py`
  - `lgwks_rank.py`
  - `lgwks_entity_graph.py`
  - `lgwks_substrate_run.py`

- workflow/runtime surfaces
  - `lgwks_do.py`
  - `lgwks_workflows.py`
  - `lgwks_run.py`
  - `lgwks_repo.py`
  - `lgwks_spawn.py`
  - `lgwks_agent_os.py`

- state/security substrate
  - `lgwks_sqlite.py`
  - `lgwks_cognition.py`
  - `lgwks_access.py`
  - `lgwks_capability.py`
  - `lgwks_crdt.py`
  - `lgwks_sign.py`

- research output shape
  - `lgwks_manifest.py`
  - `lgwks_ingest.py`
  - `lgwks_research.py`

## 3. What is left

> **Status update (2026-06-16): P0 met + hardened to world-class.** The lifecycle/packet
> contract below is now backed by an executable falsification harness,
> `tests/test_daemon_world_class.py` (H0 = "the daemon lacks world-class daemon properties"),
> green at **23/23** invariants across 8 categories. Every P0 acceptance line maps to a test:
> "restart loses no committed state" → B1; "concurrent sessions don't corrupt/lose" → C1/C2;
> "packet fetched deterministically by session" → C3; tenant isolation → C4. Added beyond P0:
> bounded-queue backpressure (`MAX_QUEUE_DEPTH`), orphaned-work recovery + startup reclaim,
> dead-letter (`MAX_ATTEMPTS`), readiness probe (`daemon ready`), heartbeat-staleness, unified
> `daemon stats`. See BUILDLOG 2026-06-16. **Deferred:** live hook-wiring (Director-gated until
> the standalone daemon is certified) and periodic orphan-recovery (needs a per-item lease
> before dispatch goes concurrent). The Rust single-writer port remains the post-freeze seam.

### P0. Daemon lifecycle and packet API

Need one owned daemon process with:

- single-writer state ownership
- per-session identity
- queue/enqueue API
- read packet API
- crash-safe restart
- shared-referee scheduling across concurrent agent workloads
- per-agent subconscious packet generation over shared tenant state

Acceptance:

- daemon can be started independently of any client
- ingress can enqueue work
- packet can be fetched deterministically by session
- restart loses no committed state
- three concurrent agent sessions in one tenant do not corrupt state or lose updates
- shared jobs are arbitrated once; agent-local packets remain distinct

Implementation note:

- do this in Python first unless/until the queue/state contract is stable enough to migrate
- if/when migrated, Rust should own the single-writer backend, not fork the business rules

### P1. Ingress and transcript normalization ✅ DONE (`6182a7d`)

`lgwks_transcript.py`: stateless JSONL tail-reader (`tail(path, n=20)`) → normalized turn payloads.
`hooks/claude_tool_hook.py`: PostToolUse hook → `tool_call` event (actor=agent, lane=telemetry, metadata-only).
`hooks/claude_stop_hook.py`: Stop hook → reads transcript tail → `transcript_turn` events; PK-idempotent.

Acceptance MET:
- Claude ingress hook (UserPromptSubmit) → `human_message`; Stop hook → `transcript_turn`; PostToolUse hook → `tool_call` — all normalized `lgwks.daemon.event.v1` envelopes ✅
- Codex/Gemini adapters unchanged (same `human_message` contract; tool/transcript hooks are Claude Code-specific) ✅
- every event carries `tenant_id` + `session_id` ✅

Honest limit: `claude_stop_hook.py` and `claude_tool_hook.py` are not yet registered in `.claude/settings.local.json` — they exist and are tested; live wiring needs Director go (UserPromptSubmit already live; Stop/PostToolUse additive).

### P2. Daemon-owned git/worktree runtime ✅ DONE (`12383d2` + `6182a7d`)

WorktreeManager: create/close/list with single-session referee (one active worktree per
(tenant, session)); CRDT ORSet per tenant at store/daemon/crdt/; migration v4; CLI
`daemon worktree create/close/list`; worktree_open/close in WORK_KINDS + dispatcher.

Acceptance MET:
- daemon creates/closes worktrees without manual shell choreography ✅
- CRDT ORSet snapshot is the auditable merge record ✅
- per-session referee serializes conflicting actions ✅
- entity-graph CRDT sidecars from closed worktrees reconverge into canonical path (`_crdt_reconverge_entity_graph`) ✅

### P3. Research run front door

Need one obvious command/runtime surface for:

- target website
- crawl/build/map
- graph artifacts
- embeddings
- STEM facts and DB outputs
- future queryability by the daemon

Acceptance:

- one command or one actor run produces a complete research substrate
- daemon can index that run and serve later packets from it

Real-world constraints to respect:

- bounded crawl budgets
- auth wall escalation instead of silent scrape failure
- explicit storage tiering for large media/vector runs
- promotion rules for what becomes durable shared knowledge

### P4. Client adapters

Need thin adapters for:

- Claude
- Codex
- Gemini

Acceptance:

- same core packet contract
- no client-specific business logic in the daemon core
- adapters identify the caller cleanly enough for per-agent subconscious state and referee arbitration

### P5. Archive/export tier ✅ DONE (`a816b4d`)

ExportManager: export_run (tar.gz + sha256), verify_export (re-hash check),
cleanup_run (blocked without verified export; --force logs override), export_session
(JSONL + sha256). Migration v5 adds exported_at/export_path/export_hash to daemon_runs.
CLI: `daemon export run/verify/session`, `daemon cleanup <run_id>`.

Acceptance MET:
- export is content-addressed (sha256) and recorded in store ✅
- cleanup_run refuses unless verify_export passes ✅
- cloud export: deferred; local archive is the first tier — pluggable by extending ExportManager

## 4. First concrete experience: website research

The first thing to get running end to end should be:

> I point it at a website and it comprehensively makes me a graph/map, embeddings, STEM facts, and a reusable substrate for future agent work.

That runtime should be:

```mermaid
graph TD
    A[target website] --> B[daemon creates research session]
    B --> C[crawl/build via substrate runtime]
    C --> D[chunks + STEM facts + vectors]
    D --> E[graph db/json/mermaid + manifest]
    E --> F[daemon indexes run into shared state]
    F --> G[next agent/human ask hits the same run]
```

### What already exists for this experience

- crawl/build surfaces in `lgwks_manifest.py`
- pipeline/runtime in `lgwks_substrate_run.py`
- end-to-end ingest path in `lgwks_ingest.py`
- autonomous research loop in `lgwks_research.py`
- graph output and viz support in `lgwks_graph_viz.py`

### What is missing for this experience

- one canonical research session front door
- one manifest packet that the daemon always knows how to ingest
- one daemon index step that registers the run into long-lived state
- one query surface for later recall

## 5. The next few moves

1. ✅ Normalize the daemon event model.
   Status: DONE — `lgwks.daemon.event.v1` + store append + session heads (2026-06-12, `18f0ecf`/`7bfdd84`)

2. ✅ Build the daemon lifecycle shell + work queue + packet read.
   Status: DONE — start/stop/status/doctor + poll loop + enqueue/dequeue (IMMEDIATE, no double-claim)
   + `get_packet()` deterministic snapshot (2026-06-12, `464c470`)

3. ✅ Research-session front door + run registry.
   Status: DONE — `daemon research <url>` calls `build_run()`, registers manifest via `register_run()`;
   `daemon runs` lists indexed runs; `research_run` dispatcher in poll loop (2026-06-12, `bc3b67e`)

4. ✅ Daemon indexes completed research run.
   Status: DONE — bundled with Move 3. Migration v3 `daemon_runs` table; idempotent by run_id.

5. ✅ Claude adapter.
   Status: DONE — `hooks/subconscious_inbound.py` emits `human_message` (lane=ingress, client=claude)
   to daemon store on every prompt; fail-silent (INV-6); session_id from LGWKS_TRANSCRIPT_PATH
   (2026-06-12, `fe400a4`)

6. ✅ Codex + Gemini adapters.
   Status: DONE — hooks/codex_inbound.py, hooks/gemini_inbound.py; same event contract;
   Gemini handles multipart parts[] format; all fail-silent (INV-6) (2026-06-12, `2e8e638`)

7. ✅ Daemon-owned worktree runtime (P2).
   Status: DONE — WorktreeManager: create/close/list with per-session referee (one active
   worktree per session), CRDT ORSet audit trail per tenant, migration v4 daemon_worktrees
   table; worktree_open/close in WORK_KINDS + dispatcher (2026-06-12, `12383d2`)

8. ✅ Content-addressed export + safe cleanup gate (P5).
   Status: DONE — ExportManager: export_run (tar.gz + sha256), verify_export (re-hash),
   cleanup_run (blocks unless verified), export_session (JSONL); migration v5 export columns
   on daemon_runs; CLI daemon export/cleanup (2026-06-12, `a816b4d`)

## 6. Decision rules

- Keep `complex math -> ML -> SLM if needed`.
- Prefer MLX over llama.cpp when practical.
- Use hooks as adapters, not as the core truth source.
- Use transcript/history tails as the simplest durable outbound source when the client provides them.
- Extend built surfaces before minting new ones.
- Bin work explicitly by latency, trust, storage, and compute class before choosing where it runs.
- Distinguish `shared-referee` work from `agent-local subconscious` work in every runtime decision.
