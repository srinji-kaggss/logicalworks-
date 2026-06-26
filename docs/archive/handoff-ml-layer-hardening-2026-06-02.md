---
type: Archive
title: Handoff: ML Layer Hardening + All-in-One CLI Roadmap
description: Instead of building N separate compression tools, build ONE layer that every module calls:
tags: [archive]
timestamp: 2026-06-23T00:24:35-04:00
---

# Handoff: ML Layer Hardening + All-in-One CLI Roadmap

**Date:** 2026-06-02
**Branch:** main @ ca8e4c8
**Scope:** Harden the ML layer; define the path to 90% token reduction via native + transformer features
**Sources:** arXiv 2308.10248v5 (Activation Engineering), CodeRabbit CLI docs, LeanCTX, tok, Skim, TokenForge, Claude God Mode

---

## Part 1: Competitive Intelligence — What Exists

### 1.1 LeanCTX (Rust, MCP Server)
- **Claim:** Up to 99% token savings
- **Mechanism:** 10 read modes (full → map → signatures → diff → lines:N-M), 56 shell pattern modules, tree-sitter AST for 18 languages, multi-edge Property Graph, session memory, browser dashboard
- **Integration:** MCP protocol + shell hooks (Hybrid mode); 30+ agents supported
- **Key insight:** *Routing* is as important as compression — send simple queries to cheap outputs

### 1.2 tok (Go, CLI)
- **Claim:** 60–90% savings
- **Mechanism:** 6 compression modes (lite → full → ultra + wenyan variants), transparent shell hook (`tok init -g` rewrites `git status` → `tok git status`), SQLite analytics with WAL
- **Key insight:** *Transparent interception* — agent doesn't know it's being optimized

### 1.3 Skim (Rust, cargo/npm/Homebrew)
- **Claim:** 15–95% reduction
- **Mechanism:** Tree-sitter AST parsing (17 languages), 6 transformation modes (full → minimal → pseudo → structure → signatures → types), PreToolUse hook rewrites `cat`/`git diff`/`cargo test`, SHA256(file+mtime+mode) cache → 48x speedup, ~5ms cache hits
- **Key insight:** *AST-aware compression* keeps intent, drops minutiae; caching is critical

### 1.4 TokenForge (Rust, MCP Server)
- **Claim:** 20–95% across all token sources
- **Mechanism:** AST-aware compression via real tree-sitter grammars, semantic diff compression, lossless reversibility (SQLite/zstd), MCP server, quality scoring 0–100, per-category token budgets
- **Key insight:** *Quality scoring* — know when compression degraded the signal

### 1.5 CodeRabbit CLI
- **Features:** Review uncommitted changes, `--agent` JSON mode, `cr doctor` (audit runtime health, storage, credentials), `cr review findings` (replay), `cr --show-prompts`, auth/org switching
- **Key insight:** *Agent-first JSON output* + health audit + findings replay = the interface an AI needs

### 1.6 arXiv 2308.10248v5 — "Steering Language Models With Activation Engineering"
- **Contribution:** Activation Addition (ActAdd) — inject steering vectors into residual stream at inference time without retraining
- **Relevance:** Could steer the *output quality* of generated code (safety patterns, documentation tone) but does NOT directly address token reduction
- **Verdict:** Interesting for intent enforcement layer, NOT a token reduction technique. File under "future enrichment" not "core compression"

---

## Part 2: What We Have (Current State)

### Built Modules (all committed to main @ ca8e4c8)
| Module | Purpose | DiD | Status |
|---|---|---|---|
| `lgwks_graph.py` | Functional codebase graph (AST imports, adjacency, shortest path, impact radius) | T0–T6 | ✅ Complete |
| `lgwks_debug.py` | Pattern-based failure detection (25+ signatures), risk-classified fixes | T0–T6 | ✅ Complete |
| `lgwks_intent.py` | Schema-driven intent router (probe → match → act), condition allowlist | T0–T6 | ✅ Complete |
| `lgwks_gh.py` | GitHub CLI wrapper with validation, scrub, rate-limit, audit | T0–T6 | ✅ Complete |
| `lgwks_repo.py` | Repo lifecycle (audit, recover, cleanup, merge, handoff, graph, sync) | T0–T5 | ✅ Complete |
| `lgwks_manifest.py` | Machine-readable contract — 49 verbs fully documented | T0 | ✅ Complete |
| `lgwks_capabilities.py` | Resolver for 18 capabilities + 13 external dev tools | T0 | ✅ Complete |

### Architecture Strengths
- **Schema-first:** Every command returns structured JSON (`--json` flag universal)
- **DiD layers:** T0 schema → T1 shell safety → T2 secret scrub → T3 rate-limit → T4 timeout → T5 audit → T6 auth/risk gate
- **Pattern DB:** Regex-based failure signatures with severity + fix_risk classification
- **Graph engine:** Immutable Node/Edge with adjacency indexes, forward/reverse traversal
- **Manifest-driven:** 49 verbs + 13 external tools discoverable via single command

---

## Part 3: Critical Gaps — The 90% Token Reduction Problem

### Gap 1: No Compression Layer (HIGHEST PRIORITY)
**What:** Every file read costs full tokens. Every `git status` dumps 800 tokens of raw output. No AST-aware shrinking, no read mode routing.
**Impact:** We're leaving 60–90% of tokens on the table.
**Evidence:** LeanCTX claims ~99% with caching + 56 pattern modules. Skim achieves 15–95% with 6 AST modes.
**What we need:**
- Tree-sitter integration for AST-aware compression
- Read mode router: `full` → `map` → `signatures` → `types` → `diff` → `lines:N-M`
- Shell output pattern modules (56+ signatures like LeanCTX)
- Transparent interception: agent calls `git status`, we return `lgwks status --json` instead

### Gap 2: No Caching Layer (HIGH PRIORITY)
**What:** No SHA256(file+content) cache. Every re-read is a full re-parse.
**Impact:** Skim reports 48x speedup and ~5ms cache hits. We're at 0x.
**What we need:**
- `.lgwks/cache/` directory with SHA256-indexed file contents
- Cache invalidation on mtime change
- Graph cache already exists (`.lgwks/graph.cache.json`) — expand to all reads

### Gap 3: No Token Analytics (MEDIUM PRIORITY)
**What:** No visibility into token spend per command, per session, per project.
**Impact:** Can't optimize what we don't measure. Can't prove 90% reduction without baselines.
**Evidence:** tok has SQLite analytics (`tok gain --graph`). TokenForge has quality scoring 0–100.
**What we need:**
- `.lgwks/token-audit.jsonl` — append-only record of every command's input/output token count
- Per-verb token budget tracking
- Quality scoring on compressed vs. raw output
- `lgwks stats` command showing session spend, savings, cache hit rate

### Gap 4: No MCP Server Architecture (MEDIUM PRIORITY)
**What:** We're CLI-only. Agents call us via subprocess. No protocol-native integration.
**Impact:** Can't hook into Cursor, Claude Code, Copilot at the protocol level. Can't do PreToolUse interception.
**Evidence:** LeanCTX, TokenForge, Skim all expose MCP servers. CodeRabbit has dedicated `/coderabbit:review` plugin.
**What we need:**
- `lgwks mcp` subcommand launching an MCP server
- `tool/compress` — compress file content before agent sees it
- `tool/shell` — intercept shell commands, return filtered output
- `tool/graph` — expose codebase graph as MCP resource

### Gap 5: No Transformer-Based Intent Classifier (HIGH PRIORITY)
**What:** `lgwks_intent.py` is rule-based only. The ML classifier (`lgwks_intent_classifier.py`) exists as a stub.
**Impact:** Intent routing is brittle — can't handle ambiguous states or novel conditions.
**What we need:**
- Finish the 66M param encoder-only classifier (issue #27)
- Integrate into intent router as fallback when rule-based matching fails
- Train on historical intent → action pairs from `.lgwks/intent-audit.jsonl`
- Target: <2ms ANE inference (CoreML adapter)

### Gap 6: No Session Memory / Persistence (MEDIUM PRIORITY)
**What:** Every command is stateless. No cross-session learning. No "the agent already knows X, don't re-explain."
**Impact:** Same context re-built on every turn. LeanCTX has session memory; we don't.
**What we need:**
- `lgwks_session.py` — track session state, decisions, blockers
- Summarize previous sessions on startup
- Prune old context (Cozempic-style auto-pruning)

### Gap 7: No Quality Scoring on Compression (LOW PRIORITY)
**What:** When we compress output, we don't know if we broke the signal.
**Impact:** Compressed garbage is worse than verbose truth.
**Evidence:** TokenForge has 0–100 quality scoring. Skim keeps "intent, not minutiae."
**What we need:**
- Simple heuristic: if compressed output has fewer symbols matching the query, score drops
- LLM-based scoring: ask a cheap model "does this compressed text still answer the question?"
- Fallback to full content when score < threshold

---

## Part 4: Recommended Architecture — "Context Fabric"

Instead of building N separate compression tools, build ONE layer that every module calls:

```
┌─────────────────────────────────────────────────────────────┐
│  AI Agent (Cursor / Claude Code / Copilot / lgwks CLI)     │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP / CLI
┌──────────────────────▼──────────────────────────────────────┐
│  Context Fabric (the token reduction layer)                 │
│  ├── Router: decides fidelity needed (full vs signatures)   │
│  ├── Compressor: AST-aware shrinking (tree-sitter)        │
│  ├── Cache: SHA256(file+content) → compressed blob        │
│  ├── Pattern DB: 56+ shell output filters                   │
│  └── Scorer: quality 0–100, fallback if degraded            │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  lgwks Core (existing modules)                                │
│  ├── repo (audit, sync, graph)                              │
│  ├── gh (issues, PRs, state)                                │
│  ├── debug (pattern match, propose fixes)                   │
│  ├── intent (probe → route → act)                           │
│  ├── review (graph-aware code review)                       │
│  └── manifest (machine-readable contract)                   │
└─────────────────────────────────────────────────────────────┘
```

### The Router Decision Tree
```python
def route_read(path: Path, intent: str) -> ReadMode:
    if is_new_file(path):          return ReadMode.FULL
    if intent == "review":         return ReadMode.SIGNATURES  # needs structure
    if intent == "debug":          return ReadMode.DIFF        # needs changes
    if intent == "refactor":       return ReadMode.FULL        # needs bodies
    if intent == "overview":       return ReadMode.MAP         # needs topology
    if cache_hit(path):           return ReadMode.CACHED      # ~13 tokens
    return ReadMode.FULL
```

---

## Part 5: Implementation Roadmap (Prioritized)

### Phase 1: Compression Foundation (Week 1–2)
**Goal:** Get 60%+ token reduction on the most common operations.

1. **Integrate tree-sitter** (`pip install tree-sitter tree-sitter-python`)
   - Parse Python files → AST
   - Extract: imports, class signatures, function signatures, docstrings
   - Drop: bodies, comments, whitespace
   - File: `lgwks_compress.py`

2. **Build read mode router**
   - Modes: `full`, `map`, `signatures`, `types`, `diff`, `lines:N-M`, `cached`
   - Default: `signatures` for review/overview intents
   - File: `lgwks_router.py` (or add to `lgwks_manifest.py`)

3. **Add cache layer**
   - `.lgwks/cache/` with SHA256(filename+content+mode) keys
   - Invalidation on mtime change
   - Integrate into `lgwks_graph.py` (already has `.lgwks/graph.cache.json`)

4. **Shell output pattern modules**
   - Port LeanCTX's 56 patterns (git status, npm install, pytest, docker, etc.)
   - Each module: regex → structured JSON → token count
   - File: `lgwks_patterns.py` (extends `lgwks_debug.py`)

**Deliverable:** `python lgwks compress --mode signatures src/foo.py` → compressed output. Token savings measured.

### Phase 2: Intent Classifier (Week 2–3)
**Goal:** Make intent routing ML-driven, not rule-only.

5. **Finish `lgwks_intent_classifier.py`**
   - 66M param encoder-only (DistilBERT-size)
   - Train on `.lgwks/intent-audit.jsonl` historical data
   - 12 intent classes: `review`, `debug`, `test`, `deploy`, `sync`, `audit`, `graph`, `extract`, `search`, `refactor`, `merge`, `explore`
   - CoreML export for ANE inference (<2ms)

6. **Wire classifier into intent router**
   - Rule-based first (deterministic, fast)
   - ML classifier as fallback when rules ambiguous
   - Confidence threshold: <0.7 → ask human (or default to `overview`)

**Deliverable:** `python lgwks intent classify --text "fix the bug in login"` → `{intent: "debug", confidence: 0.92, next_cmd: "lgwks debug run python -m pytest"}`

### Phase 3: MCP Server + Transparent Hooks (Week 3–4)
**Goal:** Integrate at protocol level, not just CLI.

7. **Build MCP server**
   - `lgwks mcp start` → stdio/sse server
   - Tools: `ctx_compress`, `ctx_shell`, `ctx_graph`, `ctx_audit`
   - Resources: `file://{path}?mode={mode}`, `repo://{slug}/state`

8. **Transparent interception**
   - PreToolUse hook: `cat src/foo.py` → `lgwks compress --mode signatures src/foo.py`
   - PostToolUse hook: `git status` → `lgwks patterns git-status`
   - Agent doesn't know it's optimized

**Deliverable:** Cursor/Claude Code can call `lgwks` via MCP. File reads return compressed content automatically.

### Phase 4: Analytics + Session Memory (Week 4–5)
**Goal:** Measure, learn, persist.

9. **Token analytics**
   - `.lgwks/token-audit.jsonl`: every command → input tokens, output tokens, saved tokens, cache hit
   - `lgwks stats` → ASCII graph of session spend
   - `lgwks stats --project` → project-level aggregation

10. **Session memory**
    - `lgwks_session.py`: track decisions, blockers, findings across sessions
    - Summarize on startup: "Last session: reviewed 3 files, found 2 warnings, merged PR #42"
    - Prune: keep only actionable context (Cozempic-style)

**Deliverable:** `python lgwks stats` shows token savings, cache hit rate, quality scores.

### Phase 5: Quality Scoring + Hardening (Week 5–6)
**Goal:** Ensure compressed output is still useful.

11. **Quality scoring**
    - Heuristic: symbol coverage (compressed / full ratio)
    - LLM-judge: "Does this compressed text answer the original query?"
    - Threshold: <60 → return full content

12. **Adversarial testing**
    - Hacker pass on compression layer (binning, context-loss, oversimplification)
    - Fuzz: random files × random modes × quality check
    - Ensure no secret leakage in compressed output

**Deliverable:** Compression layer passes adversarial review. 90% token reduction proven with quality >80 on benchmark.

---

## Part 6: Open Questions for Next Agent

### Technical Decisions Needed
1. **Tree-sitter vs. AST module?** We already have `ast` in `lgwks_graph.py`. Should we:
   - A) Extend `ast` with more languages (limited — Python only)
   - B) Add tree-sitter as dep (supports 18+ languages, but adds binary)
   - C) Both — `ast` for Python (fast, no dep), tree-sitter for others

2. **Cache storage format?**
   - A) JSON files (human-readable, slow)
   - B) SQLite (fast, queryable, but adds dep)
   - C) Flat files with msgpack (fast, binary, small)

3. **Intent classifier training data?**
   - We have `.lgwks/intent-audit.jsonl` but it's sparse (just started logging)
   - Need synthetic data: generate 1000+ (intent_text, action) pairs
   - Or fine-tune on public datasets (Stack Overflow intent classification)

4. **MCP server transport?**
   - A) stdio (simple, works everywhere)
   - B) SSE (networkable, but adds infra)
   - C) Both

### Known Risks
- **tree-sitter dependency:** May fail on exotic Python installs (ARM, old glibc). Have `ast` fallback.
- **Cache invalidation:** File system clocks can drift. Use mtime + size, not just mtime.
- **ML classifier bias:** Trained on historical data = biased toward past patterns. Need adversarial samples.
- **Over-compression:** Removing bodies loses context for complex bugs. Router must be conservative.

---

## Part 7: Files to Read First

1. `lgwks_manifest.py` — the 49-verb contract. Understand what's already built.
2. `lgwks_graph.py` — AST extraction, caching pattern. Extend this for compression.
3. `lgwks_debug.py` — pattern DB structure. 56 shell patterns go here.
4. `lgwks_intent.py` — rule-based router. ML classifier wires in as fallback.
5. `lgwks_capabilities.py` — tool resolver. Add tree-sitter, SQLite as capabilities.
6. `tests/test_graph.py`, `tests/test_debug.py`, `tests/test_intent.py` — test strategy (mock-based, no real deps).

---

## Part 8: Invariant for Next Agent

> **Before adding any new feature, ask:**
> 1. Does it reduce tokens for the most common operations?
> 2. Does it return structured JSON an AI can act on without prose parsing?
> 3. Does it have a cache so the next call is ~13 tokens, not ~2000?
> 4. Does it have a quality score so we know when compression breaks?
> 5. Does it integrate via MCP, not just CLI?

If any answer is "no," that's the gap. Fix it before building the next feature.

---

*Generated by Claude Opus 4.8 after research on LeanCTX, tok, Skim, TokenForge, CodeRabbit CLI, and arXiv 2308.10248v5.*
*Current repo: 49 verbs, 18 capabilities, 13 external tools, 6 DiD-hardened modules.*
*Next target: 90% token reduction via Context Fabric (compression + routing + caching + scoring).*
