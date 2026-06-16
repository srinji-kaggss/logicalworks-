"""
lgwks_bot_optimizer — U7: deterministic optimization static analyzer.

Scans repo Python files for four surface families:
  O1 god module
  O2 split candidate
  O3 token-waste indicator
  O4 reuse candidate

No LLM calls. No internet. Fail closed on parse errors.
Every finding is a valid lgwks.bot.record.v1 record linking to a repo-local path.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional, Any

import lgwks_project_artifacts as artifacts

_BOT = "optimizer"

# Modules that are already shared/facade and should be excluded from reuse/waste warnings
_SHARED_UTILITY_PATTERNS = {"cycle", "artifacts", "graph", "utils", "util"}

# Facade module re-exports mapping (direct module -> facade module)
_RE_EXPORTS = {
    "lgwks_project_artifacts": "lgwks_project",
    "lgwks_project_plan": "lgwks_project",
    "lgwks_project_deploy": "lgwks_project",
    "lgwks_project_review": "lgwks_project",
}


def _run_seed(repo: str) -> str:
    return artifacts.run_seed(_BOT, repo)


def _make(
    *,
    run_id: str,
    repo: str,
    file: str,
    kind: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence: list[dict],
    tags: list[str],
    symbol: Optional[str] = None,
) -> dict:
    return artifacts.make_record(
        bot=_BOT, run_id=run_id, kind=kind, summary=summary, severity=severity,
        confidence=confidence, evidence=evidence, tags=tags, target_id=file,
        links={"repo": repo, "file": file, "symbol": symbol, "tests": [], "artifacts": []},
        world_refs=[{"kind": "concept", "id": kind}],
    )


def _failure_record(run_id: str, repo: str, file: str, reason: str) -> dict:
    return _make(
        run_id=run_id, repo=repo, file=file,
        kind="analyzer_failure",
        summary=f"error in optimizer for {file}: {reason[:120]}",
        severity="info",
        confidence=1.0,
        evidence=[{"type": "trace", "name": "error", "value": reason[:300]}],
        tags=["analyzer", "error"],
    )


def _get_stems(symbol_name: str) -> set[str]:
    parts = symbol_name.split("_")
    stems = set()
    for p in parts:
        p_clean = re.sub(r"[^a-z0-9]", "", p.lower())
        if len(p_clean) >= 2:
            stems.add(p_clean)
    return stems


def _jaccard_similarity(s1: set[str], s2: set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    return len(s1.intersection(s2)) / len(s1.union(s2))


def _is_shared(path: str) -> bool:
    name = Path(path).name.lower()
    return any(p in name for p in _SHARED_UTILITY_PATTERNS)


class _OptimizerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.public_symbols: list[str] = []
        self.unused_params: list[tuple[str, str, int]] = []  # (func_name, param_name, lineno)
        self.imports: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not node.name.startswith("_"):
            self.public_symbols.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("_"):
            self.public_symbols.append(node.name)
            
            # Unused parameter detection
            args = [arg.arg for arg in node.args.args]
            if args and args[0] in {"self", "cls"}:
                args = args[1:]
            
            used_names = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    used_names.add(child.id)
            
            for arg in args:
                if arg not in used_names:
                    self.unused_params.append((node.name, arg, node.lineno))
                    
        self.generic_visit(node)


def _analyze_file(path: Path) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    lines = source.splitlines()
    visitor = _OptimizerVisitor()
    visitor.visit(tree)
    return {
        "line_count": len(lines),
        "public_symbols": visitor.public_symbols,
        "unused_params": visitor.unused_params,
        "imports": visitor.imports,
    }


def _detect_symbol_clusters(defines: list[str]) -> list[str]:
    prefixes = {}
    for d in defines:
        if d.startswith("_"):
            continue
        parts = d.split("_", 1)
        if len(parts) > 1 and parts[0]:
            pref = parts[0]
            prefixes.setdefault(pref, []).append(d)
    active = {p: syms for p, syms in prefixes.items() if len(syms) >= 2}
    if len(active) >= 2:
        return [f"{p} ({len(syms)} symbols)" for p, syms in active.items()]
    return []


def run(
    repo: Path | str,
    changed_files: Optional[list[str]] = None,
    graph: Optional[Any] = None,
    run_id: Optional[str] = None,
) -> list[dict]:
    """
    Run O1–O4 optimization checks.

    Args:
        repo: repository path.
        changed_files: subset of files to scan/report on.
        graph: repository graph cache. Must be present.
        run_id: run identifier.
    """
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = "optimizer:" + _run_seed(repo_str)

    # U7 constraint: graph cache must be loaded before run — emit analyzer_failure if unavailable
    if graph is None:
        return [_failure_record(run_id, repo_str, "graph_cache", "missing graph cache")]

    # Find py files in the repo
    py_files = sorted(repo.glob("**/*.py"))
    py_files = [p for p in py_files if not any(
        part in {".git", "__pycache__", ".venv", "venv", "node_modules"}
        for part in p.parts
    )]

    # Analyze all Python files in the repo to get baseline/graph statistics
    file_info = {}
    for p in py_files:
        rel = str(p.relative_to(repo))
        try:
            file_info[rel] = _analyze_file(p)
        except Exception as exc:
            file_info[rel] = {"error": str(exc), "line_count": 0, "public_symbols": [], "unused_params": [], "imports": []}

    # Decide which files to scan findings for
    if changed_files is not None:
        targets_rel = [f for f in changed_files if f.endswith(".py") and f in file_info]
    else:
        targets_rel = list(file_info.keys())

    findings: list[dict] = []

    # Emit analyzer failures for files that failed to parse
    for rel in targets_rel:
        if "error" in file_info[rel]:
            findings.append(_failure_record(run_id, repo_str, rel, file_info[rel]["error"]))

    # -- Graph stats for O1 God Module --
    file_nodes = [nid for nid in graph.nodes if graph.nodes[nid].kind == "file"]
    if file_nodes:
        in_degrees = {nid: len(graph.predecessors(nid)) for nid in file_nodes}
        out_degrees = {nid: len(graph.neighbors(nid)) for nid in file_nodes}
        avg_in = sum(in_degrees.values()) / len(file_nodes)
        avg_out = sum(out_degrees.values()) / len(file_nodes)
    else:
        in_degrees = {}
        out_degrees = {}
        avg_in = 0.0
        avg_out = 0.0

    try:
        bc = graph.betweenness_centrality()
    except Exception:
        bc = {}

    # -- Global Import counts for O3 --
    import_counts: dict[str, int] = {}
    for rel, info in file_info.items():
        for imp in info.get("imports", []):
            import_counts[imp] = import_counts.get(imp, 0) + 1

    # -- Global Symbol Registry for O3 Re-implementation & O4 Reuse Candidate --
    all_symbols: list[tuple[str, str, set[str]]] = []  # (rel_file, sym_name, stems)
    for rel, info in file_info.items():
        for sym in info.get("public_symbols", []):
            stems = _get_stems(sym)
            if stems:
                all_symbols.append((rel, sym, stems))

    for rel in targets_rel:
        info = file_info[rel]
        if "error" in info:
            continue

        line_count = info["line_count"]
        public_symbols = info["public_symbols"]
        unused_params = info["unused_params"]
        imports = info["imports"]

        # ── O1: God Module ──
        if rel in file_nodes:
            in_deg = in_degrees.get(rel, 0)
            out_deg = out_degrees.get(rel, 0)
            btwn = bc.get(rel, 0.0)
            
            # Check thresholds: in-degree or out-degree > 3x average, betweenness > 0.1, line count > 500
            deg_exceeded = (avg_in > 0 and in_deg > 3 * avg_in) or (avg_out > 0 and out_deg > 3 * avg_out)
            if deg_exceeded and btwn > 0.1 and line_count > 500:
                severity = "high" if btwn > 0.15 or line_count > 800 else "medium"
                findings.append(_make(
                    run_id=run_id, repo=repo_str, file=rel,
                    kind="god_module",
                    summary=f"God module detected: line count {line_count}, betweenness centrality {btwn:.4f}",
                    severity=severity, confidence=0.9,
                    evidence=[
                        {"type": "metric", "name": "line_count", "value": line_count},
                        {"type": "metric", "name": "in_degree", "value": in_deg},
                        {"type": "metric", "name": "out_degree", "value": out_deg},
                        {"type": "metric", "name": "betweenness_centrality", "value": btwn},
                    ],
                    tags=["god-module", "architecture", "o1"],
                ))

        # ── O2: Split Candidate ──
        # Threshold A: lines > 350 and defines > 8 public symbols
        if line_count > 350 and len(public_symbols) > 8:
            findings.append(_make(
                run_id=run_id, repo=repo_str, file=rel,
                kind="split_candidate",
                summary=f"Split candidate: file defines {len(public_symbols)} public symbols across {line_count} lines",
                severity="medium", confidence=0.9,
                evidence=[
                    {"type": "metric", "name": "line_count", "value": line_count},
                    {"type": "metric", "name": "public_symbols_count", "value": len(public_symbols)},
                ],
                tags=["split-candidate", "size", "o2"],
            ))
        else:
            # Threshold B: multiple disjoint clusters from symbol names
            clusters = _detect_symbol_clusters(public_symbols)
            if clusters:
                findings.append(_make(
                    run_id=run_id, repo=repo_str, file=rel,
                    kind="split_candidate",
                    summary=f"Split candidate: multiple disjoint responsibility clusters: {', '.join(clusters)}",
                    severity="medium", confidence=0.5,
                    evidence=[
                        {"type": "trace", "name": "symbol_clusters", "value": ", ".join(clusters)},
                    ],
                    tags=["split-candidate", "clusters", "o2"],
                ))

        # ── O3: Token-Waste Indicator ──
        # 1. Duplicate imports when re-export exists
        for imp in imports:
            if imp in _RE_EXPORTS:
                cnt = import_counts.get(imp, 0)
                if cnt >= 5:
                    facade = _RE_EXPORTS[imp]
                    findings.append(_make(
                        run_id=run_id, repo=repo_str, file=rel,
                        kind="token_waste_duplicate_import",
                        summary=f"Import of '{imp}' directly in {cnt} files; use shared facade '{facade}' instead",
                        severity="medium", confidence=0.7,
                        evidence=[
                            {"type": "metric", "name": "import_count", "value": cnt},
                            {"type": "external_ref", "name": "suggested_facade", "value": facade},
                        ],
                        tags=["token-waste", "import", "o3"],
                    ))

        # 2. Re-implemented utility patterns (Jaccard similarity >= 0.8)
        if not _is_shared(rel):
            for sym in public_symbols:
                stems = _get_stems(sym)
                if not stems:
                    continue
                for other_file, other_sym, other_stems in all_symbols:
                    if other_file == rel or _is_shared(other_file):
                        continue
                    sim = _jaccard_similarity(stems, other_stems)
                    if sim >= 0.8:
                        findings.append(_make(
                            run_id=run_id, repo=repo_str, file=rel,
                            kind="token_waste_reimplemented_utility",
                            summary=f"Symbol '{sym}' has high stem similarity ({sim:.2f}) with '{other_sym}' in {other_file}",
                            severity="medium", confidence=0.7,
                            evidence=[
                                {"type": "trace", "name": "overlapping_symbol", "value": other_sym},
                                {"type": "metric", "name": "overlap_score", "value": sim},
                            ],
                            tags=["token-waste", "duplication", "o3"],
                            symbol=sym,
                        ))

        # 3. Dead parameters
        for func_name, param_name, lineno in unused_params:
            findings.append(_make(
                run_id=run_id, repo=repo_str, file=rel,
                kind="dead_parameter",
                summary=f"Parameter '{param_name}' in public function '{func_name}' is never referenced",
                severity="medium", confidence=0.7,
                evidence=[
                    {"type": "file_excerpt", "name": "lineno", "value": lineno},
                    {"type": "trace", "name": "parameter", "value": param_name},
                ],
                tags=["token-waste", "dead-code", "o3"],
                symbol=func_name,
            ))

        # ── O4: Reuse Candidate ──
        if not _is_shared(rel):
            for sym in public_symbols:
                stems = _get_stems(sym)
                if not stems:
                    continue
                matching_files = {rel}
                for other_file, other_sym, other_stems in all_symbols:
                    if other_file == rel or _is_shared(other_file):
                        continue
                    if _jaccard_similarity(stems, other_stems) >= 0.85:
                        matching_files.add(other_file)
                if len(matching_files) >= 3:
                    findings.append(_make(
                        run_id=run_id, repo=repo_str, file=rel,
                        kind="reuse_candidate",
                        summary=f"Symbol '{sym}' is duplicated or highly similar across {len(matching_files)} files; consider moving to a shared module",
                        severity="low", confidence=0.7,
                        evidence=[
                            {"type": "trace", "name": "matching_files", "value": ", ".join(sorted(matching_files))},
                        ],
                        tags=["reuse-candidate", "architecture", "o4"],
                        symbol=sym,
                    ))

    return findings
