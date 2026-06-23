"""Research re-binding (Director 2026-06-23): the orchestrator binds the AI as the BOUNDED director
of a DETERMINISTIC deep gather, not a per-round reasoner.

Locks the behavior that fixes "lgwks research isn't going deep":
  - DEFAULT `lgwks research <q>` runs the deep, grounded, AI-planned loop (not the old repo
    world-view that fetched nothing, and not estimate-mode that planned without fetching).
  - The AI plans the frontier once (compile_research_plan), fail-closed when offline.
  - Model offline => graceful, ANNOUNCED fallback to single-shot grounding (never silent, never
    empty-handed). --probe = world-view; --quick = single-shot.
"""
from __future__ import annotations

import argparse
from unittest import mock

import lgwks_research as r
import lgwks_tongue as t


def _args(**kw) -> argparse.Namespace:
    base = dict(prompt="quantum error correction 2025", deep=False, probe=False,
                quick=False, live=False, sources=8, rounds=12, budget=200_000,
                repo=".", json=True)
    base.update(kw)
    return argparse.Namespace(**base)


def test_planner_fails_closed_on_empty():
    assert t.compile_research_plan("") is None
    assert t.compile_research_plan("   ") is None


def test_default_routes_to_grounded_deep_loop():
    captured = {}

    def fake_run_auto(cfg, emit=print):
        captured["cfg"] = cfg
        return r.AutoResult(run_id="x", rounds=3, stop_reason="max_rounds", surviving=[],
                            spent=6000, out_dir="/tmp/x", ledger_intact=True, integrity_mode="ok")

    with mock.patch("lgwks_research.run_auto", fake_run_auto):
        rc = r.research_command(_args())
    assert rc == 0
    cfg = captured["cfg"]
    assert cfg.crawl_mode == "ground", "deep must ALWAYS ground (no estimate-mode trap)"
    assert cfg.max_rounds == 12 and cfg.max_pages == 8  # scaled-but-bounded defaults


def test_tongue_offline_degrades_to_grounding_announced(capsys):
    """Model offline => the loop fails closed, then we fall back to single-shot grounding with a
    printed notice (announced, not silent) instead of leaving the user empty-handed."""
    off = r.AutoResult(run_id="x", rounds=1, stop_reason="tongue_offline", surviving=[],
                       spent=2000, out_dir="/tmp/x", ledger_intact=True, integrity_mode="ok")
    ground_called = {}

    def fake_ground(query, want_docs=True, want_web=True, read_top=3):
        ground_called["read_top"] = read_top
        return {"query": query, "docs": "d", "web": "w", "sources": ["docs", "web"],
                "doc_sources": ["http://x"], "has_evidence": True}

    with mock.patch("lgwks_research.run_auto", return_value=off), \
         mock.patch("lgwks_ground.ground", fake_ground), \
         mock.patch("lgwks_ground.as_findings", return_value="FINDINGS"):
        rc = r.research_command(_args())
    assert rc == 0
    assert ground_called, "must fall back to grounding when the model is offline"
    assert ground_called["read_top"] == 8  # depth lever threaded from --sources
    err = capsys.readouterr().err
    assert "reasoning model offline" in err  # announced, never silent (constitution)


def test_quick_is_single_shot_no_loop():
    with mock.patch("lgwks_research.run_auto") as ra, \
         mock.patch("lgwks_ground.ground", return_value={
             "query": "q", "docs": "", "web": "w", "sources": ["web"],
             "doc_sources": ["http://x"], "has_evidence": True}), \
         mock.patch("lgwks_ground.as_findings", return_value="F"):
        rc = r.research_command(_args(quick=True))
    assert rc == 0
    ra.assert_not_called()  # --quick must NOT run the autonomous loop


def test_probe_is_worldview_no_fetch():
    with mock.patch("lgwks_research.run_auto") as ra, \
         mock.patch("lgwks_session.session_begin", return_value={"ok": True}), \
         mock.patch("lgwks_engine.run_engine", return_value={"ok": True}):
        rc = r.research_command(_args(probe=True))
    assert rc == 0
    ra.assert_not_called()  # --probe is the local world-view, never the loop
