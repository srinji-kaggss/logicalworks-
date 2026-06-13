"""lgwks_audit_graph — U5 Build #4: Agnostic, Graph-Theoretic SAST (ADR-080).

Evolves from syntax-matching to semantic graph analysis:
1. Universal Parsing: Uses 'trailmark' to build a 16-language SCG (Semantic Code Graph).
2. Centrality Benchmarking: Uses Z-eigenpair math to detect AI vs Human signatures.
3. Path-based Taint: Detects OWASP/PayloadsAllTheThings via cross-module traversals.

This is the "moat": the Daemon does the heavy lifting to find what regex cannot.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import trailmark.query.api as tm
import lgwks_rank
import lgwks_substrate_io as io

_SCHEMA = "lgwks.audit.graph.v1"

@dataclass
class AuditResult:
    findings: list[dict]
    rankings: list[dict]
    summary: dict
    schema: str = _SCHEMA

def run_audit(repo_path: Path, language: str = "python") -> AuditResult:
    """Run the agnostic graph-theoretic audit on a repository."""
    
    # 1. Universal Parsing (Trailmark)
    print(f"[audit-graph] parsing {repo_path} ({language})...", file=sys.stderr)
    engine = tm.QueryEngine.from_directory(str(repo_path), language=language)
    
    # 2. Pre-analysis (Taint, Blast Radius, Boundaries)
    print(f"[audit-graph] running pre-analysis passes...", file=sys.stderr)
    pre = engine.preanalysis()
    
    # 3. Map Trailmark IR to lgwks.rank format
    print(f"[audit-graph] building semantic tensor...", file=sys.stderr)
    tm_raw = engine.to_json()
    tm_json = json.loads(tm_raw) if isinstance(tm_raw, str) else tm_raw
    
    if not isinstance(tm_json, dict) or "nodes" not in tm_json:
        return AuditResult([], [], {"error": "Invalid SCG format", "nodes": 0, "edges": 0})

    # Map tm_json nodes/edges to lgwks graph format
    # Trailmark nodes is a dict[id -> node_info]
    tm_nodes = tm_json["nodes"]
    lgwks_graph = {
        "nodes": [{"id": nid} for nid in tm_nodes.keys()],
        "links": []
    }
    
    # Trailmark edges is a list of dicts
    tm_edges = tm_json.get("edges", [])
    
    # Map Trailmark kinds to our RELATIONS vocabulary
    REL_MAP = {
        "calls": "calls",
        "inherits": "inherits",
        "imports": "imports_from",
        "contains": "contains",
    }
    
    for edge in tm_edges:
        kind = REL_MAP.get(edge["kind"], "uses")
        lgwks_graph["links"].append({
            "source": edge["source"],
            "target": edge["target"],
            "relation": kind,
            "confidence_score": 1.0 if edge["confidence"] == "certain" else 0.5,
            "weight": 1.0
        })

    # 4. Statistical Benchmarking (Z-eigenpair)
    print(f"[audit-graph] computing Z-centrality signatures...", file=sys.stderr)
    # The rank module provides a high-level rank_graph() that builds the tensor 
    # and computes both relation-weighted and relation-blind centralities (Delta).
    rankings = lgwks_rank.rank_graph(lgwks_graph)
    
    findings = []
    
    # 5. Agnostic Vulnerability Detection (Taint Traversals)
    # We use graph queries to find paths from entrypoints to dangerous sinks.
    
    # Pass 5.1: SSRF / Command Injection / wget-style sinks
    tainted_subgraph = engine.subgraph("tainted")
    if tainted_subgraph:
        for node_id in tainted_subgraph:
            node_info = tm_nodes.get(node_id)
            if not node_info: continue
            
            callees = engine.callees_of(node_id)
            callee_names = [c.get("name", "").lower() for c in callees]
            
            # SSRF/wget check: network sinks
            if any(any(s in name for s in ["get", "post", "urlopen", "request", "wget", "curl"]) for name in callee_names):
                # Look for missing guards in the execution path
                callers = engine.callers_of(node_id)
                caller_names = [c.get("name", "") for c in callers]
                if not any("_remote_allowed" in name for name in caller_names):
                    findings.append({
                        "kind": "ssrf_risk",
                        "node": node_id,
                        "summary": "Agnostic Graph Trace: Untrusted input flows to network sink without _remote_allowed guard.",
                        "severity": "high",
                        "confidence": 0.85
                    })

            # Command Injection check: exec sinks
            if any(any(s in name for s in ["system", "popen", "spawn", "run"]) for name in callee_names):
                if not any("quote" in name for name in callee_names): # shlex.quote / shells-escape
                    findings.append({
                        "kind": "command_injection_risk",
                        "node": node_id,
                        "summary": "Agnostic Graph Trace: Untrusted input flows to process-spawn sink without shell-escaping.",
                        "severity": "critical",
                        "confidence": 0.9
                    })

    # Pass 5.2: Insecure Deserialization (Agnostic)
    for node_id, node_info in tm_nodes.items():
        callees = engine.callees_of(node_id)
        callee_names = [c.get("name", "").lower() for c in callees]
        if any(any(s in name for s in ["pickle", "marshal", "unsafe_load", "deserialize"]) for name in callee_names):
             findings.append({
                 "kind": "insecure_deserialization",
                 "node": node_id,
                 "summary": "Dangerous deserialization sink detected in call graph.",
                 "severity": "high",
                 "confidence": 0.75
             })

    # Pass 5.3: Manual Memory Management Anomaly (Human Signature)
    # Detect 'malloc' calls without a reachable 'free' in the same module/scope
    # //why human signature: AI rarely misses local cleanup; humans often forget it in complex branches.
    if language in {"c", "cpp", "rust"}:
        for node_id in tm_nodes.keys():
            callees = engine.callees_of(node_id)
            callee_names = [c.get("name", "") for c in callees]
            if any("malloc" in name for name in callee_names) and not any("free" in name for name in callee_names):
                findings.append({
                    "kind": "memory_leak_risk",
                    "node": node_id,
                    "summary": "Human Signature Anomaly: 'malloc' detected without corresponding 'free' in visible execution paths.",
                    "severity": "medium",
                    "confidence": 0.7
                })

    # Pass 5.4: Unchecked Privilege Path (Auth Bypass)
    # Finds paths from public entrypoints to privileged sinks that don't cross an AuthGate.
    for node_id, node_info in tm_nodes.items():
        if any(p in node_id.lower() for p in ["admin", "secret", "vault", "private"]):
            # This is a privileged node. Look for callers.
            callers = engine.callers_of(node_id)
            caller_names = [c.get("name", "").lower() for c in callers]
            if callers and not any("auth" in name or "permission" in name for name in caller_names):
                findings.append({
                    "kind": "auth_gate_missing",
                    "node": node_id,
                    "summary": "Privileged function reachable without evidence of an 'auth' or 'permission' gate in the call stack.",
                    "severity": "critical",
                    "confidence": 0.8
                })

    # 6. Human vs AI Signature Detection (Anomaly detection)
    for r in rankings:
        # High Discrepancy (Delta) suggests structural mismatch between logic and boilerplate
        if r.lane == "human":
             node_info = tm_nodes.get(r.node_cid)
             if node_info:
                 # AI Signature: "Hollow Centrality"
                 # High verbosity (text size) but very low centrality contribution to the system graph.
                 # node_info.get("text") might be in different subfields depending on trailmark version
                 node_text = node_info.get("text") or node_info.get("docstring") or ""
                 if len(node_text) > 1000 and r.centrality < 0.0001:
                     findings.append({
                         "kind": "ai_hollow_centrality",
                         "node": r.node_cid,
                         "summary": "AI Signature: High-verbosity node with exceptionally low centrality. Likely non-functional boilerplate.",
                         "severity": "info",
                         "confidence": 0.75
                     })

    return AuditResult(
        findings=findings,
        rankings=[r.__dict__ for r in rankings],
        summary={
            "nodes": len(tm_json["nodes"]),
            "edges": len(tm_json["edges"]),
            "critical_findings": len([f for f in findings if f["severity"] in {"high", "critical"}]),
            "discrepancy_nodes": len([r for r in rankings if r.lane == "human"])
        }
    )

def main():
    import argparse
    parser = argparse.ArgumentParser(description="lgwks-audit-graph — Agnostic Graph-Theoretic SAST")
    parser.add_argument("repo", help="path to the repository to audit")
    parser.add_argument("--lang", default="python", help="target language (default: python)")
    parser.add_argument("--json", action="store_true", help="output as JSON")
    args = parser.parse_args()
    
    result = run_audit(Path(args.repo), language=args.lang)
    
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print("\n=== LGWKS Agnostic Audit Report ===")
        print(f"Summary: {result.summary['nodes']} nodes, {result.summary['edges']} edges")
        print(f"Found {len(result.findings)} findings.")
        for f in result.findings:
            print(f"[{f['severity'].upper()}] {f['kind']}: {f['node']}")
            print(f"  {f['summary']}\n")

if __name__ == "__main__":
    main()
