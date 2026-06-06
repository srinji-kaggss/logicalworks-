"""Tests for lgwks_graph_viz — simple localhost graph visualization."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_graph_viz as viz


# ── data adapter ──────────────────────────────────────────────────────────────

def test_adapter_loads_graph():
    """L0: GraphDataAdapter loads the graph from a real repo."""
    repo = Path("/Users/srinji/logicalworks-")
    adapter = viz.GraphDataAdapter(repo)
    assert adapter.load() is True
    assert adapter.graph is not None
    assert len(adapter.graph.nodes) > 0


def test_adapter_to_frontend_structure():
    """L0: to_frontend returns nodes and edges arrays."""
    repo = Path("/Users/srinji/logicalworks-")
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
    repo = Path("/Users/srinji/logicalworks-")
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
    repo = Path("/Users/srinji/logicalworks-")
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    assert adapter.node_detail("nonexistent.py") is None


def test_adapter_query_runs_cypher():
    """L0: adapter.query runs Cypher-like queries against the graph."""
    repo = Path("/Users/srinji/logicalworks-")
    adapter = viz.GraphDataAdapter(repo)
    adapter.load()
    result = adapter.query('MATCH (n) WHERE n.kind = "file" RETURN n.id LIMIT 5')
    assert "columns" in result
    assert "rows" in result
    assert len(result["rows"]) <= 5


# ── DOT export ────────────────────────────────────────────────────────────────

def test_handler_to_dot_valid_syntax():
    """L0: _to_dot produces valid DOT syntax."""
    repo = Path("/Users/srinji/logicalworks-")
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
        args.repo = "/Users/srinji/logicalworks-"
        args.serve = False
        args.export_html = out
        args.port = 3000
        rc = viz.viz_command(args)
        assert rc == 0
        assert Path(out).exists()
        content = Path(out).read_text()
        assert "<svg>" in content
        assert "d3.v7.min.js" in content
    finally:
        Path(out).unlink(missing_ok=True)


def test_viz_command_requires_serve_or_export():
    """L0: without --serve or --export-html, returns error."""
    args = MagicMock()
    args.repo = "/Users/srinji/logicalworks-"
    args.serve = False
    args.export_html = None
    args.port = 3000
    rc = viz.viz_command(args)
    assert rc == 1
