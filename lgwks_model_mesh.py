"""lgwks_model_mesh — model law rendered as a single queryable manifest (#119).

A "mesh" is not code and not a model. It is the **model law as data** — the way
`docs/navmap/index.json` renders the module atlas, this renders the model-stack
law (`spec/second-harness/MODEL-RUNTIME-FINALIZATION-2026-06-13.md` §3/§3.1/§3.2)
into one artifact so doctor / routing / reporting read a single source of truth.

CRITICAL CONSTRAINT (spec §3 lines 10-12, acceptance bullet): this contract
**records inventory; it does not change it.** No new default, no new selection,
no model load. `MESH_LAW` below is transcribed verbatim from §3.1 (current law)
and §3.2 (open slots); building/reading the mesh imports no model package and
touches no `store/models/` weights.

Locked public join keys (read by #120/#122 and the future LogicGPT-1 promotion
path, spec §5): `role`, `trust_class`, `input_schema`, `output_schema`,
`eval_gate`. Everything else (`health`, `notes`, `fallback`) is additive telemetry.
"""

from __future__ import annotations

import json
from typing import Any

SCHEMA = "lgwks.model.mesh.v1"

# Allowed vocabularies (supersets are additive; do not narrow without a bump).
RUNTIMES = frozenset({"mlx", "transformers", "ollama", "coreml", "llama_cpp", "provider_seam"})
LOCALITIES = frozenset({"local", "cloud"})
ROLES = frozenset({"embed", "intent", "classify", "extract", "salience", "rerank", "asr", "proposal", "code"})
TRUST_CLASSES = frozenset({"deterministic", "sensor", "generative"})
STATUSES = frozenset({"current_law", "open_slot", "candidate_reference"})
HEALTH_STATUSES = frozenset({"unknown", "ok", "degraded", "down"})
EVAL_STATUSES = frozenset({"passed", "pending", "none"})


def _health_unknown() -> dict[str, Any]:
    """Default health for a descriptive entry — doctor populates this at runtime."""
    return {"status": "unknown", "latency_ms_p50": None, "last_checked": None}


def _entry(
    *,
    name: str | None,
    runtime: str | None,
    locality: str | None,
    role: str,
    trust_class: str | None,
    status: str,
    input_schema: str | None = None,
    output_schema: str | None = None,
    fallback: str | None = None,
    eval_gate: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "runtime": runtime,
        "locality": locality,
        "role": role,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "trust_class": trust_class,
        "fallback": fallback,
        "health": _health_unknown(),
        "eval_gate": eval_gate,
        "status": status,
    }
    if notes is not None:
        entry["notes"] = notes
    return entry


# ── The Model Law: Workaround Hierarchy (Borrowed Cognition for Data Collection) ──
# Provenance (reconciled 2026-06-14): these models are temporary workers used
# to generate the trajectories needed to train the Standalone Aetherius Model.
MESH_LAW: list[dict[str, Any]] = [
    # TARGET: THE OWNED FOUNDATION (SCAFFOLDING)
    _entry(
        name="logicalworks/aetherius-standalone-v1", runtime="custom", locality="local", role="foundation",
        trust_class="authority", status="open_slot",
        notes="The future proprietary core. Will eventually unify all roles below.",
    ),

    # WORKAROUND 1: UNIVERSAL MULTIMODAL EYE (BORROWED)
    _entry(
        name="Qwen/Qwen3-VL-Embedding-8B", runtime="mlx", locality="local", role="embed",
        input_schema="lgwks.modality.item.v1", output_schema="lgwks.vector.record.v1",
        trust_class="sensor", status="current_law",
        notes="Temporary sensor for high-fidelity multimodal data collection.",
    ),
    
    # WORKAROUND 2: DEEP REASONING TONGUE (BORROWED)
    _entry(
        name="mlx-community/Olmo-3-1125-32B-4bit", runtime="mlx", locality="local", role="proposal",
        trust_class="generative", status="current_law",
        notes="Temporary simplifier for complex state-to-language delegation.",
    ),

    # WORKAROUND 3: SPECIALIZED SENSORS (BORROWED)
    _entry(
        name="WhisperKit/lg-v3-turbo", runtime="mlx", locality="local", role="asr",
        trust_class="sensor", status="current_law",
        notes="Temporary ear layer for voice trajectory capture.",
    ),
    _entry(
        name="meta-llama/Llama-Prompt-Guard-2-86M", runtime="transformers", locality="local", role="classify",
        trust_class="sensor", status="current_law",
        notes="Temporary safety gate for training data sanitization.",
    ),
]


def build_mesh(*, generated_at: str | None = None) -> dict[str, Any]:
    """Build the model-mesh manifest from the static law. Loads NO model.

    `generated_at` is passed through verbatim (callers stamp it); kept as a param
    so tests get a deterministic artifact and the builder script supplies a clock.
    """
    mesh: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "models": [dict(entry, health=_health_unknown()) for entry in MESH_LAW],
    }
    return validate_mesh(mesh)


def validate_mesh(mesh: dict[str, Any]) -> dict[str, Any]:
    """Validate a model-mesh manifest; return it unchanged on success."""
    if not isinstance(mesh, dict):
        raise ValueError("mesh must be a dict")
    if mesh.get("schema") != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if "generated_at" not in mesh:
        raise ValueError("missing generated_at")
    models = mesh.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("models must be a non-empty list")
    for i, entry in enumerate(models):
        _validate_entry(i, entry)
    return mesh


def _opt_choice(label: str, value: Any, allowed: frozenset[str], *, nullable: bool) -> None:
    if value is None:
        if nullable:
            return
        raise ValueError(f"{label} must not be null")
    if value not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)} (got {value!r})")


def _validate_entry(i: int, entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"models[{i}] must be a dict")
    status = entry.get("status")
    _opt_choice(f"models[{i}].status", status, STATUSES, nullable=False)
    is_open = status == "open_slot"
    # name is null only for open slots / seam entries; never an empty string.
    name = entry.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError(f"models[{i}].name must be a non-empty string or null")
    if is_open and name is not None:
        raise ValueError(f"models[{i}] is an open_slot and must have name=null")
    _opt_choice(f"models[{i}].runtime", entry.get("runtime"), RUNTIMES, nullable=True)
    _opt_choice(f"models[{i}].locality", entry.get("locality"), LOCALITIES, nullable=True)
    _opt_choice(f"models[{i}].role", entry.get("role"), ROLES, nullable=False)
    _opt_choice(f"models[{i}].trust_class", entry.get("trust_class"), TRUST_CLASSES, nullable=True)
    for key in ("input_schema", "output_schema", "fallback"):
        val = entry.get(key)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"models[{i}].{key} must be a schema-id string or null")
    health = entry.get("health")
    if not isinstance(health, dict):
        raise ValueError(f"models[{i}].health must be a dict")
    _opt_choice(f"models[{i}].health.status", health.get("status"), HEALTH_STATUSES, nullable=False)
    eg = entry.get("eval_gate")
    if eg is not None:
        if not isinstance(eg, dict):
            raise ValueError(f"models[{i}].eval_gate must be a dict or null")
        _opt_choice(f"models[{i}].eval_gate.status", eg.get("status"), EVAL_STATUSES, nullable=False)


def load_mesh(path) -> dict[str, Any]:
    """Read + validate a mesh artifact from disk. Imports no model package."""
    with open(path, "r", encoding="utf-8") as fh:
        return validate_mesh(json.load(fh))
