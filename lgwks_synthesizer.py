"""
lgwks_synthesizer — U9/U9A: LLM reasoning layer & Apple-native/cloud synthesis seam.

Consumes a JEPA package, evaluates residual claims, tracks L-budgets,
logs call metrics, and handles graceful fallbacks.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Optional, Any

import lgwks_project_artifacts as artifacts


from lgwks_clock import now_iso as _ts  # one source of truth for timestamps


def _write_meter(repo_path: Path, record: dict) -> None:
    """Log synthesis metadata to store/synth-meter.jsonl.

    Hardening (#154 M9): serialize concurrent appends with an exclusive file
    lock so interleaved writes from parallel synthesis runs cannot tear a JSONL
    line and silently corrupt the meter (matches the cognition-log pattern).
    """
    meter_file = repo_path / "store" / "synth-meter.jsonl"
    meter_file.parent.mkdir(parents=True, exist_ok=True)
    with meter_file.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def run_synthesis(
    input_data: dict,
    *,
    strength_gate: dict,
) -> dict:
    """
    Run the synthesis phase on a pre-solved package.

    Args:
        input_data: dict conforming to lgwks.synth.input.v1.
        strength_gate: dict output from artifacts.evaluate_artifact_strength.
    """
    repo_path = Path(input_data.get("repo", ".")).resolve()
    package_id = input_data.get("package_id", "unknown")
    l_budget = input_data.get("l_budget", 0.15)

    # 1. Check U11 artifact strength gate first
    if not strength_gate.get("pass", False):
        return {
            "synth_status": "skipped",
            "reason": "artifact_strength_gate_failed",
            "checks": strength_gate.get("checks", {}),
        }

    # 2. Test mock mode. Real reasoning availability is decided by the ONE model
    # gateway downstream (it defers/hands-off cleanly when no synchronous provider is
    # reachable → the cloud branch's None-handler writes the failure meter). No
    # separate network-provider gate (no rented cloud; MESH_LAW is local-only).
    is_mock = os.environ.get("LGWKS_TEST_SYNTH_MOCK") == "1"

    start_time = time.time()
    
    # 3. Simulate or execute LLM call
    if is_mock:
        # Seeded output for testing
        mock_type = os.environ.get("LGWKS_TEST_SYNTH_MOCK_TYPE", "success")
        if mock_type == "exceed_budget":
            # l_score = 2/3 = 0.66 > 0.15
            llm_response = {
                "reasoning": ["inferred that module x is coupling target y"],
                "next_actions": ["refactor x"],
                "claims": [
                    {"text": "grounded claim", "origin_type": "grounded", "basis": ["finding:1"]},
                    {"text": "invented claim A", "origin_type": "invented", "basis": []},
                    {"text": "invented claim B", "origin_type": "invented", "basis": []},
                ],
            }
        else:
            # l_score = 0/2 = 0.0
            llm_response = {
                "reasoning": ["grounded reasoning"],
                "next_actions": ["check god module"],
                "claims": [
                    {"text": "grounded claim A", "origin_type": "grounded", "basis": ["finding:1"]},
                    {"text": "grounded claim B", "origin_type": "inferred", "basis": ["cluster:1"]},
                ],
            }
        provider = "local"
        model = "mock-model"
        input_tokens = 120
        output_tokens = 80
    else:
        # Reasoning via the ONE model gateway (lgwks_tongue._generate → lgwks_model_port):
        # local mesh-law model or agent handoff, NOT a rented-cloud tongue.
        prompt = (
            f"Analyze the following code review findings and clusters for repo {input_data.get('repo')}.\n"
            f"Package ID: {package_id}\n"
            f"Findings: {json.dumps(input_data.get('ranked_findings'))}\n"
            f"Clusters: {json.dumps(input_data.get('clusters'))}\n"
            f"Contradictions: {json.dumps(input_data.get('contradictions'))}\n"
        )
        schema_hint = (
            "{ reasoning: [string], next_actions: [string], claims: [ { text: string, origin_type: 'grounded'|'inferred'|'invented', basis: [string] } ] }"
        )
        import lgwks_tongue
        response_json = lgwks_tongue._generate(prompt, schema_hint)

        if response_json is None:
            # no synchronous reasoning provider produced output → meter + unavailable
            meter_record = {
                "schema": "lgwks.synth.meter.v1",
                "package_id": package_id,
                "provider": "none",
                "model": "none",
                "input_tokens": len(prompt) // 4,
                "output_tokens": 0,
                "l_score": 0.0,
                "wall_time": time.time() - start_time,
                "status": "failed_no_provider",
                "timestamp": _ts(),
            }
            _write_meter(repo_path, meter_record)
            return {
                "synth_status": "unavailable",
                "reason": "no_provider_reachable",
            }

        llm_response = response_json
        provider = "model_port"
        model = "mesh-law"
        input_tokens = len(prompt) // 4
        output_tokens = len(json.dumps(response_json)) // 4

    wall_time = time.time() - start_time

    # 4. Calculate L score and enforce budget
    claims = llm_response.get("claims", [])
    invented_claims = [c for c in claims if c.get("origin_type") == "invented"]
    total_claims = len(claims)
    
    l_score = len(invented_claims) / total_claims if total_claims > 0 else 0.0
    l_exceeded = l_score > l_budget

    # 5. Log call to synth-meter.jsonl
    meter_record = {
        "schema": "lgwks.synth.meter.v1",
        "package_id": package_id,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "l_score": round(l_score, 4),
        "wall_time": round(wall_time, 3),
        "status": "success" if not l_exceeded else "exceeded_budget",
        "timestamp": _ts(),
    }
    _write_meter(repo_path, meter_record)

    # 6. Format and return enriched output
    if l_exceeded:
        return {
            "schema": "lgwks.synth.output.v1",
            "package_id": package_id,
            "reasoning": ["L budget exceeded: generated too many ungrounded/invented claims"],
            "next_actions": [],
            "l_score": round(l_score, 4),
            "l_exceeded": True,
            "claims": [],
            "provider": provider,
            "model": model,
        }

    # Ensure every claim has origin_type and basis
    sanitized_claims = []
    for c in claims:
        sanitized_claims.append({
            "text": c.get("text", ""),
            "origin_type": c.get("origin_type", "invented"),
            "basis": list(c.get("basis", [])),
        })

    return {
        "schema": "lgwks.synth.output.v1",
        "package_id": package_id,
        "reasoning": list(llm_response.get("reasoning", [])),
        "next_actions": list(llm_response.get("next_actions", [])),
        "l_score": round(l_score, 4),
        "l_exceeded": False,
        "claims": sanitized_claims,
        "provider": provider,
        "model": model,
    }
