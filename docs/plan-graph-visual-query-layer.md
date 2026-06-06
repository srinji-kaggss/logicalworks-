# Graph Visual+Query Layer — Factory Spec

**Status:** Draft — pending Director approval  
**Scope:** Terminal-native graph visualization that IS the query interface  
**Files touched:** `lgwks_graph_viz.py` (new), `lgwks_graph.py` (additions), `lgwks_home.py` (integration), `tests/test_graph_viz.py` (new)

---

## 1. Problem Statement

The graph exists (`lgwks_graph.py`, 1,200 lines, 24 public methods, Cypher-like query engine). It is powerful but invisible. Users run `lgwks graph --complexity` and get JSON. They run `lgwks graph --query "MATCH (n) WHERE n.kind = 'file' RETURN n.id LIMIT 10"` and get JSON. There is no spatial intuition — no "see the graph, click a node, explore its neighbors, understand impact radius visually."

The REPL and browser have the same gap: the graph is data, never a navigable surface.

**Root cause:** Every query path terminates in JSON or text. No rendering pipeline. No "graph as interface."

**User evidence:**
> "can u build in the graphing visual layer, see how you can factory spec it so its basically the query layer as well"

---

## 2. Existing Inventory (what we have, no invention)

| Component | State | API |
|---|---|---|
| `Graph` class | Production | `neighbors()`, `predecessors()`, `shortest_path()`, `impact_radius()`, `pagerank()`, `betweenness_centrality()`, `detect_patterns()`, `change_propagation_score()` |
| `Node` / `Edge` | Immutable dataclasses | `id`, `kind`, `imports`, `defines`, `calls`, `variables`, `config_keys`, `sha256` |
| `execute_query()` | Cypher-like | `MATCH (n)-[:import]->(m) WHERE ... RETURN ... LIMIT` |
| `graph_command()` | CLI | `--impact`, `--complexity`, `--path`, `--neighbors`, `--query`, `--patterns` |
| `get_graph()` | Cached | Incremental load from `.lgwks/graph.cache.json` |
| `lgwks_ui.py` | Terminal rendering | Spine/tree, 256-color palette, `fg()`, `spine()`, `scale()` |

---

## 3. What We Do NOT Have

| Gap | Impact |
|---|---|
| No ASCII/Unicode graph rendering | Cannot "see" the graph in the terminal |
| No DOT/SVG export | Cannot use external tools (Graphviz, d2, Obsidian) |
| No interactive graph navigation | Cannot click/select a node and explore |
| No "graph browser" in `lgwks_home` | The browser has domains/commands, no graph mode |
| No visual query (spatial → query) | Cannot draw a subgraph and ask "what depends on this?" |
| No `lgwks graph viz` subcommand | No CLI path to visualization |

---

## 4. Design: The Visual Layer IS the Query Layer

**Inversion:** Instead of "write a query → get JSON → mentally map to graph structure," the user sees the graph, navigates it spatially, and every navigation action IS a query.

### 4.1 Mental Model

```
User sees:
  ┌─ lgwks_graph.py (root)
  │  ├─ Node (class)
  │  │  └─ id, kind, imports, defines, calls...
  │  ├─ Edge (class)
  │  │  └─ source, target, kind, weight
  │  └─ Graph (class)
  │     └─ neighbors(), pagerank(), shortest_path()...
  │
  └─ lgwks_graph_viz.py (new)
     ├─ GraphRenderer (ASCII/Unicode tree)
     ├─ DotExporter (DOT format for Graphviz)
     ├─ GraphBrowser (interactive TUI)
     └─ VizQueryEngine (spatial selection → query)
```

### 4.2 Three Render Modes

| Mode | Use Case | Output |
|---|---|---|
| **ASCII tree** | Terminal, quick look, REPL | Unicode box-drawing, depth-colored |
| **DOT export** | External tools, presentations, PRs | `.dot` file → Graphviz SVG/PNG |
| **Interactive TUI** | Deep exploration, impact analysis | Select node → see neighbors, metrics, paths |

### 4.3 The Query Loop (visual → query → visual)

```
1. User runs: lgwks graph viz --repo ~/my-project
2. GraphBrowser loads the graph (cached)
3. Shows: root modules as top-level tree nodes
4. User selects a node (arrow keys / number)
5. Action menu: [n] neighbors  [i] impact  [p] path to...  [q] query  [e] expand
6. Selecting [n] runs graph.neighbors(node) → renders sub-tree
7. Selecting [i] runs graph.impact_radius([node]) → renders heat map (color = score)
8. Selecting [p] prompts for target → runs shortest_path → renders the path
9. Selecting [q] opens Cypher query input → execute_query → renders results as table
```

Every action is a query. The visualization IS the query result, and the next action is the next query.

---

## 5. Architecture

### 5.1 New File: `lgwks_graph_viz.py`

```python
# ── renderers ──────────────────────────────────────────────────────────────────

class GraphRenderer:
    """ASCII/Unicode tree rendering of a Graph subgraph."""
    def render_tree(self, graph: Graph, root_ids: list[str], depth: int = 3) -> list[str]:
        """Return lines of Unicode box-drawing text."""

    def render_impact_heatmap(self, graph: Graph, scores: dict[str, float]) -> list[str]:
        """Render nodes colored by impact score (0→green, 1→red)."""

    def render_path(self, graph: Graph, path: list[str]) -> list[str]:
        """Render a shortest path as a connected chain."""

    def render_query_table(self, result: QueryResult, max_width: int = 80) -> list[str]:
        """Render QueryResult as a bordered table."""


class DotExporter:
    """Export Graph or subgraph to DOT format for Graphviz."""
    def export(self, graph: Graph, path: Path, highlight: set[str] | None = None) -> None:
        """Write .dot file. highlight = node IDs to color differently."""


# ── interactive browser ─────────────────────────────────────────────────────

class GraphBrowser:
    """Stack-based TUI for graph exploration. Same navigation model as lgwks_home browser."""
    def __init__(self, graph: Graph, on: bool = True):
        self.graph = graph
        self.stack: list[tuple[str, ...]] = []  # ("overview",) | ("node", node_id) | ("impact", node_id) | ("path", src, dst)
        self.selected_node: str | None = None

    def run(self) -> int:
        """Main loop. Returns exit code."""

    def _render_overview(self) -> None:
        """Show top-level modules/files as a tree."""

    def _render_node_detail(self, node_id: str) -> None:
        """Show node metadata + action menu."""

    def _render_impact_view(self, node_id: str) -> None:
        """Show impact radius as heat map."""

    def _render_path_view(self, src: str, dst: str) -> None:
        """Show shortest path between two nodes."""

    def _render_query_input(self) -> None:
        """Prompt for Cypher query, execute, show results."""
```

### 5.2 Integration Points

| Integration | Change |
|---|---|
| `lgwks_graph.py` | Add `to_dot()` method on Graph; add `viz` subcommand in `graph_command()` |
| `lgwks_home.py` | Add "6 Visual" domain with `graph`, `entity-graph` commands; add `v` quick action for "visual graph browser" |
| `lgwks_repl.py` | Add `.viz` special command to launch GraphBrowser with loaded graph |
| CLI | `lgwks graph viz --repo .` launches interactive browser; `lgwks graph viz --export-dot out.dot` exports |

### 5.3 Rendering Details

**ASCII Tree (terminal-native):**
```
▸ lgwks_graph.py
  ├─ Node (class)
  │  ├─ id: str
  │  ├─ kind: str
  │  └─ imports: tuple
  ├─ Edge (class)
  │  └─ source, target, kind, weight
  └─ Graph (class)
     ├─ neighbors() → list[str]
     ├─ pagerank() → dict[str, float]
     └─ shortest_path() → list[str] | None
```

Color encoding:
- Nodes: cream (normal), emerald (high pagerank), amber (high betweenness), slate_dim (orphan)
- Edges: emerald (import), amber (call), muted (inherit)
- Heat map: gradient from cream (0) → amber (0.5) → red (1.0) for impact scores

**DOT Export:**
- Full graph or filtered subgraph
- Node shape by kind (box=file, ellipse=config, diamond=data)
- Edge color by kind
- Highlight set colored differently
- `dot -Tsvg out.dot -o graph.svg` for PRs/presentations

---

## 6. CLI Surface

```bash
# Interactive visual browser (the main experience)
lgwks graph viz --repo ~/my-project

# Export to DOT for external tools
lgwks graph viz --repo ~/my-project --export-dot graph.dot
lgwks graph viz --repo ~/my-project --export-dot - | dot -Tsvg > graph.svg

# Render specific query results visually
lgwks graph viz --repo ~/my-project --query "MATCH (n) WHERE n.kind = 'file' RETURN n.id"

# Impact heat map
lgwks graph viz --repo ~/my-project --impact --files src/core.py --radius 3

# From REPL
cl-ideas >>> .viz
[launches GraphBrowser with loaded graph]

# From browser home
❯ v
[launches GraphBrowser]
```

---

## 7. Test Plan (H0 Falsification)

| Test | Falsifies |
|---|---|
| `test_renderer_tree_non_empty` | "render_tree produces no output" |
| `test_renderer_tree_respects_depth` | "render_tree ignores depth limit" |
| `test_dot_exporter_valid_syntax` | "DOT output is malformed" |
| `test_browser_overview_shows_nodes` | "browser starts empty" |
| `test_browser_select_node_shows_detail` | "node selection does nothing" |
| `test_browser_impact_shows_heatmap` | "impact view is flat" |
| `test_browser_path_renders_chain` | "path view skips intermediate nodes" |
| `test_browser_query_executes_cypher` | "query input is ignored" |
| `test_repl_dotviz_launches_browser` | `.viz command fails` |
| `test_home_quick_v_launches_viz` | "v quick action missing" |

---

## 8. Factory Breakdown (3-agent sequence)

**Phase 1: Spec → Architecture** (this document) → Director approval

**Phase 2: Implement** (coder agent)
- `lgwks_graph_viz.py`: GraphRenderer, DotExporter, GraphBrowser
- Additions to `lgwks_graph.py`: `to_dot()`, `viz` subcommand
- Integration: `lgwks_home.py` "Visual" domain, `v` quick action
- Integration: `lgwks_repl.py` `.viz` special command

**Phase 3: Harden** (hacker agent)
- Fuzz GraphBrowser with malformed node IDs
- Verify DOT output is valid (run through `dot -Tsvg` if available)
- Test memory: large graphs (10k+ nodes) don't hang renderer
- Test empty graph: renders gracefully, not crash
- Test no Graphviz: `--export-dot` still writes file, warns about missing `dot`

---

## 9. Usage Examples

### 9.1 Daily Flow: Understand a New Repo

```bash
$ cd ~/new-project
$ lgwks
# browser detects repo, shows home screen
❯ v
# GraphBrowser opens:
# ▸ Overview — 147 nodes, 312 edges
#   1 src/          23 files
#   2 tests/        8 files
#   3 config/       3 files
#   4 docs/         2 files
#
# q quit  ·  [number] pick module  ·  s search  ·  p patterns
❯ 1
# ▸ src/core.py
#   kind: file  |  pagerank: 0.042  |  betweenness: 0.018
#   defines: Graph, Node, Edge
#   calls: get_graph, extract_from_repo
#
#   [n] neighbors  [i] impact  [p] path to...  [q] query  [e] expand  [b] back
❯ n
# ▸ neighbors of src/core.py
#   outgoing:
#     1 src/cache.py     (import)
#     2 src/schema.py    (import)
#     3 src/query.py     (call)
#   incoming:
#     1 src/cli.py       (import)
#     2 tests/test_graph.py (import)
❯ i
# ▸ impact radius: src/core.py (radius=3)
#   src/core.py           ████████░░ 0.82  [changed]
#   src/cache.py          ██████░░░░ 0.61
#   src/cli.py            ████░░░░░░ 0.42
#   tests/test_graph.py   ██░░░░░░░░ 0.18
```

### 9.2 PR Review: Check Change Propagation

```bash
$ lgwks graph viz --impact --files src/auth.py,src/session.py --radius 3
# Renders heat map in terminal:
#   src/auth.py           ██████████ 1.00  [changed]
#   src/session.py        ██████████ 1.00  [changed]
#   src/middleware.py     ████████░░ 0.78
#   src/api.py            ██████░░░░ 0.54
#   tests/test_auth.py    ████░░░░░░ 0.31
```

### 9.3 External Visualization

```bash
$ lgwks graph viz --export-dot graph.dot
$ dot -Tsvg graph.dot -o graph.svg
# Open graph.svg in browser — full Graphviz layout with colors
```

---

## 10. Open Questions

1. **Large graphs (>1k nodes):** ASCII tree may be unwieldy. Do we paginate, filter by pagerank threshold, or use a "focus mode" (show N highest-pagerank nodes only)?
2. **Entity graph vs code graph:** The entity graph (`lgwks_entity_graph.py`) uses SQLite, different schema. Do we visualize both, or is this spec for the code graph only?
3. **Real-time updates:** If files change during browsing, do we auto-refresh, warn, or require `.refresh`?

---

## 11. Decision Needed

| Option | Pros | Cons |
|---|---|---|
| **A: Terminal-only** (ASCII tree + DOT export) | Zero deps, works everywhere, fast | No mouse interaction, limited layout |
| **B: Terminal + optional rich/TUI** (use `rich` or `textual` if installed) | Better visuals, mouse support | Adds optional dependency, complexity |
| **C: Web viewer** (export HTML with D3.js) | Best visuals, interactive | Requires browser, not terminal-native |

**Recommendation: Option A for core, Option B as optional enhancement.**

The terminal is the lgwks native surface. ASCII tree + DOT export covers 90% of use cases. If `rich` is installed, we can detect it and use panels/tables for prettier rendering, but the core works without it.

---

## 12. Rollout

1. **This spec** → Director approval
2. **Implement** → `lgwks_graph_viz.py` + integrations
3. **Tests** → 10 H0-falsification tests
4. **Harden** → adversarial pass
5. **Docs** → update `lgwks graph --help`, add `.viz` to REPL help, add `v` to browser help
6. **Align** → commit, merge to main, push

RISK: Graph layout in ASCII is inherently limited. Complex graphs (dense, many cross-edges) will look messy. Mitigation: default to tree view (hierarchical), offer "focus on node" to reduce clutter. DOT export is the escape hatch for complex graphs.

---

*Reading you as: Director wants a terminal-native graph visualization that doubles as the query interface — not a separate tool, but the primary way to explore and query the graph. This spec proposes a 3-render-mode system (ASCII tree, DOT export, interactive TUI browser) integrated into the existing browser, REPL, and CLI.*

*RISK: Scope could expand to "build a full graph database GUI in the terminal." The spec gates that by limiting to: (1) ASCII tree rendering of existing query results, (2) DOT export for external tools, (3) stack-based TUI browser reusing the browser navigation model. No new query engine, no new graph data model — only visualization of what exists.*
