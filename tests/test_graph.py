"""Tests for lgwks_graph — functional, traversable codebase graph.

Strategy: build graphs in memory, assert query correctness. No subprocess, no filesystem.
"""

from __future__ import annotations

import pytest

import lgwks_graph as gmod


# ── node / edge ──────────────────────────────────────────────────────────────

def test_node_immutable():
    n = gmod.Node(id="a.py", kind="file", imports=("b",), defines=("def:foo",))
    assert n.id == "a.py"
    assert n.imports == ("b",)


def test_edge_defaults():
    e = gmod.Edge(source="a.py", target="b.py", kind="import")
    assert e.weight == 1.0


# ── graph build ──────────────────────────────────────────────────────────────

def test_graph_neighbors():
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    graph.edges.append(gmod.Edge(source="a.py", target="b.py", kind="import"))
    assert graph.neighbors("a.py") == ["b.py"]
    assert graph.neighbors("b.py") == []


def test_graph_predecessors():
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    graph.edges.append(gmod.Edge(source="a.py", target="b.py", kind="import"))
    assert graph.predecessors("b.py") == ["a.py"]
    assert graph.predecessors("a.py") == []


# ── traversal ────────────────────────────────────────────────────────────────

def test_reverse_deps():
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py", "d.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
        gmod.Edge("d.py", "b.py", "import"),
    ]
    # reverse deps of c.py: b.py (direct), a.py (via b), d.py (via b)
    rdeps = graph.reverse_deps("c.py", max_depth=3)
    assert "b.py" in rdeps
    assert "a.py" in rdeps
    assert "d.py" in rdeps


def test_forward_deps():
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
    ]
    fdeps = graph.forward_deps("a.py", max_depth=3)
    assert "b.py" in fdeps
    assert "c.py" in fdeps


def test_shortest_path():
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
    ]
    path = graph.shortest_path("a.py", "c.py")
    assert path == ["a.py", "b.py", "c.py"]


def test_shortest_path_none():
    graph = gmod.Graph()
    for n in ["a.py", "b.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    assert graph.shortest_path("a.py", "b.py") is None


# ── impact radius ────────────────────────────────────────────────────────────

def test_impact_radius():
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
    ]
    result = graph.impact_radius(["b.py"], radius=2)
    assert "b.py" in result
    assert "a.py" in result["b.py"]["transitive_impacted"]


# ── symbol search ──────────────────────────────────────────────────────────────

def test_find_by_symbol():
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file", defines=("def:foo", "class:Bar"))
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file", defines=("def:baz",))
    matches = graph.find_by_symbol("foo")
    assert len(matches) == 1
    assert matches[0].id == "a.py"


# ── stats ────────────────────────────────────────────────────────────────────

def test_stats():
    graph = gmod.Graph()
    for n in ["a.py", "b.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [gmod.Edge("a.py", "b.py", "import")]
    s = graph.stats()
    assert s["nodes"] == 2
    assert s["edges"] == 1
    assert s["avg_out_degree"] == 0.5


# ── serialization ────────────────────────────────────────────────────────────

def test_roundtrip_dict():
    graph = gmod.Graph(repo="/tmp/demo")
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file", imports=("b",), defines=("def:main",))
    graph.edges.append(gmod.Edge("a.py", "b.py", "import", weight=2.0))
    d = graph.to_dict()
    g2 = gmod.Graph.from_dict(d)
    assert g2.repo == "/tmp/demo"
    assert g2.nodes["a.py"].defines == ("def:main",)
    assert g2.edges[0].weight == 2.0


def test_from_dict_schema_mismatch():
    try:
        gmod.Graph.from_dict({"schema": "wrong"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "schema mismatch" in str(e)


# ── caching ──────────────────────────────────────────────────────────────────

def test_cache_roundtrip(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    graph = gmod.Graph(repo=str(repo))
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    gmod.save_cached(repo, graph)
    loaded = gmod.load_cached(repo)
    assert loaded is not None
    assert loaded.nodes["a.py"].id == "a.py"


# ── complex graph math (deterministic) ─────────────────────────────────────────

def _chain_graph() -> gmod.Graph:
    """a -> b -> c, d -> b"""
    g = gmod.Graph()
    for n in ["a.py", "b.py", "c.py", "d.py"]:
        g.nodes[n] = gmod.Node(id=n, kind="file")
    g.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
        gmod.Edge("d.py", "b.py", "import"),
    ]
    return g


def test_pagerank():
    graph = _chain_graph()
    pr = graph.pagerank()
    # b.py is most central (2 incoming, 1 outgoing)
    assert pr["b.py"] > pr["a.py"]
    assert pr["b.py"] > pr["d.py"]


def test_betweenness_centrality():
    graph = _chain_graph()
    bc = graph.betweenness_centrality()
    # b.py lies on a->c and d->c paths
    assert bc["b.py"] > bc["a.py"]
    assert bc["b.py"] > bc["c.py"]


def test_clustering_coefficient():
    graph = _chain_graph()
    cc = graph.clustering_coefficient()
    # b.py neighbors = {a,c,d}; possible = 3*2=6; actual edges among them = 0
    assert cc["b.py"] == 0.0


def test_graph_density():
    graph = _chain_graph()
    # 4 nodes, possible = 4*3 = 12, actual = 3
    assert graph.graph_density() == round(3 / 12, 6)


def test_module_instability():
    graph = _chain_graph()
    mi = graph.module_instability()
    # c.py: Ca=0, Ce=1 -> I=1.0 (maximally unstable, no outgoing)
    assert mi["c.py"] == 1.0
    # a.py: Ca=1, Ce=0 -> I=0.0 (maximally stable, no incoming)
    assert mi["a.py"] == 0.0


def test_change_propagation_score():
    graph = _chain_graph()
    scores = graph.change_propagation_score(["b.py"], radius=2)
    # a.py and d.py depend on b.py; c.py is downstream
    assert "a.py" in scores or "c.py" in scores


def test_complexity_index():
    graph = _chain_graph()
    ci = graph.complexity_index()
    assert "index" in ci
    assert "components" in ci
    assert 0.0 <= ci["index"] <= 1.0


def test_cache_stale(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    graph = gmod.Graph(repo=str(repo))
    gmod.save_cached(repo, graph)
    loaded = gmod.load_cached(repo, max_age_seconds=0.0)
    assert loaded is None  # stale immediately


def test_cache_missing(tmp_path):
    loaded = gmod.load_cached(tmp_path)
    assert loaded is None
