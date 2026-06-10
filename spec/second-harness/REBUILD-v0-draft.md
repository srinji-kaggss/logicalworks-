# lgwks Rebuild — v0 DRAFT (not authority, not fully mapped)

Status: **DRAFT · working sketch · NOT a source of truth** · 2026-06-09
Author: Logical Claude. Posture: assume this is wrong until the Director redlines it.

## Reading guide — what is and isn't mapped

| Area | Confidence | Basis |
|---|---|---|
| Crawl front (BFS, auth-aware, frontier) | **verified** | read [lgwks_substrate_crawl.py:81](../../lgwks_substrate_crawl.py:81)–210 |
| Substrate build pipeline | **verified** | read [lgwks_substrate_run.py:143](../../lgwks_substrate_run.py:143)–342 |
| Graph/index + query | partially | read structure of `_substrate_db`, `_substrate_vector`, `query_run` |
| Workflow orchestration | partially | read `lgwks_workflows` structure (phases/cache/checkpoint/verdict) |
| Control-bus / human-IDE principle | **verified** | [docs/machine-nervous-system.md:199](../../docs/machine-nervous-system.md:199), :4 |
| Intent pipeline (5 stages) | mapped | read all 5 modules last turn |
| Governance math (PM/AI-mgmt) | **sketch only** | not yet extracted from code |
| **Model layer** | **OUT OF SCOPE** | Director: ignore completely. Treated as an opaque dependency below. |
| Language (Go vs the doc's Rust) | **OPEN** | nervous-system doc says Rust seams + Python training; conflicts with "Go daemon". Director's call, unresolved. |

This doc specs **one end-to-end slice that is actually figured out** — the crawl→substrate→graph→query→control-bus spine — and marks everything else by its real confidence. It does not pretend the whole system is understood.

---

## 1. The figured-out spine (verified, model-free)

The durable product is not an answer — it is a typed, replayable local substrate (manifests, chunks, vectors, graph, machine packets) that later agents inspect without trusting raw web content ([nervous-system §One-Line](../../docs/machine-nervous-system.md:7)).

```
intake → capture → crawl → chunk/fact-extract → [EMBED SEAM: opaque, out of scope]
       → graph + index → query/baseline → JSON control bus → {Opus schema · human neo-IDE}
```

### 1a. Crawl (verified)
`_crawl_site` is a breadth-first crawler with the hard cases already handled — this is the part that is genuinely done:
- BFS frontier queue, `max_pages`/`max_depth` bounds, per-URL canonicalization + dedup by `(url, sha(text))`.
- **Auth-gate detection** (`_looks_like_login_gate`) with a tiered escalation: bypass-retry → human auth handoff (`save_session`, capped by `max_auth_handoffs`) → `auth_exhausted`.
- **Frontier as audit log**: every URL ends with an explicit status (`blocked·retrying_blocker·error·retrying_gate·auth_exhausted·auth_failed·ok`) — append-only, never silently dropped.
- Optional click-discovery for JS surfaces; remote-allow gate before any fetch.
- Returns `(docs, frontier)` — pure data, no side effects on the graph.

### 1b. Substrate build (verified)
`build_run` turns docs into the typed substrate:
- run dir `store/substrate/<run_id>/`; source/doc rows with content-addressed ids (`sha`-derived).
- chunk via `_chunk_text(size, overlap)`; per chunk: `fact_score`, `stem`, `chunk_kind`.
- fact extraction (`_fact_sentences`) → fact rows.
- **dual-lane vectors** per chunk/fact (the embed seam is opaque, but the *contract* is clear): a deterministic audit vector is **always** written; a semantic vector is written **only when available** (`if dual["sem"]`) — never-block. `is_semantic` labels the lane; lexical ≠ semantic edges.
- `graph_input_rows` carry `schema = chunk_kind.upper()` for the graph build.
- (downstream, not yet read line-by-line) → `_build_index_db` (SQLite + FTS5), `manifest.json` records exact vector spaces + artifact paths.

### 1c. The control bus (verified principle)
"The CLI is not the product UI. It is the control bus" — JSON in / JSON out, no human wording in machine paths; **human interfaces are thin frontends over the same machine contracts** ([:199](../../docs/machine-nervous-system.md:199)). This is the seam that makes the **human neo-IDE usable without the AI**: the IDE and Opus consume the *same* JSON. Build the engine as that bus, and the IDE is a renderer, not a rewrite.

---

## 2. The rebuild — dedup the scatter onto the spine

The scatter collapses onto this spine as follows (modules → one seam):

| Seam | Collapses (scattered today) | Note |
|---|---|---|
| **Crawl** | `substrate_crawl` · `crawl` (single-page shim) · `browser` (render/auth) · jarvis front-door | one crawl entry, frontier-logged |
| **Substrate** | `substrate_run` · `_io` · `_text` · `_db` · `_vector` · `_config` | already the most cohesive family — this is the orchestration that works |
| **World-graph + index** | `graph` · `entity_graph` · `codebase` · `substrate_db` | one store, evidence-labelled edges |
| **Query/retrieve** | `query_run` · `substrate_vector._vector_search` | space-checked against manifest |
| **Control bus** | the `--machine` JSON surface | dual consumer: Opus schema + human IDE |
| **Embed** | *(opaque — out of scope per Director)* | one dependency the spine calls; not specced here |

Everything else (REPL, viz, project/deploy verbs, home launcher) is **not** this slice.

---

## 3. Problems this actually addresses

1. **The scatter** — 5+ half-modules per capability collapse to one seam with one contract; the substrate family is the model of what "done" looks like.
2. **No-AI usability** — the control bus is the IDE's data source; you operate the substrate, graph, query, and (later) governance through a thin frontend with zero Opus.
3. **Audit-by-construction** — frontier log + dual-lane vectors + content-addressed ids + manifest mean the substrate is replayable and inspectable without trusting raw web.
4. **Governance-by-math (sketch, §4)** — scope/quality move out of my memory into deterministic records.

---

## 4. Governance math layer (SKETCH — not yet extracted, do not trust)

Intended: the daemon runs PM + AI-management as math, not my judgment.
- **Schema registry** — every interaction across the codebase emits a typed, versioned record (`lgwks.<name>.v1`). Scope creep = a record outside the logged intent's allowed set.
- **Scope-creep gate** — on detected expansion: **force reject → log to ledger → return to logged intent** (Director's mechanism). Hard gate, not advisory.
- **Audit ledger** — append-only, hash-chained; decisions/verdicts/scope-changes/blocks written as side-effects; docs/ADRs write themselves.
- **Gates/scores** — coverage/gap/confidence thresholds decide proceed/block/escalate; per-turn slop/drift verdict on AI output.
- **DBs** — separate single-writer stores: `governance.db`, `worldgraph.db`, `cgp.db`, `schema.db`.

This section is a sketch. The real extraction (which modules hold which working fragment) is **not done** — flagged so I don't pretend it is.

---

## 5. Decisions — settled vs open (blur cleared 2026-06-09)

**Settled:**
- **Crawl seam = Rust, standalone, BUILT.** The first seam is implemented as a standalone Rust crate ([`crawler/`](../../crawler), see [CRAWLER-spec.md](CRAWLER-spec.md)) — doc-aligned (the nervous-system doc puts crawl/hot-path in Rust). This is the proof-of-shape for the rebuild.
- **Model layer = OUT OF SCOPE.** Director: ignore completely until a dedicated session. Treated as an opaque dependency. Do not re-spec it.

**Open (Director's call):**
1. **Daemon language** — the *crawler* is Rust, but the **daemon/control-bus** language (Go for speed vs Rust for fleet-consistency with axiom/logic-os-kernel) is still unsettled. The nervous-system doc favors Python-orchestrator + Rust-seams + daemon-last; reconcile vs "Go daemon" before the daemon spine is built.
2. **Canonical content-address scheme** — axiom uses **blake2**, the Python substrate uses **sha256**, the new crawler uses **blake2b**. One must win (recommend blake2b, migrate substrate). Correctness issue: crawler feeds substrate, keys must agree.
3. **Governance math** — §4 still a sketch; needs real extraction before it's trustworthy.
