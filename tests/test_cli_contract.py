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


# ── Orchestration surface contract (no-regrowth gate) ──────────────────────
# The canonical top-level verb set. Adding a verb without updating this set
# fails the gate on purpose: every top-level verb is a distinct intent label in
# the cortex training stream, so surface growth must be a deliberate decision,
# not an accident. Removing a verb here must be matched by a deprecation shim
# (see _DEPRECATED_VERBS in `lgwks`) or a hard-removal record below.
CANONICAL_VERBS = {
    "research", "crawl", "review", "repo", "graph", "route", "gate", "state",
    "ops", "doctor", "model-hub", "jarvis", "manifest", "extract", "convert",
    "auth", "fetch", "verify", "human", "solve", "do", "wf-run", "x",
}
# Collapsed into canonical grouped forms; served by deprecation shim (warn+rewrite).
SHIMMED_VERBS = {"run": "state run", "context": "state context", "agent-os": "ops agent-os"}
# Hard-removed: were thin aliases of `research` (probe's help was even false).
REMOVED_VERBS = {"begin", "probe"}


def _top_level_verbs() -> set[str]:
    proc = _run("--help")
    assert proc.returncode == 0
    # argparse prints the choice set as {a,b,c} on the usage line(s).
    import re
    m = re.search(r"\{([a-z0-9,_-]+)\}", proc.stdout)
    assert m, f"could not parse verb set from help:\n{proc.stdout}"
    return set(m.group(1).split(","))


def test_top_level_surface_matches_canonical_set_no_regrowth():
    """Verb-budget gate: the top-level surface is exactly CANONICAL_VERBS.

    Fails on regrowth (a new verb nobody approved) AND on silent loss."""
    verbs = _top_level_verbs()
    extra = verbs - CANONICAL_VERBS
    missing = CANONICAL_VERBS - verbs
    assert not extra, f"verb surface regrew (un-budgeted top-level verbs): {sorted(extra)}"
    assert not missing, f"canonical verbs disappeared: {sorted(missing)}"


def test_collapsed_aliases_are_not_top_level():
    """begin/probe (removed) and run/context/agent-os (shimmed) must not pollute
    the canonical surface — they are no longer distinct top-level intent labels."""
    verbs = _top_level_verbs()
    for gone in REMOVED_VERBS | set(SHIMMED_VERBS):
        assert gone not in verbs, f"{gone!r} is still a top-level verb after collapse"


def test_hard_removed_verbs_error():
    for gone in REMOVED_VERBS:
        proc = _run(gone, "anything")
        assert proc.returncode != 0, f"{gone!r} should be hard-removed but exited 0"
        assert "invalid choice" in proc.stderr or "invalid choice" in proc.stdout


def test_deprecation_shim_warns_and_delegates():
    """`lgwks run`/`context`/`agent-os` still work but warn and rewrite to the
    canonical grouped command (preserves legacy callers; one migration nudge)."""
    proc = _run("run", "--demo")
    assert proc.returncode == 0, proc.stderr
    assert "deprecated" in proc.stderr and "state run" in proc.stderr
    assert "run demo-crm" in proc.stdout  # delegated payload is unchanged


def test_route_act_is_the_front_door():
    """The single agentic entrypoint maps NL intent -> typed action and refuses
    to auto-execute mutations (safety membrane)."""
    proc = _run("route", "act", "delete all the logs", "--dry-run")
    assert proc.returncode != 0, "mutation intent must not report ok"
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.route.act.v1"
    assert payload["blocked"] is True
    assert payload["action"]["effect_class"] == "write"


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


def test_manifest_shortcut_is_parseable_json():
    proc = _run("manifest")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["manifest"] == "lgwks.manifest.v0"
    assert payload["verbs"]


def test_route_map_uses_live_manifest_contract():
    proc = _run("route", "map", "research a website and build graph", "--top", "3")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.map.v1"
    assert payload["verb_count"] > 0
    assert payload["matches"][0]["verb"] == "ops daemon research"
    assert payload["matches"][0]["intent"] != "(no metadata)"


def test_route_engine_dispatches_to_subconscious_engine():
    proc = _run("route", "engine", "research a website and build graph", "--top", "3")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.engine.schema.v1"
    assert payload["pathways"][0] == "ops daemon research"


def test_state_cortex_index_builds_trajectory(tmp_path: Path):
    """The transcript->trajectory step is CLI-reachable (was orphaned: index_command
    had no parser). Feeds the PRD-06 cortex / training-data pipeline."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "map the codebase"}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "done"}}) + "\n",
        encoding="utf-8",
    )
    proc = _run("state", "cortex", "index", str(transcript),
                "--session-id", "contract-cortex", "--repo", str(tmp_path), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.cortex.index.v1"
    assert payload["ok"] is True
    assert (tmp_path / "store" / "cortex" / "contract-cortex.cortex.jsonl").exists()
