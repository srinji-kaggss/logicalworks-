"""Tests for lgwks_graph — functional, traversable codebase graph.

Strategy: build graphs in memory, assert query correctness. No subprocess, no filesystem.
"""

from __future__ import annotations

import ast
import subprocess

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


# ── Phase 2: entity expansion (variables, calls, config, incremental) ──────────

def test_node_has_variables_and_calls():
    """L0: Node dataclass carries variables and calls for cross-file analysis."""
    n = gmod.Node(id="a.py", kind="file", variables=("MAX_RETRIES",), calls=("fetch", "parse"))
    assert n.variables == ("MAX_RETRIES",)
    assert n.calls == ("fetch", "parse")


def test_walk_variables():
    """L0: _walk_variables extracts module-level names from ast.Assign."""
    source = "MAX_RETRIES = 5\nREPO_ROOT = '/tmp'\n\ndef foo():\n    local = 1\n"
    tree = ast.parse(source)
    vars_found = gmod._walk_variables(tree)
    assert "MAX_RETRIES" in vars_found
    assert "REPO_ROOT" in vars_found
    assert "local" not in vars_found  # function-scoped, ignored


def test_walk_calls():
    """L0: _walk_calls collects function names from ast.Call nodes."""
    source = "fetch(url)\nparse(data)\nobj.save()\n"
    tree = ast.parse(source)
    calls = gmod._walk_calls(tree)
    assert "fetch" in calls
    assert "parse" in calls
    assert "save" in calls


def test_config_keys_json(tmp_path):
    """L0: _config_keys extracts top-level keys from JSON files."""
    f = tmp_path / "config.json"
    f.write_text('{"api_url": "https://x", "timeout": 30}', encoding="utf-8")
    keys = gmod._config_keys(f)
    assert sorted(keys) == ["api_url", "timeout"]


def test_config_keys_env(tmp_path):
    """L0: _config_keys extracts keys from .env files."""
    f = tmp_path / ".env"
    f.write_text("API_KEY=secret\n# comment\nDEBUG=1\n", encoding="utf-8")
    keys = gmod._config_keys(f)
    assert sorted(keys) == ["API_KEY", "DEBUG"]


def test_extract_creates_call_edges(tmp_path):
    """L0: extract_from_repo builds call edges when one file calls a function defined in another."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def helper(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("import a\nhelper()\n", encoding="utf-8")
    # git init so ls-files works
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    graph = gmod.extract_from_repo(repo)
    call_edges = [e for e in graph.edges if e.kind == "call"]
    assert any(e.source == "b.py" and e.target == "a.py" for e in call_edges)


def test_extract_creates_config_node(tmp_path):
    """L0: JSON config files become nodes with config_keys."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.json").write_text('{"host": "localhost", "port": 8080}', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    graph = gmod.extract_from_repo(repo)
    assert "settings.json" in graph.nodes
    assert graph.nodes["settings.json"].kind == "config"
    assert set(graph.nodes["settings.json"].config_keys) == {"host", "port"}


def test_incremental_skips_unchanged_files(tmp_path):
    """L1: extract_from_repo with previous graph reuses nodes whose sha256 matches."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("def bar(): pass\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)

    first = gmod.extract_from_repo(repo)
    # modify only b.py
    (repo / "b.py").write_text("def bar(): pass\ndef baz(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "change", "-q"], cwd=repo, check=True)

    second = gmod.extract_from_repo(repo, previous=first)
    # a.py should be the exact same node object (reused)
    assert second.nodes["a.py"] is first.nodes["a.py"]
    # b.py should be a new node (re-parsed)
    assert second.nodes["b.py"] is not first.nodes["b.py"]
    # b.py now has 2 defines
    assert len(second.nodes["b.py"].defines) == 2


def test_v1_backward_compat():
    """L1: graphs saved with v1 schema still load (missing fields default to empty tuples)."""
    v1_data = {
        "schema": "lgwks.graph.v1",
        "repo": "/tmp",
        "nodes": {
            "a.py": {"id": "a.py", "kind": "file", "imports": ["b"], "defines": ["def:main"], "sha256": "abc"}
        },
        "edges": [],
    }
    g = gmod.Graph.from_dict(v1_data)
    assert g.nodes["a.py"].variables == ()
    assert g.nodes["a.py"].calls == ()
    assert g.nodes["a.py"].config_keys == ()


# ── Phase 3: query engine ──────────────────────────────────────────────────────

def test_query_match_all_nodes():
    """L0: MATCH (n) returns all nodes."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    result = gmod.execute_query(graph, "MATCH (n)")
    assert len(result.rows) == 2


def test_query_where_kind():
    """L0: WHERE n.kind = 'file' filters correctly."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["cfg.json"] = gmod.Node(id="cfg.json", kind="config")
    result = gmod.execute_query(graph, "MATCH (n) WHERE n.kind = 'file' RETURN n.id")
    assert len(result.rows) == 1
    assert result.rows[0]["n.id"] == "a.py"


def test_query_where_contains():
    """L0: WHERE n.defines CONTAINS 'foo' finds nodes with the symbol."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file", defines=("def:foo", "def:bar"))
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file", defines=("def:baz",))
    result = gmod.execute_query(graph, "MATCH (n) WHERE n.defines CONTAINS 'foo' RETURN n.id")
    ids = [r["n.id"] for r in result.rows]
    assert "a.py" in ids
    assert "b.py" not in ids


def test_query_limit():
    """L0: LIMIT caps result count."""
    graph = gmod.Graph()
    for i in range(10):
        graph.nodes[f"f{i}.py"] = gmod.Node(id=f"f{i}.py", kind="file")
    result = gmod.execute_query(graph, "MATCH (n) LIMIT 3")
    assert len(result.rows) == 3


def test_query_edge_import():
    """L0: MATCH (n)-[:import]->(m) returns import edges."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    graph.edges.append(gmod.Edge("a.py", "b.py", "import"))
    result = gmod.execute_query(graph, "MATCH (n)-[:import]->(m)")
    assert len(result.rows) == 1
    assert result.rows[0]["n"]["id"] == "a.py"
    assert result.rows[0]["m"]["id"] == "b.py"


def test_query_invalid_syntax():
    """L1: Unrecognized query raises ValueError."""
    graph = gmod.Graph()
    with pytest.raises(ValueError):
        gmod.execute_query(graph, "SELECT * FROM nodes")


def test_graph_command_complexity(tmp_path, capsys):
    """L0: `graph --complexity` outputs KGCI payload."""
    import argparse
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    args = argparse.Namespace(repo=str(repo), refresh=True, impact=False, files="", radius=3,
                               complexity=True, path=False, from_node="", to_node="",
                               neighbors=False, of="", query="")
    rc = gmod.graph_command(args)
    assert rc == 0
    captured = capsys.readouterr()
    assert "kgci" in captured.out


def test_graph_command_neighbors(tmp_path, capsys):
    """L0: `graph --neighbors --of FILE` outputs neighbor lists."""
    import argparse
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("import a\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    args = argparse.Namespace(repo=str(repo), refresh=True, impact=False, files="", radius=3,
                               complexity=False, path=False, from_node="", to_node="",
                               neighbors=True, of="b.py", query="",
                               patterns=False, schema_infer=False)
    rc = gmod.graph_command(args)
    assert rc == 0
    captured = capsys.readouterr()
    assert "a.py" in captured.out


# ── Phase 5: deterministic pattern/schema extraction ───────────────────────────

def test_detect_patterns_circular_deps():
    """L0: detect_patterns finds a circular import chain a→b→c→a."""
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
        gmod.Edge("c.py", "a.py", "import"),
    ]
    pats = graph.detect_patterns()
    assert pats["circular_dependencies"]["count"] == 1
    group = pats["circular_dependencies"]["groups"][0]
    assert set(group) == {"a.py", "b.py", "c.py"}


def test_detect_patterns_god_modules():
    """L0: a node with extreme in-degree is flagged as a god module."""
    graph = gmod.Graph()
    for i in range(10):
        graph.nodes[f"dep{i}.py"] = gmod.Node(id=f"dep{i}.py", kind="file")
    graph.nodes["core.py"] = gmod.Node(id="core.py", kind="file")
    for i in range(9):
        graph.edges.append(gmod.Edge(f"dep{i}.py", "core.py", "import"))
    pats = graph.detect_patterns()
    assert "core.py" in pats["god_modules"]["modules"]


def test_detect_patterns_orphans():
    """L0: nodes with no edges are listed as orphans."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    graph.edges = [gmod.Edge("a.py", "b.py", "import")]
    pats = graph.detect_patterns()
    assert pats["orphans"] == []
    graph.nodes["c.py"] = gmod.Node(id="c.py", kind="file")
    pats = graph.detect_patterns()
    assert "c.py" in pats["orphans"]


def test_detect_patterns_unstable():
    """L0: leaf modules with only incoming edges have instability > 0.8."""
    graph = gmod.Graph()
    graph.nodes["util.py"] = gmod.Node(id="util.py", kind="file")
    graph.nodes["main.py"] = gmod.Node(id="main.py", kind="file")
    graph.edges = [
        gmod.Edge("main.py", "util.py", "import"),
    ]
    pats = graph.detect_patterns()
    assert "util.py" in pats["unstable_modules"]["modules"]


def test_tarjan_scc_no_cycle():
    """L0: Tarjan on acyclic graph returns all singleton SCCs."""
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("b.py", "c.py", "import"),
    ]
    sccs = graph._tarjan_scc()
    assert all(len(scc) == 1 for scc in sccs)


def test_infer_schema_entity_types():
    """L0: infer_schema extracts entity type frequencies from node kinds."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["cfg.json"] = gmod.Node(id="cfg.json", kind="config", config_keys=("host", "port"))
    graph.nodes["data.csv"] = gmod.Node(id="data.csv", kind="data")
    schema = gmod.infer_schema(graph)
    assert "file" in schema.entity_types
    assert "config" in schema.entity_types
    assert schema.entity_types["config"]["count"] == 1


def test_infer_schema_cardinality():
    """L0: relationship cardinality inferred from edge distribution."""
    graph = gmod.Graph()
    for n in ["a.py", "b.py", "c.py", "d.py"]:
        graph.nodes[n] = gmod.Node(id=n, kind="file")
    # a imports b, c, d → 1:N from a's perspective
    graph.edges = [
        gmod.Edge("a.py", "b.py", "import"),
        gmod.Edge("a.py", "c.py", "import"),
        gmod.Edge("a.py", "d.py", "import"),
    ]
    schema = gmod.infer_schema(graph)
    rel = next(r for r in schema.relationships if r["rel"] == "import")
    assert rel["cardinality"] == "1:N"  # one source (a.py) → many targets (b,c,d)


def test_infer_schema_coverage():
    """L0: field coverage computed as fraction of nodes having the field."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file", config_keys=("host",))
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    schema = gmod.infer_schema(graph)
    # host appears on 1 of 2 file nodes, but coverage is across ALL nodes
    # Actually coverage is computed across all nodes, so host = 1/2 = 0.5
    assert schema.coverage.get("host", 0.0) == 0.5


def test_infer_schema_anomalies():
    """L0: anomalies list includes orphan count and edge statistics."""
    graph = gmod.Graph()
    graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
    graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")
    schema = gmod.infer_schema(graph)
    assert any("no edges" in a for a in schema.anomalies)


def test_graph_command_patterns(tmp_path, capsys):
    """L0: `graph --patterns` outputs pattern report."""
    import argparse
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("import a\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    args = argparse.Namespace(repo=str(repo), refresh=True, impact=False, files="", radius=3,
                               complexity=False, path=False, from_node="", to_node="",
                               neighbors=False, of="", query="",
                               patterns=True, schema_infer=False)
    rc = gmod.graph_command(args)
    assert rc == 0
    captured = capsys.readouterr()
    assert "circular_dependencies" in captured.out


def test_graph_command_schema_infer(tmp_path, capsys):
    """L0: `graph --schema-infer` outputs inferred schema."""
    import argparse
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.json").write_text('{"host": "localhost", "port": 8080}', encoding="utf-8")
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)
    args = argparse.Namespace(repo=str(repo), refresh=True, impact=False, files="", radius=3,
                               complexity=False, path=False, from_node="", to_node="",
                               neighbors=False, of="", query="",
                               patterns=False, schema_infer=True)
    rc = gmod.graph_command(args)
    assert rc == 0
    captured = capsys.readouterr()
    assert "entity_types" in captured.out
