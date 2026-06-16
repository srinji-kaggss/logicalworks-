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
import datetime as _dt
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import lgwks_clock
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
    return f"{safe}-{content_id(value, 12)}"


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


from lgwks_hashing import digest as _sha, content_id  # canonical text/id hashing (one source of truth)


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
    "slop_math",
    "stress",
}


def run_seed(bot: str, repo: str) -> str:
    """Deterministic 12-char run id for a bot scanning a repo (replay-stable).

    One source of truth — every bot lane derives its run id this way; do not
    re-spell ``sha256(f"{bot}:{repo}")[:12]`` per module.
    """
    return content_id(f"{bot}:{repo}", 12)


def make_record(
    *,
    bot: str,
    run_id: str,
    kind: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence: list[dict],
    tags: list[str],
    links: dict,
    target_id: str,
    target_kind: str = "file",
    world_refs: Optional[list[dict]] = None,
    created_at: Optional[str] = None,
) -> dict:
    """Canonical ``lgwks.bot.record.v1`` builder — one source of truth for every bot lane.

    Each bot supplies its own ``links`` / ``world_refs`` / ``target``; the shared
    skeleton (schema id, ``status="open"``, timestamp default) is built here. ``created_at``
    is injectable so a run over unchanged code is byte-reproducible — stamp it once per
    run() and thread it down rather than calling the clock per finding (doctrine T4).
    """
    rec = {
        "schema": BOT_RECORD_SCHEMA,
        "run_id": run_id,
        "bot": bot,
        "target": {"kind": target_kind, "id": target_id},
        "kind": kind,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "status": "open",
        "evidence": evidence,
        "links": links,
        "tags": tags,
        "created_at": created_at or lgwks_clock.now_iso(),
    }
    if world_refs is not None:
        rec["world_refs"] = world_refs
    return rec


def _is_str(v) -> bool:
    return isinstance(v, str)


def _is_nonempty_str(v) -> bool:
    return _is_str(v) and len(v) > 0


def _require(obj: dict, key: str, kind: str | None = None) -> list[str]:
    errs: list[str] = []
    if key not in obj:
        errs.append(f"missing required field: {key}")
        return errs
    if kind is not None:
        if kind == "str" and not _is_nonempty_str(obj[key]):
            errs.append(f"{key} must be a string")
        elif kind == "number" and (
            not isinstance(obj[key], (int, float)) or isinstance(obj[key], bool)
        ):
            errs.append(f"{key} must be a number")
        elif kind == "bool" and not isinstance(obj[key], bool):
            errs.append(f"{key} must be a boolean")
        elif kind == "list" and not isinstance(obj[key], list):
            errs.append(f"{key} must be a list")
        elif kind == "dict" and not isinstance(obj[key], dict):
            errs.append(f"{key} must be an object")
    return errs


def _reject_unknown_keys(obj: dict, allowed: set[str], path: str) -> list[str]:
    return [f"{path} contains unknown field: {k}" for k in obj.keys() if k not in allowed]


def _is_datetime_str(v: str) -> bool:
    try:
        _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_bot_record(record: dict) -> tuple[bool, list[str]]:
    """
    Validate a bot record against the lgwks.bot.record.v1 schema.

    Returns (is_valid, error_messages).
    Fail-closed: any deviation from the schema is reported.
    """
    errs: list[str] = []

    if not isinstance(record, dict):
        return False, ["record must be a JSON object"]

    errs.extend(_reject_unknown_keys(record, {
        "schema", "run_id", "bot", "target", "kind", "summary", "severity",
        "confidence", "status", "evidence", "links", "world_refs", "tags",
        "created_at",
    }, "record"))

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
        errs.extend(_reject_unknown_keys(target, {"kind", "id"}, "target"))
        if "kind" not in target:
            errs.append("target.kind is required")
        elif not _is_nonempty_str(target["kind"]):
            errs.append("target.kind must be a string")
        if "id" not in target:
            errs.append("target.id is required")
        elif not _is_nonempty_str(target["id"]):
            errs.append("target.id must be a string")

    # evidence: at least one item, each with a type
    evidence = record["evidence"]
    if len(evidence) == 0:
        errs.append("evidence must contain at least one item")
    for idx, ev in enumerate(evidence):
        if not isinstance(ev, dict):
            errs.append(f"evidence[{idx}] must be an object")
            continue
        errs.extend(_reject_unknown_keys(ev, {"type", "name", "value", "unit"}, f"evidence[{idx}]"))
        ev_type = ev.get("type")
        if not _is_nonempty_str(ev_type):
            errs.append(f"evidence[{idx}].type is required and must be a string")
        elif ev_type not in BOT_EVIDENCE_TYPES:
            errs.append(f"evidence[{idx}].type {ev_type!r} is not in {sorted(BOT_EVIDENCE_TYPES)}")
        if "name" in ev and ev["name"] is not None and not _is_nonempty_str(ev["name"]):
            errs.append(f"evidence[{idx}].name must be a non-empty string when present")
        if "unit" in ev and ev["unit"] is not None and not _is_nonempty_str(ev["unit"]):
            errs.append(f"evidence[{idx}].unit must be a non-empty string when present")

    # links: at least one repo-local anchor (file, symbol, test, artifact)
    links = record["links"]
    if not isinstance(links, dict):
        errs.append("links must be an object")
    else:
        errs.extend(_reject_unknown_keys(links, {"repo", "file", "symbol", "tests", "artifacts"}, "links"))
        if "repo" not in links:
            errs.append("links.repo is required")
        elif not _is_nonempty_str(links["repo"]):
            errs.append("links.repo must be a string")
        if "file" in links and links["file"] is not None and not _is_nonempty_str(links["file"]):
            errs.append("links.file must be a non-empty string when present")
        if "symbol" in links and links["symbol"] is not None and not _is_nonempty_str(links["symbol"]):
            errs.append("links.symbol must be a non-empty string when present")
        for name in ("tests", "artifacts"):
            if name in links:
                val = links[name]
                if not isinstance(val, list):
                    errs.append(f"links.{name} must be a list when present")
                else:
                    for i, item in enumerate(val):
                        if not _is_nonempty_str(item):
                            errs.append(f"links.{name}[{i}] must be a non-empty string")
        has_anchor = bool(
            _is_nonempty_str(links.get("file"))
            or _is_nonempty_str(links.get("symbol"))
            or (isinstance(links.get("tests"), list) and len(links["tests"]) > 0)
            or (isinstance(links.get("artifacts"), list) and len(links["artifacts"]) > 0)
        )
        if not has_anchor:
            errs.append(
                "links must contain at least one repo-local anchor "
                "(file, symbol, tests, or artifacts)"
            )

    world_refs = record.get("world_refs", [])
    if not isinstance(world_refs, list):
        errs.append("world_refs must be a list when present")
    else:
        for idx, ref in enumerate(world_refs):
            if not isinstance(ref, dict):
                errs.append(f"world_refs[{idx}] must be an object")
                continue
            errs.extend(_reject_unknown_keys(ref, {"kind", "id"}, f"world_refs[{idx}]"))
            if not _is_nonempty_str(ref.get("kind")):
                errs.append(f"world_refs[{idx}].kind must be a non-empty string")
            if not _is_nonempty_str(ref.get("id")):
                errs.append(f"world_refs[{idx}].id must be a non-empty string")

    tags = record.get("tags", [])
    if not isinstance(tags, list):
        errs.append("tags must be a list when present")
    else:
        for idx, tag in enumerate(tags):
            if not _is_nonempty_str(tag):
                errs.append(f"tags[{idx}] must be a non-empty string")

    if not _is_datetime_str(record["created_at"]):
        errs.append("created_at must be a valid ISO 8601 date-time string")

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

    errs.extend(_reject_unknown_keys(plan, {
        "schema", "plan_id", "run_kind", "target_repo", "world_db_mode",
        "bots", "jepa", "synth", "policy", "outputs",
    }, "plan"))

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
        errs.extend(_reject_unknown_keys(b, {"name", "enabled"}, f"bots[{idx}]"))
        name = b.get("name")
        if not _is_nonempty_str(name):
            errs.append(f"bots[{idx}].name is required and must be a string")
        elif name not in registry:
            errs.append(f"bots[{idx}].name {name!r} is not in the bot registry")
        enabled = b.get("enabled")
        if not isinstance(enabled, bool):
            errs.append(f"bots[{idx}].enabled is required and must be a boolean")

    # jepa
    jepa = plan["jepa"]
    errs.extend(_reject_unknown_keys(jepa, {"enabled", "mode"}, "jepa"))
    if "enabled" not in jepa:
        errs.append("jepa.enabled is required")
    elif not isinstance(jepa["enabled"], bool):
        errs.append("jepa.enabled must be a boolean")
    if "mode" in jepa and jepa["mode"] is not None and not _is_nonempty_str(jepa["mode"]):
        errs.append("jepa.mode must be a non-empty string when present")

    # synth
    synth = plan["synth"]
    errs.extend(_reject_unknown_keys(synth, {"enabled", "provider", "optional"}, "synth"))
    if "enabled" not in synth:
        errs.append("synth.enabled is required")
    elif not isinstance(synth["enabled"], bool):
        errs.append("synth.enabled must be a boolean")
    if "provider" in synth and synth["provider"] is not None and not _is_nonempty_str(synth["provider"]):
        errs.append("synth.provider must be a non-empty string when present")
    if "optional" in synth and not isinstance(synth["optional"], bool):
        errs.append("synth.optional must be a boolean when present")

    # policy
    policy = plan["policy"]
    errs.extend(_reject_unknown_keys(
        policy, {"allow_external_research", "branch_state_mode", "max_artifact_bytes"}, "policy"
    ))
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
    errs.extend(_reject_unknown_keys(outputs, {"root", "machine", "human"}, "outputs"))
    if "root" not in outputs:
        errs.append("outputs.root is required")
    elif not _is_nonempty_str(outputs["root"]):
        errs.append("outputs.root must be a string")
    for name in ("machine", "human"):
        if name in outputs and outputs[name] is not None and not _is_nonempty_str(outputs[name]):
            errs.append(f"outputs.{name} must be a non-empty string when present")

    return len(errs) == 0, errs


# -- bot-fabric reducer / package / strength gate (U3/U4/U11) -------------

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_relpath(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).replace("\\", "/")
    text = re.sub(r"/+", "/", text)
    return text.strip()


def _dedupe_strings(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not _is_nonempty_str(item):
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _record_primary_evidence(record: dict) -> str:
    evidence = record.get("evidence") or []
    primary = evidence[0] if evidence else {}
    return _stable_json(primary)


def _normalized_record_id(record: dict) -> str:
    base = {
        "kind": record.get("kind", ""),
        "target": record.get("target", {}),
        "primary_evidence": _record_primary_evidence(record),
    }
    return "finding:" + content_id(_stable_json(base))


def _normalize_bot_record(record: dict) -> dict:
    ok, errs = validate_bot_record(record)
    if not ok:
        raise ValueError("invalid bot record: " + "; ".join(errs))
    normalized = json.loads(json.dumps(record))
    links = normalized["links"]
    links["repo"] = _canonical_relpath(links["repo"])
    if links.get("file") is not None:
        links["file"] = _canonical_relpath(links["file"])
    for key in ("tests", "artifacts"):
        links[key] = [_canonical_relpath(item) for item in links.get(key, [])]
    normalized["tags"] = _dedupe_strings(list(normalized.get("tags", [])))
    normalized["record_id"] = _normalized_record_id(normalized)
    normalized["severity_rank"] = _SEVERITY_RANK[normalized["severity"]]
    normalized["summary"] = normalized.get("summary") or normalized["kind"].replace("_", " ")
    normalized["source_records"] = [normalized["record_id"]]
    normalized["contributing_bots"] = [normalized["bot"]]
    return normalized


def _merge_bot_records(records: list[dict]) -> dict:
    best = max(records, key=lambda r: (_SEVERITY_RANK[r["severity"]], r["confidence"], r["created_at"]))
    evidence_map: dict[str, dict] = {}
    for rec in records:
        for ev in rec["evidence"]:
            evidence_map[_stable_json(ev)] = ev
    merged_tests: list[str] = []
    merged_artifacts: list[str] = []
    tags: list[str] = []
    world_refs: list[dict] = []
    source_records: list[str] = []
    bots: list[str] = []
    for rec in records:
        merged_tests.extend(rec["links"].get("tests", []))
        merged_artifacts.extend(rec["links"].get("artifacts", []))
        tags.extend(rec.get("tags", []))
        world_refs.extend(rec.get("world_refs", []))
        source_records.extend(rec.get("source_records", [rec["record_id"]]))
        bots.extend(rec.get("contributing_bots", [rec["bot"]]))
    merged = json.loads(json.dumps(best))
    merged["evidence"] = [evidence_map[key] for key in sorted(evidence_map)]
    merged["links"]["tests"] = _dedupe_strings(merged_tests)
    merged["links"]["artifacts"] = _dedupe_strings(merged_artifacts)
    merged["tags"] = _dedupe_strings(tags)
    merged["world_refs"] = sorted(
        {(_stable_json(ref),) for ref in world_refs},
        key=lambda item: item[0],
    )
    merged["world_refs"] = [json.loads(item[0]) for item in merged["world_refs"]]
    merged["source_records"] = _dedupe_strings(source_records)
    merged["contributing_bots"] = _dedupe_strings(bots)
    merged["bot_count"] = len(merged["contributing_bots"])
    merged["confidence"] = round(max(rec["confidence"] for rec in records), 4)
    merged["severity"] = max(records, key=lambda r: _SEVERITY_RANK[r["severity"]])["severity"]
    merged["severity_rank"] = _SEVERITY_RANK[merged["severity"]]
    return merged


def _cluster_key(finding: dict) -> tuple[str, str]:
    links = finding["links"]
    if _is_nonempty_str(links.get("file")):
        return "file", links["file"]
    if _is_nonempty_str(links.get("symbol")):
        return "symbol", links["symbol"]
    if finding.get("world_refs"):
        ref = finding["world_refs"][0]
        return "world", f"{ref['kind']}:{ref['id']}"
    return "target", finding["target"]["id"]


def _blast_radius(finding: dict, repo_graph_metrics: dict | None = None) -> float:
    if not repo_graph_metrics:
        return 0.0
    file_key = finding["links"].get("file") or finding["target"]["id"]
    metric = repo_graph_metrics.get(file_key, {})
    value = metric.get("blast_radius", metric.get("betweenness", 0.0))
    try:
        return float(value)
    except Exception:
        return 0.0


def _recommended_read(finding: dict) -> str:
    links = finding["links"]
    if _is_nonempty_str(links.get("file")):
        return links["file"]
    if links.get("tests"):
        return links["tests"][0]
    if links.get("artifacts"):
        return links["artifacts"][0]
    return finding["target"]["id"]


def _recommended_command(finding: dict) -> str:
    links = finding["links"]
    if _is_nonempty_str(links.get("file")) and _is_nonempty_str(links.get("symbol")):
        return f"rg -n '{links['symbol']}' {links['file']}"
    if _is_nonempty_str(links.get("file")):
        return f"sed -n '1,220p' {links['file']}"
    if links.get("tests"):
        return f"python3 -m unittest {links['tests'][0].replace('/', '.').removesuffix('.py')}"
    return f"rg -n '{finding['target']['id']}' ."


def reduce_bot_records(
    records: list[dict],
    repo_graph_metrics: dict | None = None,
    historical_package_fingerprints: list[str] | None = None,
) -> dict:
    """U3: deterministic reducer over validated bot records."""
    normalized = [_normalize_bot_record(record) for record in records]
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for record in normalized:
        key = (
            record["kind"],
            _stable_json(record["target"]),
            _record_primary_evidence(record),
        )
        groups.setdefault(key, []).append(record)
    merged = [_merge_bot_records(groups[key]) for key in sorted(groups)]

    clusters_by_key: dict[tuple[str, str], list[str]] = {}
    contradictions: list[dict] = []
    for finding in merged:
        clusters_by_key.setdefault(_cluster_key(finding), []).append(finding["record_id"])
        if "contradiction" in finding["kind"] or "contradiction" in finding.get("tags", []):
            contradictions.append({
                "id": "ctr:" + content_id(finding["record_id"], 12),
                "subject": finding["target"]["id"],
                "finding_id": finding["record_id"],
                "current_confidence": finding["confidence"],
                "recommended_resolution": _recommended_command(finding),
                "evidence_refs": [ev.get("name") or ev["type"] for ev in finding["evidence"]],
            })
    clusters: list[dict] = []
    for idx, key in enumerate(sorted(clusters_by_key), start=1):
        axis, value = key
        finding_ids = sorted(clusters_by_key[key])
        clusters.append({
            "cluster_id": f"cluster:{idx}",
            "axis": axis,
            "key": value,
            "finding_ids": finding_ids,
        })
    cluster_lookup = {fid: [] for fid in [f["record_id"] for f in merged]}
    for cluster in clusters:
        for fid in cluster["finding_ids"]:
            cluster_lookup.setdefault(fid, []).append(cluster["cluster_id"])

    historical_hits = set(historical_package_fingerprints or [])
    for finding in merged:
        recurrence = 1 if finding["record_id"] in historical_hits else 0
        blast = _blast_radius(finding, repo_graph_metrics)
        contradiction_density = 1 if any(c["finding_id"] == finding["record_id"] for c in contradictions) else 0
        bot_count = max(1, finding.get("bot_count", 1))
        rank = (
            finding["severity_rank"] * 1000
            + int(round(finding["confidence"] * 100))
            + int(round(blast * 100))
            + bot_count * 10
            + contradiction_density * 5
            + recurrence * 5
        )
        finding["rank"] = rank
        finding["blast_radius"] = round(blast, 4)
        finding["cluster_ids"] = sorted(cluster_lookup.get(finding["record_id"], []))

    merged.sort(key=lambda r: (-r["rank"], -r["severity_rank"], r["record_id"]))
    anomaly_cards = []
    for finding in merged[: min(8, len(merged))]:
        anomaly_cards.append({
            "card_id": "card:" + finding["record_id"].split(":", 1)[1],
            "title": finding["summary"],
            "severity": finding["severity"],
            "why_it_matters": (
                f"{finding['kind']} on {finding['target']['id']} surfaced by "
                f"{len(finding['contributing_bots'])} bot(s)"
            ),
            "drilldown_links": {
                "file": finding["links"].get("file"),
                "symbol": finding["links"].get("symbol"),
                "tests": list(finding["links"].get("tests", [])),
                "artifacts": list(finding["links"].get("artifacts", [])),
            },
            "finding_id": finding["record_id"],
        })

    top_findings = [{
        "finding_id": finding["record_id"],
        "summary": finding["summary"],
        "severity": finding["severity"],
        "confidence": finding["confidence"],
        "rank": finding["rank"],
        "read": _recommended_read(finding),
        "command": _recommended_command(finding),
    } for finding in merged[: min(10, len(merged))]]

    review_packet = {
        "schema": "lgwks.review.packet.v1",
        "top_findings": top_findings,
        "clusters": clusters,
        "open_contradictions": contradictions,
        "recommended_next_reads": _dedupe_strings([row["read"] for row in top_findings])[:10],
        "recommended_next_commands": _dedupe_strings([row["command"] for row in top_findings])[:10],
    }

    return {
        "findings_normalized": merged,
        "clusters": clusters,
        "anomaly_cards": anomaly_cards,
        "review_packet": review_packet,
    }


def build_jepa_package(
    reduced: dict,
    *,
    repo: str,
    plan_id: str,
    world_db_bindings: list[str] | None = None,
    prior_package_refs: list[str] | None = None,
    human_dump: str = "",
) -> dict:
    """U4: build one canonical JEPA package from reducer outputs."""
    findings = list(reduced.get("findings_normalized", []))
    clusters = list(reduced.get("clusters", []))
    review_packet = dict(reduced.get("review_packet", {}))
    anomaly_cards = list(reduced.get("anomaly_cards", []))
    world_refs = _dedupe_strings(list(world_db_bindings or []))
    for finding in findings:
        for ref in finding.get("world_refs", []):
            world_refs.append(f"wdb:{ref['kind']}:{ref['id']}")
    world_refs = _dedupe_strings(world_refs)

    anchors: list[dict] = []
    seen_anchor_keys: set[tuple[str, str]] = set()
    for finding in findings[:10]:
        for kind, value in (
            ("file", finding["links"].get("file")),
            ("symbol", finding["links"].get("symbol")),
            (finding["target"]["kind"], finding["target"]["id"]),
        ):
            if _is_nonempty_str(value):
                key = (kind, value)
                if key not in seen_anchor_keys:
                    seen_anchor_keys.add(key)
                    anchors.append({"kind": kind, "id": value})
        for ref in finding.get("world_refs", []):
            key = (ref["kind"], ref["id"])
            if key not in seen_anchor_keys:
                seen_anchor_keys.add(key)
                anchors.append({"kind": ref["kind"], "id": ref["id"]})

    contradiction_records = list(review_packet.get("open_contradictions", []))
    package_seed = {
        "repo": repo,
        "plan_id": plan_id,
        "finding_ids": [f["record_id"] for f in findings],
        "cluster_ids": [c["cluster_id"] for c in clusters],
        "prior": prior_package_refs or [],
    }
    package_id = "pkg:" + content_id(_stable_json(package_seed))

    links_index = {
        "schema": "lgwks.links.index.v1",
        "package_id": package_id,
        "findings": {
            finding["record_id"]: {
                "file": finding["links"].get("file"),
                "symbol": finding["links"].get("symbol"),
                "tests": list(finding["links"].get("tests", [])),
                "artifacts": list(finding["links"].get("artifacts", [])),
            }
            for finding in findings
        },
    }

    machine_packet = {
        "schema": "lgwks.machine.packet.v1",
        "package_id": package_id,
        "top_anchors": anchors[:10],
        "ranked_findings": [
            {
                "finding_id": finding["record_id"],
                "summary": finding["summary"],
                "severity": finding["severity"],
                "confidence": finding["confidence"],
                "rank": finding["rank"],
            }
            for finding in findings[:10]
        ],
        "contradictions": contradiction_records,
        "recommended_reads": list(review_packet.get("recommended_next_reads", [])),
        "recommended_commands": list(review_packet.get("recommended_next_commands", [])),
        "prior_package_refs": list(prior_package_refs or []),
    }

    human_summary = {
        "schema": "lgwks.human.summary.v1",
        "package_id": package_id,
        "anomaly_cards": anomaly_cards,
        "top_blocks": [
            {
                "cluster_id": cluster["cluster_id"],
                "axis": cluster["axis"],
                "key": cluster["key"],
                "finding_count": len(cluster["finding_ids"]),
            }
            for cluster in clusters[:10]
        ],
        "drilldown_links": links_index["findings"],
        "what_changed": [finding["summary"] for finding in findings[:5]],
        "what_matters_now": review_packet.get("recommended_next_reads", [])[:5],
        "human_dump": human_dump[:500],
    }

    package = {
        "schema": "lgwks.jepa.package.v1",
        "package_id": package_id,
        "plan_id": plan_id,
        "repo": repo,
        "anchors": anchors,
        "clusters": [cluster["cluster_id"] for cluster in clusters],
        "contradictions": [record["id"] for record in contradiction_records],
        "world_refs": world_refs,
        "next_actions": list(review_packet.get("recommended_next_commands", [])),
        "synth_ready": False,
    }

    return {
        "package": package,
        "machine_packet": machine_packet,
        "contradictions": contradiction_records,
        "human_summary": human_summary,
        "links_index": links_index,
    }


def evaluate_artifact_strength(
    review_packet: dict,
    package: dict,
    machine_packet: dict,
    links_index: dict,
    *,
    synth_status: str,
) -> dict:
    """U11: verify that the package is actionable without synth."""
    top_findings = list(review_packet.get("top_findings", []))
    finding_links = dict(links_index.get("findings", {}))
    contradictions = list(machine_packet.get("contradictions", []))
    next_steps = list(machine_packet.get("recommended_reads", [])) + list(machine_packet.get("recommended_commands", []))

    ranked_findings = bool(top_findings) and all(
        _is_nonempty_str(item.get("severity")) and item.get("confidence") is not None
        for item in top_findings
    )
    drilldown = True
    for item in top_findings:
        refs = finding_links.get(item.get("finding_id", ""), {})
        has_link = bool(
            _is_nonempty_str(refs.get("file"))
            or _is_nonempty_str(refs.get("symbol"))
            or refs.get("tests")
            or refs.get("artifacts")
        )
        if not has_link:
            drilldown = False
            break
    contradictions_ok = all(
        _is_nonempty_str(item.get("subject"))
        and isinstance(item.get("evidence_refs"), list)
        and _is_nonempty_str(item.get("recommended_resolution"))
        for item in contradictions
    )
    next_steps_ok = any(_is_nonempty_str(step) for step in next_steps)
    prose_dependency = bool(package.get("anchors")) and all(item.get("finding_id") in finding_links for item in top_findings)
    degraded_mode = synth_status in {"skipped", "unavailable", "complete"}

    checks = {
        "ranked_findings": ranked_findings,
        "drilldown": drilldown,
        "contradictions": contradictions_ok,
        "next_steps": next_steps_ok,
        "prose_dependency": prose_dependency,
        "degraded_mode": degraded_mode,
    }
    passed = all(checks.values())
    return {
        "schema": "lgwks.artifact.strength.v1",
        "package_id": package.get("package_id", ""),
        "pass": passed,
        "checks": checks,
        "actionable_without_synth": passed and synth_status in {"skipped", "unavailable", "complete"},
        "synth_status": synth_status,
    }
