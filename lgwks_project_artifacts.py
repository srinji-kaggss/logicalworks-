"""
lgwks_project_artifacts — shared schemas, JSONL writers, record builders,
and helpers for the project orchestrator.

The four project verbs (plan / deploy / review) and the deploy executor all
share these types, writers, and pure record builders. Keep this module
dependency-free (stdlib only) and importable from any of the split files.

The pure-data record builders (cycles / leases / token-ledger / critics /
machine-packets / graph-edges / model-state / model-lineage) live here
because they are pure projections of the cycles produced by
`lgwks_cycle.make_cycles`; deploy wires them into the artifact set.

Spec (round-1, lgwks_project.py split, refactor/project-split):
  L0 intent: split the 829-line lgwks_project.py into <=350-line files
    without changing behaviour; this file owns the JSONL writers, the
    shared schema constants, and the pure record builders.
  L1 reality gap: any test that monkey-patches lgwks_project.DEPLOY_ROOT
    or calls build_plan / deploy_command / review_project on the
    shim module must keep working — these constants and helpers
    are exposed *via the shim* (lgwks_project re-exports them).
  L4 invariant: every existing artifact writer (cycles.jsonl,
    leases.jsonl, token-ledger.jsonl, ...) keeps its schema string and
    ordering. The 123-test suite must pass unmodified.
  L5 industry parallel: classic "facade" pattern — a thin package
    surface over a set of focused modules; the public name survives.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import lgwks_cycle

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT / "store" / "project-plans"
DEPLOY_ROOT = ROOT / "store" / "project-deploy"

DEFAULT_REASONING_CYCLES = 5
DEFAULT_EMBEDDING_ROUNDS = 400
DEFAULT_TOKENS = 8000
EMBED_DIMS = 128

ACADEMIC_SOURCES = ["openalex", "crossref", "openverse"]
DEFAULT_WEIGHT = {
    "retrieval": 0.35,
    "evidence_quality": 0.25,
    "novelty": 0.15,
    "contradiction": 0.15,
    "license_safety": 0.10,
}

# //why: the four defined mapper roles are the single source of concurrency
# truth. The spawnable ceiling is min(host-formula-headroom, role_count) — see
# lgwks_workercap. A new role is a deliberate addition here, not a phantom slot.
MAPPER_ROLES = [
    {"slot": 1, "worker_id": "context-001", "mapper": "internal-context-mapper",
     "owns": ["prompt transcript", "memory-context", "operator-profile"], "api_keys": "none"},
    {"slot": 2, "worker_id": "source-001", "mapper": "internal-public-source-mapper",
     "owns": ["open-license source metadata"], "api_keys": "none-by-default"},
    {"slot": 3, "worker_id": "embed-001", "mapper": "internal-deterministic-embed-mapper",
     "owns": ["artifact-embeddings", "vector-vault"], "api_keys": "none"},
    {"slot": 4, "worker_id": "critic-packet-001", "mapper": "internal-critic-packet-mapper",
     "owns": ["critic-records", "machine-packets", "graph-edges"], "api_keys": "none"},
]
MAPPER_ROLE_COUNT = len(MAPPER_ROLES)


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


def _embedding(text: str, dims: int = EMBED_DIMS) -> list[float]:
    vec = [0.0] * dims
    features = _terms(text)
    features.extend(" ".join(features[i:i + 2]) for i in range(max(0, len(features) - 1)))
    for feat in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        vec[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [round(v / norm, 6) for v in vec]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clamp(value: Optional[int], default: int, low: int, high: int) -> int:
    value = default if value is None else value
    return max(low, min(high, value))


def jsonl(path: Path, rows: list[dict]) -> None:
    lgwks_cycle.write_jsonl(path, rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def deploy_path(project: str) -> Path:
    return lgwks_cycle.deploy_dir(DEPLOY_ROOT, project)


# -- pure record builders used by deploy ----------------------------------
# Each builder takes a list of cycle rows from lgwks_cycle.make_cycles and
# returns a list of dicts (or one dict) matching a published schema. They
# are pure: no I/O, no side effects. Deploy wires them into the artifact
# set.

def worker_leases(project: str, chain_head: str, tokens_per_cycle: int, max_workers: int) -> list[dict]:
    workers = [
        ("context-001", "scope_memory", ["memory", "transcript", "operator-profile"]),
        ("source-001", "neutral_academic", ["openalex", "crossref", "openverse"]),
        ("embed-001", "vectorize_everything", ["artifact-embeddings", "local-folder", "subvaults"]),
        ("critic-packet-001", "rigor_packet", ["critic", "heldout", "ai-to-ai"]),
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


def token_ledger(cycles: list[dict]) -> list[dict]:
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


def critic_records(cycles: list[dict]) -> list[dict]:
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


def model_state(project: str, prompt: str) -> dict:
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


def model_lineage(project: str, learning_mode: str) -> list[dict]:
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


def machine_packets(cycles: list[dict], model_lineage_rows: list[dict]) -> list[dict]:
    refs = {row["role"]: row["model_id"] for row in model_lineage_rows}
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


def graph_edges(cycles: list[dict]) -> list[dict]:
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


# -- bot-fabric schema constants and validators (U1/U2) -------------------
# Pure stdlib validation for lgwks.bot.record.v1 and lgwks.bot.plan.v1.
# These functions are dependency-free so any bot lane can import them.

BOT_RECORD_SCHEMA = "lgwks.bot.record.v1"
BOT_PLAN_SCHEMA = "lgwks.bot.plan.v1"

BOT_SEVERITY_LEVELS = {"info", "low", "medium", "high", "critical"}
BOT_STATUS_VALUES = {"open", "confirmed", "suppressed", "duplicate", "resolved"}
BOT_EVIDENCE_TYPES = {
    "metric", "edge", "trace", "query",
    "test_output", "file_excerpt", "history", "external_ref",
}
BOT_RUN_KINDS = {"review", "research", "continue", "stress", "optimize"}
BOT_WORLD_DB_MODES = {"bind", "readonly", "skip"}
BOT_BRANCH_STATE_MODES = {"shared", "per_branch"}

# Default known bot registry. Callers may extend via validate_bot_plan(known_bots=...)
BOT_REGISTRY_DEFAULT = {
    "graph_anomaly",
    "code_hacker",
    "optimizer",
    "intent_classifier",
    "scope_creep_guard",
    "review",
}


def _is_str(v) -> bool:
    return isinstance(v, str)


def _require(obj: dict, key: str, kind: str | None = None) -> list[str]:
    errs: list[str] = []
    if key not in obj:
        errs.append(f"missing required field: {key}")
        return errs
    if kind is not None:
        if kind == "str" and not _is_str(obj[key]):
            errs.append(f"{key} must be a string")
        elif kind == "number" and not isinstance(obj[key], (int, float)):
            errs.append(f"{key} must be a number")
        elif kind == "bool" and not isinstance(obj[key], bool):
            errs.append(f"{key} must be a boolean")
        elif kind == "list" and not isinstance(obj[key], list):
            errs.append(f"{key} must be a list")
        elif kind == "dict" and not isinstance(obj[key], dict):
            errs.append(f"{key} must be an object")
    return errs


def validate_bot_record(record: dict) -> tuple[bool, list[str]]:
    """
    Validate a bot record against the lgwks.bot.record.v1 schema.

    Returns (is_valid, error_messages).
    Fail-closed: any deviation from the schema is reported.
    """
    errs: list[str] = []

    if not isinstance(record, dict):
        return False, ["record must be a JSON object"]

    errs.extend(_require(record, "schema", "str"))
    errs.extend(_require(record, "run_id", "str"))
    errs.extend(_require(record, "bot", "str"))
    errs.extend(_require(record, "target", "dict"))
    errs.extend(_require(record, "kind", "str"))
    errs.extend(_require(record, "severity", "str"))
    errs.extend(_require(record, "confidence", "number"))
    errs.extend(_require(record, "status", "str"))
    errs.extend(_require(record, "evidence", "list"))
    errs.extend(_require(record, "links", "dict"))
    errs.extend(_require(record, "created_at", "str"))

    if errs:
        return False, errs

    # schema discriminator
    if record["schema"] != BOT_RECORD_SCHEMA:
        errs.append(f"schema must be '{BOT_RECORD_SCHEMA}', got {record['schema']!r}")

    # severity
    sev = record["severity"]
    if sev not in BOT_SEVERITY_LEVELS:
        errs.append(f"severity {sev!r} is not in {sorted(BOT_SEVERITY_LEVELS)}")

    # confidence clamp
    conf = record["confidence"]
    if not (0.0 <= conf <= 1.0):
        errs.append(f"confidence {conf} must be in [0.0, 1.0]")

    # status
    st = record["status"]
    if st not in BOT_STATUS_VALUES:
        errs.append(f"status {st!r} is not in {sorted(BOT_STATUS_VALUES)}")

    # target
    target = record["target"]
    if not isinstance(target, dict):
        errs.append("target must be an object")
    else:
        if "kind" not in target:
            errs.append("target.kind is required")
        elif not _is_str(target["kind"]):
            errs.append("target.kind must be a string")
        if "id" not in target:
            errs.append("target.id is required")
        elif not _is_str(target["id"]):
            errs.append("target.id must be a string")

    # evidence: at least one item, each with a type
    evidence = record["evidence"]
    if len(evidence) == 0:
        errs.append("evidence must contain at least one item")
    for idx, ev in enumerate(evidence):
        if not isinstance(ev, dict):
            errs.append(f"evidence[{idx}] must be an object")
            continue
        ev_type = ev.get("type")
        if not _is_str(ev_type):
            errs.append(f"evidence[{idx}].type is required and must be a string")
        elif ev_type not in BOT_EVIDENCE_TYPES:
            errs.append(f"evidence[{idx}].type {ev_type!r} is not in {sorted(BOT_EVIDENCE_TYPES)}")

    # links: at least one repo-local anchor (file, symbol, test, artifact)
    links = record["links"]
    if not isinstance(links, dict):
        errs.append("links must be an object")
    else:
        if "repo" not in links:
            errs.append("links.repo is required")
        elif not _is_str(links["repo"]):
            errs.append("links.repo must be a string")
        has_anchor = bool(
            _is_str(links.get("file"))
            or _is_str(links.get("symbol"))
            or (isinstance(links.get("tests"), list) and len(links["tests"]) > 0)
            or (isinstance(links.get("artifacts"), list) and len(links["artifacts"]) > 0)
        )
        if not has_anchor:
            errs.append(
                "links must contain at least one repo-local anchor "
                "(file, symbol, tests, or artifacts)"
            )

    return len(errs) == 0, errs


def validate_bot_plan(plan: dict, known_bots: set[str] | None = None) -> tuple[bool, list[str]]:
    """
    Validate a bot plan against the lgwks.bot.plan.v1 schema.

    Returns (is_valid, error_messages).
    Unknown bot names fail closed.
    """
    errs: list[str] = []

    if not isinstance(plan, dict):
        return False, ["plan must be a JSON object"]

    errs.extend(_require(plan, "schema", "str"))
    errs.extend(_require(plan, "plan_id", "str"))
    errs.extend(_require(plan, "run_kind", "str"))
    errs.extend(_require(plan, "target_repo", "str"))
    errs.extend(_require(plan, "bots", "list"))
    errs.extend(_require(plan, "jepa", "dict"))
    errs.extend(_require(plan, "synth", "dict"))
    errs.extend(_require(plan, "policy", "dict"))
    errs.extend(_require(plan, "outputs", "dict"))

    if errs:
        return False, errs

    # schema discriminator
    if plan["schema"] != BOT_PLAN_SCHEMA:
        errs.append(f"schema must be '{BOT_PLAN_SCHEMA}', got {plan['schema']!r}")

    # run_kind
    rk = plan["run_kind"]
    if rk not in BOT_RUN_KINDS:
        errs.append(f"run_kind {rk!r} is not in {sorted(BOT_RUN_KINDS)}")

    # world_db_mode (optional, default bind)
    wdb = plan.get("world_db_mode", "bind")
    if wdb not in BOT_WORLD_DB_MODES:
        errs.append(f"world_db_mode {wdb!r} is not in {sorted(BOT_WORLD_DB_MODES)}")

    # bots: at least one, known names only
    bots = plan["bots"]
    if len(bots) == 0:
        errs.append("bots must contain at least one bot reference")
    registry = BOT_REGISTRY_DEFAULT if known_bots is None else known_bots
    for idx, b in enumerate(bots):
        if not isinstance(b, dict):
            errs.append(f"bots[{idx}] must be an object")
            continue
        name = b.get("name")
        if not _is_str(name):
            errs.append(f"bots[{idx}].name is required and must be a string")
        elif name not in registry:
            errs.append(f"bots[{idx}].name {name!r} is not in the bot registry")
        enabled = b.get("enabled")
        if not isinstance(enabled, bool):
            errs.append(f"bots[{idx}].enabled is required and must be a boolean")

    # jepa
    jepa = plan["jepa"]
    if "enabled" not in jepa:
        errs.append("jepa.enabled is required")
    elif not isinstance(jepa["enabled"], bool):
        errs.append("jepa.enabled must be a boolean")

    # synth
    synth = plan["synth"]
    if "enabled" not in synth:
        errs.append("synth.enabled is required")
    elif not isinstance(synth["enabled"], bool):
        errs.append("synth.enabled must be a boolean")

    # policy
    policy = plan["policy"]
    if "allow_external_research" not in policy:
        errs.append("policy.allow_external_research is required")
    elif not isinstance(policy["allow_external_research"], bool):
        errs.append("policy.allow_external_research must be a boolean")
    if "branch_state_mode" not in policy:
        errs.append("policy.branch_state_mode is required")
    elif policy["branch_state_mode"] not in BOT_BRANCH_STATE_MODES:
        errs.append(
            f"policy.branch_state_mode {policy['branch_state_mode']!r} "
            f"is not in {sorted(BOT_BRANCH_STATE_MODES)}"
        )
    if "max_artifact_bytes" not in policy:
        errs.append("policy.max_artifact_bytes is required")
    elif not isinstance(policy["max_artifact_bytes"], int) or isinstance(policy["max_artifact_bytes"], bool):
        errs.append("policy.max_artifact_bytes must be an integer")
    elif policy["max_artifact_bytes"] < 0:
        errs.append("policy.max_artifact_bytes must be >= 0")

    # outputs
    outputs = plan["outputs"]
    if "root" not in outputs:
        errs.append("outputs.root is required")
    elif not _is_str(outputs["root"]):
        errs.append("outputs.root must be a string")

    return len(errs) == 0, errs
