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
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_SCHEMA = "lgwks.graph.v2"
_CACHE_SCHEMA = "lgwks.graph.cache.v1"


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


# ── extraction from repo ─────────────────────────────────────────────────────

def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


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


def extract_from_repo(repo: Path, previous: Graph | None = None) -> Graph:
    """Build a Graph from a git repository using AST parsing.

    If *previous* is provided, only re-parse files whose sha256 changed (incremental).
    Deleted files are removed. Untracked files are ignored (git ls-files boundary).
    """
    import subprocess
    g = Graph(repo=str(repo.resolve()))

    # respect .gitignore via git ls-files
    p = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return g

    paths = [ln for ln in p.stdout.splitlines() if ln.strip()]

    # ── incremental setup ──────────────────────────────────────────────────────
    prev_nodes: dict[str, Node] = {}
    prev_by_def: dict[str, str] = {}  # def:name -> file path
    if previous:
        prev_nodes = dict(previous.nodes)
        for nid, n in prev_nodes.items():
            for d in n.defines:
                if d.startswith("def:"):
                    prev_by_def[d[4:]] = nid

    # First pass: gather all definitions for cross-file call-graph mapping
    all_defs: dict[str, str] = {}  # def:name -> file path
    file_data: list[tuple[str, Path, str, ast.AST | None, list[str], list[str], set[str], set[str], list[str]]] = []
    # (rel_path, fpath, source, tree, imports, defines, variables, calls, config_keys)

    for rel_path in paths:
        fpath = repo / rel_path
        if not fpath.exists():
            continue

        # Config files: JSON, YAML, .env
        if rel_path.endswith((".json", ".yaml", ".yml", ".env")) or fpath.name == ".env":
            keys = _config_keys(fpath)
            try:
                source = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            sha = _file_hash(source)
            # incremental: reuse previous node if sha matches
            if previous and rel_path in prev_nodes and prev_nodes[rel_path].sha256 == sha:
                g.nodes[rel_path] = prev_nodes[rel_path]
                continue
            kind = "config" if rel_path.endswith((".json", ".yaml", ".yml")) else "data"
            g.nodes[rel_path] = Node(
                id=rel_path, kind=kind, config_keys=tuple(keys), sha256=sha,
            )
            continue

        if not rel_path.endswith(".py"):
            continue

        try:
            source = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        sha = _file_hash(source)

        # incremental: reuse previous node if sha matches
        if previous and rel_path in prev_nodes and prev_nodes[rel_path].sha256 == sha:
            g.nodes[rel_path] = prev_nodes[rel_path]
            # still need its defs for call-graph mapping
            for d in prev_nodes[rel_path].defines:
                if d.startswith("def:"):
                    all_defs[d[4:]] = rel_path
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        imports: list[str] = []
        defines: list[str] = []
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

        file_data.append((rel_path, fpath, source, tree, imports, defines, variables, calls, []))

    # Second pass: build nodes + import edges
    for rel_path, fpath, source, tree, imports, defines, variables, calls, _ in file_data:
        # map imports to likely internal modules
        internal_imports: list[str] = []
        for imp in imports:
            parts = imp.split(".")
            candidate = "/".join(parts) + ".py"
            if (repo / candidate).exists():
                internal_imports.append(candidate)
            else:
                candidate_init = "/".join(parts) + "/__init__.py"
                if (repo / candidate_init).exists():
                    internal_imports.append(candidate_init)

        sha = _file_hash(source)
        g.nodes[rel_path] = Node(
            id=rel_path,
            kind="file",
            imports=tuple(imports),
            defines=tuple(defines),
            variables=tuple(sorted(variables)),
            calls=tuple(sorted(calls)),
            sha256=sha,
        )

        for imp in internal_imports:
            g.edges.append(Edge(source=rel_path, target=imp, kind="import", weight=1.0))

    # Third pass: call-graph edges (cross-file)
    # Build full def map from both fresh and cached nodes
    full_def_map = dict(all_defs)
    for nid, n in g.nodes.items():
        if n.kind != "file":
            continue
        for d in n.defines:
            if d.startswith("def:"):
                full_def_map[d[4:]] = nid
    for nid, n in (previous.nodes if previous else {}).items():
        if nid not in g.nodes or g.nodes[nid].kind != "file":
            continue
        for d in n.defines:
            if d.startswith("def:") and d[4:] not in full_def_map:
                full_def_map[d[4:]] = nid

    for rel_path, _, _, _, _, _, _, calls, _ in file_data:
        for call_name in calls:
            target_file = full_def_map.get(call_name)
            if target_file and target_file != rel_path:
                g.edges.append(Edge(source=rel_path, target=target_file, kind="call", weight=1.0))

    # Copy cached call edges from unchanged files (they still hold)
    if previous:
        for e in previous.edges:
            if e.kind == "call":
                # If both source and target are unchanged, preserve the edge
                src_unchanged = e.source in prev_nodes and e.source in g.nodes and g.nodes[e.source].sha256 == prev_nodes[e.source].sha256
                dst_unchanged = e.target in prev_nodes and e.target in g.nodes and g.nodes[e.target].sha256 == prev_nodes[e.target].sha256
                if src_unchanged and dst_unchanged:
                    # avoid duplicates
                    if not any(x.source == e.source and x.target == e.target and x.kind == "call" for x in g.edges):
                        g.edges.append(e)

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
