"""Tests for graphify.cluster — Leiden/Louvain community detection.

Tests marked with @requires_leiden are skipped when leidenalg is absent (py≥3.13).
Tests for safety contracts (no-silent-fallback, force_louvain, metadata) are always run.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import networkx as nx
import pytest

from graphify.cluster import (
    SCHEMA_VERSION,
    ClusterResult,
    LeidenUnavailableError,
    cluster,
)

# Module-level check: is leidenalg available on this interpreter?
_LEIDEN_AVAILABLE = importlib.util.find_spec("leidenalg") is not None

requires_leiden = pytest.mark.skipif(
    not _LEIDEN_AVAILABLE,
    reason="leidenalg not available on this Python version (requires <3.13)",
)


# ── shared fixture ────────────────────────────────────────────────────────────

def _two_community_graph() -> nx.Graph:
    """5-node undirected graph with two clear communities (A-B-C vs D-E)."""
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C"), ("A", "C")])
    g.add_edges_from([("D", "E")])
    g.add_edge("C", "D")  # weak bridge between clusters
    return g


# ── Leiden tests (skipped when leidenalg absent) ──────────────────────────────

@requires_leiden
def test_leiden_runs_and_result_carries_leiden():
    result = cluster(_two_community_graph())
    assert isinstance(result, ClusterResult)
    assert result.schema == SCHEMA_VERSION
    assert result.algorithm == "leiden"
    assert result.metadata["leidenalg_available"] is True
    assert result.metadata["forced"] is False


@requires_leiden
def test_leiden_communities_cover_all_nodes():
    g = _two_community_graph()
    result = cluster(g)
    assert result.community_count >= 1
    assert all(len(c) > 0 for c in result.communities)
    all_nodes = {n for comm in result.communities for n in comm}
    assert all_nodes == set(g.nodes())


@requires_leiden
def test_deterministic_with_seed():
    g = _two_community_graph()
    r1 = cluster(g, seed=42)
    r2 = cluster(g, seed=42)
    c1 = sorted(sorted(c) for c in r1.communities)
    c2 = sorted(sorted(c) for c in r2.communities)
    assert c1 == c2


# ── always-runnable safety tests ──────────────────────────────────────────────

def test_no_silent_fallback_raises_leiden_unavailable():
    """If leidenalg import fails, cluster() must raise LeidenUnavailableError, not silently use Louvain."""
    g = _two_community_graph()

    original_import = __import__

    def blocking_import(name, *args, **kwargs):
        if name in ("leidenalg", "igraph"):
            raise ImportError(f"simulated unavailability: {name}")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=blocking_import):
        with pytest.raises(LeidenUnavailableError) as exc_info:
            cluster(g, algorithm="leiden")

    err = exc_info.value
    assert err.info["reason"] == "leidenalg_unavailable"
    assert err.info["algorithm"] == "leiden_requested"
    assert err.info["py_version"]


def test_force_louvain_runs_and_marks_forced():
    g = _two_community_graph()
    result = cluster(g, force_louvain=True)
    assert result.algorithm == "louvain"
    assert result.schema == SCHEMA_VERSION
    assert result.metadata["forced"] is True
    assert result.community_count >= 1
    all_nodes = {n for comm in result.communities for n in comm}
    assert all_nodes == set(g.nodes())


def test_result_metadata_carries_py_version():
    result = cluster(_two_community_graph(), force_louvain=True)
    assert result.metadata["py_version"]
    assert sys.version in result.metadata["py_version"] or result.metadata["py_version"] in sys.version


def test_as_dict_is_json_serializable():
    import json
    result = cluster(_two_community_graph(), force_louvain=True)
    d = result.as_dict()
    json.dumps(d)  # must not raise
    assert d["schema"] == SCHEMA_VERSION
    assert d["algorithm"] == "louvain"
