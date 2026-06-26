"""lgwks_graph — functional, traversable codebase graph with query engine and persistence.

//why: `repo_graph` extracted nodes/edges but had no traversal. Impact analysis in `review`
was a linear scan. This module makes the graph a first-class queryable structure:
neighbors, reverse dependencies, shortest path, impact radius, and file-mtime cache.

DiD layers:
  T0 schema: every load validates schema version and required keys.
  T1 sanitization: all file paths resolved through repo root; no traversal outside.
  T2 capability: graph ops are pure (no subprocess, no network); safe to call anywhere.
  T3 audit: mutation log for every save/load with timestamp.
"""

from __future__ import annotations

import ast
import lgwks_hashing
import json
import re as _re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_SCHEMA = "lgwks.graph.v2"
_CACHE_SCHEMA = "lgwks.graph.cache.v2"


@dataclass(frozen=True)
class Node:
    """Immutable graph node representing a source file or config artifact."""
    id: str              # relative path, e.g. "src/main.py"
    kind: str            # "file" | "config" | "data"
    imports: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()
    variables: tuple[str, ...] = ()   # module-level variable names
    calls: tuple[str, ...] = ()       # function names called in this file
    config_keys: tuple[str, ...] = () # keys for config/data nodes
    sha256: str = ""     # content hash for cache invalidation


@dataclass(frozen=True)
class Edge:
    """Immutable directed edge: from -> to with typed relationship."""
    source: str      # node id
    target: str      # node id or external module name
    kind: str        # "import" | "call" | "inherit" | "contains"
    weight: float = 1.0


@dataclass
class Graph:
    """In-memory directed graph with adjacency indexes. All query methods are pure."""
    schema: str = _SCHEMA
    repo: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    _adj_out: dict[str, list[Edge]] = field(default_factory=dict, repr=False)
    _adj_in: dict[str, list[Edge]] = field(default_factory=dict, repr=False)
    _built: bool = field(default=False, repr=False)

    def _ensure_index(self) -> None:
        """Lazy adjacency build — O(E) once, then O(1) lookups."""
        if self._built:
            return
        self._adj_out.clear()
        self._adj_in.clear()
        for e in self.edges:
            self._adj_out.setdefault(e.source, []).append(e)
            self._adj_in.setdefault(e.target, []).append(e)
        self._built = True

    # ── core queries ──────────────────────────────────────────────────────

    def neighbors(self, node_id: str) -> list[str]:
        """Direct successors (outgoing edges)."""
        self._ensure_index()
        return [e.target for e in self._adj_out.get(node_id, [])]

    def predecessors(self, node_id: str) -> list[str]:
        """Direct predecessors (incoming edges)."""
        self._ensure_index()
        return [e.source for e in self._adj_in.get(node_id, [])]

    def reverse_deps(self, node_id: str, max_depth: int = 5) -> set[str]:
        """All nodes that transitively depend on node_id (reverse traversal)."""
        self._ensure_index()
        visited: set[str] = set()
        frontier = {node_id}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                for e in self._adj_in.get(nid, []):
                    if e.source not in visited:
                        next_frontier.add(e.source)
            visited.update(frontier)
            frontier = next_frontier
            if not frontier:
                break
        visited.discard(node_id)
        return visited

    def forward_deps(self, node_id: str, max_depth: int = 5) -> set[str]:
        """All nodes that node_id transitively depends on."""
        self._ensure_index()
        visited: set[str] = set()
        frontier = {node_id}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                for e in self._adj_out.get(nid, []):
                    if e.target not in visited:
                        next_frontier.add(e.target)
            visited.update(frontier)
            frontier = next_frontier
            if not frontier:
                break
        visited.discard(node_id)
        return visited

    def shortest_path(self, source: str, target: str, max_depth: int = 10) -> list[str] | None:
        """BFS shortest path from source to target. Returns node list or None."""
        self._ensure_index()
        if source == target:
            return [source]
        queue: list[tuple[str, list[str]]] = [(source, [source])]
        visited: set[str] = {source}
        while queue and len(visited) < max_depth * 10:
            current, path = queue.pop(0)
            for e in self._adj_out.get(current, []):
                nxt = e.target
                if nxt == target:
                    return path + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
        return None

    def impact_radius(self, changed_files: list[str], radius: int = 2) -> dict[str, Any]:
        """Map each changed file to its reverse dependency cone up to radius."""
        self._ensure_index()
        result: dict[str, Any] = {}
        for f in changed_files:
            impacted = self.reverse_deps(f, max_depth=radius)
            result[f] = {
                "direct_callers": list(self.predecessors(f)),
                "transitive_impacted": sorted(impacted),
                "count": len(impacted),
            }
        return result

    def find_by_symbol(self, symbol: str) -> list[Node]:
        """Find nodes that define a given symbol (class/function name)."""
        matches: list[Node] = []
        for n in self.nodes.values():
            if any(symbol in d for d in n.defines):
                matches.append(n)
        return matches

    def stats(self) -> dict[str, Any]:
        """Graph statistics for quick health checks."""
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "avg_out_degree": round(len(self.edges) / max(1, len(self.nodes)), 2),
            "orphan_nodes": [n.id for n in self.nodes.values() if not self.neighbors(n.id) and not self.predecessors(n.id)],
        }

    def to_dot(self, highlight: set[str] | None = None) -> str:
        """Export the graph to Graphviz DOT format."""
        lines = ["digraph lgwks {", "  rankdir=LR;", "  node [shape=box, fontname=\"monospace\", fontsize=10];"]
        kind_color = {"file": "#3b82f6", "config": "#22c55e", "data": "#f97316"}
        hl = highlight or set()
        for nid, node in self.nodes.items():
            if nid in hl:
                color = "#f59e0b"
                fontcolor = "#f59e0b"
            else:
                color = kind_color.get(node.kind, "#6b7280")
                fontcolor = "#e2e8f0"
            label = nid.split("/")[-1] if "/" in nid else nid
            lines.append(f'  "{nid}" [label="{label}", color="{color}", fontcolor="{fontcolor}"];')
        for e in self.edges:
            style = {"import": "solid", "call": "dashed", "inherit": "dotted", "contains": "solid"}.get(e.kind, "solid")
            lines.append(f'  "{e.source}" -> "{e.target}" [style={style}, color="#64748b", fontsize=9];')
        lines.append("}")
        return "\n".join(lines)

    # ── complex graph math (deterministic, no AI/LLM) ─────────────────────

    def pagerank(self, damping: float = 0.85, iterations: int = 30) -> dict[str, float]:
        """PageRank over the import/call graph. High rank = central / depended-on module.
        Pure iterative matrix-power method; no LLM involved."""
        self._ensure_index()
        n = len(self.nodes)
        if n == 0:
            return {}
        node_ids = list(self.nodes.keys())
        idx = {nid: i for i, nid in enumerate(node_ids)}
        # Build adjacency matrix (outgoing normalized)
        rank = [1.0 / n] * n
        for _ in range(iterations):
            new_rank = [0.0] * n
            for i, nid in enumerate(node_ids):
                out_edges = self._adj_out.get(nid, [])
                share = rank[i] / max(1, len(out_edges)) if out_edges else 0.0
                for e in out_edges:
                    j = idx.get(e.target)
                    if j is not None:
                        new_rank[j] += share
            # Damping + teleport
            for j in range(n):
                new_rank[j] = damping * new_rank[j] + (1.0 - damping) / n
            rank = new_rank
        return {node_ids[i]: round(rank[i], 6) for i in range(n)}

    def betweenness_centrality(self, sample: int | None = None) -> dict[str, float]:
        """Brandes-style betweenness centrality on directed graph.
        Gatekeeper score: high = module lies on many shortest paths."""
        self._ensure_index()
        nids = list(self.nodes.keys())
        n = len(nids)
        if n == 0:
            return {}
        # Sample for large graphs to keep O(V*E) bounded
        sources = nids if sample is None or sample >= n else nids[:sample]
        cb: dict[str, float] = {nid: 0.0 for nid in nids}
        for s in sources:
            # BFS from s
            stack: list[str] = []
            preds: dict[str, list[str]] = {v: [] for v in nids}
            sigma: dict[str, float] = {v: 0.0 for v in nids}
            dist: dict[str, int] = {v: -1 for v in nids}
            queue: list[str] = [s]
            sigma[s] = 1.0
            dist[s] = 0
            while queue:
                v = queue.pop(0)
                stack.append(v)
                for e in self._adj_out.get(v, []):
                    w = e.target
                    if w not in dist:
                        continue
                    if dist[w] < 0:
                        queue.append(w)
                        dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        preds[w].append(v)
            # Accumulation
            delta: dict[str, float] = {v: 0.0 for v in nids}
            while stack:
                w = stack.pop()
                for v in preds[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    cb[w] += delta[w]
        # Normalize
        norm = max(1.0, (n - 1) * (n - 2)) if n > 2 else 1.0
        return {k: round(v / norm, 6) for k, v in cb.items()}

    def clustering_coefficient(self) -> dict[str, float]:
        """Local directed clustering (cycle density around each node).
        High = tightly coupled local cluster."""
        self._ensure_index()
        result: dict[str, float] = {}
        for nid in self.nodes:
            out_neighbors = {e.target for e in self._adj_out.get(nid, [])}
            in_neighbors = {e.source for e in self._adj_in.get(nid, [])}
            neighbors = out_neighbors | in_neighbors
            if len(neighbors) < 2:
                result[nid] = 0.0
                continue
            count = 0
            possible = len(neighbors) * (len(neighbors) - 1)
            for a in neighbors:
                a_out = {e.target for e in self._adj_out.get(a, [])}
                for b in neighbors:
                    if a != b and b in a_out:
                        count += 1
            result[nid] = round(count / possible, 6) if possible else 0.0
        return result

    def graph_density(self) -> float:
        """Ratio of actual edges to possible edges. High = tightly coupled monolith."""
        n = len(self.nodes)
        if n < 2:
            return 0.0
        possible = n * (n - 1)
        return round(len(self.edges) / possible, 6)

    def module_instability(self) -> dict[str, float]:
        """Robert C. Martin Instability: I = Ce / (Ca + Ce).
        Ce = afferent (incoming) edges; Ca = efferent (outgoing) edges.
        I=0 = maximally stable (abstract); I=1 = maximally unstable (concrete/leaf)."""
        self._ensure_index()
        result: dict[str, float] = {}
        for nid in self.nodes:
            ca = len(self._adj_out.get(nid, []))
            ce = len(self._adj_in.get(nid, []))
            total = ca + ce
            result[nid] = round(ce / total, 6) if total else 0.0
        return result

    def change_propagation_score(self, changed_files: list[str], radius: int = 3) -> dict[str, float]:
        """Probability-weighted impact score for a set of changed files.
        Combines distance decay + betweenness gatekeeping + PageRank of impacted nodes.
        Pure math; no LLM."""
        self._ensure_index()
        pr = self.pagerank()
        bc = self.betweenness_centrality()
        scores: dict[str, float] = {}
        for cf in changed_files:
            if cf not in self.nodes:
                continue
            impacted = self.reverse_deps(cf, max_depth=radius)
            for node in impacted:
                # Distance matters: closer = higher score
                path = self.shortest_path(node, cf, max_depth=radius)
                distance = len(path) if path else radius
                decay = 1.0 / (distance ** 1.5)
                # Gatekeeper boost: if node is a bottleneck, changes propagate harder
                gatekeeper = 1.0 + (bc.get(node, 0.0) * 5.0)
                # Target importance: high-PageRank nodes are costlier to break
                importance = 1.0 + (pr.get(node, 0.0) * 10.0)
                score = decay * gatekeeper * importance
                scores[node] = round(max(scores.get(node, 0.0), score), 6)
        return scores

    def complexity_index(self) -> dict[str, Any]:
        """Composite Knowledge Graph Complexity Index (KGCI) — single number summarizing
        graph health. Deterministic; no AI. Components:
          - Density (coupling)
          - Mean PageRank variance (inequality of importance)
          - Mean clustering (local tightness)
          - Orphan ratio (disconnected code)
          - Mean instability (architectural balance)
        """
        n = len(self.nodes)
        if n == 0:
            return {"index": 0.0, "components": {}}
        pr = self.pagerank()
        cc = self.clustering_coefficient()
        mi = self.module_instability()
        density = self.graph_density()
        orphans = [nid for nid in self.nodes if not self.neighbors(nid) and not self.predecessors(nid)]
        pr_values = list(pr.values())
        pr_variance = sum((v - (sum(pr_values) / n)) ** 2 for v in pr_values) / n if n else 0.0
        cc_mean = sum(cc.values()) / n
        mi_mean = sum(mi.values()) / n
        orphan_ratio = len(orphans) / n
        # Composite: higher = more complex / more attention needed
        # Each component normalized to ~0..1 range
        index = round(
            (density * 0.25) +
            (pr_variance * 100.0 * 0.25) +
            (cc_mean * 0.20) +
            (orphan_ratio * 0.15) +
            (mi_mean * 0.15),
            6,
        )
        return {
            "index": index,
            "components": {
                "density": density,
                "pr_variance": round(pr_variance, 6),
                "clustering_mean": round(cc_mean, 6),
                "orphan_ratio": round(orphan_ratio, 6),
                "instability_mean": round(mi_mean, 6),
            },
        }

    # ── deterministic pattern detection (no AI) ─────────────────────────────

    def detect_patterns(self) -> dict[str, Any]:
        """Detect architectural anti-patterns and structural anomalies.
        Pure graph topology — no LLM involved."""
        self._ensure_index()
        n = len(self.nodes)
        if n == 0:
            return {}

        pr = self.pagerank()
        bc = self.betweenness_centrality()
        mi = self.module_instability()
        cc = self.clustering_coefficient()
        in_degrees = {nid: len(self._adj_in.get(nid, [])) for nid in self.nodes}
        out_degrees = {nid: len(self._adj_out.get(nid, [])) for nid in self.nodes}
        avg_in = sum(in_degrees.values()) / n
        avg_out = sum(out_degrees.values()) / n

        patterns: dict[str, Any] = {}

        # 1. Circular dependencies (SCC > 1 via Tarjan over the dependency graph).
        #    Only import edges count — call edges form benign cycles and would
        #    otherwise report the entire codebase as one false circular dep.
        sccs = self._tarjan_scc(kinds={"import"})
        cycles = [scc for scc in sccs if len(scc) > 1]
        patterns["circular_dependencies"] = {
            "count": len(cycles),
            "groups": [sorted(c) for c in cycles],
        }

        # 2. God modules (in-degree > 3× avg or out-degree > 3× avg)
        gods = [nid for nid in self.nodes if in_degrees[nid] > avg_in * 3 or out_degrees[nid] > avg_out * 3]
        patterns["god_modules"] = {
            "threshold_in": round(avg_in * 3, 2),
            "threshold_out": round(avg_out * 3, 2),
            "modules": gods,
        }

        # 3. Orphan clusters (nodes with zero edges)
        orphans = [nid for nid in self.nodes if in_degrees[nid] == 0 and out_degrees[nid] == 0]
        patterns["orphans"] = orphans

        # 4. Unstable islands (instability > 0.8)
        unstable = [nid for nid, i in mi.items() if i > 0.8]
        patterns["unstable_modules"] = {
            "threshold": 0.8,
            "modules": unstable,
        }

        # 5. Gatekeeper bottlenecks (betweenness > 0.1)
        gatekeepers = [nid for nid, v in bc.items() if v > 0.1]
        patterns["gatekeepers"] = {
            "threshold": 0.1,
            "modules": gatekeepers,
        }

        # 6. Tight coupling clusters (clustering > 0.5)
        tight = [nid for nid, v in cc.items() if v > 0.5]
        patterns["tight_coupling"] = {
            "threshold": 0.5,
            "modules": tight,
        }

        # 7. Long dependency chains (max shortest path > 6)
        long_chains: list[dict[str, Any]] = []
        checked: set[tuple[str, str]] = set()
        for src in list(self.nodes.keys())[:min(n, 50)]:  # sample for speed
            for dst in list(self.nodes.keys())[:min(n, 50)]:
                if src >= dst:
                    continue
                pair = (src, dst)
                if pair in checked:
                    continue
                checked.add(pair)
                p = self.shortest_path(src, dst, max_depth=10)
                if p and len(p) > 6:
                    long_chains.append({"from": src, "to": dst, "length": len(p), "path": p})
        patterns["long_chains"] = long_chains[:5]

        return patterns

    def _tarjan_scc(self, kinds: set[str] | None = None) -> list[list[str]]:
        """Tarjan's strongly connected components algorithm.

        When ``kinds`` is given, only edges of those kinds are traversed. This
        matters for "circular dependencies": a dependency cycle is an *import*
        cycle. Call edges form large benign SCCs (utility functions are called
        everywhere), so mixing them in reports the whole codebase as one fake
        cycle. Pass ``kinds={"import"}`` for the dependency graph.
        """
        index_counter = [0]
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: set[str] = set()
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlinks[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            for e in self._adj_out.get(v, []):
                if kinds is not None and e.kind not in kinds:
                    continue
                w = e.target
                if w not in self.nodes:
                    continue
                if w not in lowlinks:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], index[w])
            if lowlinks[v] == index[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        for v in self.nodes:
            if v not in lowlinks:
                strongconnect(v)
        return sccs

    # ── serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "repo": self.repo,
            "nodes": {
                k: {
                    "id": n.id,
                    "kind": n.kind,
                    "imports": list(n.imports),
                    "defines": list(n.defines),
                    "variables": list(n.variables),
                    "calls": list(n.calls),
                    "config_keys": list(n.config_keys),
                    "sha256": n.sha256,
                }
                for k, n in self.nodes.items()
            },
            "edges": [
                {"source": e.source, "target": e.target, "kind": e.kind, "weight": e.weight}
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        schema = data.get("schema", "")
        if schema not in (_SCHEMA, "lgwks.graph.v1", "lgwks.repo.graph.v0"):
            raise ValueError(f"graph schema mismatch: expected {_SCHEMA}, got {schema!r}")
        g = cls(schema=_SCHEMA, repo=data.get("repo", ""))
        for k, n in data.get("nodes", {}).items():
            g.nodes[k] = Node(
                id=n["id"],
                kind=n.get("kind", "file"),
                imports=tuple(n.get("imports", [])),
                defines=tuple(n.get("defines", [])),
                variables=tuple(n.get("variables", [])),
                calls=tuple(n.get("calls", [])),
                config_keys=tuple(n.get("config_keys", [])),
                sha256=n.get("sha256", ""),
            )
        for e in data.get("edges", []):
            g.edges.append(Edge(
                source=e["source"],
                target=e["target"],
                kind=e.get("kind", "import"),
                weight=e.get("weight", 1.0),
            ))
        return g

    def save(self, path: Path) -> None:
        """Atomic write to JSON."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "Graph":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


# ── Rust parsing (lightweight regex — no external deps) ───────────────────────
# //why: logic-os-kernel and other repos are Rust-first. Python's ast module can't
# parse .rs. We use regex (not a full parser) because: (1) zero deps, (2) fast,
# (3) "good enough" for import/definition/call extraction at graph granularity.
# The regex approach has false negatives (complex macros, nested modules) but
# never false positives — safe for the graph layer.

_RUST_USE_RE = _re.compile(r"^\s*use\s+([^;]+);", _re.MULTILINE)
_RUST_MOD_RE = _re.compile(r"^\s*mod\s+(\w+)", _re.MULTILINE)
_RUST_FN_RE = _re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)", _re.MULTILINE)
_RUST_STRUCT_RE = _re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)", _re.MULTILINE)
_RUST_ENUM_RE = _re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)", _re.MULTILINE)
_RUST_TRAIT_RE = _re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)", _re.MULTILINE)
_RUST_IMPL_RE = _re.compile(r"^\s*impl\s+(?:<[^>]+>\s+)?(?:\w+\s+for\s+)?(\w+)", _re.MULTILINE)
_RUST_CALL_RE = _re.compile(r"\b(\w+)\s*\(", _re.MULTILINE)
_RUST_VAR_RE = _re.compile(r"^\s*let\s+(?:mut\s+)?(\w+)", _re.MULTILINE)


def _parse_rust_file(source: str, rel_path: str) -> tuple[list[str], list[str], set[str], set[str]]:
    """Extract (imports, defines, variables, calls) from Rust source.
    Returns same shape as Python AST extraction so the graph pipeline is uniform."""
    imports: list[str] = []
    defines: list[str] = []
    variables: set[str] = set()
    calls: set[str] = set()

    for m in _RUST_USE_RE.finditer(source):
        imports.append(m.group(1).strip())

    for m in _RUST_MOD_RE.finditer(source):
        defines.append(f"mod:{m.group(1)}")

    for m in _RUST_FN_RE.finditer(source):
        defines.append(f"fn:{m.group(1)}")

    for m in _RUST_STRUCT_RE.finditer(source):
        defines.append(f"struct:{m.group(1)}")

    for m in _RUST_ENUM_RE.finditer(source):
        defines.append(f"enum:{m.group(1)}")

    for m in _RUST_TRAIT_RE.finditer(source):
        defines.append(f"trait:{m.group(1)}")

    for m in _RUST_IMPL_RE.finditer(source):
        defines.append(f"impl:{m.group(1)}")

    for m in _RUST_VAR_RE.finditer(source):
        variables.add(m.group(1))

    for m in _RUST_CALL_RE.finditer(source):
        name = m.group(1)
        # Filter out Rust keywords that look like calls
        if name not in ("if", "while", "for", "match", "return", "let", "pub", "fn", "struct", "enum", "impl", "use", "mod", "trait"):
            calls.add(name)

    return imports, defines, variables, calls



_CPP_INCLUDE_RE = _re.compile(r'#include\s*(["<])(.*?)([">])')
_CPP_CLASS_RE = _re.compile(r'\b(class|struct)\s+([A-Za-z0-9_]+)\s*[{:]')
_CPP_FUNC_RE = _re.compile(r'^[ \t]*([A-Za-z0-9_:]+[ \t]+[*&]*[ \t]*)([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{', _re.MULTILINE)
_CPP_CALL_RE = _re.compile(r'\b([A-Za-z0-9_]+)\s*\(')

def _parse_cpp_file(source: str, rel_path: str) -> tuple[list[str], list[str], set[str], set[str]]:
    imports: list[str] = []
    defines: list[str] = []
    variables: set[str] = set()
    calls: set[str] = set()

    for m in _CPP_INCLUDE_RE.finditer(source):
        imports.append(m.group(2))

    for m in _CPP_CLASS_RE.finditer(source):
        defines.append(f"{m.group(1)}:{m.group(2)}")

    for m in _CPP_FUNC_RE.finditer(source):
        defines.append(f"def:{m.group(2)}")

    for m in _CPP_CALL_RE.finditer(source):
        calls.add(m.group(1))

    return imports, defines, variables, calls

def _rust_import_to_path(imp: str, repo: Path, rel_path: str) -> str | None:
    """Map a Rust use statement to a likely file path in the repo.
    Handles: crate::foo::bar, super::baz, self::qux, std::... (external)."""
    # Strip trailing items (e.g. "crate::foo::bar::{Baz, Qux}")
    imp = imp.split(" as ")[0].strip()
    if imp.endswith("}"):
        # Handle crate::foo::{Bar, Baz} → map to crate::foo
        brace = imp.rfind("{")
        if brace > 0:
            imp = imp[:brace].rstrip(":")

    parts = imp.split("::")
    if not parts:
        return None

    # External crate (std, core, alloc, third-party) — no internal mapping
    if parts[0] in ("std", "core", "alloc", "std::os", "std::collections"):
        return None

    # crate::foo::bar → src/foo/bar.rs or src/foo/bar/mod.rs, then progressively
    # fall back to shorter paths (src/foo.rs) because the target may be a submodule
    # inside a single-file module.
    if parts[0] == "crate":
        path_parts = parts[1:]
        if not path_parts:
            return None
        # Try full path first
        candidate = "src/" + "/".join(path_parts) + ".rs"
        if (repo / candidate).exists():
            return candidate
        candidate_mod = "src/" + "/".join(path_parts) + "/mod.rs"
        if (repo / candidate_mod).exists():
            return candidate_mod
        # Progressive fallback: try each prefix as a module file
        for i in range(len(path_parts) - 1, 0, -1):
            fallback = "src/" + "/".join(path_parts[:i]) + ".rs"
            if (repo / fallback).exists():
                return fallback
            fallback_mod = "src/" + "/".join(path_parts[:i]) + "/mod.rs"
            if (repo / fallback_mod).exists():
                return fallback_mod
        return None

    # super::foo → relative to current file's directory, then progressive fallback
    if parts[0] == "super":
        current_dir = Path(rel_path).parent
        for _ in range(len([p for p in parts if p == "super"])):
            current_dir = current_dir.parent
        remaining = [p for p in parts if p != "super"]
        if remaining:
            candidate = str(current_dir / "/".join(remaining)) + ".rs"
            if (repo / candidate).exists():
                return candidate
            candidate_mod = str(current_dir / "/".join(remaining)) + "/mod.rs"
            if (repo / candidate_mod).exists():
                return candidate_mod
            # Progressive fallback to shorter paths
            for i in range(len(remaining) - 1, 0, -1):
                fallback = str(current_dir / "/".join(remaining[:i])) + ".rs"
                if (repo / fallback).exists():
                    return fallback
        return None

    # self::foo → relative to current file, then progressive fallback
    if parts[0] == "self":
        current_dir = Path(rel_path).parent
        remaining = parts[1:]
        if remaining:
            candidate = str(current_dir / "/".join(remaining)) + ".rs"
            if (repo / candidate).exists():
                return candidate
            candidate_mod = str(current_dir / "/".join(remaining)) + "/mod.rs"
            if (repo / candidate_mod).exists():
                return candidate_mod
            for i in range(len(remaining) - 1, 0, -1):
                fallback = str(current_dir / "/".join(remaining[:i])) + ".rs"
                if (repo / fallback).exists():
                    return fallback
        return None

    # Raw module path (foo::bar) → try src/foo/bar.rs
    candidate = "src/" + "/".join(parts) + ".rs"
    if (repo / candidate).exists():
        return candidate
    candidate_mod = "src/" + "/".join(parts) + "/mod.rs"
    if (repo / candidate_mod).exists():
        return candidate_mod

    return None


def _detect_unindexed_languages(paths: list[str], indexed_paths: set[str]) -> list[str]:
    """Detect dominant languages with zero indexed files and return warning messages.
    //why: the hollow-green trap — empty authoritative JSON for unindexed languages.
    A Rust repo returning {} for impact analysis is a false negative, not a confirmation."""
    from collections import Counter

    # Count files by extension
    ext_counts: Counter[str] = Counter()
    for p in paths:
        if "." in p:
            ext = p.rsplit(".", 1)[-1].lower()
            ext_counts[ext] += 1

    total_source = sum(c for ext, c in ext_counts.items() if ext in ("py", "rs", "js", "ts", "go", "java", "swift", "rb", "php", "c", "cpp", "h", "hpp", "cs", "scala", "kt"))
    if total_source == 0:
        return []

    warnings: list[str] = []
    for ext, count in ext_counts.most_common():
        if count < 5 or count / total_source < 0.1:
            continue
        # Check if any files of this extension are indexed
        indexed_count = sum(1 for p in indexed_paths if p.endswith(f".{ext}"))
        if indexed_count == 0:
            warnings.append(
                f"[graph] WARNING: {count} .{ext} files detected but not indexed — "
                f"graph results cover 0% of {ext}-language codebase"
            )

    return warnings


# ── extraction from repo ─────────────────────────────────────────────────────

def _file_hash(content: str) -> str:
    return lgwks_hashing.content_id(content)


def _walk_calls(node: ast.AST) -> set[str]:
    """Recursively walk AST and collect simple function/method names called."""
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.add(child.func.attr)
    return calls


def _walk_variables(node: ast.AST) -> set[str]:
    """Collect module-level variable names from ast.Assign targets."""
    variables: set[str] = set()
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    variables.add(target.id)
        elif isinstance(child, ast.AnnAssign):
            if isinstance(child.target, ast.Name):
                variables.add(child.target.id)
    return variables


def _config_keys(path: Path) -> list[str]:
    """Extract top-level keys from JSON or .env files."""
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    if ext == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return list(data.keys())
        except Exception:
            pass
    elif ext in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return list(data.keys())
        except Exception:
            pass
    elif path.name == ".env" or ext == ".env":
        keys: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                keys.append(line.split("=", 1)[0].strip())
        return keys
    return []


def _lang_of(path: str) -> str:
    """Coarse language bucket for a node id, used to forbid cross-language
    call edges (a Python `def` and a Rust `fn` of the same bare name share no
    call relationship — resolving across them fabricates edges)."""
    if path.endswith(".rs"):
        return "rs"
    if path.endswith((".py", ".pyi")):
        return "py"
    if path.endswith((".c", ".cc", ".cpp", ".cxx", ".h", ".hpp")):
        return "cpp"
    return "other"


_FileData = tuple[str, Path, str, ast.AST | None, list[str], list[str], set[str], set[str], list[str]]


def _git_ls_files(repo: Path) -> list[str]:
    import subprocess
    p = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return []
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def _previous_nodes(previous: Graph | None) -> dict[str, Node]:
    """Return cached nodes for incremental parsing."""
    return dict(previous.nodes) if previous else {}


def _add_config_node(g: Graph, repo: Path, rel_path: str, fpath: Path, prev_nodes: dict[str, Node]) -> None:
    keys = _config_keys(fpath)
    try:
        source = fpath.read_text(encoding="utf-8")
    except Exception:
        return
    sha = _file_hash(source)
    if rel_path in prev_nodes and prev_nodes[rel_path].sha256 == sha:
        g.nodes[rel_path] = prev_nodes[rel_path]
        return
    kind = "config" if rel_path.endswith((".json", ".yaml", ".yml")) else "data"
    g.nodes[rel_path] = Node(id=rel_path, kind=kind, config_keys=tuple(keys), sha256=sha)


def _collect_file_data(
    *,
    repo: Path,
    paths: list[str],
    g: Graph,
    prev_nodes: dict[str, Node],
) -> tuple[list[_FileData], dict[str, str]]:
    all_defs: dict[str, str] = {}
    file_data: list[_FileData] = []

    for rel_path in paths:
        fpath = repo / rel_path
        if not fpath.exists():
            continue
        if rel_path.endswith((".json", ".yaml", ".yml", ".env")) or fpath.name == ".env":
            _add_config_node(g, repo, rel_path, fpath, prev_nodes)
            continue

        is_py = rel_path.endswith(".py")
        is_rs = rel_path.endswith(".rs")
        is_cpp = rel_path.endswith((".cc", ".cpp", ".c", ".cxx", ".h", ".hpp", ".mm"))
        if not (is_py or is_rs or is_cpp):
            continue
        try:
            source = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        sha = _file_hash(source)
        if rel_path in prev_nodes and prev_nodes[rel_path].sha256 == sha:
            g.nodes[rel_path] = prev_nodes[rel_path]
            for d in prev_nodes[rel_path].defines:
                if d.startswith("def:") or d.startswith("fn:"):
                    all_defs[d.split(":", 1)[1]] = rel_path
            continue

        imports: list[str] = []
        defines: list[str] = []
        variables: set[str] = set()
        calls: set[str] = set()
        if is_py:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in node.names:
                        imports.append(f"{mod}.{alias.name}" if mod else alias.name)
                elif isinstance(node, ast.ClassDef):
                    defines.append(f"class:{node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defines.append(f"def:{node.name}")
                    all_defs[node.name] = rel_path
            variables = _walk_variables(tree)
            calls = _walk_calls(tree)
        elif is_rs:
            imports, defines, variables, calls = _parse_rust_file(source, rel_path)
            for d in defines:
                if d.startswith("fn:"):
                    all_defs[d[4:]] = rel_path
        elif is_cpp:
            imports, defines, variables, calls = _parse_cpp_file(source, rel_path)
            for d in defines:
                if d.startswith("def:"):
                    all_defs[d[4:]] = rel_path
        file_data.append((rel_path, fpath, source, None, imports, defines, variables, calls, []))
    return file_data, all_defs


def _internal_imports(repo: Path, rel_path: str, fpath: Path, imports: list[str]) -> list[str]:
    internal_imports: list[str] = []
    is_rs = rel_path.endswith(".rs")
    is_cpp = rel_path.endswith((".cc", ".cpp", ".c", ".cxx", ".h", ".hpp", ".mm"))
    for imp in imports:
        if is_rs:
            mapped = _rust_import_to_path(imp, repo, rel_path)
            if mapped:
                internal_imports.append(mapped)
        elif is_cpp:
            if (repo / imp).exists():
                internal_imports.append(imp)
            else:
                rel_to_curr = (fpath.parent / imp).resolve()
                try:
                    rel_mapped = rel_to_curr.relative_to(repo)
                    if (repo / rel_mapped).exists():
                        internal_imports.append(str(rel_mapped))
                except ValueError:
                    pass
        else:
            parts = imp.split(".")
            candidate = "/".join(parts) + ".py"
            if (repo / candidate).exists():
                internal_imports.append(candidate)
            else:
                candidate_init = "/".join(parts) + "/__init__.py"
                if (repo / candidate_init).exists():
                    internal_imports.append(candidate_init)
    return internal_imports


def _emit_file_nodes_and_import_edges(g: Graph, repo: Path, file_data: list[_FileData]) -> None:
    for rel_path, fpath, source, _tree, imports, defines, variables, calls, _ in file_data:
        g.nodes[rel_path] = Node(
            id=rel_path,
            kind="file",
            imports=tuple(imports),
            defines=tuple(defines),
            variables=tuple(sorted(variables)),
            calls=tuple(sorted(calls)),
            sha256=_file_hash(source),
        )
        for imp in _internal_imports(repo, rel_path, fpath, imports):
            g.edges.append(Edge(source=rel_path, target=imp, kind="import", weight=1.0))


def _emit_call_edges(g: Graph, file_data: list[_FileData]) -> None:
    def_files: dict[str, set[str]] = {}
    for nid, n in g.nodes.items():
        if n.kind != "file":
            continue
        for d in n.defines:
            if d.startswith("def:") or d.startswith("fn:"):
                def_files.setdefault(d.split(":", 1)[1], set()).add(nid)

    for rel_path, _, _, _, _, _, _, calls, _ in file_data:
        src_lang = _lang_of(rel_path)
        for call_name in calls:
            candidates = {f for f in def_files.get(call_name, ()) if f != rel_path}
            candidates = {f for f in candidates if _lang_of(f) == src_lang}
            if len(candidates) == 1:
                g.edges.append(Edge(source=rel_path, target=next(iter(candidates)), kind="call", weight=1.0))


def _restore_cached_edges(g: Graph, previous: Graph | None, prev_nodes: dict[str, Node]) -> None:
    if not previous:
        return

    def src_unchanged(e: Edge) -> bool:
        return (e.source in prev_nodes and e.source in g.nodes
                and g.nodes[e.source].sha256 == prev_nodes[e.source].sha256)

    for e in previous.edges:
        if e.source not in g.nodes or e.target not in g.nodes:
            continue
        if e.kind == "import":
            if src_unchanged(e) and not any(
                x.source == e.source and x.target == e.target and x.kind == "import"
                for x in g.edges
            ):
                g.edges.append(e)
        elif e.kind == "call":
            if _lang_of(e.source) != _lang_of(e.target):
                continue
            dst_unchanged = (e.target in prev_nodes
                             and g.nodes[e.target].sha256 == prev_nodes[e.target].sha256)
            if src_unchanged(e) and dst_unchanged and not any(
                x.source == e.source and x.target == e.target and x.kind == "call"
                for x in g.edges
            ):
                g.edges.append(e)


def extract_from_repo(repo: Path, previous: Graph | None = None) -> Graph:
    """Build a Graph from a git repository using AST parsing.

    If *previous* is provided, only re-parse files whose sha256 changed (incremental).
    Deleted files are removed. Untracked files are ignored (git ls-files boundary).
    """
    g = Graph(repo=str(repo.resolve()))
    paths = _git_ls_files(repo)
    if not paths:
        return g

    prev_nodes: dict[str, Node] = {}
    if previous:
        prev_nodes = _previous_nodes(previous)
    file_data, _all_defs = _collect_file_data(repo=repo, paths=paths, g=g, prev_nodes=prev_nodes)
    _emit_file_nodes_and_import_edges(g, repo, file_data)
    _emit_call_edges(g, file_data)
    _restore_cached_edges(g, previous, prev_nodes)
    return g


# ── caching ──────────────────────────────────────────────────────────────────

def _cache_path(repo: Path) -> Path:
    return repo / ".lgwks" / "graph.cache.json"


def load_cached(repo: Path, max_age_seconds: float = 300.0) -> Graph | None:
    """Load graph from cache if present and not stale."""
    cache = _cache_path(repo)
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("schema") != _CACHE_SCHEMA:
            return None
        ts = data.get("timestamp", 0)
        if time.time() - ts > max_age_seconds:
            return None
        return Graph.from_dict(data.get("graph", {}))
    except Exception:
        return None


def save_cached(repo: Path, graph: Graph) -> None:
    """Save graph to cache with timestamp."""
    cache = _cache_path(repo)
    cache.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": _CACHE_SCHEMA,
        "timestamp": time.time(),
        "graph": graph.to_dict(),
    }
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(cache)


def get_graph(repo: Path, force_refresh: bool = False) -> Graph:
    """High-level: incremental load — only re-parse files whose sha256 changed."""
    previous: Graph | None = None
    if not force_refresh:
        previous = load_cached(repo)
    graph = extract_from_repo(repo, previous=previous)
    save_cached(repo, graph)
    return graph


# ── deterministic schema inference (no AI) ───────────────────────────────────
# L0: given a graph dump, infer entity types, relationships, cardinality, domain.
# L1: no LLM — pure frequency, co-occurrence, and edge-direction analysis.

@dataclass
class SchemaReport:
    """Inferred schema from a graph dump."""
    entity_types: dict[str, dict[str, Any]]  # type -> {count, domain_values, required}
    relationships: list[dict[str, Any]]      # inferred rel types with cardinality
    coverage: dict[str, float]               # field -> fraction of nodes that have it
    anomalies: list[str]                     # human-readable pattern findings


def infer_schema(graph: Graph) -> SchemaReport:
    """Infer schema from a code/config graph (Node.kind + Node.config_keys + edges).
    For entity graphs (SQLite), use lgwks_entity_graph.infer_entity_schema."""
    n = len(graph.nodes)
    if n == 0:
        return SchemaReport({}, [], {}, ["empty graph"])

    graph._ensure_index()

    # Entity type frequencies
    type_counts: dict[str, int] = {}
    type_fields: dict[str, dict[str, int]] = {}  # type -> field -> count
    for node in graph.nodes.values():
        k = node.kind
        type_counts[k] = type_counts.get(k, 0) + 1
        if k not in type_fields:
            type_fields[k] = {}
        if node.config_keys:
            for key in node.config_keys:
                type_fields[k][key] = type_fields[k].get(key, 0) + 1
        if node.defines:
            for d in node.defines:
                type_fields[k][d] = type_fields[k].get(d, 0) + 1
        if node.variables:
            for v in node.variables:
                type_fields[k][v] = type_fields[k].get(v, 0) + 1

    entity_types: dict[str, dict[str, Any]] = {}
    for t, c in type_counts.items():
        fields = type_fields.get(t, {})
        coverage = {f: round(count / c, 3) for f, count in fields.items()}
        # required = coverage > 0.9
        required = [f for f, r in coverage.items() if r > 0.9]
        # domain = values that appear for fields with coverage > 0.5 and low cardinality
        domain: dict[str, list[str]] = {}
        for f, r in coverage.items():
            if r > 0.5 and len(fields) <= 20:
                # collect actual values for this field across nodes of this type
                values: set[str] = set()
                for node in graph.nodes.values():
                    if node.kind != t:
                        continue
                    if f in node.config_keys:
                        values.add(f)
                    elif f in node.defines:
                        values.add(f)
                    elif f in node.variables:
                        values.add(f)
                if values:
                    domain[f] = sorted(values)[:20]
        entity_types[t] = {
            "count": c,
            "fraction": round(c / n, 3),
            "required_fields": required,
            "optional_fields": [f for f in fields if f not in required],
            "domain": domain,
            "field_coverage": coverage,
        }

    # Relationship inference from edges
    rel_counts: dict[str, int] = {}
    rel_pairs: dict[str, dict[tuple[str, str], int]] = {}  # rel -> (src_kind, dst_kind) -> count
    for e in graph.edges:
        rel_counts[e.kind] = rel_counts.get(e.kind, 0) + 1
        src_node = graph.nodes.get(e.source)
        dst_node = graph.nodes.get(e.target)
        if src_node and dst_node:
            pair = (src_node.kind, dst_node.kind)
            if e.kind not in rel_pairs:
                rel_pairs[e.kind] = {}
            rel_pairs[e.kind][pair] = rel_pairs[e.kind].get(pair, 0) + 1

    relationships: list[dict[str, Any]] = []
    for rel, total in sorted(rel_counts.items(), key=lambda x: -x[1]):
        pairs = rel_pairs.get(rel, {})
        # Cardinality inference:
        # If every src has exactly 1 dst for this rel -> 1:1 or 1:N
        src_counts: dict[str, int] = {}
        dst_counts: dict[str, int] = {}
        for e in graph.edges:
            if e.kind != rel:
                continue
            src_counts[e.source] = src_counts.get(e.source, 0) + 1
            dst_counts[e.target] = dst_counts.get(e.target, 0) + 1
        avg_src = sum(src_counts.values()) / max(1, len(src_counts))
        avg_dst = sum(dst_counts.values()) / max(1, len(dst_counts))
        if avg_src <= 1.1 and avg_dst <= 1.1:
            cardinality = "1:1"
        elif avg_src <= 1.1 and avg_dst > 1.1:
            cardinality = "N:1"  # many sources → one target (many-to-one)
        elif avg_src > 1.1 and avg_dst <= 1.1:
            cardinality = "1:N"  # one source → many targets (one-to-many)
        else:
            cardinality = "N:M"

        top_pairs = sorted(pairs.items(), key=lambda x: -x[1])[:3]
        relationships.append({
            "rel": rel,
            "count": total,
            "cardinality": cardinality,
            "avg_per_src": round(avg_src, 2),
            "avg_per_dst": round(avg_dst, 2),
            "top_pairs": [{"from": p[0], "to": p[1], "count": c} for p, c in top_pairs],
        })

    # Coverage of fields across ALL nodes
    all_fields: dict[str, int] = {}
    for node in graph.nodes.values():
        for f in list(node.config_keys) + list(node.defines) + list(node.variables):
            all_fields[f] = all_fields.get(f, 0) + 1
    coverage = {f: round(c / n, 3) for f, c in all_fields.items()}

    # Anomalies (human-readable)
    anomalies: list[str] = []
    orphan_count = len([nid for nid in graph.nodes if not graph.neighbors(nid) and not graph.predecessors(nid)])
    if orphan_count > 0:
        anomalies.append(f"{orphan_count} orphaned nodes (no edges)")
    if len(rel_counts) == 0:
        anomalies.append("no edges — graph is fully disconnected")
    else:
        most_common_rel = max(rel_counts.items(), key=lambda x: x[1])
        anomalies.append(f"most common relationship: {most_common_rel[0]} ({most_common_rel[1]} edges)")
    # high instability
    mi = graph.module_instability()
    unstable = [nid for nid, v in mi.items() if v > 0.8]
    if unstable:
        anomalies.append(f"{len(unstable)} modules with instability > 0.8 (leaf/concrete)")

    return SchemaReport(entity_types, relationships, coverage, anomalies)


# ── query engine (lightweight Cypher-like) ─────────────────────────────────────
# L0: graph usable from CLI without writing Python.
# L1: syntax is a tiny subset — enough for 90% of graph questions, never a full parser.

import re as _re

_QUERY_TOKENS = _re.compile(
    r"MATCH\s*\((\w+)\)"
    # relationship: optional binding var and optional :type, in either order —
    # -[r]->  /  -[:import]->  /  -[r:import]->  /  -[]->
    r"(?:\s*-\[\s*(\w+)?\s*(?::\s*(\w+))?\s*\]->\s*\((\w+)\))?"
    r"(?:\s*WHERE\s+(.+?)(?=\s+RETURN|\s+LIMIT|$))?"
    r"(?:\s*RETURN\s+(.+?)(?=\s+LIMIT|$))?"
    r"(?:\s*LIMIT\s+(\d+))?",
    _re.IGNORECASE,
)


class QueryResult:
    """Structured result from a graph query."""
    def __init__(self, columns: list[str], rows: list[dict[str, Any]]):
        self.columns = columns
        self.rows = rows

    def to_dict(self) -> dict[str, Any]:
        return {"columns": self.columns, "rows": self.rows}


def _parse_where(clause: str) -> list[tuple[str, str, str]]:
    """Parse WHERE conditions: a.op.b where op is =, !=, CONTAINS, ENDS WITH, STARTS WITH."""
    clause = clause.strip()
    conditions: list[tuple[str, str, str]] = []
    parts = _re.split(r"\s+AND\s+", clause, flags=_re.IGNORECASE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # multi-word operators first (ENDS WITH, STARTS WITH) then single-word (=, !=, CONTAINS)
        m = _re.match(
            r"(\w+(?:\.\w+)?)\s*(ENDS WITH|STARTS WITH|CONTAINS|=|!=)\s*(.+)",
            part,
            _re.IGNORECASE,
        )
        if m:
            field, op, val = m.group(1), m.group(2).upper(), m.group(3).strip()
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1]
            conditions.append((field, op, val))
    return conditions


def _get_field(node: Node, field: str) -> Any:
    """Resolve n.id, n.kind, n.defines, n.variables, n.pagerank, etc."""
    if field in ("id", "kind", "sha256"):
        return getattr(node, field)
    if field == "imports":
        return node.imports
    if field == "defines":
        return node.defines
    if field == "variables":
        return node.variables
    if field == "calls":
        return node.calls
    if field == "config_keys":
        return node.config_keys
    return None


def _eval_condition(node: Node, field: str, op: str, val: str) -> bool:
    """Evaluate one WHERE condition against a node."""
    actual = _get_field(node, field)
    if op == "=":
        return str(actual) == val
    if op == "!=":
        return str(actual) != val
    if op == "CONTAINS":
        if isinstance(actual, tuple):
            return any(val in str(item) for item in actual)
        if isinstance(actual, str):
            return val in actual
        if isinstance(actual, list):
            return any(val in str(item) for item in actual)
        return False
    if op == "ENDS WITH":
        s = str(actual)
        return s.endswith(val)
    if op == "STARTS WITH":
        s = str(actual)
        return s.startswith(val)
    return False


def execute_query(graph: Graph, query: str) -> QueryResult:
    """Run a Cypher-like query against the graph.

    Supported syntax:
      MATCH (n)
      MATCH (n)-[:import]->(m)
      WHERE n.kind = 'file' AND n.defines CONTAINS 'foo'
      RETURN n.id, n.pagerank
      LIMIT 10
    """
    m = _QUERY_TOKENS.search(query)
    if not m:
        raise ValueError(f"query syntax not recognized: {query!r}")
    node_var = m.group(1)
    rel_var = m.group(2)      # binding variable in -[r]-> (any type)
    edge_kind = m.group(3)    # typed relationship in -[:import]-> / -[r:import]->
    node_b = m.group(4)
    where_clause = m.group(5)
    return_clause = m.group(6)
    limit_str = m.group(7)

    limit = int(limit_str) if limit_str else 1000

    # Build result set
    results: list[dict[str, Any]] = []
    conditions = _parse_where(where_clause) if where_clause else []

    def _node_view(node: Node) -> dict[str, Any]:
        return {"id": node.id, "kind": node.kind, "defines": list(node.defines),
                "variables": list(node.variables), "calls": list(node.calls),
                "config_keys": list(node.config_keys)}

    if node_b:
        # Relationship query: iterate edges. A bare -[r]-> matches ANY kind;
        # -[:import]-> filters by kind. The relationship variable (if any) is
        # bound so RETURN can project r.kind / r.source / r.target / r.weight.
        graph._ensure_index()
        for e in graph.edges:
            if edge_kind and e.kind.lower() != edge_kind.lower():
                continue
            src = graph.nodes.get(e.source)
            dst = graph.nodes.get(e.target)
            if not src or not dst:
                continue
            row: dict[str, Any] = {node_var: _node_view(src), node_b: _node_view(dst)}
            if rel_var:
                row[rel_var] = {"kind": e.kind, "source": e.source,
                                "target": e.target, "weight": e.weight}
            # WHERE applies to the source node by default
            ok = all(_eval_condition(src, f.replace(node_var + ".", ""), op, val) for f, op, val in conditions)
            if ok:
                results.append(row)
    else:
        # Node query
        for nid, node in graph.nodes.items():
            ok = all(_eval_condition(node, f.replace(node_var + ".", ""), op, val) for f, op, val in conditions)
            if ok:
                results.append({node_var: {"id": node.id, "kind": node.kind, "defines": list(node.defines),
                                            "variables": list(node.variables), "calls": list(node.calls),
                                            "config_keys": list(node.config_keys)}})

    # Truncate
    results = results[:limit]

    # RETURN projection (with DISTINCT support)
    if return_clause:
        rc = return_clause.strip()
        distinct = False
        if rc.upper().startswith("DISTINCT "):
            distinct = True
            rc = rc[9:]
        cols = [c.strip() for c in rc.split(",")]
        projected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in results:
            proj: dict[str, Any] = {}
            for col in cols:
                col = col.strip()
                if "." in col:
                    var, field = col.split(".", 1)
                    obj = row.get(var, {})
                    if isinstance(obj, dict):
                        proj[col] = obj.get(field)
                    elif hasattr(obj, field):
                        proj[col] = getattr(obj, field)
                    else:
                        proj[col] = None
                else:
                    proj[col] = row.get(col)
            if distinct:
                key = json.dumps(proj, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    continue
                seen.add(key)
            projected.append(proj)
        return QueryResult(cols, projected)

    return QueryResult([node_var], results)


def _build_meta(rows: list[Any], query_validated: bool = True, warnings: list[str] | None = None) -> dict[str, Any]:
    """Meta block for every JSON payload: explains emptiness, validation state, and warnings."""
    meta: dict[str, Any] = {"query_validated": query_validated, "row_count": len(rows)}
    if not rows:
        meta["why_empty"] = "query_constraint_returned_zero_matches"
    if warnings:
        meta["warnings"] = warnings
    return meta


def graph_command(args) -> int:
    """CLI entry point for `lgwks graph …` queries."""
    import argparse
    import subprocess
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not (repo / ".git").exists():
        print(f"[graph] not a git repo: {repo}", file=sys.stderr)
        return 1

    graph = get_graph(repo, force_refresh=getattr(args, "refresh", False))

    # ── language coverage warning (hollow-green trap guard) ──────────────────────
    pre_warnings: list[str] = []
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "ls-files"],
            capture_output=True, text=True, timeout=30,
        )
        if p.returncode == 0:
            all_paths = [ln for ln in p.stdout.splitlines() if ln.strip()]
            indexed_paths = set(graph.nodes.keys())
            pre_warnings = _detect_unindexed_languages(all_paths, indexed_paths)
            for w in pre_warnings:
                print(w, file=sys.stderr)
    except Exception:
        pass

    # ── impact ─────────────────────────────────────────────────────────────────
    if getattr(args, "impact", None):
        files = [f.strip() for f in getattr(args, "files", "").split(",") if f.strip()]
        radius = getattr(args, "radius", 3)
        scores = graph.change_propagation_score(files, radius=radius)
        rows = [{"id": k, "score": v} for k, v in sorted(scores.items(), key=lambda x: -x[1])]
        payload = {
            "schema": "lgwks.graph.impact.v0",
            "repo": str(repo),
            "changed": files,
            "radius": radius,
            "scores": {k: v for k, v in sorted(scores.items(), key=lambda x: -x[1])},
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── complexity ─────────────────────────────────────────────────────────────
    if getattr(args, "complexity", False):
        ci = graph.complexity_index()
        pr = graph.pagerank()
        bc = graph.betweenness_centrality()
        rows = [{"id": k, "pagerank": v} for k, v in sorted(pr.items(), key=lambda x: -x[1])[:10]]
        payload = {
            "schema": "lgwks.graph.complexity.v0",
            "repo": str(repo),
            "kgci": ci,
            "top_pagerank": dict(sorted(pr.items(), key=lambda x: -x[1])[:10]),
            "top_betweenness": dict(sorted(bc.items(), key=lambda x: -x[1])[:10]),
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── path ───────────────────────────────────────────────────────────────────
    if getattr(args, "path", None):
        src = getattr(args, "from_node", "")
        dst = getattr(args, "to_node", "")
        p = graph.shortest_path(src, dst)
        rows = [{"id": node} for node in (p if p else [])]
        payload = {
            "schema": "lgwks.graph.path.v0",
            "repo": str(repo),
            "from": src,
            "to": dst,
            "path": p if p else [],
            "reachable": p is not None,
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── neighbors ──────────────────────────────────────────────────────────────
    if getattr(args, "neighbors", None):
        nid = getattr(args, "of", "")
        out_n = graph.neighbors(nid)
        in_n = graph.predecessors(nid)
        rows = [{"id": nid, "direction": "out", "neighbor": n} for n in out_n] + [{"id": nid, "direction": "in", "neighbor": n} for n in in_n]
        payload = {
            "schema": "lgwks.graph.neighbors.v0",
            "repo": str(repo),
            "node": nid,
            "outgoing": out_n,
            "incoming": in_n,
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── query ────────────────────────────────────────────────────────────────────
    q = getattr(args, "query", "")
    if q:
        try:
            result = execute_query(graph, q)
            query_warnings: list[str] = []
            if not result.rows:
                query_warnings.append("query_returned_zero_rows — verify predicates (CONTAINS, ENDS WITH, STARTS WITH are supported; keys() is not)")
            payload = {
                "schema": "lgwks.graph.query.v0",
                "repo": str(repo),
                "query": q,
                "columns": result.columns,
                "rows": result.rows,
                "meta": _build_meta(result.rows, query_validated=True, warnings=query_warnings + pre_warnings),
            }
            print(json.dumps(payload, indent=2))
        except ValueError as e:
            err_payload = {
                "schema": "lgwks.graph.query.v0",
                "repo": str(repo),
                "query": q,
                "error": str(e),
                "meta": {"query_validated": False, "why_empty": "query_syntax_error", "row_count": 0},
            }
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
            return 1
        return 0

    # ── patterns ─────────────────────────────────────────────────────────────────
    if getattr(args, "patterns", False):
        pats = graph.detect_patterns()
        rows = [{"pattern": k, "count": len(v)} for k, v in pats.items()]
        payload = {
            "schema": "lgwks.graph.patterns.v0",
            "repo": str(repo),
            "patterns": pats,
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── schema-infer ───────────────────────────────────────────────────────────────
    if getattr(args, "schema_infer", False):
        schema = infer_schema(graph)
        rows = [{"type": k, "count": v.get("count", 0)} for k, v in schema.entity_types.items()]
        payload = {
            "schema": "lgwks.graph.schema-infer.v0",
            "repo": str(repo),
            "entity_types": schema.entity_types,
            "relationships": schema.relationships,
            "coverage": schema.coverage,
            "anomalies": schema.anomalies,
            "meta": _build_meta(rows, warnings=pre_warnings or None),
        }
        print(json.dumps(payload, indent=2))
        return 0

    # ── viz (visualization) ────────────────────────────────────────────────────
    if getattr(args, "graph_command", None) == "viz" or getattr(args, "viz", False):
        import lgwks_graph_viz as vizmod
        return vizmod.viz_command(args)

    # ── export-html (static export) ──────────────────────────────────────────────
    export_html = getattr(args, "export_html", None)
    if export_html:
        import lgwks_graph_viz as vizmod
        return vizmod.viz_command(args)

    print("[graph] nothing to do — specify --impact, --complexity, --path, --neighbors, --query, --patterns, --schema-infer, or --viz", file=sys.stderr)
    return 1


def add_graph_parser(subparsers) -> None:
    """Register `lgwks graph` subparser."""
    p = subparsers.add_parser(
        "graph",
        help="query the codebase graph: impact, complexity, path, neighbors, Cypher-like queries",
    )
    p.add_argument("--repo", default=".", help="path to git repo (default: cwd)")
    p.add_argument("--refresh", action="store_true", help="force re-extraction, ignore cache")
    p.add_argument("--impact", action="store_true", help="run change-propagation impact analysis")
    p.add_argument("--files", default="", help="comma-separated changed files for --impact")
    p.add_argument("--radius", type=int, default=3, help="impact radius (default: 3)")
    p.add_argument("--complexity", action="store_true", help="print KGCI complexity index")
    p.add_argument("--path", action="store_true", help="shortest path between two files")
    p.add_argument("--from", dest="from_node", default="", help="source node for --path")
    p.add_argument("--to", dest="to_node", default="", help="target node for --path")
    p.add_argument("--neighbors", action="store_true", help="list neighbors of a node")
    p.add_argument("--of", default="", help="node id for --neighbors")
    p.add_argument("--query", default="", help='Cypher-like query, e.g. \'MATCH (n) WHERE n.kind = "file" RETURN n.id\'')
    p.add_argument("--patterns", action="store_true", help="detect architectural patterns (circular deps, god modules, orphans, etc.)")
    p.add_argument("--schema-infer", action="store_true", help="infer schema from graph topology (entity types, cardinality, coverage)")
    p.add_argument("--viz", action="store_true", help="start interactive visualization server (localhost only)")
    p.add_argument("--serve", action="store_true", help="alias for --viz: start HTTP server")
    p.add_argument("--port", type=int, default=3000, help="server port for --viz (default: 3000)")
    p.add_argument("--export-html", default="", help="export static HTML file (no server)")
    p.add_argument("--json", action="store_true", help="structured output (default when piped or LGWRS_MACHINE set)")
    p.set_defaults(func=graph_command)

    gp = p.add_subparsers(dest="graph_command", required=False)
    viz_parser = gp.add_parser("viz", help="interactive visual graph browser and exporter")
    viz_parser.add_argument("--repo", default=".", help="repository path")
    viz_parser.add_argument("--serve", action="store_true", help="start HTTP server instead of terminal TUI")
    viz_parser.add_argument("--port", type=int, default=3000, help="server port")
    viz_parser.add_argument("--export-html", help="export static HTML file")
    viz_parser.add_argument("--export-dot", help="export DOT file (use - for stdout)")
    viz_parser.add_argument("--files", default="", help="comma-separated changed files to highlight in DOT export")
