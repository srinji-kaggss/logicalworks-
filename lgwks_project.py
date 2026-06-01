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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT / "store" / "project-plans"

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

