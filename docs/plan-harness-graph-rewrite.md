---
type: Plan
title: Plan: lgwks CLI Harness Rewrite + Graph Engine Gap Analysis
description: A Claude Code-style REPL that is:
tags: [plan]
timestamp: 2026-06-05T13:34:17-04:00
---

# Plan: lgwks CLI Harness Rewrite + Graph Engine Gap Analysis

## 1. Problem Statement

### 1.1 The home launcher is broken
- `_run()` launches subprocesses that may fail silently (`subprocess.run` without `check=True`)
- Subprocess output is immediately overwritten by the re-rendered menu
- No error surfacing → user types `1`, sees nothing, thinks it's broken
- Not a true REPL — just a loop that launches external binaries

### 1.2 The graph is shallow vs Greptile
| Dimension | Greptile | lgwks today | Gap |
|---|---|---|---|
| Entity granularity | file, function, class, variable, config key | file, symbol (class/def) | Missing variables, config keys |
| Relationship types | import, call, inherit, contain, data-flow, override | import only | Missing call graph, data flow |
| Index persistence | Pre-built, incremental, git-hash invalidation | JSON file, 5-min TTL | No incremental updates |
| Query interface | Natural language + structured graph query | Python API only | No CLI query verb |
| Pattern matching | Compare against existing codebase patterns | None | No consistency enforcement |
| Impact analysis | Full transitive impact with confidence | `impact_radius()` (boolean reachability) | Needs probability-weighted scoring |
| Integration | GitHub PR comments, IDE, CI | CLI only | No CI/IDE integration |

### 1.3 AI is used everywhere, math nowhere
- `refine`, `public`, `crawl` all rely on LLM/embedding models
- The new graph math engine (`pagerank`, `betweenness`, etc.) is not wired into any verb
- No "graph-first, AI-second" pipeline: graph should do the heavy lifting, AI only for semantic gaps

---

## 2. Vision: The lgwks Harness

A Claude Code-style REPL that is:
- **Graph-native**: Every command operates on or produces graph structure
- **Deterministic-first**: Math/graph ops run locally, instantly, token-free
- **AI-augmented**: LLM is called only for semantic tasks math can't do
- **Interactive**: True REPL with readline, history, completion, inline help
- **Pluggable**: New commands register via manifest, discoverable by AI agents

---

## 3. Implementation Plan

### Phase 1: Fix the immediate bug (1 day)
**Goal:** `lgwks` home launcher works — picks execute, errors surface.

1. Fix `_run()` error handling
   - Add `check=True` or at least capture `returncode`
   - Print subprocess stderr on failure before re-rendering menu
   - Add `input("Press Enter to continue...")` after subprocess output so user can read it

2. Fix `_entryway()` flow
   - After subprocess, print a separator line, not just empty `ui.spine()`
   - On error, show the command that failed + exit code

3. Test: run `lgwks`, type `3`, see doctor output. Run `lgwks`, type `1`, see solve output.

### Phase 2: Graph entity expansion (2 days)
**Goal:** Symbol-level graph competitive with Greptile's entity layer.

1. `lgwks_graph.py` — add variable and call-graph extraction
   - AST walk: extract `Name` nodes assigned in scope → `variable` entities
   - AST walk: extract `Call` nodes → map to defined functions in repo → `call` edges
   - Extract config keys (JSON/YAML/TOML) → `config` entities
   - Wire into `extract_from_repo()`

2. Add relationship types
   - `call`: function A calls function B
   - `inherit`: class A inherits from class B
   - `contain`: file contains function/class
   - `use_var`: function uses variable
   - `config_ref`: code references config key

3. Incremental indexing
   - Cache graph by git commit hash
   - Only re-parse changed files (use `git diff`)
   - Merge new nodes/edges into existing graph instead of full rebuild

### Phase 3: Query engine (2 days)
**Goal:** Query the graph from CLI without writing Python.

1. New verb: `lgwks graph query`
   - `lgwks graph query --symbol "foo"` → find defining file + callers
   - `lgwks graph query --impact a.py` → `change_propagation_score` output
   - `lgwks graph query --complexity` → `complexity_index` output
   - `lgwks graph query --path a.py c.py` → shortest path
   - `lgwks graph query --neighbors a.py` → direct deps

2. Add Cypher-like query language (lightweight)
   - `MATCH (f:file)-[:import]->(g:file) WHERE f.id = "a.py" RETURN g.id`
   - Parse with PEG grammar or simple regex parser
   - Execute against in-memory graph

3. Add natural language bridge (AI-only call)
   - `lgwks graph ask "what breaks if I change a.py"` → NL → structured query → deterministic execution
   - The AI translates intent to query; math answers it

### Phase 4: Harness REPL (3 days)
**Goal:** Claude Code-style interactive experience.

1. Replace `_entryway()` with a proper REPL
   - `cmd` module or `prompt-toolkit` for readline/history/completion
   - Tab completion for verbs, flags, file paths
   - Persistent history (`~/.lgwks/history`)

2. Inline command execution (not subprocess)
   - Import verb modules directly, call their `*_command()` functions
   - Same process → shared state, faster, error handling is real Python exceptions
   - Subprocess only for isolation-heavy ops (browser launch, long crawls)

3. Context-aware prompt
   - Show current project, recent runs, graph complexity index in prompt
   - `lgwks>` prompt instead of blank `❯`

4. Slash commands
   - `/graph` → enter graph query mode
   - `/doctor` → run health check inline
   - `/exit` or `/quit` → leave

### Phase 5: Pattern matching + AI bridge (3 days)
**Goal:** Greptile-style pattern consistency + minimal AI usage.

1. Pattern extraction (deterministic)
   - For each function, extract structural signature: (error handling pattern, validation pattern, DB access pattern, etc.)
   - Cluster by Jaccard similarity on pattern vectors
   - Outlier detection: flag functions that don't match their cluster

2. AI-only tasks (clear boundaries)
   - Semantic intent classification: what does this function DO? (NL description)
   - Cross-language pattern matching (Python vs Rust vs TS)
   - Documentation gap detection (function has no docstring, should it?)

3. Composite analysis pipeline
   ```
   Input: changed file a.py
   Step 1 (math): graph.change_propagation_score(["a.py"]) → impacted nodes
   Step 2 (math): graph.pattern_consistency("a.py") → outliers in same cluster
   Step 3 (AI, optional): "summarize what a.py does and whether the change breaks its contract"
   Output: deterministic impact + AI semantic overlay
   ```

---

## 4. Acceptance Criteria (per phase)

### Phase 1
- [ ] `lgwks` → type `3` → doctor output visible, then returns to menu
- [ ] `lgwks` → type `1` → solve output visible, then returns to menu
- [ ] `lgwks` → type `q` → exits cleanly
- [ ] `lgwks` → type nonsense → shows error, doesn't crash

### Phase 2
- [ ] `lgwks graph extract` produces nodes for functions, classes, variables, config keys
- [ ] Call graph edges (`call` kind) exist between functions
- [ ] Incremental update: second run uses cache, only parses changed files
- [ ] Graph size on logicalworks- repo > 500 nodes, > 1000 edges

### Phase 3
- [ ] `lgwks graph query --impact a.py` returns JSON with scores
- [ ] `lgwks graph query --complexity` returns KGCI index
- [ ] Cypher-like query parses and executes on logicalworks- repo
- [ ] `lgwks graph ask "what depends on a.py"` works (AI bridge)

### Phase 4
- [ ] Tab completion works for verbs and flags
- [ ] History persists across sessions
- [ ] Inline execution: `lgwks> solve git` runs in same process
- [ ] Prompt shows project name + graph complexity

### Phase 5
- [ ] Pattern clustering identifies > 5 clusters on logicalworks- repo
- [ ] Outlier detection flags ≥ 1 function that breaks cluster pattern
- [ ] Composite pipeline: `lgwks review a.py` outputs math impact + AI summary
- [ ] AI call count for review < 1 (only for semantic overlay)

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| REPL rewrite breaks existing non-interactive usage | Keep `lgwks <verb>` working; REPL is only when bare `lgwks` is called |
| Call-graph extraction is O(n²) on large repos | Limit to Python only; sample for JS/TS; use caching |
| Cypher parser scope creep | Start with 4 patterns only; no subqueries |
| AI bridge feels like the old AI-everything pattern | Document clear boundary: AI translates, math computes |
| Phase 2-5 is 10 days of work | Decompose into GitHub issues; work in priority order |

---

## 6. Why this order

1. **Phase 1** unblocks the Director's immediate frustration (can't use the tool)
2. **Phase 2** builds the data layer that makes everything else possible
3. **Phase 3** makes the graph usable from CLI (currently only Python API)
4. **Phase 4** makes the CLI feel like a modern tool (not a 1980s menu)
5. **Phase 5** adds the AI layer on top of a solid deterministic foundation

---

*Plan version: 2026-06-05*
*Author: Logical Claude*
*Status: Draft, awaiting Director approval*
