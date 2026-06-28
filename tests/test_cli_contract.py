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
    "research", "crawl", "review", "repo", "graph", "agent", "gate", "state",
    "ops", "doctor", "model-hub", "manifest", "extract", "convert",
    "auth", "fetch", "verify", "human", "solve",
    # Restored (2026-06-24): `refactor` was shipped in 8bc4485 ("feat: implement
    # refactor, diff, local LLM...") alongside a complete lgwks_refactor.py
    # (refactor_command + add_parser) but got un-wired in the 7bf1eb6 "CLI Layering
    # and Audit Cleanup" — the module stayed, the verb vanished. The agent entrypoint
    # skill documents `lgwks refactor` and the product's mission is a local-first
    # replacement for paid refactor tools (Cursor/Sourcegraph). Re-surfacing it is a
    # deliberate capability restoration, not accidental regrowth — this entry records
    # the decision the no-regrowth gate exists to force.
    "refactor",
    # Added (2026-06-25, epic #335 / S3 #338): `models` is the ONE selector across
    # the model locality axis — local Mesh (MESH_LAW) ⊕ cloud models.dev ⊕ reserved
    # Aetherius — list/get/use/locality. It is the single user-facing entrypoint for
    # the two-plane model layer the TUI projects; there was no prior selection verb
    # (`model-hub` manages local weights, a different concern). The raw cloud catalog
    # (lgwks_models_dev) is deliberately NOT a second top-level verb — it is reached
    # via `models list --provider X`. A budgeted, deliberate addition, not regrowth.
    "models",
}
# Collapsed into canonical grouped forms; served by deprecation shim (warn+rewrite).
SHIMMED_VERBS = {"run": "state run", "context": "state context", "agent-os": "ops agent-os"}
# Two-token legacy paths whose subcommands fold onto an existing canonical verb.
# `jarvis crawl` == `crawl --engine legacy` (crawl_command delegates to it);
# `jarvis remap-db` == `crawl --remap-db`. The parent verb (`jarvis`) is gone
# from the top-level surface; the 2-token deprecation shim rewrites callers.
SHIMMED_SUBVERBS = {("jarvis", "crawl"): "crawl", ("jarvis", "remap-db"): "crawl --remap-db"}
_SUBSHIM_PARENTS = {parent for parent, _ in SHIMMED_SUBVERBS}
# Hard-removed: were thin aliases of `research` (probe's help was even false).
# route/do/wf-run/x = the four overlapping front doors collapsed into one `agent`
# door (#255 phase 2). No faithful argv shim (subcommand semantics differ); they
# hard-error with argparse, pointing callers at `agent`.
REMOVED_VERBS = {"begin", "probe", "route", "do", "wf-run", "x"}


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
    for gone in REMOVED_VERBS | set(SHIMMED_VERBS) | _SUBSHIM_PARENTS:
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


def test_agent_is_the_front_door():
    """The single agentic entrypoint maps NL intent -> typed plan and refuses
    to auto-execute mutations (safety membrane S1)."""
    proc = _run("agent", "delete all the logs", "--act")
    assert proc.returncode != 0, "mutation intent must not auto-execute / report ok"
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.agent.v1"
    assert payload["blocked"] is True
    assert payload["plan"]["effect_class"] == "write"


def test_run_demo_shortcut_still_works():
    proc = _run("run", "--demo")
    assert proc.returncode == 0, proc.stderr
    assert "run demo-crm" in proc.stdout


def test_model_hub_list_shortcut_still_works():
    proc = _run("model-hub", "list")
    assert proc.returncode == 0, proc.stderr
    assert "ModernBERT" in proc.stdout


def test_crawl_estimate_is_machine_parseable_json():
    """Canonical crawl emits a parseable estimate (formerly `jarvis crawl`)."""
    proc = _run("crawl", "https://example.com", "--engine", "legacy", "--estimate-only")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["estimated_seconds"] > 0


def test_jarvis_subverbs_shim_warns_and_delegates_then_parent_is_gone():
    """`jarvis crawl` / `jarvis remap-db` are rewritten onto `crawl` (warn+delegate),
    keeping stdout clean JSON; the bare `jarvis` parent no longer exists."""
    # subcommand still works, stdout stays pure JSON, warning on stderr
    proc = _run("jarvis", "crawl", "https://example.com", "--estimate-only")
    assert proc.returncode == 0, proc.stderr
    assert "deprecated" in proc.stderr and "crawl" in proc.stderr
    assert json.loads(proc.stdout)["estimated_seconds"] > 0
    # bare parent verb is removed from the surface
    bare = _run("jarvis")
    assert bare.returncode != 0
    assert "invalid choice" in bare.stderr or "invalid choice" in bare.stdout


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


def test_agent_worldview_ranks_pathways():
    """`route map` ranking folded into the agent worldview (perceive): the
    top pathway for a research intent is the daemon research path."""
    proc = _run("agent", "research a website and build graph", "--explain", "--top", "3")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "lgwks.agent.v1"
    assert payload["worldview"]["pathways"][0] == "ops daemon research"


def test_agent_worldview_carries_subconscious_schema():
    """`route engine` (subconscious schema) folded into the agent worldview:
    C/G/P scores + pathways are present in the perceive payload."""
    proc = _run("agent", "research a website and build graph", "--explain", "--top", "3")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    wv = payload["worldview"]
    assert "scores" in wv["insights"]
    assert wv["pathways"][0] == "ops daemon research"


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
