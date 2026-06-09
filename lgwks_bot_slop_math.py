"""
lgwks_bot_slop_math — U6: deterministic structural slop-detection bots (S1–S6).

Six independent sub-bots; each callable separately or together via run_all().
No LLM calls. No internet. All findings are lgwks.bot.record.v1 records.

  S1 graph_anomaly   — hub risk, cycles, long chains, instability hotspots
  S2 naming_bot      — generic names, synonym drift, term overload
  S3 spec_drift      — schema/manifest claims vs code reality
  S4 proof_gap       — claims without tests or evidence
  S5 dead_abstraction — unused definitions and pass-through layers
  S6 contradiction   — conflicting constants/claims across files
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import lgwks_project_artifacts as artifacts

_BOT_PREFIX = "slop_math"
# Generic names that flag naming_drift / dead_abstraction candidates
_GENERIC_NAMES = frozenset({
    "util", "utils", "helper", "helpers", "data", "tmp", "misc",
    "handler", "manager", "processor", "wrapper", "base", "common",
    "stuff", "things", "process", "handle", "do_stuff", "run_stuff",
})

# Planned/unresolved claim markers
_TODO_RE = re.compile(r"#\s*(TODO|FIXME|PLANNED|XXX|HACK)(?:\(([^)]+)\))?:?\s*(.+)", re.I)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_id(bot: str, repo: str) -> str:
    return f"slop-math:{bot}:" + hashlib.sha256(f"{bot}:{repo}".encode()).hexdigest()[:10]


def _make(
    *,
    run_id: str,
    bot: str,
    repo: str,
    kind: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence: list[dict],
    tags: list[str],
    file: Optional[str] = None,
    symbol: Optional[str] = None,
    target_kind: str = "file",
    target_id: str = "",
) -> dict:
    tid = target_id or file or repo
    links: dict[str, Any] = {"repo": repo}
    if file:
        links["file"] = file
    if symbol:
        links["symbol"] = symbol
    # ensure at least one anchor
    if not file and not symbol:
        links["artifacts"] = [repo]
    return {
        "schema": artifacts.BOT_RECORD_SCHEMA,
        "run_id": run_id,
        "bot": bot,
        "target": {"kind": target_kind, "id": tid},
        "kind": kind,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "status": "open",
        "evidence": evidence,
        "links": links,
        "tags": tags,
        "created_at": _ts(),
    }


def _py_files(repo: Path) -> list[Path]:
    return sorted(
        p for p in repo.glob("**/*.py")
        if not any(part in {".git", "__pycache__", ".venv", "venv"} for part in p.parts)
    )


def _rel(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


# ── S1 — Graph anomaly bot ────────────────────────────────────────────────────

def run_s1_graph_anomaly(graph: Any, repo: str = "", run_id: Optional[str] = None) -> list[dict]:
    """Emit bot records for hub risk, cycles, long chains, and instability hotspots."""
    if run_id is None:
        run_id = _run_id("graph_anomaly", repo)
    bot = f"{_BOT_PREFIX}.graph_anomaly"
    findings: list[dict] = []

    try:
        patterns: dict[str, Any] = graph.detect_patterns()
    except Exception as exc:
        return [_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="analyzer_failure",
            summary=f"graph.detect_patterns() failed: {exc}",
            severity="info", confidence=1.0,
            evidence=[{"type": "trace", "name": "error", "value": str(exc)[:300]}],
            tags=["analyzer", "graph"],
            target_kind="repo", target_id=repo,
        )]

    # hub_risk — god modules (high in/out degree)
    god = patterns.get("god_modules", {})
    for mod in god.get("modules", []):
        findings.append(_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="hub_risk",
            summary=f"god module '{mod}': in/out-degree exceeds 3× avg",
            severity="medium", confidence=0.9,
            evidence=[{"type": "metric", "name": "threshold_in", "value": god.get("threshold_in", 0)}],
            tags=["graph", "hub", "s1"],
            file=mod, target_kind="file", target_id=mod,
        ))

    # hub_risk — gatekeepers (high betweenness)
    for mod in patterns.get("gatekeepers", {}).get("modules", []):
        findings.append(_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="hub_risk",
            summary=f"gatekeeper bottleneck '{mod}': betweenness > 0.1",
            severity="medium", confidence=0.88,
            evidence=[{"type": "metric", "name": "betweenness_threshold", "value": 0.1}],
            tags=["graph", "hub", "betweenness", "s1"],
            file=mod, target_kind="file", target_id=mod,
        ))

    # cycle_risk — circular dependencies
    for group in patterns.get("circular_dependencies", {}).get("groups", []):
        cycle_id = ":".join(sorted(group))
        findings.append(_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="cycle_risk",
            summary=f"circular dependency among {len(group)} modules: {', '.join(group[:3])}{'...' if len(group) > 3 else ''}",
            severity="high", confidence=0.95,
            evidence=[{"type": "edge", "name": "cycle_members", "value": ", ".join(sorted(group)[:6])}],
            tags=["graph", "cycle", "s1"],
            file=group[0] if group else None,
            target_kind="concept", target_id=f"cycle:{hashlib.sha256(cycle_id.encode()).hexdigest()[:8]}",
        ))

    # instability_hotspot
    for mod in patterns.get("unstable_modules", {}).get("modules", []):
        findings.append(_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="instability_hotspot",
            summary=f"unstable module '{mod}': instability > 0.8",
            severity="low", confidence=0.8,
            evidence=[{"type": "metric", "name": "instability_threshold", "value": 0.8}],
            tags=["graph", "instability", "s1"],
            file=mod, target_kind="file", target_id=mod,
        ))

    # long_chain
    for chain in patterns.get("long_chains", []):
        findings.append(_make(
            run_id=run_id, bot=bot, repo=repo,
            kind="long_chain",
            summary=f"dependency chain length {chain['length']}: {chain['from']} → {chain['to']}",
            severity="low", confidence=0.75,
            evidence=[{"type": "trace", "name": "path", "value": " → ".join(chain.get("path", [])[:8])}],
            tags=["graph", "chain", "s1"],
            file=chain["from"], target_kind="file", target_id=chain["from"],
        ))

    return findings


# ── S2 — Naming / binning bot ─────────────────────────────────────────────────

def run_s2_naming_bot(repo: Path | str, run_id: Optional[str] = None) -> list[dict]:
    """Flag generic names, synonym drift, and overloaded terms."""
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("naming_bot", repo_str)
    bot = f"{_BOT_PREFIX}.naming_bot"
    findings: list[dict] = []

    name_to_files: dict[str, list[str]] = defaultdict(list)
    # concept_map: lowercase concept -> set of distinct identifiers used
    concept_map: dict[str, set[str]] = defaultdict(set)

    for path in _py_files(repo):
        rel = _rel(path, repo)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name.lower()
                # flag generic function/class names
                if name in _GENERIC_NAMES or name.startswith(("_util", "_helper", "_tmp")):
                    findings.append(_make(
                        run_id=run_id, bot=bot, repo=repo_str,
                        kind="naming_drift",
                        summary=f"generic name '{node.name}' in {rel}",
                        severity="low", confidence=0.7,
                        evidence=[{"type": "file_excerpt", "name": "lineno", "value": node.lineno}],
                        tags=["naming", "generic", "s2"],
                        file=rel, symbol=node.name,
                    ))
                # collect concept clusters for overload detection
                stem = re.sub(r"(^_+|_+$|_v\d+$)", "", name)
                if len(stem) >= 4:
                    concept_map[stem].add(f"{rel}::{node.name}")
                name_to_files[node.name].append(rel)

    # term_overload — same name defined in 3+ distinct files
    for name, locs in name_to_files.items():
        distinct_files = list(dict.fromkeys(locs))
        if len(distinct_files) >= 3 and name.lower() not in _GENERIC_NAMES:
            findings.append(_make(
                run_id=run_id, bot=bot, repo=repo_str,
                kind="term_overload",
                summary=f"'{name}' defined in {len(distinct_files)} files — possible concept binning",
                severity="low", confidence=0.6,
                evidence=[{"type": "file_excerpt", "name": "occurrence_count", "value": len(distinct_files)}],
                tags=["naming", "overload", "s2"],
                file=distinct_files[0], symbol=name,
            ))

    return findings


# ── S3 — Spec drift bot ───────────────────────────────────────────────────────

def run_s3_spec_drift(repo: Path | str, run_id: Optional[str] = None) -> list[dict]:
    """Detect schema/manifest claims that diverge from code constants."""
    import json as _json
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("spec_drift", repo_str)
    bot = f"{_BOT_PREFIX}.spec_drift"
    findings: list[dict] = []

    # collect code-level schema string constants
    code_schemas: dict[str, str] = {}  # constant_name -> value
    for path in _py_files(repo):
        rel = _rel(path, repo)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and "SCHEMA" in tgt.id.upper():
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            code_schemas[node.value.value] = rel

    # compare against JSON schema files in docs/schemas/
    schema_dir = repo / "docs" / "schemas"
    if schema_dir.is_dir():
        for schema_file in schema_dir.glob("*.json"):
            rel_sf = _rel(schema_file, repo)
            try:
                schema_doc = _json.loads(schema_file.read_text(encoding="utf-8"))
            except Exception as exc:
                findings.append(_make(
                    run_id=run_id, bot=bot, repo=repo_str,
                    kind="manifest_drift",
                    summary=f"schema file {rel_sf} is invalid JSON: {exc}",
                    severity="medium", confidence=0.9,
                    evidence=[{"type": "file_excerpt", "name": "error", "value": str(exc)[:200]}],
                    tags=["spec", "schema", "s3"],
                    file=rel_sf, target_kind="file", target_id=rel_sf,
                ))
                continue
            doc_title = schema_doc.get("title", "")
            if doc_title and doc_title not in code_schemas:
                findings.append(_make(
                    run_id=run_id, bot=bot, repo=repo_str,
                    kind="spec_code_drift",
                    summary=f"schema '{doc_title}' documented but no matching code constant found",
                    severity="medium", confidence=0.8,
                    evidence=[{"type": "file_excerpt", "name": "schema_title", "value": doc_title}],
                    tags=["spec", "drift", "schema", "s3"],
                    file=rel_sf, target_kind="file", target_id=rel_sf,
                ))

    # find Python functions documented in spec .md files but absent in code
    defined_functions: set[str] = set()
    for path in _py_files(repo):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_functions.add(node.name)

    spec_dir = repo / "docs"
    if spec_dir.is_dir():
        fn_claim_re = re.compile(r"`([a-z_][a-z0-9_]+)\(\)`")
        for md_file in spec_dir.rglob("*.md"):
            rel_md = _rel(md_file, repo)
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for match in fn_claim_re.finditer(text):
                claimed = match.group(1)
                if len(claimed) >= 4 and claimed not in defined_functions:
                    findings.append(_make(
                        run_id=run_id, bot=bot, repo=repo_str,
                        kind="undocumented_surface",
                        summary=f"spec claims `{claimed}()` but no such function in codebase",
                        severity="low", confidence=0.5,
                        evidence=[{"type": "file_excerpt", "name": "claimed_fn", "value": claimed}],
                        tags=["spec", "drift", "function", "s3"],
                        file=rel_md, symbol=claimed,
                    ))

    return findings


# ── S4 — Proof gap bot ────────────────────────────────────────────────────────

def run_s4_proof_gap(repo: Path | str, run_id: Optional[str] = None) -> list[dict]:
    """Find claims (TODO/FIXME/assertions) without linked tests or evidence."""
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("proof_gap", repo_str)
    bot = f"{_BOT_PREFIX}.proof_gap"
    findings: list[dict] = []

    # collect all test function names for cross-reference
    test_names: set[str] = set()
    for path in (repo / "tests").glob("*.py") if (repo / "tests").is_dir() else []:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                test_names.add(node.name)

    for path in _py_files(repo):
        rel = _rel(path, repo)
        if "test_" in rel:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for lineno, line in enumerate(source.splitlines(), 1):
            m = _TODO_RE.search(line)
            if m:
                marker, issue_ref, claim_text = m.group(1), m.group(2), m.group(3)
                if not issue_ref:
                    findings.append(_make(
                        run_id=run_id, bot=bot, repo=repo_str,
                        kind="proof_gap",
                        summary=f"{marker} without issue ref in {rel}:{lineno}: {claim_text[:80]}",
                        severity="low", confidence=0.8,
                        evidence=[{"type": "file_excerpt", "name": "lineno", "value": lineno},
                                  {"type": "query", "name": "marker", "value": marker}],
                        tags=["proof", "todo", "s4"],
                        file=rel,
                    ))

    # functions with no corresponding test_<name> coverage
    for path in _py_files(repo):
        rel = _rel(path, repo)
        if "test_" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                probe = f"test_{node.name}"
                if probe not in test_names:
                    findings.append(_make(
                        run_id=run_id, bot=bot, repo=repo_str,
                        kind="test_gap",
                        summary=f"public function '{node.name}' in {rel} has no test_{node.name}",
                        severity="info", confidence=0.5,
                        evidence=[{"type": "file_excerpt", "name": "lineno", "value": node.lineno}],
                        tags=["proof", "test-gap", "s4"],
                        file=rel, symbol=node.name,
                    ))

    return findings


# ── S5 — Dead abstraction bot ─────────────────────────────────────────────────

def run_s5_dead_abstraction(
    repo: Path | str,
    run_id: Optional[str] = None,
    changed_files: Optional[list[str]] = None,
) -> list[dict]:
    """Detect definitions that are never referenced outside their own file.

    O(n) algorithm: single-pass global reference index, not per-definition file reads.
    """
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("dead_abstraction", repo_str)
    bot = f"{_BOT_PREFIX}.dead_abstraction"
    findings: list[dict] = []

    py_paths = _py_files(repo)
    if changed_files:
        changed_set = set(changed_files)
        py_paths = [p for p in py_paths if _rel(p, repo) in changed_set]
        if not py_paths:
            return findings

    # pass 1: build global reference index (single scan of all files)
    global_ref_count: dict[str, int] = defaultdict(int)
    global_ref_files: dict[str, set[str]] = defaultdict(set)

    all_py = _py_files(repo)
    for path in all_py:
        rel = _rel(path, repo)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        tokens = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]+)\b", source))
        for tok in tokens:
            global_ref_count[tok] += source.count(tok)
            global_ref_files[tok].add(rel)

    # pass 2: collect definitions (scoped to changed_files if provided)
    defined: dict[str, list[tuple[str, int]]] = {}
    for path in py_paths:
        rel = _rel(path, repo)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        names = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    names.append((node.name, node.lineno))
        defined[rel] = names

    # pass 3: check each defined name against global index
    for rel, names in defined.items():
        for name, lineno in names:
            other_refs = global_ref_files.get(name, set()) - {rel}
            if not other_refs:
                findings.append(_make(
                    run_id=run_id, bot=bot, repo=repo_str,
                    kind="dead_abstraction",
                    summary=f"'{name}' in {rel} appears unreferenced across the repo",
                    severity="info", confidence=0.6,
                    evidence=[{"type": "file_excerpt", "name": "lineno", "value": lineno},
                              {"type": "metric", "name": "reference_count",
                               "value": global_ref_count.get(name, 0)}],
                    tags=["abstraction", "dead-code", "s5"],
                    file=rel, symbol=name,
                ))

    return findings


# ── S6 — Contradiction bot ────────────────────────────────────────────────────

def run_s6_contradiction(
    repo: Path | str,
    run_id: Optional[str] = None,
    changed_files: Optional[list[str]] = None,
) -> list[dict]:
    """Detect conflicting constants and stale assumptions across files."""
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("contradiction", repo_str)
    bot = f"{_BOT_PREFIX}.contradiction"
    findings: list[dict] = []

    py_paths = _py_files(repo)
    if changed_files:
        changed_set = set(changed_files)
        py_paths = [p for p in py_paths if _rel(p, repo) in changed_set]
        if not py_paths:
            return findings

    constant_map: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for path in py_paths:
        rel = _rel(path, repo)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id.isupper() and len(tgt.id) >= 3:
                        if isinstance(node.value, ast.Constant):
                            val_str = repr(node.value.value)
                            constant_map[tgt.id][val_str].append(rel)

    for const_name, value_map in constant_map.items():
        if len(value_map) > 1:
            locs = {v: files for v, files in value_map.items()}
            first_files = [f for files in locs.values() for f in files[:1]]
            findings.append(_make(
                run_id=run_id, bot=bot, repo=repo_str,
                kind="contradiction",
                summary=f"constant '{const_name}' has {len(value_map)} distinct values across files",
                severity="medium", confidence=0.85,
                evidence=[{"type": "query", "name": "values", "value": ", ".join(list(locs.keys())[:4])}],
                tags=["contradiction", "constant", "s6"],
                file=first_files[0] if first_files else None,
                symbol=const_name,
                target_kind="concept", target_id=f"const:{const_name}",
            ))

    # stale_assumption: spec .md files that reference a constant value not matching code
    const_value_re = re.compile(r"`([A-Z_]{3,})\s*=\s*([^`\n]+)`")
    spec_dir = repo / "docs"
    if spec_dir.is_dir():
        for md_file in spec_dir.rglob("*.md"):
            rel_md = _rel(md_file, repo)
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for m in const_value_re.finditer(text):
                const_name, claimed_val = m.group(1), m.group(2).strip().strip("'\"")
                if const_name in constant_map:
                    code_vals = set(constant_map[const_name].keys())
                    if repr(claimed_val) not in code_vals and claimed_val not in code_vals:
                        findings.append(_make(
                            run_id=run_id, bot=bot, repo=repo_str,
                            kind="stale_assumption",
                            summary=f"doc claims `{const_name}={claimed_val}` but code has different value",
                            severity="low", confidence=0.6,
                            evidence=[{"type": "file_excerpt", "name": "claimed", "value": claimed_val[:100]}],
                            tags=["contradiction", "stale", "s6"],
                            file=rel_md, symbol=const_name,
                        ))

    return findings


# ── run_all ───────────────────────────────────────────────────────────────────

def run_all(
    repo: Path | str,
    graph: Optional[Any] = None,
    run_id: Optional[str] = None,
    changed_files: Optional[list[str]] = None,
) -> list[dict]:
    """Run S1–S6; S1 skipped when graph is None.

    When *changed_files* is provided, S5 and S6 restrict scope to those files
    for O(n) bounded performance on large repos.
    """
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = _run_id("all", repo_str)

    findings: list[dict] = []
    if graph is not None:
        findings.extend(run_s1_graph_anomaly(graph, repo=repo_str, run_id=run_id))
    findings.extend(run_s2_naming_bot(repo, run_id=run_id))
    findings.extend(run_s3_spec_drift(repo, run_id=run_id))
    findings.extend(run_s4_proof_gap(repo, run_id=run_id))
    findings.extend(run_s5_dead_abstraction(repo, run_id=run_id, changed_files=changed_files))
    findings.extend(run_s6_contradiction(repo, run_id=run_id, changed_files=changed_files))
    return findings
