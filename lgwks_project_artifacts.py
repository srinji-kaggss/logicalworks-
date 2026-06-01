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
