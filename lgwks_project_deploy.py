"""
lgwks_project_deploy — `lgwks project deploy` verb.

Owns the deploy DAG assembly + the non-ML executor (memory init,
public search, optional embed vault) + the deploy-side record
builders (learning-records, operator-profile, worker-map, source
records, embeddings, execution events). Schemas + jsonl writers
+ shared types live in `lgwks_project_artifacts`; the record
builders live here because they are deploy-output.

Spec (round-1, lgwks_project.py split, refactor/project-split):
  L0 intent: split the deploy half of lgwks_project.py off the
    monolith; preserve deploy_command, _deploy_path,
    _run_non_ml_execution, and the deploy-family record builders.
  L1 reality gap: tests do `proj.DEPLOY_ROOT = tmp/"deploy"` then
    call `proj.deploy_command(args)`. The shim's DEPLOY_ROOT is the
    canonical mutable; _deploy_path is resolved at call time via a
    lazy import of the shim so the monkey-patch takes effect.
  L4 invariant: every artifact file (cycles.jsonl, leases.jsonl, ...)
    keeps its schema and writing order. 123-test suite passes.
  L5 industry parallel: command module — one verb per file.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import lgwks_cycle

from lgwks_project_artifacts import (
    DEFAULT_EMBEDDING_ROUNDS,
    DEFAULT_REASONING_CYCLES,
    DEFAULT_TOKENS,
    EMBED_DIMS,
    MAPPER_ROLES,
    _clamp,
    _embedding,
    _sha,
    _terms,
    jsonl,
    write_json,
    # record builders — one source of truth (were verbatim copies here); local _names preserved
    worker_leases as _worker_leases,
    token_ledger as _token_ledger,
    critic_records as _critic_records,
    model_state as _model_state,
    model_lineage as _model_lineage,
    machine_packets as _machine_packets,
    graph_edges as _graph_edges,
)
from lgwks_project_plan import worker_cap


# -- pure record builders -------------------------------------------------
# These 7 (worker_leases, token_ledger, critic_records, model_state,
# model_lineage, machine_packets, graph_edges) are imported from
# lgwks_project_artifacts (their one source of truth) and aliased to the
# _names deploy_command calls below. They used to be verbatim copies here.

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
            # //why honest label (issue #12): when device_consent == "research-only", we suppress
            # the raw public-search.json and memory-context.json writes, thus derived_only_enforced is True.
            "redaction_status": "derived_only" if device_consent == "research-only" else "raw_vaulted",
            "derived_only_enforced": device_consent == "research-only",
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


def _worker_map(project: str, max_workers: int, cap: dict) -> dict:
    return {
        "schema": "lgwks-worker-map/1",
        "project": project,
        "max_concurrent_workers": cap["computed_cap"],
        "requested_workers": max_workers,
        "active_slots": MAPPER_ROLES[:max_workers],
        "worker_cap": cap,
        "api_key_policy": "prefer internal deterministic mappers; keyed external providers are optional later",
        "spawn_policy": (
            f"never run more than the computed cap ({cap['computed_cap']}) worker slots at once; "
            f"cap basis = {cap['cap_basis']}, host {cap['host']['ram_total_gib']}GiB/"
            f"{cap['host']['cpu_total']}cpu ({cap['host']['source']})"
        ),
    }


def _embedding_record(project: str, kind: str, artifact: str, item_id: str, text: str,
                      *, local_only: bool = True) -> dict:
    text_hash = _sha(text)
    return {
        "schema": "lgwks-artifact-embedding/1",
        "project": project,
        "kind": kind,
        "artifact": artifact,
        "item_id": item_id,
        "text_sha256": text_hash,
        "embedding_model": "deterministic-feature-hash-v1",
        "dimensions": EMBED_DIMS,
        "local_only": local_only,
        "embedding": _embedding(text, EMBED_DIMS),
        "hash": _sha(f"{project}\n{kind}\n{artifact}\n{item_id}\n{text_hash}"),
    }


def _artifact_embeddings(project: str, prompt: str, artifact_rows: dict, artifact_docs: dict) -> list[dict]:
    rows = [_embedding_record(project, "transcript", "prompt", "prompt", prompt)]
    for artifact, doc in artifact_docs.items():
        rows.append(_embedding_record(project, "artifact_doc", artifact, artifact,
                                      json.dumps(doc, sort_keys=True, ensure_ascii=False)))
    for artifact, records in artifact_rows.items():
        for idx, rec in enumerate(records):
            item_id = rec.get("hash") or rec.get("packet_id") or rec.get("source_id") or rec.get("cycle_hash")
            if not item_id:
                item_id = f"{artifact}:{idx + 1}"
            rows.append(_embedding_record(project, "artifact_record", artifact, str(item_id),
                                          json.dumps(rec, sort_keys=True, ensure_ascii=False)))
    return rows


def _event(project: str, step: str, status: str, started: float, *, inputs: Optional[dict] = None,
           outputs: Optional[dict] = None, error: str = "") -> dict:
    return {
        "schema": "lgwks-execution-event/1",
        "project": project,
        "step": step,
        "status": status,
        "started_at": started,
        "finished_at": time.time(),
        "inputs": inputs or {},
        "outputs": outputs or {},
        "error": error,
    }


def _source_records(project: str, payload: dict) -> list[dict]:
    rows = []
    for rec in payload.get("records", []):
        core = {
            "project": project,
            "via": rec.get("source", ""),
            "title": rec.get("title", ""),
            "url": rec.get("url", ""),
            "open_url": rec.get("open_url", ""),
            "license": rec.get("license", ""),
            "license_url": rec.get("license_url", ""),
            "basis": rec.get("basis", ""),
            "year": rec.get("year"),
            "creator": rec.get("creator", ""),
            "content_status": "metadata_only",
        }
        source_id = _sha(json.dumps(core, sort_keys=True, ensure_ascii=False))
        rows.append({
            "schema": "lgwks-source-record/1",
            **core,
            "source_id": source_id,
            "hash": source_id,
        })
    return rows


# //why: the shim's DEPLOY_ROOT is the canonical mutable so tests can
# monkey-patch it (the test does `proj.DEPLOY_ROOT = tmp/"deploy"` then
# `proj.deploy_command(args)`). Resolving the deploy path via the shim
# at call time (not at import time) keeps the monkey-patch in effect.
def _deploy_path(project: str) -> Path:
    import lgwks_project
    return lgwks_project._deploy_path(project)


def _run_non_ml_execution(args: argparse.Namespace, prompt: str, keywords: list[str],
                          out_dir: Path) -> dict:
    events: list[dict] = []
    source_rows: list[dict] = []
    memory_context: dict = {}
    vector_summary: dict = {"status": "skipped", "reason": "no --folder provided"}

    site = args.site or "open-public-sources"
    started = time.time()
    try:
        import lgwks_memory
        lgwks_memory.init_project(args.project, site, prompt)
        memory_context = lgwks_memory.context(args.project, query=" ".join(keywords[:8]))
        if args.device_consent != "research-only":
            write_json(out_dir / "memory-context.json", memory_context)
        events.append(_event(args.project, "memory", "ok", started,
                             inputs={"site": site}, outputs={"artifact": "memory-context.json" if args.device_consent != "research-only" else "derived_only_suppressed",
                                                             "events": memory_context.get("events", 0)}))
    except Exception as exc:
        events.append(_event(args.project, "memory", "error", started,
                             inputs={"site": site}, error=type(exc).__name__))

    query = " ".join(keywords[:8]) or prompt
    started = time.time()
    try:
        import lgwks_public
        public_payload = lgwks_public.search_public(query, source=args.source, limit=args.source_limit)
        source_rows = _source_records(args.project, public_payload)
        jsonl(out_dir / "source-records.jsonl", source_rows)
        if args.device_consent != "research-only":
            write_json(out_dir / "public-search.json", public_payload)
        events.append(_event(args.project, "public_search", "ok", started,
                             inputs={"query": query, "source": args.source, "limit": args.source_limit},
                             outputs={"records": len(source_rows), "artifact": "source-records.jsonl",
                                      "errors": public_payload.get("errors", {})}))
    except Exception as exc:
        jsonl(out_dir / "source-records.jsonl", [])
        events.append(_event(args.project, "public_search", "error", started,
                             inputs={"query": query}, error=type(exc).__name__))

    if args.folder:
        started = time.time()
        try:
            folder = Path(args.folder).expanduser()
            if not folder.exists() or not folder.is_dir():
                vector_summary = {"status": "skipped", "reason": "folder missing", "folder": str(folder)}
                events.append(_event(args.project, "embed", "skipped", started,
                                     inputs={"folder": str(folder)}, outputs=vector_summary))
            else:
                import lgwks_embed
                vault = lgwks_embed.build_vault(str(folder), args.project, keywords,
                                                cycles=max(1, args.embed_cycles),
                                                max_cycles=max(1, args.embed_cycles),
                                                max_files=args.max_files)
                vector_summary = {"status": "ok", **vault}
                events.append(_event(args.project, "embed", "ok", started,
                                     inputs={"folder": str(folder), "cycles": args.embed_cycles,
                                             "max_files": args.max_files},
                                     outputs={"records": vault.get("records", 0),
                                              "cycles_run": vault.get("cycles_run", 0),
                                              "artifact": "vector-vault.json"}))
        except Exception as exc:
            vector_summary = {"status": "error", "error": type(exc).__name__}
            events.append(_event(args.project, "embed", "error", started, error=type(exc).__name__))

    started = time.time()
    events.append(_event(args.project, "auth_private_crawl", "skipped", started,
                         outputs={"reason": "deferred until final hacker review gate"}))

    write_json(out_dir / "vector-vault.json", vector_summary)
    jsonl(out_dir / "execution-events.jsonl", events)
    return {
        "events": events,
        "source_records": len(source_rows),
        "memory_context": memory_context,
        "vector_summary": vector_summary,
    }


def deploy_command(args: argparse.Namespace) -> int:
    prompt = args.prompt or args.project
    cap = worker_cap()
    reasoning_cycles = _clamp(args.reasoning_cycles, DEFAULT_REASONING_CYCLES, 1, 50)
    embedding_rounds = _clamp(args.embedding_rounds, DEFAULT_EMBEDDING_ROUNDS, 1, 10_000)
    max_workers = _clamp(args.max_workers, cap["computed_cap"], 1, cap["computed_cap"])
    tokens_per_cycle = _clamp(args.tokens_per_cycle, DEFAULT_TOKENS, 1000, 200_000)
    learning_mode = args.learning_mode
    dry_run = args.dry_run or not args.execute
    keywords = _terms(prompt)
    m_state = _model_state(args.project, prompt)
    rollback_ref = m_state["champion"]["id"]
    cycles = lgwks_cycle.make_cycles(args.project, prompt, cycles=reasoning_cycles,
                                     tokens_per_cycle=tokens_per_cycle, keywords=keywords,
                                     rollback_ref=rollback_ref)
    chain_head = cycles[-1]["hash"] if cycles else lgwks_cycle.GENESIS
    m_lineage = _model_lineage(args.project, learning_mode)
    learning = _learning_records(args.project, prompt, cycles, learning_mode, args.device_consent)
    packets = _machine_packets(cycles, m_lineage)
    edges = _graph_edges(cycles)
    leases = _worker_leases(args.project, chain_head, tokens_per_cycle, max_workers)
    critics = _critic_records(cycles)
    ledger = _token_ledger(cycles)
    operator = _operator_profile(args.project, prompt, learning_mode, args.device_consent)
    w_map = _worker_map(args.project, max_workers, cap)
    execution_summary = {"events": [], "source_records": 0,
                         "vector_summary": {"status": "skipped", "reason": "dry-run"}}

    out_dir = _deploy_path(args.project)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl(out_dir / "cycles.jsonl", cycles)
    jsonl(out_dir / "leases.jsonl", leases)
    jsonl(out_dir / "token-ledger.jsonl", ledger)
    jsonl(out_dir / "critic-records.jsonl", critics)
    jsonl(out_dir / "machine-packets.jsonl", packets)
    jsonl(out_dir / "learning-records.jsonl", learning)
    jsonl(out_dir / "model-lineage.jsonl", m_lineage)
    jsonl(out_dir / "graph-edges.jsonl", edges)
    jsonl(out_dir / "source-records.jsonl", [])
    jsonl(out_dir / "execution-events.jsonl", [])
    (out_dir / "model_state.json").write_text(json.dumps(m_state, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "operator-profile.json").write_text(json.dumps(operator, indent=2, sort_keys=True),
                                                   encoding="utf-8")
    write_json(out_dir / "worker-map.json", w_map)
    write_json(out_dir / "vector-vault.json", execution_summary["vector_summary"])
    if not dry_run:
        execution_summary = _run_non_ml_execution(args, prompt, keywords, out_dir)
    source_rows = lgwks_cycle.read_jsonl(out_dir / "source-records.jsonl")
    execution_events = lgwks_cycle.read_jsonl(out_dir / "execution-events.jsonl")
    vector_summary = json.loads((out_dir / "vector-vault.json").read_text(encoding="utf-8"))
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
                    "max_workers": max_workers, "max_concurrent_workers": cap["computed_cap"],
                    "worker_cap": cap, "tokens_per_cycle": tokens_per_cycle},
        "ai_research_skills_map": {
            "orchestration": "autoresearch two-loop",
            "artifact": "ARA compiler/research-manager/rigor-reviewer",
            "retrieval": "sentence-transformers/faiss/qdrant class",
            "model_spine": "BERT/ModernBERT/E5/BGE/UniXcoder -> PEFT/adapters -> CoreML",
            "eval": "lm-evaluation-harness/observability class",
        },
        "artifacts": {
            "cycles": "cycles.jsonl", "leases": "leases.jsonl", "tokens": "token-ledger.jsonl",
            "critics": "critic-records.jsonl", "packets": "machine-packets.jsonl",
            "learning": "learning-records.jsonl", "lineage": "model-lineage.jsonl",
            "graph": "graph-edges.jsonl", "model_state": "model_state.json",
            "operator_profile": "operator-profile.json", "sources": "source-records.jsonl",
            "execution_events": "execution-events.jsonl", "vector_vault": "vector-vault.json",
            "worker_map": "worker-map.json", "artifact_embeddings": "artifact-embeddings.jsonl",
        },
        "chain_head": chain_head,
        "execution": {
            "enabled": not dry_run,
            "source_records": execution_summary["source_records"],
            "vector_status": execution_summary["vector_summary"].get("status", "skipped"),
            "auth_private_crawl": "deferred",
        },
    }
    (out_dir / "deploy-dag.json").write_text(json.dumps(dag, indent=2, sort_keys=True), encoding="utf-8")
    embeds = _artifact_embeddings(args.project, prompt, {
        "cycles.jsonl": cycles, "leases.jsonl": leases, "token-ledger.jsonl": ledger,
        "critic-records.jsonl": critics, "machine-packets.jsonl": packets,
        "learning-records.jsonl": learning, "model-lineage.jsonl": m_lineage,
        "graph-edges.jsonl": edges, "source-records.jsonl": source_rows,
        "execution-events.jsonl": execution_events,
    }, {
        "model_state.json": m_state, "operator-profile.json": operator,
        "worker-map.json": w_map, "vector-vault.json": vector_summary,
        "deploy-dag.json": dag,
        "artifact-embeddings.jsonl": {
            "schema": "lgwks-artifact-embedding/1",
            "coverage": "transcript plus each deploy artifact document and JSONL record",
        },
    })
    jsonl(out_dir / "artifact-embeddings.jsonl", embeds)
    print(json.dumps({**dag, "path": str(out_dir)}, indent=2, sort_keys=True))

    if not dry_run:
        # Produce a runnable artifact: a script to re-verify or run the project's index
        run_sh = out_dir / "run.sh"
        run_sh.write_text(f"""#!/bin/bash
# lgwks generated run script for project: {args.project}
# run_id: {out_dir.name}

echo "◆ Running project: {args.project}"
{sys.executable} lgwks state run index {out_dir}
""", encoding="utf-8")
        run_sh.chmod(0o755)
        print(f"  ✅ runnable artifact: {run_sh}")

    return 0
