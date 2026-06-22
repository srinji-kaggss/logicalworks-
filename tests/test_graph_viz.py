"""Tests for lgwks_graph_viz — simple localhost graph visualization."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_graph_viz as viz


# The repo under test = this checkout's root (tests/..), NOT a hardcoded absolute
# path. The old hardcoded-home-dir literal passed only on that one machine; on any
# other checkout / CI runner the adapter's `.git` check failed, load() returned
# False, and the graph came back empty.
_REPO = Path(__file__).resolve().parents[1]


# ── data adapter ──────────────────────────────────────────────────────────────

def test_adapter_loads_graph():
    """L0: GraphDataAdapter loads the graph from a real repo."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    assert adapter.load() is True
    assert adapter.graph is not None
    assert len(adapter.graph.nodes) > 0


def test_adapter_to_frontend_structure():
    """L0: to_frontend returns nodes and edges arrays."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    data = adapter.to_frontend()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0
    # Each node has required fields
    n = data["nodes"][0]
    assert "id" in n
    assert "kind" in n
    assert "pagerank" in n


def test_adapter_node_detail_found():
    """L0: node_detail returns metadata for an existing node."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    nid = list(adapter.graph.nodes.keys())[0]
    detail = adapter.node_detail(nid)
    assert detail is not None
    assert detail["id"] == nid
    assert "pagerank" in detail
    assert "outgoing" in detail


def test_adapter_node_detail_missing():
    """L0: node_detail returns None for unknown node."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    assert adapter.node_detail("nonexistent.py") is None


def test_adapter_query_runs_cypher():
    """L0: adapter.query runs Cypher-like queries against the graph."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    result = adapter.query('MATCH (n) WHERE n.kind = "file" RETURN n.id LIMIT 5')
    assert "columns" in result
    assert "rows" in result
    assert len(result["rows"]) <= 5


# ── DOT export ────────────────────────────────────────────────────────────────

def test_handler_to_dot_valid_syntax():
    """L0: _to_dot produces valid DOT syntax."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    dot = viz.VizHandler._to_dot(adapter.graph)
    assert dot.startswith("digraph lgwks {")
    assert dot.endswith("}")
    assert "rankdir=LR" in dot
    # Every node appears
    for nid in adapter.graph.nodes:
        assert f'"{nid}"' in dot


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_viz_command_export_html():
    """L0: --export-html writes a file and exits."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out = f.name
    try:
        args = MagicMock()
        args.repo = str(_REPO)
        args.serve = False
        args.export_html = out
        args.export_dot = None
        args.port = 3000
        rc = viz.viz_command(args)
        assert rc == 0
        assert Path(out).exists()
        content = Path(out).read_text()
        assert "<svg>" in content
        assert "d3.v7.min.js" in content
    finally:
        Path(out).unlink(missing_ok=True)


def test_viz_command_default_runs_tui():
    """L0: without --serve or --export, runs interactive TUI (returns 0 on non-tty)."""
    args = MagicMock()
    args.repo = str(_REPO)
    args.serve = False
    args.export_html = None
    args.export_dot = None
    args.port = 3000
    rc = viz.viz_command(args)
    assert rc == 0


# ── Enhanced tests for plan-graph-visual-query-layer ──────────────────────────

def test_renderer_tree_non_empty():
    """L0: render_tree produces non-empty output."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    renderer = viz.GraphRenderer()
    roots = list(adapter.graph.nodes.keys())[:3]
    lines = renderer.render_tree(adapter.graph, roots, depth=2)
    assert len(lines) > 0
    assert any("lgwks" in line for line in lines) or any(".py" in line for line in lines)


def test_renderer_tree_respects_depth():
    """L0: render_tree respects the depth limit."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    renderer = viz.GraphRenderer()
    roots = list(adapter.graph.nodes.keys())[:2]
    lines_d0 = renderer.render_tree(adapter.graph, roots, depth=0)
    lines_d1 = renderer.render_tree(adapter.graph, roots, depth=1)
    assert len(lines_d1) >= len(lines_d0)


def test_dot_exporter_creates_file():
    """L0: DotExporter writes a dot file and handles highlight set."""
    import tempfile
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    exporter = viz.DotExporter()
    with tempfile.NamedTemporaryFile(suffix=".dot", delete=False) as f:
        out = f.name
    try:
        hl = {list(adapter.graph.nodes.keys())[0]}
        exporter.export(adapter.graph, out, highlight=hl)
        assert Path(out).exists()
        content = Path(out).read_text()
        assert "digraph lgwks" in content
    finally:
        Path(out).unlink(missing_ok=True)


def test_browser_interactive_states():
    """L0: GraphBrowser traverses neighbors, impact, path, and search screens."""
    repo = _REPO
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    
    browser = viz.GraphBrowser(adapter.graph, on=False)
    
    # We mock _ask to simulate navigation inputs:
    # 1. '1': pick node 1 -> stack has ("node", node_id)
    # 2. 'n': view neighbors -> stack has ("neighbors", node_id)
    # 3. 'b': back -> stack has ("node", node_id)
    # 4. 'i': view impact -> stack has ("impact", node_id)
    # 5. 'b': back -> stack has ("node", node_id)
    # 6. 'p': view path -> stack has ("path", src, dst) (prompts for dst, then we return a node id)
    # 7. 'b': back -> stack has ("node", node_id)
    # 8. 'b': back -> stack has ("overview",)
    # 9. 's': search -> prompts for pattern, we return 'home' -> stack has ("search_results", 'home', matched)
    # 10. 'b': back -> stack has ("overview",)
    # 11. 'q': quit
    inputs = [
        "1", 
        "n", 
        "b", 
        "i", 
        "b", 
        "p", "lgwks_graph.py", 
        "b", 
        "b",
        "s", "home",
        "b", 
        "q"
    ]
    input_idx = 0
    
    def mock_ask(prompt: str) -> str:
        nonlocal input_idx
        val = inputs[input_idx]
        input_idx += 1
        return val
        
    browser._ask = mock_ask
    
    with patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.print"):
        rc = browser.run()
        assert rc == 0
        assert input_idx == len(inputs)


def test_repl_dotviz_launches_browser():
    """L0: .viz command in REPL successfully runs GraphBrowser."""
    import lgwks_repl as repl
    from unittest.mock import MagicMock
    
    ctx = repl.GraphContext()
    ctx.repo = _REPO
    ctx.graph = MagicMock()
    
    repl_inputs = [".viz", ".quit"]
    repl_idx = 0
    
    def mock_repl_input(prompt: str = "") -> str:
        nonlocal repl_idx
        val = repl_inputs[repl_idx]
        repl_idx += 1
        return val
        
    with patch("builtins.input", mock_repl_input), \
         patch("lgwks_graph_viz.GraphBrowser") as mock_browser_cls, \
         patch("builtins.print"):
        
        mock_browser = MagicMock()
        mock_browser_cls.return_value = mock_browser
        
        rc = repl.run_repl(repo_path=str(_REPO))
        assert rc == 0
        assert mock_browser_cls.called
        assert mock_browser.run.called


def test_home_quick_v_launches_viz():
    """L0: 'v' quick action in home launches GraphBrowser in-process."""
    import lgwks_home as home
    from unittest.mock import MagicMock
    
    home_inputs = ["v", "q"]
    home_idx = 0
    
    def mock_home_input(prompt: str = "") -> str:
        nonlocal home_idx
        if home_idx < len(home_inputs):
            val = home_inputs[home_idx]
            home_idx += 1
            return val
        return "q"
        
    with patch("builtins.input", mock_home_input), \
         patch("lgwks_graph_viz.GraphBrowser") as mock_browser_cls, \
         patch("lgwks_graph.get_graph") as mock_get_graph, \
         patch("builtins.print"):
        
        mock_browser = MagicMock()
        mock_browser_cls.return_value = mock_browser
        mock_get_graph.return_value = MagicMock()
        
        with patch("sys.stdin.isatty", return_value=True):
            home._browser_entryway(on=True)
            
        assert mock_browser_cls.called
        assert mock_browser.run.called

