"""lgwks_review — graph-aware, spec-bound code review.

Consumes `repo graph` structural context, git diff, and heuristics to produce a review
artifact. After review, proposes git actions (commit message, branch rename, PR creation)
based on the analysis. The human gate is preserved: `--yes` auto-executes read-only
proposals; mutating actions need explicit confirmation.

Wires the full bot fabric pipeline into a single `lgwks review` verb.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import lgwks_ui as ui
import lgwks_graph as graph_engine
from lgwks_repo import _git, _is_repo, repo_graph

_HEURISTIC_PATTERNS = {
    "trivial_assertion": re.compile(r"assert\s+\d+\s*==\s*\d+|assert\s+True|assert\s+False"),
    "hardcoded_secret": re.compile(r"api[_-]?key\s*=\s*['\"][^'\"]{8,}['\"]|password\s*=\s*['\"][^'\"]+['\"]|token\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
    "bare_except": re.compile(r"except\s*:\s*$|except\s+Exception\s*:\s*.*pass"),
    "missing_docstring": re.compile(r"^\s*(?:def|class)\s+\w+\([^)]*\):\s*\n\s+(?!['\"]|#)"),
    "print_debug": re.compile(r"\bprint\s*\(\s*(?:[\"']debug|TODO|FIXME|HACK)"),
    "todo_without_issue": re.compile(r"#\s*(TODO|FIXME|HACK)(?!\s*#\d+)"),
}

DEFAULT_PLAN = {
    "schema": "lgwks.bot.plan.v1",
    "plan_id": "default",
    "run_kind": "review",
    "target_repo": ".",
    "bots": [
        {"name": "code_hacker", "enabled": True},
        {"name": "slop_math", "enabled": True},
        {"name": "optimizer", "enabled": True},
        {"name": "stress", "enabled": True}
    ],
    "jepa": {"enabled": True},
    "synth": {"enabled": False, "optional": True},
    "policy": {
        "allow_external_research": False,
        "branch_state_mode": "per_branch",
        "max_artifact_bytes": 10485760,
        "l_budget": 0.15
    },
    "outputs": {"root": "findings/"}
}

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class ReviewFinding:
    file: str
    line: int
    check: str
    severity: str  # info | warn | danger
    message: str
    snippet: str = ""


@dataclass
class ReviewArtifact:
    schema: str = "lgwks.review.v0"
    files_changed: list[str] = field(default_factory=list)
    findings: list[ReviewFinding] = field(default_factory=list)
    graph_impact: list[dict[str, Any]] = field(default_factory=list)
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    commit_suggestion: str = ""


def _git_diff(repo: Path, ref: str = "HEAD") -> tuple[list[str], dict[str, str]]:
    """Return (files, file_to_diff). Default: staged vs HEAD."""
    rc, out = _git(repo, "diff", "--cached", "--name-only")
    files = [ln for ln in out.splitlines() if ln.strip()]
    if not files:
        # nothing staged — compare working tree vs HEAD
        rc, out = _git(repo, "diff", "--name-only")
        files = [ln for ln in out.splitlines() if ln.strip()]
    diffs: dict[str, str] = {}
    for f in files:
        rc, d = _git(repo, "diff", "--cached", "--", f) if (repo / f).exists() else _git(repo, "diff", "HEAD", "--", f)
        diffs[f] = d
    return files, diffs


def _heuristic_scan(path: Path, rel: str) -> list[ReviewFinding]:
    """Run static heuristics on a single file."""
    findings: list[ReviewFinding] = []
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return findings
    lines = source.splitlines()
    for check, pattern in _HEURISTIC_PATTERNS.items():
        for i, ln in enumerate(lines, start=1):
            if pattern.search(ln):
                findings.append(ReviewFinding(
                    file=rel, line=i, check=check,
                    severity="warn" if check in ("todo_without_issue", "missing_docstring", "print_debug") else "danger",
                    message=f"{check.replace('_', ' ')}", snippet=ln.strip()[:80],
                ))
    # AST-level checks
    if path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                if isinstance(node.test, ast.Compare):
                    left = node.test.left
                    comparators = node.test.comparators
                    if all(isinstance(n, ast.Constant) for n in [left] + comparators):
                        findings.append(ReviewFinding(
                            file=rel, line=getattr(node, "lineno", 0), check="trivial_assertion_ast",
                            severity="danger", message="assert compares constants — always true/false, not a real test",
                            snippet=lines[getattr(node, "lineno", 1)-1].strip()[:80],
                        ))
    return findings


def _impact_analysis(repo: Path, files: list[str], graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Cross-reference changed files with the codebase graph to find callers and analogs."""
    impacts: list[dict[str, Any]] = []
    file_set = set(files)

    try:
        g = graph_engine.get_graph(repo)
        for f in files:
            if f not in g.nodes:
                continue
            for caller in g.predecessors(f):
                if caller not in file_set:
                    impacts.append({
                        "kind": "caller",
                        "changed": f,
                        "caller": caller,
                        "note": f"{caller} imports from changed module {f}",
                    })
            impacted = g.reverse_deps(f, max_depth=2)
            for impacted_file in impacted:
                if impacted_file not in file_set and impacted_file not in {i["caller"] for i in impacts}:
                    impacts.append({
                        "kind": "transitive",
                        "changed": f,
                        "caller": impacted_file,
                        "note": f"{impacted_file} transitively depends on changed module {f}",
                    })
    except Exception:
        changed_modules = {f.replace("/", ".").replace(".py", "") for f in files if f.endswith(".py")}
        for edge in graph.get("edges", []):
            if edge.get("type") == "import" and edge.get("from") not in file_set:
                imp = edge.get("to", "")
                for cm in changed_modules:
                    if imp == cm or imp.startswith(cm + "."):
                        impacts.append({
                            "kind": "caller",
                            "changed": cm,
                            "caller": edge["from"],
                            "note": f"{edge['from']} imports from changed module {cm}",
                        })

    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for imp in impacts:
        key = imp["caller"] + "->" + imp["changed"]
        if key not in seen:
            seen.add(key)
            uniq.append(imp)
    return uniq


def _propose_git_actions(repo: Path, artifact: ReviewArtifact) -> list[dict[str, Any]]:
    """Based on review findings, propose concrete next git actions."""
    actions: list[dict[str, Any]] = []
    has_danger = any(f.severity == "danger" for f in artifact.findings)
    has_warn = any(f.severity == "warn" for f in artifact.findings)

    files = ", ".join(artifact.files_changed[:3])
    if has_danger:
        actions.append({
            "verb": "commit",
            "cmd": f'git commit -m "WIP: review findings on {files} (danger detected)"',
            "risk": "mutate",
            "reason": "danger findings present — do not ship without fixing",
        })
    else:
        actions.append({
            "verb": "commit",
            "cmd": f'git commit -m "review: {files}"',
            "risk": "mutate",
            "reason": "clean review — commit with descriptive message",
        })

    if artifact.graph_impact:
        actions.append({
            "verb": "warn",
            "cmd": "",
            "risk": "read",
            "reason": f"{len(artifact.graph_impact)} caller(s) may be affected — run tests before pushing",
        })

    if not has_danger and not has_warn:
        actions.append({
            "verb": "push",
            "cmd": "git push origin $(git branch --show-current)",
            "risk": "mutate",
            "reason": "review clean — safe to push",
        })

    return actions


def review_repo(repo: Path, ref: str = "HEAD") -> ReviewArtifact:
    """Run the legacy review pipeline."""
    files, diffs = _git_diff(repo, ref)
    artifact = ReviewArtifact(files_changed=files)

    for f in files:
        fpath = repo / f
        if fpath.exists() and fpath.is_file():
            artifact.findings.extend(_heuristic_scan(fpath, f))

    graph = repo_graph(repo)
    artifact.graph_impact = _impact_analysis(repo, files, graph)
    artifact.proposed_actions = _propose_git_actions(repo, artifact)

    scope = " · ".join(files[:3]) if files else "repo"
    if any(f.severity == "danger" for f in artifact.findings):
        artifact.commit_suggestion = f"review: fix {len([f for f in artifact.findings if f.severity=='danger'])} danger finding(s) in {scope}"
    else:
        artifact.commit_suggestion = f"review: {scope} — clean"

    return artifact


def _render_findings(findings: list[ReviewFinding]) -> list[str]:
    on = ui.color_on()
    out: list[str] = []
    for f in findings:
        color = ui.EMERALD if f.severity == "info" else (ui.AMBER if f.severity == "warn" else ui.RUST)
        out.append(ui.spine(ui.fg(f"  [{f.severity.upper()}] {f.file}:{f.line} — {f.message}", color, on=on), on=on))
        if f.snippet:
            out.append(ui.twig(f.snippet, 1, "proof", on=on))
    return out


def _generate_report_md(
    reduced: dict,
    built: dict,
    strength: dict,
    synth_status: str,
    l_score: float,
) -> str:
    critical_count = sum(1 for f in reduced["findings_normalized"] if f.get("severity") == "critical")
    high_count = sum(1 for f in reduced["findings_normalized"] if f.get("severity") == "high")
    medium_count = sum(1 for f in reduced["findings_normalized"] if f.get("severity") == "medium")
    low_count = sum(1 for f in reduced["findings_normalized"] if f.get("severity") == "low")

    date_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    md = f"""# Session Report — {date_str}

## Health radar
- **Critical anomalies**: {critical_count}
- **High anomalies**: {high_count}
- **Medium anomalies**: {medium_count}
- **Low anomalies**: {low_count}
- **L Score**: {l_score:.2f} (synth_status: {synth_status})
- **Contradictions**: {len(built["contradictions"])}

## Anomaly cards (top 8)
"""
    top_findings = {tf["finding_id"]: tf for tf in reduced["review_packet"]["top_findings"]}
    for card in built["human_summary"].get("anomaly_cards", [])[:8]:
        tf = top_findings.get(card["finding_id"], {})
        cmd = tf.get("command", "N/A")
        drill = card["drilldown_links"]
        loc = drill.get("file") or ""
        if drill.get("symbol"):
            loc += f":{drill['symbol']}"
        md += f"""
### {card['title']}
- **Severity**: {card['severity'].upper()}
- **Why it matters**: {card['why_it_matters']}
- **Drill-down**: {loc or 'N/A'}
- **Recommended command**: `{cmd}`
"""

    md += "\n## Sitemap\n"
    for cluster in reduced["clusters"]:
        md += f"\n### Cluster: {cluster['axis']} = {cluster['key']}\n"
        files_in_cluster = {}
        for fid in cluster["finding_ids"]:
            finding = next((f for f in reduced["findings_normalized"] if f["record_id"] == fid), None)
            if not finding:
                continue
            file_path = finding["links"].get("file") or finding["target"]["id"]
            if not file_path:
                continue
            sev = finding.get("severity", "info").lower()
            if file_path not in files_in_cluster:
                files_in_cluster[file_path] = {"count": 0, "max_severity": "info"}
            files_in_cluster[file_path]["count"] += 1
            current_rank = _SEVERITY_RANK.get(sev, 0)
            max_rank = _SEVERITY_RANK.get(files_in_cluster[file_path]["max_severity"], 0)
            if current_rank > max_rank:
                files_in_cluster[file_path]["max_severity"] = sev
        for path, info in sorted(files_in_cluster.items()):
            md += f"- `{path}`: {info['count']} finding(s), highest severity: **{info['max_severity'].upper()}**\n"

    md += "\n## Contradictions\n"
    if built["contradictions"]:
        for c in built["contradictions"]:
            md += f"""
### Subject: {c['subject']}
- **ID**: {c['id']}
- **Conflicting Claims**: Finding {c['finding_id']} (Evidence: {', '.join(c['evidence_refs'])})
- **Resolution Command**: `{c['recommended_resolution']}`
"""
    else:
        md += "No open contradictions detected.\n"

    md += "\n## Next actions\n"
    reads = list(reduced["review_packet"].get("recommended_next_reads", []))
    cmds = list(reduced["review_packet"].get("recommended_next_commands", []))
    for r in reads[:5]:
        md += f"- Read: `{r}`\n"
    for c in cmds[:5]:
        md += f"- Run: `{c}`\n"

    md += f"""
## L score
- **Coefficient**: {l_score:.2f}
- **Status**: {synth_status}
- **Interpretation**: A coefficient of {l_score:.2f} indicates that {l_score * 100:.1f}% of the claims in this report are inferred or synthesized by LLM reasoning layers.
"""
    return md


def run_watch_mode(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    print("Watching for .py file changes... Press Ctrl+C to exit.")
    
    mtimes = {}
    
    def _find_py_files() -> list[Path]:
        py_files = sorted(repo.glob("**/*.py"))
        return [p for p in py_files if not any(
            part in {".git", "__pycache__", ".venv", "venv", "node_modules", "findings"}
            for part in p.parts
        )]
        
    for p in _find_py_files():
        try:
            mtimes[p] = p.stat().st_mtime
        except Exception:
            pass
            
    import copy
    
    try:
        while True:
            time.sleep(1.0)
            changed = []
            current_files = _find_py_files()
            
            for p in current_files:
                try:
                    m = p.stat().st_mtime
                    if p not in mtimes:
                        mtimes[p] = m
                        changed.append(p)
                    elif m > mtimes[p]:
                        mtimes[p] = m
                        changed.append(p)
                except Exception:
                    pass
                    
            deleted = [p for p in mtimes if p not in current_files]
            for p in deleted:
                del mtimes[p]
                
            if changed:
                rel_paths = [str(p.relative_to(repo)) for p in changed]
                print(f"\nChange detected: {', '.join(rel_paths)}. Running review...")
                sub_args = copy.copy(args)
                sub_args.watch = False
                sub_args.changed = ",".join(rel_paths)
                review_command(sub_args)
                print("\nWatching for .py file changes... Press Ctrl+C to exit.")
    except KeyboardInterrupt:
        print("\nExited watch mode.")
        return 0


def review_command(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo", ".")).resolve()
    if not _is_repo(repo):
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 3

    if getattr(args, "watch", False):
        return run_watch_mode(args)

    plan_path = repo / ".lgwks" / "bot-plan.json"
    if plan_path.exists():
        try:
            with plan_path.open("r", encoding="utf-8") as f:
                plan = json.load(f)
            import lgwks_project_artifacts as artifacts
            ok, errs = artifacts.validate_bot_plan(plan)
            if not ok:
                plan = DEFAULT_PLAN
        except Exception:
            plan = DEFAULT_PLAN
    else:
        plan = DEFAULT_PLAN

    if getattr(args, "bots", "") and args.bots != "all":
        requested_bots = [b.strip() for b in args.bots.split(",")]
        for p_bot in plan["bots"]:
            p_bot["enabled"] = p_bot["name"] in requested_bots

    if getattr(args, "synth", False):
        plan["synth"]["enabled"] = True

    if getattr(args, "l_budget", None) is not None:
        plan["policy"]["l_budget"] = float(args.l_budget)

    changed_files = None
    if getattr(args, "changed", ""):
        changed_files = [f.strip() for f in args.changed.split(",") if f.strip()]
    elif getattr(args, "ref", "") != "HEAD":
        files, _ = _git_diff(repo, args.ref)
        changed_files = files

    # 1. Load or refresh graph
    try:
        graph = graph_engine.get_graph(repo)
    except Exception:
        graph = None

    # 2. Run selected bots
    all_findings = []
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_id = f"run:{ts}:" + hashlib.sha256(str(repo).encode()).hexdigest()[:8]

    # Legacy static check findings map to BOT_RECORD_SCHEMA
    legacy_artifact = review_repo(repo, getattr(args, "ref", "HEAD"))
    for f in legacy_artifact.findings:
        all_findings.append({
            "schema": "lgwks.bot.record.v1",
            "run_id": run_id,
            "bot": "review",
            "target": {"kind": "file", "id": f.file},
            "kind": f.check,
            "summary": f.message,
            "severity": f.severity,
            "confidence": 1.0,
            "status": "open",
            "evidence": [{"type": "file_excerpt", "name": f.check, "value": f.snippet}],
            "links": {
                "repo": str(repo),
                "file": f.file,
                "symbol": None,
                "tests": [],
                "artifacts": [],
            },
            "world_refs": [{"kind": "concept", "id": f.check}],
            "tags": ["review", "static-heuristic"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    for p_bot in plan["bots"]:
        if not p_bot["enabled"]:
            continue
        bot_name = p_bot["name"]
        if bot_name == "code_hacker":
            import lgwks_bot_code_hacker as hacker
            try:
                hacker_findings = hacker.run(repo, changed_files=changed_files, run_id=run_id)
                all_findings.extend(hacker_findings)
            except Exception as exc:
                print(f"warning: code_hacker bot failed: {exc}", file=sys.stderr)
        elif bot_name == "slop_math":
            import lgwks_bot_slop_math as slop
            try:
                slop_findings = slop.run_all(repo, graph=graph, run_id=run_id)
                if changed_files:
                    changed_set = set(changed_files)
                    slop_findings = [
                        f for f in slop_findings
                        if (f["links"].get("file") in changed_set) or (f["target"]["id"] in changed_set)
                    ]
                all_findings.extend(slop_findings)
            except Exception as exc:
                print(f"warning: slop_math bot failed: {exc}", file=sys.stderr)
        elif bot_name == "optimizer":
            try:
                import lgwks_bot_optimizer as optimizer
                opt_findings = optimizer.run(repo, changed_files=changed_files, graph=graph, run_id=run_id)
                all_findings.extend(opt_findings)
            except (ImportError, AttributeError):
                pass
        elif bot_name == "stress":
            try:
                import lgwks_bot_stress as stress
                stress_findings = stress.run(repo, store_path=str(repo / "findings/"), run_id=run_id)
                all_findings.extend(stress_findings)
            except (ImportError, AttributeError):
                pass

    # 3. Reduce findings (U3)
    import lgwks_project_artifacts as artifacts
    bc_metrics = {}
    if graph:
        try:
            bc = graph.betweenness_centrality()
            bc_metrics = {k: {"blast_radius": v, "betweenness": v} for k, v in bc.items()}
        except Exception:
            pass

    reduced = artifacts.reduce_bot_records(all_findings, repo_graph_metrics=bc_metrics)

    # 4. Build JEPA package (U4)
    world_db_bindings = []
    for f in reduced.get("findings_normalized", []):
        for ref in f.get("world_refs", []):
            world_db_bindings.append(f"wdb:{ref['kind']}:{ref['id']}")
    world_db_bindings = list(set(world_db_bindings))

    built = artifacts.build_jepa_package(
        reduced,
        repo=str(repo),
        plan_id=f"plan:{plan.get('plan_id', 'default')}",
        world_db_bindings=world_db_bindings,
        prior_package_refs=[],
    )

    # 5. Check artifact strength (U11)
    synth_status = "skipped"
    strength = artifacts.evaluate_artifact_strength(
        reduced["review_packet"],
        built["package"],
        built["machine_packet"],
        built["links_index"],
        synth_status=synth_status,
    )

    # 6. Optionally run synthesizer (U9) if --synth and strength passes
    l_score = 0.0
    invented_claim_count = 0
    l_budget = plan["policy"].get("l_budget", 0.15)
    machine_packet = built["machine_packet"]
    if plan["synth"]["enabled"] and strength["pass"]:
        try:
            import lgwks_synthesizer
            synth_input = {
                "schema": "lgwks.synth.input.v1",
                "package_id": built["package"]["package_id"],
                "ranked_findings": reduced["review_packet"]["top_findings"],
                "clusters": reduced["clusters"],
                "contradictions": reduced["review_packet"]["open_contradictions"],
                "recommended_reads": reduced["review_packet"]["recommended_next_reads"],
                "repo": str(repo),
                "l_budget": l_budget,
            }
            synth_res = lgwks_synthesizer.run_synthesis(synth_input, strength_gate=strength)
            if "synth_status" in synth_res:
                synth_status = synth_res["synth_status"]
            else:
                synth_status = "success"
                l_score = synth_res.get("l_score", 0.0)
                claims = synth_res.get("claims", [])
                invented_claim_count = len([c for c in claims if c.get("origin_type") == "invented"])
                machine_packet.update({
                    "reasoning": synth_res.get("reasoning", []),
                    "next_actions": synth_res.get("next_actions", []),
                    "claims": claims,
                })
        except Exception as exc:
            print(f"warning: synthesis failed: {exc}", file=sys.stderr)
            synth_status = "unavailable"

    out_root = repo / plan["outputs"].get("root", "findings/")
    out_root.mkdir(parents=True, exist_ok=True)

    machine_packet.update({
        "l_score": l_score,
        "l_budget_used": f"{int(round((l_score / l_budget) * 100)) if l_budget else 0}%",
        "session_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grounded_claim_count": len(reduced["findings_normalized"]),
        "invented_claim_count": invented_claim_count,
        "synth_status": synth_status,
    })

    report_md = _generate_report_md(reduced, built, strength, synth_status, l_score)
    (out_root / "report.md").write_text(report_md, encoding="utf-8")
    (out_root / "machine-packet.json").write_text(json.dumps(machine_packet, indent=2), encoding="utf-8")

    if getattr(args, "json", False):
        print(json.dumps(machine_packet, indent=2))
        return 0

    print(f"L score: {l_score:.2f}")

    on = ui.color_on()
    out = [""]
    out += ui.band("lgwks · review", f"{len(legacy_artifact.files_changed)} file(s) changed", on=on)
    out.append(ui.spine(on=on))
    out.append(ui.spine(ui.fg(f"Health: {'PASS' if strength['pass'] else 'DEGRADED'}", ui.CREAM_DIM, on=on), on=on))
    out.append(ui.spine(ui.fg(f"Findings: {len(reduced['findings_normalized'])} reduced anomalies", ui.CREAM_DIM, on=on), on=on))

    top_findings_map = {tf["finding_id"]: tf for tf in reduced["review_packet"]["top_findings"]}
    for idx, card in enumerate(built["human_summary"].get("anomaly_cards", [])[:5], start=1):
        color = ui.RUST if card["severity"] in ("critical", "high") else ui.AMBER
        out.append(ui.spine(ui.fg(f"  [{card['severity'].upper()}] {card['title']}", color, on=on), on=on))
        out.append(ui.twig(card["why_it_matters"], 1, "card", on=on))
        tf = top_findings_map.get(card["finding_id"], {})
        cmd = tf.get("command")
        if cmd:
            out.append(ui.twig(f"command: {cmd}", 2, "cmd", on=on))
        drill = card["drilldown_links"]
        loc = drill.get("file") or ""
        if drill.get("symbol"):
            loc += f":{drill['symbol']}"
        if loc:
            out.append(ui.twig(f"drilldown: {loc}", 2, "link", on=on))

    out.append(""); out.append("  " + ui.footer("lgwks · review", on=on)); out.append("")
    print("\n".join(out))

    has_high = any(f["severity"] in ("high", "critical") for f in reduced["findings_normalized"])
    if has_high:
        return 1
    if not strength["pass"]:
        return 2
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("review", help="graph-aware code review + proposed git actions")
    p.add_argument("--repo", default=".", help="path to repo")
    p.add_argument("--ref", default="HEAD", help="diff against this ref")
    p.add_argument("--json", action="store_true", help="structured output")
    p.add_argument("--yes", action="store_true", help="auto-accept read-only proposals")
    p.add_argument("--bots", default="all", help="comma-separated list of bots: code_hacker,slop_math,optimizer,stress")
    p.add_argument("--changed", default="", help="comma-separated relative file paths for subset mode")
    p.add_argument("--synth", action="store_true", help="run synthesizer after packaging")
    p.add_argument("--l-budget", type=float, default=0.15, help="max allowed L budget coefficient")
    p.add_argument("--watch", action="store_true", help="watch for file changes and run review on subset")
    p.set_defaults(func=review_command)
