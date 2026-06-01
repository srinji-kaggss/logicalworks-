"""
lgwks_project — one-prompt project orchestrator front door.

This is the identify/spec half of the end-state. It turns a prompt into a
bounded worker plan the deploy loop can run later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

import lgwks_cycle

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT / "store" / "project-plans"
DEPLOY_ROOT = ROOT / "store" / "project-deploy"

DEFAULT_REASONING_CYCLES = 5
DEFAULT_EMBEDDING_ROUNDS = 400
DEFAULT_WORKERS = 4
DEFAULT_TOKENS = 8000
ACADEMIC_SOURCES = ["openalex", "crossref", "openverse"]
DEFAULT_WEIGHT = {
    "retrieval": 0.35,
    "evidence_quality": 0.25,
    "novelty": 0.15,
    "contradiction": 0.15,
    "license_safety": 0.10,
}


def _slug(value: str) -> str:
    safe = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip(".-") or "project"
    return f"{safe}-{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def _terms(text: str) -> list[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9_+\-.]{2,}", text.lower())
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "your", "map"}
    seen, out = set(), []
    for tok in toks:
        if tok in stop or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out[:24]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clamp(value: int, default: int, low: int, high: int) -> int:
    value = default if value is None else value
    return max(low, min(high, value))


def build_plan(args: argparse.Namespace) -> dict:
    project = args.project
    prompt = args.prompt or project
    reasoning_cycles = _clamp(args.reasoning_cycles, DEFAULT_REASONING_CYCLES, 1, 50)
    embedding_rounds = _clamp(args.embedding_rounds, DEFAULT_EMBEDDING_ROUNDS, 1, 10_000)
    max_workers = _clamp(args.max_workers, DEFAULT_WORKERS, 1, 16)
    tokens_per_cycle = _clamp(args.tokens_per_cycle, DEFAULT_TOKENS, 1000, 200_000)
    keywords = _terms(prompt)
    plan_id = _slug(project + "\n" + prompt)
    branch_workers = [
        {"id": "seed", "role": "derive source set and hypotheses", "max_commands": 2},
        {"id": "academic", "role": "query open scholarly/public indexes", "sources": ACADEMIC_SOURCES},
        {"id": "authorized", "role": "crawl keychain/session hosts only; append needs_auth on miss"},
        {"id": "embed", "role": "run vector vault rounds", "rounds": embedding_rounds},
        {"id": "critic", "role": "score evidence, contradiction, license, novelty"},
        {"id": "frontier", "role": "emit next command set within budget"},
    ]
    return {
        "schema": "lgwks-project-plan/1",
        "plan_id": plan_id,
        "project": project,
        "prompt": prompt,
        "created_at": time.time(),
        "mode": "identify-spec",
        "budgets": {
            "reasoning_cycles": reasoning_cycles,
            "embedding_rounds": embedding_rounds,
            "max_workers": max_workers,
            "tokens_per_cycle": tokens_per_cycle,
            "defaulted_reasoning_cycles": args.reasoning_cycles is None,
        },
        "machine_weight": DEFAULT_WEIGHT,
        "frontier_techniques": ["RAG", "ReAct", "Self-RAG", "HyDE-style query expansion", "champion-challenger rollback"],
        "keywords": keywords,
        "branch_workers": branch_workers[:max_workers] if max_workers < len(branch_workers) else branch_workers,
        "next_commands": [
            ["lgwks", "memory", "init", project, "--site", args.site or "open-public-sources", "--goal", prompt],
            ["lgwks", "public", " ".join(keywords[:8]) or prompt, "--source", "all", "--limit", "10"],
            ["lgwks", "embed", args.folder or ".", "--project", project, "--keywords", ", ".join(keywords[:12]),
             "--cycles", "0", "--max-cycles", str(min(embedding_rounds, 400))],
            ["lgwks", "memory", "context", project, "--query", " ".join(keywords[:8])],
        ],
        "deploy_missing": [
            "worker queue with leases",
            "semantic embedding provider beside deterministic vectors",
            "critic held-out eval set",
            "champion/challenger snapshot promotion",
            "token ledger enforcement",
        ],
        "whimsy": {
            "instrument": "frontier compass",
            "clock": "turn back to last champion if challenger drifts",
            "surface": "show the math, but let the dashboard breathe",
        },
    }


def plan_command(args: argparse.Namespace) -> int:
    plan = build_plan(args)
    out_dir = PROJECT_ROOT / plan["plan_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "plan.json"
    path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    plan["path"] = str(path)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _jsonl(path: Path, rows: list[dict]) -> None:
    lgwks_cycle.write_jsonl(path, rows)


def _deploy_path(project: str) -> Path:
    return lgwks_cycle.deploy_dir(DEPLOY_ROOT, project)


def _worker_leases(project: str, chain_head: str, tokens_per_cycle: int, max_workers: int) -> list[dict]:
    workers = [
        ("seed-001", "seed_hypotheses", ["memory", "public"]),
        ("academic-001", "neutral_academic", ["openalex", "crossref", "openverse"]),
        ("authorized-001", "authorized_research", ["keychain-session-hosts"]),
        ("embed-001", "vectorize", ["local-folder", "subvaults"]),
        ("critic-001", "rigor_review", ["critic", "heldout"]),
        ("packet-001", "machine_packet", ["ai-to-ai"]),
    ]
    out: list[dict] = []
    for worker_id, form, sources in workers[:max_workers]:
        out.append({
            "schema": "lgwks-worker-lease/1",
            "worker_id": worker_id,
            "project": project,
            "input_chain_head": chain_head,
            "budget": {"tokens": tokens_per_cycle, "commands": 8, "fetches": 25},
            "allowed_sources": sources,
            "query_form": form,
            "postcondition": "claims have source handle or unsupported label; no narrative as source of truth",
        })
    return out


def _token_ledger(cycles: list[dict]) -> list[dict]:
    return [{
        "schema": "lgwks-token-ledger/1",
        "project": row["project"],
        "cycle_hash": row["hash"],
        "seq": row["seq"],
        "token_budget": row["token_budget"],
        "estimated_tokens": row["estimated_tokens"],
        "token_status": row["token_status"],
        "reason": "dry-run estimate; execute path records measured provider counts",
    } for row in cycles]


def _critic_records(cycles: list[dict]) -> list[dict]:
    rows = []
    for row in cycles:
        rows.append({
            "schema": "lgwks-critic/1",
            "cycle_hash": row["hash"],
            "claim_id": f"claim-{row['seq']:03d}",
            "label": "unsupported" if row["query_form"] in {"synthesis_packet", "disproof"} else "observed",
            "bias": {
                "human_bias": [{"kind": "desired_outcome_pressure", "severity": "l"}],
                "ai_bias": [{"kind": "slop_completion_pressure", "severity": "m"}],
                "prompt_bias": [{"kind": "thesis_lock", "severity": "m"}],
                "cognitive_bias": [{"kind": "availability", "severity": "l"}],
            },
            "contradiction": {"found": row["query_form"] == "disproof", "source": "planned:disproof-search"},
            "next_action": "disprove" if row["query_form"] == "disproof" else "deepen",
        })
    return rows


def _model_state(project: str, prompt: str) -> dict:
    champion_id = "champion-" + _sha(project + "\n" + prompt)[:16]
    return {
        "schema": "lgwks-model-state/1",
        "champion": {"id": champion_id, "score": {"brier": 0.18, "contradiction_recall": 0.70,
                                                  "slop_chain_recall": 0.0}},
        "challenger": {"id": "challenger-planned-" + champion_id.split("-", 1)[1], "score": None},
        "promotion_policy": {
            "brier_must_improve": True,
            "contradiction_recall_must_not_regress": True,
            "slop_chain_recall_must_not_regress": True,
            "raw_user_data_must_stay_local": True,
        },
    }


def _model_lineage(project: str, learning_mode: str) -> list[dict]:
    base = {
        "schema": "lgwks-model-lineage/1",
        "upstream_url": "local://lgwks/deterministic-feature-hash-v1",
        "upstream_license": "project-local",
        "upstream_sha256": _sha("deterministic-feature-hash-v1"),
        "training_data_refs": [],
        "conversion": {"source_format": "python", "target_format": "none", "conversion_tool": "none",
                       "quantization": "none", "coreml_hash": ""},
        "adapter_hash": "",
        "eval_ref": "heldout-fixture-planned",
        "export_policy": learning_mode,
    }
    return [
        {**base, "model_id": "deterministic-intent-encoder-v1", "project": project, "role": "intent_encoder",
         "base_model": "deterministic-feature-hash-v1"},
        {**base, "model_id": "deterministic-reranker-v1", "project": project, "role": "reranker",
         "base_model": "deterministic-cosine-reranker-v1"},
        {**base, "model_id": "planned-oss-coreml-spine", "project": project, "role": "oss_coreml_spine",
         "base_model": "BERT/ModernBERT/E5/BGE/UniXcoder candidate; license+hash required before download",
         "conversion": {"source_format": "safetensors|onnx", "target_format": "coreml",
                        "conversion_tool": "coremltools", "quantization": "fp16|int8", "coreml_hash": "planned"}},
    ]


def _learning_records(project: str, prompt: str, cycles: list[dict], learning_mode: str,
                      device_consent: str) -> list[dict]:
    said_ref = lgwks_cycle.prompt_ref(prompt)
    rows = []
    for row in cycles:
        rows.append({
            "schema": "lgwks-learning-record/1",
            "project": project,
            "cycle_hash": row["hash"],
            "source_scope": "transcript" if row["seq"] == 1 else "critic",
            "consent": learning_mode,
            "device_consent": device_consent,
            "redaction_status": "raw_vaulted" if device_consent == "local-device" else "derived_only",
            "said": said_ref,
            "meant": {"intent_class": "research_orchestration", "entities": _terms(prompt)[:8], "gaps": []},
            "assumed": ["CLI should act as an automated research operator"],
            "omitted": ["live fetches are not performed during dry-run"],
            "overclaimed": [] if row["query_form"] != "synthesis_packet" else ["end-state not trained yet"],
            "unsupported": [f"claim-{row['seq']:03d}"] if row["eval_result"]["status"] == "unsupported" else [],
            "corrected_by": "critic" if row["query_form"] == "disproof" else "none",
            "outcome": {"accepted": row["eval_result"]["status"] != "unsupported",
                        "reason": row["eval_result"]["status"]},
            "export_policy": learning_mode,
        })
    return rows


def _machine_packets(cycles: list[dict], model_lineage: list[dict]) -> list[dict]:
    refs = {row["role"]: row["model_id"] for row in model_lineage}
    packets = []
    for row in cycles:
        packet = {
            "schema": "lgwks-machine-packet/1",
            "project": row["project"],
            "chain_head": row["hash"],
            "intent_features": {
                "class": "research_orchestration",
                "specificity": 1.0,
                "said_meant_distance": 0.18,
                "query_form": row["query_form"],
            },
            "evidence_refs": [e["id"] for e in row["evidence_attention"]],
            "bias_planes": ["human_bias", "ai_bias", "prompt_bias", "cognitive_bias"],
            "model_refs": {
                "intent_encoder": refs.get("intent_encoder", ""),
                "reranker": refs.get("reranker", ""),
                "oss_coreml_spine": refs.get("oss_coreml_spine", ""),
            },
            "next_commands": row["next_commands"],
        }
        packet["packet_id"] = _sha(json.dumps(packet, sort_keys=True))
        packets.append(packet)
    return packets


def _graph_edges(cycles: list[dict]) -> list[dict]:
    edges = []
    for row in cycles:
        cycle_id = row["hash"]
        edges.append({
            "schema": "lgwks-graph-edge/1",
            "project": row["project"],
            "src": {"kind": "intent", "id": row["intent"]},
            "dst": {"kind": "cycle", "id": cycle_id},
            "edge_type": "refines",
            "weight": row["weight"]["intent_mapping"],
            "evidence_ref": "",
            "created_by": "deterministic",
            "attribution": {"top_features": [row["query_form"], "prompt-derived keywords"]},
        })
        for e in row["evidence_attention"]:
            edges.append({
                "schema": "lgwks-graph-edge/1",
                "project": row["project"],
                "src": {"kind": "cycle", "id": cycle_id},
                "dst": {"kind": "source", "id": e["id"]},
                "edge_type": "schedules",
                "weight": e["score"],
                "evidence_ref": e["id"],
                "created_by": "deterministic",
                "attribution": {"top_features": [e["why"]]},
            })
    return edges


def _operator_profile(project: str, prompt: str, learning_mode: str, device_consent: str) -> dict:
    """A compact prior for future AI workers: how this user steers research work.

    This is deliberately derived and editable, not hidden personalization. It lets lgwks behave like
    the user's research operator without requiring the next AI to reread a long transcript.
    """
    terms = set(_terms(prompt))
    return {
        "schema": "lgwks-operator-profile/1",
        "project": project,
        "profile_id": "operator-" + _sha(project + "\n" + prompt)[:16],
        "source": "deploy-prompt-plus-repo-doctrine",
        "device_consent": device_consent,
        "learning_mode": learning_mode,
        "stance": {
            "research_only": True,
            "one_command_replaces_many": True,
            "act_as_user_research_operator": device_consent == "local-device",
            "privacy_boundary": "local device is user-owned; remote/export remains explicit",
            "build_on_existing_work": True,
            "experiment_slightly": True,
            "architecture_fidelity_over_feature_count": True,
            "machine_native_first": True,
        },
        "ai_worker_hints": [
            "prefer existing lgwks verbs and AI-Research-SKILLs patterns before inventing new machinery",
            "compile human steering into typed packets, not long prose",
            "emit next commands with budgets so another AI can continue",
            "use dry-run artifacts as preregistration before live crawl/model execution",
            "treat user corrections as high-value learning records",
        ],
        "experiment_lanes": [
            {"lane": "steering-profile", "risk": "low", "reason": "derived metadata only"},
            {"lane": "MachinePacket continuation", "risk": "low", "reason": "AI-native surface"},
            {"lane": "graph frontier scoring", "risk": "medium", "reason": "ranking can bias crawl"},
            {"lane": "adapter fine-tune", "risk": "high", "reason": "weights change; needs held-out gate"},
        ],
        "prompt_signals": sorted(terms),
    }


def deploy_command(args: argparse.Namespace) -> int:
    prompt = args.prompt or args.project
    reasoning_cycles = _clamp(args.reasoning_cycles, DEFAULT_REASONING_CYCLES, 1, 50)
    embedding_rounds = _clamp(args.embedding_rounds, DEFAULT_EMBEDDING_ROUNDS, 1, 10_000)
    max_workers = _clamp(args.max_workers, DEFAULT_WORKERS, 1, 16)
    tokens_per_cycle = _clamp(args.tokens_per_cycle, DEFAULT_TOKENS, 1000, 200_000)
    learning_mode = args.learning_mode
    dry_run = args.dry_run or not args.execute
    keywords = _terms(prompt)
    model_state = _model_state(args.project, prompt)
    rollback_ref = model_state["champion"]["id"]
    cycles = lgwks_cycle.make_cycles(args.project, prompt, cycles=reasoning_cycles,
                                     tokens_per_cycle=tokens_per_cycle, keywords=keywords,
                                     rollback_ref=rollback_ref)
    chain_head = cycles[-1]["hash"] if cycles else lgwks_cycle.GENESIS
    model_lineage = _model_lineage(args.project, learning_mode)
    learning = _learning_records(args.project, prompt, cycles, learning_mode, args.device_consent)
    packets = _machine_packets(cycles, model_lineage)
    edges = _graph_edges(cycles)
    leases = _worker_leases(args.project, chain_head, tokens_per_cycle, max_workers)
    critics = _critic_records(cycles)
    token_ledger = _token_ledger(cycles)
    operator_profile = _operator_profile(args.project, prompt, learning_mode, args.device_consent)

    out_dir = _deploy_path(args.project)
    out_dir.mkdir(parents=True, exist_ok=True)
    _jsonl(out_dir / "cycles.jsonl", cycles)
    _jsonl(out_dir / "leases.jsonl", leases)
    _jsonl(out_dir / "token-ledger.jsonl", token_ledger)
    _jsonl(out_dir / "critic-records.jsonl", critics)
    _jsonl(out_dir / "machine-packets.jsonl", packets)
    _jsonl(out_dir / "learning-records.jsonl", learning)
    _jsonl(out_dir / "model-lineage.jsonl", model_lineage)
    _jsonl(out_dir / "graph-edges.jsonl", edges)
    (out_dir / "model_state.json").write_text(json.dumps(model_state, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "operator-profile.json").write_text(json.dumps(operator_profile, indent=2, sort_keys=True),
                                                   encoding="utf-8")
    dag = {
        "schema": "lgwks-project-deploy/1",
        "project": args.project,
        "prompt_ref": lgwks_cycle.prompt_ref(prompt),
        "mode": "dry-run" if dry_run else "execute-planned",
        "architecture": "cli-orchestrator: one prompt replaces memory+public+embed+critic+review commands",
        "model_spine": args.model_spine,
        "learning_mode": learning_mode,
        "device_consent": args.device_consent,
        "budgets": {"reasoning_cycles": reasoning_cycles, "embedding_rounds": embedding_rounds,
                    "max_workers": max_workers, "tokens_per_cycle": tokens_per_cycle},
        "ai_research_skills_map": {
            "orchestration": "autoresearch two-loop",
            "artifact": "ARA compiler/research-manager/rigor-reviewer",
            "retrieval": "sentence-transformers/faiss/qdrant class",
            "model_spine": "BERT/ModernBERT/E5/BGE/UniXcoder -> PEFT/adapters -> CoreML",
            "eval": "lm-evaluation-harness/observability class",
        },
        "artifacts": {
            "cycles": "cycles.jsonl",
            "leases": "leases.jsonl",
            "tokens": "token-ledger.jsonl",
            "critics": "critic-records.jsonl",
            "packets": "machine-packets.jsonl",
            "learning": "learning-records.jsonl",
            "lineage": "model-lineage.jsonl",
            "graph": "graph-edges.jsonl",
            "model_state": "model_state.json",
            "operator_profile": "operator-profile.json",
        },
        "chain_head": chain_head,
    }
    (out_dir / "deploy-dag.json").write_text(json.dumps(dag, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({**dag, "path": str(out_dir)}, indent=2, sort_keys=True))
    return 0


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
    model_state_path = out_dir / "model_state.json"
    model_state = json.loads(model_state_path.read_text(encoding="utf-8")) if model_state_path.exists() else {}
    operator_path = out_dir / "operator-profile.json"
    operator_profile = json.loads(operator_path.read_text(encoding="utf-8")) if operator_path.exists() else {}

    bias_counts: Counter[str] = Counter()
    unsupported: list[str] = []
    for rec in critics:
        for plane, rows in rec.get("bias", {}).items():
            bias_counts[plane] += len(rows)
        if rec.get("label") == "unsupported":
            unsupported.append(rec.get("claim_id", ""))
    export_policies = sorted({r.get("export_policy", r.get("consent", "")) for r in learning if r})
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
        "operator_profile": operator_profile.get("profile_id", ""),
        "one_command_replaces_many": operator_profile.get("stance", {}).get("one_command_replaces_many", False),
        "build_on_existing_work": operator_profile.get("stance", {}).get("build_on_existing_work", False),
        "machine_native": True,
        "human_surface_is_projection": True,
        "error": chain.get("error", ""),
    }


def review_command(args: argparse.Namespace) -> int:
    print(json.dumps(review_project(args.project), indent=2, sort_keys=True))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("project", help="one-prompt project orchestrator")
    ps = p.add_subparsers(dest="project_command", required=True)
    plan = ps.add_parser("plan", help="identify/spec a bounded worker plan from one prompt")
    plan.add_argument("project")
    plan.add_argument("--prompt", default="")
    plan.add_argument("--site", default="")
    plan.add_argument("--folder", default=".")
    plan.add_argument("--reasoning-cycles", type=int)
    plan.add_argument("--embedding-rounds", type=int, default=DEFAULT_EMBEDDING_ROUNDS)
    plan.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS)
    plan.add_argument("--tokens-per-cycle", type=int, default=DEFAULT_TOKENS)
    plan.set_defaults(func=plan_command)
    deploy = ps.add_parser("deploy", help="run the one-prompt research orchestrator")
    deploy.add_argument("project")
    deploy.add_argument("--prompt", default="")
    deploy.add_argument("--reasoning-cycles", type=int)
    deploy.add_argument("--embedding-rounds", type=int, default=DEFAULT_EMBEDDING_ROUNDS)
    deploy.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS)
    deploy.add_argument("--tokens-per-cycle", type=int, default=DEFAULT_TOKENS)
    deploy.add_argument("--learning-mode", choices=["off", "local-only", "export-allowed"], default="local-only")
    deploy.add_argument("--device-consent", choices=["research-only", "local-device"], default="local-device",
                        help="local-device means the CLI may use local user-owned context for this research run")
    deploy.add_argument("--model-spine", choices=["deterministic", "oss-coreml"], default="oss-coreml")
    deploy.add_argument("--dry-run", action="store_true", help="write planned artifacts without fetch/model execution")
    deploy.add_argument("--execute", action="store_true", help="allow approved non-dry executor when implemented")
    deploy.set_defaults(func=deploy_command)
    review = ps.add_parser("review", help="review a project deploy artifact set")
    review.add_argument("project")
    review.set_defaults(func=review_command)
