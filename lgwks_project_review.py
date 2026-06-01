"""
lgwks_project_review — `lgwks project review` verb.

Reads the deploy artifact set, computes a small summary suitable for
both human and machine consumers, and optionally renders a human
projection.

Spec (round-1, lgwks_project.py split, refactor/project-split):
  L0 intent: split review off the monolith; preserve review_project,
    review_command, and _render_review at the lgwks_project module
    level (via the shim) so the existing tests keep working.
  L1 reality gap: review reads artifacts from disk; the path
    resolution uses _deploy_path (re-exported from the deploy module
    via the shim).
  L4 invariant: review dict schema unchanged (chain_ok, cycles,
    token_status, etc.); _render_review output line-set unchanged.
  L5 industry parallel: command module — one verb per file.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import lgwks_cycle

from lgwks_project_artifacts import MAPPER_ROLE_COUNT
from lgwks_project_deploy import _deploy_path


def review_project(project: str) -> dict:
    out_dir = _deploy_path(project)
    chain = lgwks_cycle.verify_cycles(out_dir / "cycles.jsonl")
    cycles = lgwks_cycle.read_jsonl(out_dir / "cycles.jsonl")
    tokens = lgwks_cycle.read_jsonl(out_dir / "token-ledger.jsonl")
    critics = lgwks_cycle.read_jsonl(out_dir / "critic-records.jsonl")
    learning = lgwks_cycle.read_jsonl(out_dir / "learning-records.jsonl")
    lineage = lgwks_cycle.read_jsonl(out_dir / "model-lineage.jsonl")
    packets = lgwks_cycle.read_jsonl(out_dir / "machine-packets.jsonl")
    edges = lgwks_cycle.read_jsonl(out_dir / "graph-edges.jsonl")
    sources = lgwks_cycle.read_jsonl(out_dir / "source-records.jsonl")
    events = lgwks_cycle.read_jsonl(out_dir / "execution-events.jsonl")
    artifact_embeddings = lgwks_cycle.read_jsonl(out_dir / "artifact-embeddings.jsonl")
    model_state_path = out_dir / "model_state.json"
    model_state = json.loads(model_state_path.read_text(encoding="utf-8")) if model_state_path.exists() else {}
    operator_path = out_dir / "operator-profile.json"
    operator_profile = json.loads(operator_path.read_text(encoding="utf-8")) if operator_path.exists() else {}
    vector_path = out_dir / "vector-vault.json"
    vector_vault = json.loads(vector_path.read_text(encoding="utf-8")) if vector_path.exists() else {}
    worker_map_path = out_dir / "worker-map.json"
    worker_map = json.loads(worker_map_path.read_text(encoding="utf-8")) if worker_map_path.exists() else {}

    bias_counts: Counter[str] = Counter()
    unsupported: list[str] = []
    for rec in critics:
        for plane, rows in rec.get("bias", {}).items():
            bias_counts[plane] += len(rows)
        if rec.get("label") == "unsupported":
            unsupported.append(rec.get("claim_id", ""))
    export_policies = sorted({r.get("export_policy", r.get("consent", "")) for r in learning if r})
    event_counts = dict(sorted(Counter(e.get("status", "unknown") for e in events).items()))
    return {
        "schema": "lgwks-project-review/1",
        "project": project,
        "path": str(out_dir),
        "chain_ok": chain["chain_ok"],
        "chain_head": chain["chain_head"],
        "cycles": chain["cycles"],
        "token_spend": sum(int(t.get("estimated_tokens", 0)) for t in tokens),
        "token_status": "over" if any(t.get("token_status") == "over" for t in tokens) else "ok",
        "bias_counts": dict(sorted(bias_counts.items())),
        "unsupported_claims": [u for u in unsupported if u],
        "rollback_ref": model_state.get("champion", {}).get("id", ""),
        "learning_export_policy": export_policies,
        "model_lineage_count": len(lineage),
        "machine_packets": len(packets),
        "graph_edges": len(edges),
        "source_records": len(sources),
        "execution_status_counts": event_counts,
        "vector_vault_status": vector_vault.get("status", "missing"),
        "vector_records": vector_vault.get("records", 0),
        "artifact_embeddings": len(artifact_embeddings),
        "max_concurrent_workers": worker_map.get("max_concurrent_workers", 0),
        "active_worker_slots": len(worker_map.get("active_slots", [])),
        "worker_api_key_policy": worker_map.get("api_key_policy", ""),
        "operator_profile": operator_profile.get("profile_id", ""),
        "one_command_replaces_many": operator_profile.get("stance", {}).get("one_command_replaces_many", False),
        "build_on_existing_work": operator_profile.get("stance", {}).get("build_on_existing_work", False),
        "machine_native": True,
        "human_surface_is_projection": True,
        "error": chain.get("error", ""),
    }


def _render_review(review: dict) -> str:
    lines = [
        f"project {review['project']}",
        f"chain {'ok' if review['chain_ok'] else 'broken'} · cycles {review['cycles']} · tokens {review['token_status']} ({review['token_spend']})",
        f"sources {review['source_records']} · vector {review['vector_vault_status']} ({review['vector_records']} records)",
        f"artifact embeddings {review.get('artifact_embeddings', 0)} · workers {review.get('active_worker_slots', 0)}/{review.get('max_concurrent_workers', MAPPER_ROLE_COUNT)}",
        f"machine packets {review['machine_packets']} · graph edges {review['graph_edges']} · lineage {review['model_lineage_count']}",
        f"operator one-command={str(review['one_command_replaces_many']).lower()} build-on-existing={str(review['build_on_existing_work']).lower()}",
        f"rollback {review['rollback_ref'] or 'none'}",
    ]
    if review["unsupported_claims"]:
        lines.append("unsupported " + ", ".join(review["unsupported_claims"]))
    if review["execution_status_counts"]:
        counts = ", ".join(f"{k}:{v}" for k, v in review["execution_status_counts"].items())
        lines.append("execution " + counts)
    return "\n".join(lines)


def review_command(args: argparse.Namespace) -> int:
    review = review_project(args.project)
    if getattr(args, "render", False):
        print(_render_review(review))
    else:
        print(json.dumps(review, indent=2, sort_keys=True))
    return 0
