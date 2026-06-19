from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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


def test_documented_shortcuts_are_registered():
    proc = _run("--help")
    assert proc.returncode == 0
    for command in ("agent-os", "run", "context", "model-hub", "jarvis", "auth", "fetch"):
        assert command in proc.stdout


def test_run_demo_shortcut_still_works():
    proc = _run("run", "--demo")
    assert proc.returncode == 0, proc.stderr
    assert "run demo-crm" in proc.stdout


def test_model_hub_list_shortcut_still_works():
    proc = _run("model-hub", "list")
    assert proc.returncode == 0, proc.stderr
    assert "ModernBERT" in proc.stdout


def test_jarvis_estimate_shortcut_is_machine_parseable_json():
    proc = _run("jarvis", "crawl", "https://example.com", "--estimate-only")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["estimated_seconds"] > 0


def test_context_accepts_documented_positional_run_dir(tmp_path: Path):
    run_dir = tmp_path / "run"
    round_dir = run_dir / "round-001"
    round_dir.mkdir(parents=True)
    (run_dir / "rounds.ledger.jsonl").write_text(
        json.dumps({
            "n": 1,
            "surviving": ["a"],
            "falsifiers_hit": [],
            "frontier_in": "seed",
            "digest": "first digest",
            "learnings": ["first learning"],
        }) + "\n",
        encoding="utf-8",
    )
    (round_dir / "reason.json").write_text("{}", encoding="utf-8")
    (round_dir / "think.md").write_text("thinking", encoding="utf-8")

    proc = _run("context", str(run_dir), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert Path(payload["path"]).exists()
