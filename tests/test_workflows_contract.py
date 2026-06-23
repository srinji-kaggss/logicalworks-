from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import lgwks_manifest
import lgwks_workflows


ROOT = Path(__file__).resolve().parents[1]
LGWKS = ROOT / "lgwks"


def _run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LGWKS), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "LGWKS_NO_MODELS": "1"},
    )


def test_extract_and_convert_are_public_cli_verbs(tmp_path: Path):
    sample = tmp_path / "sample.txt"
    sample.write_text("alpha beta", encoding="utf-8")

    extracted = _run("extract", str(sample), "--json")
    assert extracted.returncode == 0, extracted.stderr
    payload = json.loads(extracted.stdout)
    assert payload["ok"] is True
    assert "alpha beta" in payload["text"]

    converted = _run("convert", str(sample), "--to", "json")
    assert converted.returncode == 0, converted.stderr
    converted_payload = json.loads(converted.stdout)
    assert "alpha beta" in converted_payload["text"]


def test_workflow_health_check_json_is_single_workflow_object():
    proc = _run("ops", "workflow", "health-check", "--json")
    # health-check returns 0 when the env is healthy and 2 when degraded (e.g. no
    # browser installed, as on a clean CI runner) — both are valid outcomes with an
    # identical JSON contract. Assert the contract + that the process exit code
    # reflects the reported verdict, NOT that the host happens to have a browser.
    assert proc.returncode in (0, 2), proc.stderr
    payload = json.loads(proc.stdout)
    assert proc.returncode == payload["exit_code"]
    assert payload["schema"] == "lgwks.workflow.run.v1"
    assert payload["workflow"] == "health-check"
    assert [p["name"] for p in payload["phases"]] == ["doctor:env", "manifest:sanity"]


def test_quick_scan_zero_documents_fails_closed(monkeypatch, capsys):
    import lgwks_substrate

    def fake_build_run(_args):
        return {
            "run_id": "zero-docs",
            "artifacts": {"root": str(ROOT / "store" / "substrate" / "zero-docs")},
            "counts": {
                "sources": 0,
                "documents": 0,
                "chunks": 0,
                "facts": 0,
                "frontier": 1,
                "graph_nodes": 0,
                "graph_edges": 0,
            },
        }

    monkeypatch.setattr(lgwks_substrate, "build_run", fake_build_run)
    rc = lgwks_workflows._do_quick_scan(argparse.Namespace(
        query="https://example.invalid",
        json=True,
        max_chars=100,
        engine="chromium",
        no_session=True,
    ))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["verdict"] == "degraded"
    assert payload["phases"][-1]["ok"] is False
    assert payload["phases"][-1]["exit_code"] == 2


def test_workflow_extract_returns_workflow_schema(tmp_path: Path):
    sample = tmp_path / "sample.txt"
    sample.write_text("workflow extraction", encoding="utf-8")

    proc = _run("ops", "workflow", "extract", str(sample), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.workflow.run.v1"
    assert payload["workflow"] == "extract"
    assert payload["phases"][0]["artifact"]["text"] == "workflow extraction"


def test_workflow_registry_verbs_resolve_to_live_manifest_verbs():
    live = {entry["verb"] for entry in lgwks_manifest.build_manifest()["verbs"]}
    missing = sorted({
        verb
        for meta in lgwks_workflows._WORKFLOWS.values()
        for verb in meta["verbs"]
        if verb not in live
    })
    assert missing == []


# test_wf_run_accepts_json_output removed: the `wf-run` top-level verb is retired
# (#255 phase 2). Named workflows now trigger through the single `agent` door; the
# Ruby-DSL string input is intentionally dropped. test_cli_contract.REMOVED_VERBS
# asserts `wf-run` hard-errors.
