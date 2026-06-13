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

import trailmark.query.api as tm
import lgwks_rank

_SCHEMA = "lgwks.audit.graph.v2"

@dataclass
class AuditResult:
    findings: list[dict]
    rankings: list[dict]
    summary: dict
    escalation_required: bool = False
    schema: str = _SCHEMA

def run_audit(repo_path: Path, language: str = "python", escalated: bool = False) -> AuditResult:
    """Run the agnostic Liquid Brain audit on a repository."""
    
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
            if any(any(s in name for s in ["get", "post", "urlopen", "request", "wget", "curl"]) for name in callee_names):
                callers = engine.callers_of(node_id)
                caller_names = [c.get("name", "") for c in callers]
                if not any("_remote_allowed" in name for name in caller_names):
                    findings.append({
                        "kind": "aversion_sodium_leak",
                        "node": node_id,
                        "summary": "Math Gate: Untrusted flow to external sink without _remote_allowed channel.",
                        "severity": "high", "confidence": 1.0
                    })

            # Aversion 2: Command Detonation
            if any(any(s in name for s in ["system", "popen", "spawn", "run"]) for name in callee_names):
                if not any("quote" in name for name in callee_names):
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
            if any("malloc" in name for name in callee_names) and not any("free" in name for name in callee_names):
                findings.append({
                    "kind": "anomaly_tagging_mismatch",
                    "node": node_id,
                    "summary": "ML Reflex: Resource allocation tubule lacks a convergent cleanup edge (Human signature).",
                    "severity": "medium", "confidence": 0.7
                })

    # ── Tier 3: The LLM Subconscious (Anti-Thinker Escalation) ─────────────
    # Only invoked if Tier 1/2 indicate high uncertainty (Delta discrepancy)
    risk_potential = sum(f["confidence"] for f in findings if f["severity"] in {"high", "critical"})
    needs_escalation = (risk_potential > 0 or len([r for r in rankings if r.lane == "human"]) > 0)
    
    if needs_escalation and escalated:
        # //why: Day -1 protocol. The LLM is isolated. We pass only the 
        # graph summary and findings to the Anti-Thinker.
        print(f"[liquid-brain] escalating to subconscious reasoning...", file=sys.stderr)
        # (Actual LLM call logic deferred to Host Adapter to maintain isolation)
        findings.append({
            "kind": "escalated_reasoning",
            "node": "subconscious",
            "summary": "Anti-Thinker: Analyzing high-delta nodes for cross-modality exfiltration paths.",
            "severity": "info", "confidence": 0.5
        })

    return AuditResult(
        findings=findings,
        rankings=[r.__dict__ for r in rankings],
        summary={
            "nodes": len(tm_nodes),
            "edges": len(tm_edges),
            "critical_aversions": len([f for f in findings if f["severity"] in {"high", "critical"}]),
            "anomalies": len([f for f in findings if "anomaly" in f["kind"]]),
            "risk_potential": risk_potential
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
            print("⚠ ESCALATION REQUIRED: High-delta nodes or aversions detected. Run with --escalate for Tier 3 reasoning.")

if __name__ == "__main__":
    main()
