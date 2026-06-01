"""
lgwks_project_plan — `lgwks project plan` verb.

Builds the bounded worker plan (identify/spec half) from a one-prompt
project. Pure planning, no I/O side effects beyond writing the plan.json
and printing it.

Spec (round-1, lgwks_project.py split, refactor/project-split):
  L0 intent: keep plan_command + build_plan + helpers here, off the
    monolith, while preserving every public attribute the existing
    tests rely on (build_plan, DEPLOY_ROOT via the shim).
  L1 reality gap: tests monkey-patch DEPLOY_ROOT on the lgwks_project
    module — DEPLOY_ROOT is imported here from artifacts and re-exported
    by the shim, so monkey-patching the shim attribute would not move
    it for the rest of the code. The shim sets DEPLOY_ROOT = artifacts.DEPLOY_ROOT
    at import time, and the plan module does not write to DEPLOY_ROOT
    directly (plan_command uses PROJECT_ROOT for its own subdir).
  L4 invariant: plan.json schema is unchanged; build_plan returns the
    same dict shape (schema, plan_id, project, prompt, budgets, ...).
  L5 industry parallel: command module — one verb per file.
"""

from __future__ import annotations

import argparse
import json
import time

import lgwks_workercap

from lgwks_project_artifacts import (
    ACADEMIC_SOURCES,
    DEFAULT_EMBEDDING_ROUNDS,
    DEFAULT_REASONING_CYCLES,
    DEFAULT_TOKENS,
    DEFAULT_WEIGHT,
    MAPPER_ROLE_COUNT,
    PROJECT_ROOT,
    _clamp,
    _slug,
    _terms,
)


def worker_cap() -> dict:
    """Computed worker-cap breakdown for the current (probed) host."""
    return lgwks_workercap.compute_worker_cap(MAPPER_ROLE_COUNT)


DEFAULT_WORKERS = MAPPER_ROLE_COUNT


def build_plan(args: argparse.Namespace) -> dict:
    project = args.project
    prompt = args.prompt or project
    cap = worker_cap()
    reasoning_cycles = _clamp(args.reasoning_cycles, DEFAULT_REASONING_CYCLES, 1, 50)
    embedding_rounds = _clamp(args.embedding_rounds, DEFAULT_EMBEDDING_ROUNDS, 1, 10_000)
    max_workers = _clamp(args.max_workers, cap["computed_cap"], 1, cap["computed_cap"])
    tokens_per_cycle = _clamp(args.tokens_per_cycle, DEFAULT_TOKENS, 1000, 200_000)
    keywords = _terms(prompt)
    plan_id = _slug(project + "\n" + prompt)
    branch_workers = [
        {"id": "context", "role": "scope memory, transcript, and prompt-derived themes", "max_commands": 2},
        {"id": "source", "role": "query open scholarly/public indexes", "sources": ACADEMIC_SOURCES},
        {"id": "embed", "role": "embed every artifact and run vector vault rounds", "rounds": embedding_rounds},
        {"id": "critic-packet", "role": "score evidence gaps and emit AI-to-AI packets"},
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
            "max_concurrent_workers": cap["computed_cap"],
            "worker_cap": cap,
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
            "parallel lease-claim worker runner",
            "semantic embedding provider beside deterministic vectors",
            "critic held-out eval set",
            "champion/challenger snapshot promotion",
            "auth/private crawl after final hacker review",
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
