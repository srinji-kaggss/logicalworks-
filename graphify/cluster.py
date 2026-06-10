"""graphify.cluster — Leiden community detection with no silent fallback.

//why: leidenalg is incompatible with Python ≥3.13. Any attempt to import it
fails at runtime. Prior code silently fell back to Louvain without telling the
caller (gap G-12). This module makes the algorithm explicit in the result schema
and raises LeidenUnavailableError rather than substituting a different algorithm
behind the caller's back. Use force_louvain=True for intentional Louvain runs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import networkx as nx

SCHEMA_VERSION = "lgwks.graphify.cluster.v1"


class LeidenUnavailableError(RuntimeError):
    """Raised when Leiden is requested but leidenalg cannot be imported.

    The structured payload is available as .info (a dict) for callers that need
    to log it: {"algorithm": "leiden_requested", "reason": "leidenalg_unavailable",
    "py_version": "...", "hint": "..."}.
    """

    def __init__(self, py_version: str) -> None:
        self.info: dict[str, str] = {
            "algorithm": "leiden_requested",
            "reason": "leidenalg_unavailable",
            "py_version": py_version,
            "hint": (
                "leidenalg requires Python <3.13. "
                "Use a py3.12 interpreter, or pass force_louvain=True for explicit Louvain."
            ),
        }
        super().__init__(
            f"leidenalg is unavailable on {py_version} — "
            "silent algorithm substitution is not allowed. "
            "See LeidenUnavailableError.info for structured details."
        )


@dataclass
class ClusterResult:
    """Output of cluster(). Schema version is always lgwks.graphify.cluster.v1."""

    schema: str
    algorithm: str               # "leiden" or "louvain" — which ran
    communities: list[list[str]] # node ids grouped by community
    community_count: int
    modularity: float
    resolution: float
    seed: int
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "communities": self.communities,
            "community_count": self.community_count,
            "modularity": self.modularity,
            "resolution": self.resolution,
            "seed": self.seed,
            "metadata": self.metadata,
        }


def cluster(
    graph: nx.Graph | nx.DiGraph,
    *,
    algorithm: str = "leiden",
    resolution: float = 1.0,
    seed: int = 42,
    force_louvain: bool = False,
) -> ClusterResult:
    """Detect communities in `graph`.

    Parameters
    ----------
    graph:
        A networkx Graph or DiGraph. Node ids must be strings.
    algorithm:
        "leiden" (default) or "louvain". Ignored if force_louvain=True.
    resolution:
        Resolution parameter controlling community granularity (higher → more communities).
    seed:
        Random seed for reproducibility.
    force_louvain:
        If True, use Louvain unconditionally and mark the result as forced.
        This is the only sanctioned way to get Louvain output.

    Returns
    -------
    ClusterResult with algorithm, communities, modularity, and metadata fields.

    Raises
    ------
    LeidenUnavailableError
        If algorithm="leiden" and leidenalg cannot be imported on this Python version.
        Never silently substitutes Louvain.
    """
    if force_louvain:
        return _run_louvain(graph, resolution=resolution, seed=seed, forced=True)

    if algorithm == "louvain":
        return _run_louvain(graph, resolution=resolution, seed=seed, forced=False)

    # algorithm == "leiden" (default)
    return _run_leiden(graph, resolution=resolution, seed=seed)


# ── Leiden ────────────────────────────────────────────────────────────────────

def _run_leiden(graph: nx.Graph | nx.DiGraph, *, resolution: float, seed: int) -> ClusterResult:
    py_ver = sys.version

    try:
        import igraph as ig          # noqa: PLC0415
        import leidenalg             # noqa: PLC0415
    except ImportError as exc:
        raise LeidenUnavailableError(py_ver) from exc

    ig_graph, node_list = _to_igraph(graph)

    # leidenalg.find_partition returns a VertexPartition
    partition = leidenalg.find_partition(
        ig_graph,
        leidenalg.ModularityVertexPartition,
        resolution_parameter=resolution,
        seed=seed,
    )

    communities = [
        [node_list[v] for v in community]
        for community in partition
    ]
    modularity = float(partition.modularity)

    return ClusterResult(
        schema=SCHEMA_VERSION,
        algorithm="leiden",
        communities=communities,
        community_count=len(communities),
        modularity=modularity,
        resolution=resolution,
        seed=seed,
        metadata={
            "leidenalg_available": True,
            "py_version": py_ver,
            "forced": False,
        },
    )


# ── Louvain ───────────────────────────────────────────────────────────────────

def _run_louvain(
    graph: nx.Graph | nx.DiGraph, *, resolution: float, seed: int, forced: bool
) -> ClusterResult:
    # networkx louvain_communities returns frozensets; convert to sorted lists for
    # determinism across Python versions.
    raw = nx.algorithms.community.louvain_communities(
        graph, seed=seed, resolution=resolution
    )
    communities = [sorted(c) for c in raw]

    # networkx does not return modularity directly; compute it.
    modularity = nx.community.quality.modularity(graph, raw)

    return ClusterResult(
        schema=SCHEMA_VERSION,
        algorithm="louvain",
        communities=communities,
        community_count=len(communities),
        modularity=float(modularity),
        resolution=resolution,
        seed=seed,
        metadata={
            "leidenalg_available": _leidenalg_importable(),
            "py_version": sys.version,
            "forced": forced,
        },
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_igraph(graph: nx.Graph | nx.DiGraph):
    """Convert a networkx graph to igraph, preserving node order for index→id mapping."""
    import igraph as ig  # noqa: PLC0415

    node_list = list(graph.nodes())
    node_index = {n: i for i, n in enumerate(node_list)}

    ig_graph = ig.Graph(directed=graph.is_directed())
    ig_graph.add_vertices(len(node_list))
    ig_graph.vs["name"] = node_list

    edges = [(node_index[u], node_index[v]) for u, v in graph.edges()]
    ig_graph.add_edges(edges)

    return ig_graph, node_list


def _leidenalg_importable() -> bool:
    try:
        import leidenalg  # noqa: F401,PLC0415
        return True
    except ImportError:
        return False
