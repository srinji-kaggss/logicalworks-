"""lgwks_audit_graph — U5 Build #5: The Liquid Brain (ADR-sast-003).

Evolves from graph analysis to biological-flow modeling (MATH-ML-LLM):
1. Math Substrate (The Reflex): Z-eigenpair centrality over tubule nodes.
2. ML Reflex (The Habituation): Detecting Sclerotium Density (AI slop) and 
   Synaptic Tagging Mismatch (Human resource leaks).
3. LLM Subconscious (The Anti-Thinker): Escalated reasoning on abstract topology.

Strict 0-trust isolation: LLM never sees raw primitives; Math owns the gates.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_rank
from lgwks_bot_code_hacker import _NET_SINK_ATTRS, _SUBPROCESS_ATTRS, _EXEC_ATTRS

try:
    import trailmark.query.api as tm
except ImportError:
    tm: Any = None

_SCHEMA = "lgwks.audit.graph.v2"
_NET_COMMANDS = frozenset({"wget", "curl"})
_SAFE_GUARDS = frozenset({"_remote_allowed"})
_ESCAPE_FUNCS = frozenset({"quote"})

@dataclass
class AuditResult:
    findings: list[dict]
    rankings: list[dict]
    summary: dict
    escalation_required: bool = False
    schema: str = _SCHEMA


def _callee_leaf(name: str) -> str:
    """Return the callable leaf from a Trailmark callee name.

    Trailmark can surface names as `requests.get`, `subprocess.run`, or bare
    symbols. Matching on the final segment preserves dotted-attribute support
    without substring false positives like `forget` -> `get`.
    """
    return name.rsplit(".", 1)[-1].lower()


def _has_callee(callee_names: list[str], names: set[str] | frozenset[str]) -> bool:
    wanted = {name.lower() for name in names}
    return any(_callee_leaf(name) in wanted for name in callee_names)


def _has_guard(caller_names: list[str]) -> bool:
    return _has_callee(caller_names, _SAFE_GUARDS)


def _has_escape(callee_names: list[str]) -> bool:
    return _has_callee(callee_names, _ESCAPE_FUNCS)


def run_audit(repo_path: Path, language: str = "python", escalated: bool = False) -> AuditResult:
    """Run the agnostic Liquid Brain audit on a repository."""
    if tm is None:
        raise RuntimeError("trailmark is required for lgwks_audit_graph.run_audit")
    
    # 1. Universal Parsing (Trailmark)
    print(f"[liquid-brain] thickening tubules in {repo_path} ({language})...", file=sys.stderr)
    engine = tm.QueryEngine.from_directory(str(repo_path), language=language)
    
    # 2. Pre-analysis (The 'Sodium Ion Channels' — Taint and Boundaries)
    print(f"[liquid-brain] establishing membrane potential (pre-analysis)...", file=sys.stderr)
    engine.preanalysis()  # side effect: establishes taint/boundary state on the engine
    tm_json = json.loads(engine.to_json())
    tm_nodes = tm_json["nodes"]
    tm_edges = tm_json.get("edges", [])

    # 3. Statistical Benchmarking (The 'Flow reinforcement' — Z-eigenpair)
    print(f"[liquid-brain] reinforcing flow paths...", file=sys.stderr)
    lgwks_graph = {
        "nodes": [{"id": nid} for nid in tm_nodes.keys()],
        "links": []
    }
    REL_MAP = {"calls": "calls", "inherits": "inherits", "imports": "imports_from", "contains": "contains"}
    for edge in tm_edges:
        kind = REL_MAP.get(edge["kind"], "uses")
        lgwks_graph["links"].append({
            "source": edge["source"], "target": edge["target"], "relation": kind,
            "confidence_score": 1.0 if edge["confidence"] == "certain" else 0.5, "weight": 1.0
        })

    rankings = lgwks_rank.rank_graph(lgwks_graph)
    findings = []

    # ── Tier 1: The Math Gate (Behavioral Aversion) ─────────────────────────
    # Detect absolute aversion stimuli (SSRF/SQLi/wget)
    tainted_subgraph = engine.subgraph("tainted")
    if tainted_subgraph:
        for node_id in tainted_subgraph:
            callees = engine.callees_of(node_id)
            callee_names = [c.get("name", "").lower() for c in callees]
            
            # Aversion 1: Sodium Leak (Unchecked Network/wget/curl)
            if _has_callee(callee_names, _NET_SINK_ATTRS | _NET_COMMANDS):
                callers = engine.callers_of(node_id)
                caller_names = [c.get("name", "") for c in callers]
                if not _has_guard(caller_names):
                    findings.append({
                        "kind": "aversion_sodium_leak",
                        "node": node_id,
                        "summary": "Math Gate: Untrusted flow to external sink without _remote_allowed channel.",
                        "severity": "high", "confidence": 1.0
                    })

            # Aversion 2: Command Detonation
            if _has_callee(callee_names, _EXEC_ATTRS | _SUBPROCESS_ATTRS):
                if not _has_escape(callee_names):
                    findings.append({
                        "kind": "aversion_cmd_detonation",
                        "node": node_id,
                        "summary": "Math Gate: Untrusted flow to shell without escaping.",
                        "severity": "critical", "confidence": 1.0
                    })

    # ── Tier 2: The ML Reflex (Habituation Anomaly) ─────────────────────────
    # Detect structural signatures (AI slop / Human leaks)
    for r in rankings:
        if r.lane == "human":
            node_info = tm_nodes.get(r.node_cid)
            if node_info:
                node_text = node_info.get("text") or node_info.get("docstring") or ""
                # Anomaly: Sclerotium Density (AI Slop)
                # Massive text block but zero flow reinforcement (centrality).
                if len(node_text) > 2000 and r.centrality < 0.00001:
                    findings.append({
                        "kind": "anomaly_sclerotium_density",
                        "node": r.node_cid,
                        "summary": "ML Reflex: High-density sclerotium detected (likely non-functional AI slop).",
                        "severity": "info", "confidence": 0.8
                    })

    # Anomaly: Synaptic Tagging Mismatch (Human Resource Leak)
    if language in {"c", "cpp", "rust"}:
        for node_id in tm_nodes.keys():
            callees = engine.callees_of(node_id)
            callee_names = [c.get("name", "") for c in callees]
            if _has_callee(callee_names, {"malloc"}) and not _has_callee(callee_names, {"free"}):
                findings.append({
                    "kind": "anomaly_tagging_mismatch",
                    "node": node_id,
                    "summary": "ML Reflex: Resource allocation tubule lacks a convergent cleanup edge (Human signature).",
                    "severity": "medium", "confidence": 0.7
                })

    # ── Tier 3: The LLM Subconscious (Anti-Thinker Escalation) ─────────────
    # Only invoked if Tier 1/2 indicate high uncertainty (Delta discrepancy)
    risk_potential = sum(f["confidence"] for f in findings if f["severity"] in {"high", "critical"})
    anomaly_potential = len([f for f in findings if "anomaly" in f["kind"]])
    needs_escalation = risk_potential > 0 or anomaly_potential > 0
    tier3_status = "not_required"
    
    if needs_escalation and escalated:
        # Tier 3 is a seam until a Host Adapter exists. Do not emit a finding:
        # no analysis occurred, so a finding would be fabricated evidence.
        print("[liquid-brain] Tier 3 requested; Host Adapter not configured.", file=sys.stderr)
        tier3_status = "adapter_not_configured"
    elif needs_escalation:
        tier3_status = "not_requested"

    return AuditResult(
        findings=findings,
        rankings=[r.__dict__ for r in rankings],
        summary={
            "nodes": len(tm_nodes),
            "edges": len(tm_edges),
            "critical_aversions": len([f for f in findings if f["severity"] in {"high", "critical"}]),
            "anomalies": len([f for f in findings if "anomaly" in f["kind"]]),
            "risk_potential": risk_potential,
            "tier3_status": tier3_status
        },
        escalation_required=needs_escalation
    )

def main():
    import argparse
    parser = argparse.ArgumentParser(description="lgwks-audit-graph — The Liquid Brain SAST")
    parser.add_argument("repo", help="path to the repository to audit")
    parser.add_argument("--lang", default="python", help="target language")
    parser.add_argument("--escalate", action="store_true", help="trigger Tier 3 escalated reasoning")
    parser.add_argument("--json", action="store_true", help="output as JSON")
    args = parser.parse_args()
    
    result = run_audit(Path(args.repo), language=args.lang, escalated=args.escalate)
    
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print("\n=== LGWKS Liquid Brain Audit Report ===")
        print(f"Summary: {result.summary['nodes']} tubules, {result.summary['edges']} flow edges")
        print(f"Found {len(result.findings)} behavioral signals.")
        for f in result.findings:
            print(f"[{f['severity'].upper()}] {f['kind']}: {f['node']}")
            print(f"  {f['summary']}\n")
        
        if result.escalation_required and not args.escalate:
            print("ESCALATION REQUIRED: aversions or anomalies detected. Run with --escalate to request Tier 3.")
        elif result.summary.get("tier3_status") == "adapter_not_configured":
            print("Tier 3 requested, but no Host Adapter is configured; no escalated finding was emitted.")

if __name__ == "__main__":
    main()
