# GAP ANALYSIS: lgwks CLI vs. Greptile, Firecrawl, and Modern Dev Tools

**Date:** 2026-06-09
**Base Commit:** `9146cfd`
**Tests:** 1,095/1,095 pass

---

## TL;DR

lgwks has **deep deterministic infrastructure** (deterministic crawl, AST-based refactoring, on-device models, structured review pipelines) but **gaps in SaaS-grade DX** (real-time sync, hosted multi-repo, natural language query, persistent knowledge graph). The gaps are addressable without architectural compromise — most need API/service layers on top of existing deterministic engines.

---

## Competitor Feature Matrix

### 1. Greptile (AI-Powered Code Intelligence)

| Feature | Greptile | lgwks Status | Gap Severity |
|---------|----------|--------------|--------------|
| **Multi-repo indexing** | Indexes entire GitHub orgs/repos | Single-repo `repo graph` | HIGH |
| **Natural language codebase queries** | "How does auth work?" | `comprehend` (static summary only) | HIGH |
| **Real-time PR review** | Comments on PRs automatically | `lgwks do ship` (manual, local) | HIGH |
| **Persistent knowledge graph** | Indexed embeddings stored in cloud | `substrate query` (local SQLite) | MEDIUM |
| **Cross-repo navigation** | Jump between repos | `repo graph` (single repo) | HIGH |
| **Chat interface** | Conversational Q&A over code | `repl` (command-line, no context memory) | MEDIUM |
| **CI/CD integration** | GitHub Actions, pre-commit hooks | `hooks` system exists, not CI-native | MEDIUM |
| **Team annotations** | Comments on code linked to queries | None | MEDIUM |
| **Symbol-level search** | "Find all callers of X" | `graph` (Cypher-like queries, local) | LOW |

### 2. Firecrawl (Web Scrape → LLM-Ready Markdown)

| Feature | Firecrawl | lgwks Status | Gap Severity |
|---------|-----------|--------------|--------------|
| **Hosted scrape API** | `POST /v1/scrape` with any URL | `jarvis crawl` (local Python only) | HIGH |
| **JavaScript-rendered pages** | Built-in headless browser | `fetch` (Playwright-based, works) | LOW |
| **Batch scrape at scale** | `POST /v1/batch/scrape` | `jarvis crawl` (sequential, bounded) | MEDIUM |
| **LLM extraction (JSON)** | `/v1/extract` with schema | `extract` + `convert` (deterministic, no LLM) | MEDIUM |
| **Sitemap/crawl maps** | `POST /v1/map` | `jarvis crawl` produces maps | LOW |
| **API keys & rate limits** | SaaS with quotas | No API layer; CLI only | HIGH |
| **Webhook callbacks** | `webhookUrl` parameter | No webhook system | MEDIUM |
| **Structured data extraction** | LLM-powered JSON extraction | Deterministic parsing only | MEDIUM |
| **Search + scrape combined** | `POST /v1/search` | `public` (deterministic search) | LOW |

### 3. Additional Competitors (Cursor, Sourcegraph, etc.)

| Feature | Cursor / Sourcegraph | lgwks Status | Gap Severity |
|---------|---------------------|--------------|--------------|
| **IDE integration** | VS Code extension | None | HIGH |
| **Inline code suggestions** | Ghost text, completions | None | HIGH |
| **Chat in IDE** | Side panel chat | `repl` (terminal only) | HIGH |
| **Multi-file edits** | AI proposes cross-file changes | `refactor` (single-file AST only) | HIGH |
| **Persistent code memory** | Remembers project context | `memory` (local JSONL chains) | MEDIUM |
| **Semantic search** | "Find similar code" | `embed` (local vector vault) | LOW |
| **Code intelligence API** | GraphQL API for symbols | `repo graph` (local JSON) | MEDIUM |

---

## Consolidated Gap List (Prioritized)

### P0 — Must Have for SaaS Competitiveness

1. **Natural Language Codebase Queries (NLQ)**
   - *What:* Ask questions about code in plain English: "How does error handling work in the auth module?"
   - *Current:* `comprehend` produces static architecture summaries; no interactive Q&A.
   - *Competitor:* Greptile's core value prop.
   - *Implementation:* Add RAG pipeline over `repo graph` + `embed` vector vault using the 4-model hierarchy (NeoBERT for synthesis, CodeBERT for code understanding). Reuse existing `substrate query` infrastructure.
   - *Effort:* Medium. The embeddings and graph exist; need a query router + prompt template.

2. **Hosted API / Service Layer**
   - *What:* REST API wrapping `jarvis crawl`, `review`, `do`, etc. with auth, rate limits, and webhooks.
   - *Current:* CLI-only. No server mode.
   - *Competitor:* Firecrawl's entire business model is this API.
   - *Implementation:* FastAPI wrapper around existing module functions. Add JWT auth via `keyvault` + API key management. Reuse `lgwks_aup` for request gating.
   - *Effort:* Medium. All core logic exists; need HTTP layer + async queue.

3. **Multi-Repo Indexing & Cross-Repo Navigation**
   - *What:* Index multiple repos and navigate between them (e.g., "Find where this function is used across repos").
   - *Current:* `repo graph` is single-repo. `jarvis crawl` is single-origin.
   - *Competitor:* Greptile indexes entire GitHub orgs.
   - *Implementation:* Extend `repo graph` to accept multiple repo paths. Store combined graph in SQLite. Add cross-repo edge types ("imports from", "references").
   - *Effort:* Medium. Graph engine is modular; need multi-source ingestion.

4. **Real-Time GitHub PR Integration**
   - *What:* Automatically review PRs, comment on lines, approve/block merges.
   - *Current:* `lgwks do ship` is manual CLI. `gh pr` is read-only inspection.
   - *Competitor:* Greptile's main revenue stream.
   - *Implementation:* GitHub App using `gh` CLI + `lgwks_review`. Webhook receiver → `do ship` → post review comments via GitHub API. Reuse `lgwks_hooks` for event system.
   - *Effort:* High. Need GitHub App setup, webhook infrastructure, comment formatting.

### P1 — Significant Differentiators

5. **IDE Extension (VS Code)**
   - *What:* Side panel showing lgwks insights: review findings, graph queries, intent classifier results.
   - *Current:* Terminal-only.
   - *Competitor:* Cursor, Sourcegraph, GitHub Copilot.
   - *Implementation:* VS Code extension calling local `lgwks` commands via Node.js `child_process`. Or, if API layer built first, call REST API.
   - *Effort:* Medium (if API exists) to High (if CLI-spawning only).

6. **LLM-Powered Structured Extraction**
   - *What:* Extract specific data from web pages using natural language schemas (not just deterministic parsing).
   - *Current:* `extract` + `convert` use deterministic HTML→Markdown. No LLM extraction.
   - *Competitor:* Firecrawl `/extract` endpoint.
   - *Implementation:* Add optional LLM pass after `jarvis crawl` extraction using local models via `lgwks_local_llm.py` (Ollama bridge). Keep deterministic path as fallback.
   - *Effort:* Low-Medium. Ollama bridge exists; need schema-to-prompt conversion.

7. **Persistent Cloud Knowledge Graph**
   - *What:* Sync local substrate/graph to cloud for team access and persistence across machines.
   - *Current:* `substrate query` reads local SQLite. No sync.
   - *Competitor:* Greptile's indexed knowledge base.
   - *Implementation:* Add optional cloud backend (S3/R2 for blobs, Supabase/Postgres for graph). Keep local-first default.
   - *Effort:* Medium. Need sync protocol + conflict resolution.

8. **Conversational Memory / Chat**
   - *What:* Multi-turn conversations about the codebase with context memory.
   - *Current:* `repl` is single-shot command line. `memory remember` appends but no retrieval-augmented chat.
   - *Competitor:* Every AI coding tool.
   - *Implementation:* Build chat loop on top of `memory` chains + `repo graph` RAG. Use tiny-bert for intent classification per turn.
   - *Effort:* Medium. Memory chains exist; need retrieval + response generation.

### P2 — Polish / Nice to Have

9. **Batch Operations at Scale**
   - *What:* Process thousands of URLs or files concurrently.
   - *Current:* `jarvis crawl` is bounded and sequential. `batch` exists but is typed command batching, not data processing.
   - *Competitor:* Firecrawl batch API.
   - *Implementation:* Add worker pool to `jarvis crawl`. Reuse `lgwks_batch` infrastructure.
   - *Effort:* Low-Medium.

10. **Team Collaboration Features**
    - *What:* Share findings, annotations, and review comments across a team.
    - *Current:* Single-user local findings directory.
    - *Competitor:* Greptile team features.
    - *Implementation:* Add findings sync to shared store (GitHub Issues, Slack, or cloud DB).
    - *Effort:* Medium-High.

11. **Web Dashboard**
    - *What:* Browser-based UI for graph visualization, review results, crawl status.
    - *Current:* `graph viz` generates static files. `portal show` is CLI output.
    - *Implementation:* Serve `graph viz` output via embedded HTTP server. Add HTMX/Alpine.js for interactivity.
    - *Effort:* High. Full frontend project.

---

## What lgwks Already Does Better Than Competitors

These are **defensive moats** — don't compromise them while closing gaps:

1. **Deterministic Core** — Every operation has a reproducible, non-LLM fallback. Competitors depend on LLM availability and cost.
2. **On-Device Models** — 4-model hierarchy runs without API keys or network. No competitor offers this at this integration depth.
3. **AUP / Governance Layer** — `lgwks_aup` is unique. No competitor has built-in acceptable use policy enforcement with audit trails.
4. **AST-Based Refactoring** — `lgwks_refactor` is deterministic and safe. Greptile/Cursor use LLM-based refactoring which can hallucinate.
5. **Structured Review Pipeline** — `lgwks_review` with bot fabric, JEPA packaging, and artifact strength evaluation is more rigorous than Greptile's pattern matching.
6. **Git-Native Workflow** — `repo sync`, `repo handoff`, `agent-os fleet` are deeply integrated with git. Competitors treat git as an afterthought.
7. **Schema-Driven Everything** — `manifest`, `intent`, `axiom`, `jepa` all produce typed, machine-readable artifacts. Competitors produce prose.

---

## Recommended Implementation Order

Based on impact vs. effort and maintaining the deterministic core:

| Phase | Feature | Effort | Impact | Unlocks |
|-------|---------|--------|--------|---------|
| 1 | **API Layer** (FastAPI wrapper) | Medium | HIGH | Enables IDE, CI, webhooks |
| 2 | **NLQ over repo graph** (RAG) | Medium | HIGH | Matches Greptile core value |
| 3 | **GitHub App / PR integration** | High | HIGH | Revenue stream, team adoption |
| 4 | **Multi-repo indexing** | Medium | MEDIUM | Enterprise scaling |
| 5 | **LLM extraction** (optional pass) | Low | MEDIUM | Matches Firecrawl `/extract` |
| 6 | **VS Code extension** | Medium | MEDIUM | DX parity with Cursor |
| 7 | **Cloud sync for substrate** | Medium | LOW | Team persistence |
| 8 | **Chat / conversational memory** | Medium | LOW | General AI tool parity |

---

## Files Touched by Gap Closure

| Feature | New Files | Modified Files |
|---------|-----------|----------------|
| API Layer | `lgwks_server.py`, `lgwks_api.py` | `lgwks` (add `server` verb), `lgwks_aup` (rate limiting) |
| NLQ | `lgwks_query.py` | `lgwks_repo`, `lgwks_embed`, `lgwks_graph` |
| GitHub App | `lgwks_github_app.py` | `lgwks_gh`, `lgwks_hooks` |
| Multi-repo | — | `lgwks_repo` (multi-source), `lgwks_graph` |
| LLM extraction | `lgwks_extract_llm.py` | `lgwks_crawl`, `lgwks_files` |
| VS Code ext | `vscode-lgwks/` (new dir) | — |
| Cloud sync | `lgwks_sync.py` | `lgwks_substrate`, `lgwks_vault` |
| Chat | `lgwks_chat.py` | `lgwks_memory`, `lgwks_repl` |

---

*End of analysis. All findings based on codebase inspection at commit `9146cfd` and public competitor documentation as of 2026-06-09.*
