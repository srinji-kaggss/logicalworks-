"""Golden-trajectory gate for lgwks_research.run_auto (R6.3 prerequisite + net).

`run_auto` is the autonomous research loop (a ~385-line round loop carrying rolling
state: budget, rolling digest, prev_hash chain, agenda cursor, frontier, dry/converge
streaks, covered set). The Pristine Program (R6.3) extracts its per-round body into a
`_run_round(state)` helper — the one flagged behavior-change risk. This test PINS the
loop's observable trajectory so that extraction (or any future edit) is proven behavior-
preserving rather than merely "tests still import".

Determinism harness: the Tongue (model tier) and `_crawl` (network) are monkeypatched
so the whole loop runs offline and deterministically via the announced skeleton path
(degrade_consent=True). Two trajectories are pinned, exercising distinct break paths:
  A. agenda walk → drain → EIG expansion → frontier-dry stop (planning rounds, chain).
  B. budget exhausted on the first charge → early budget_exhausted stop.

If a refactor changes round count, stop reason, surviving set, spend, agenda coverage,
the guide-verdict tally, or the ledger chain, this gate goes red.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_research as R
import lgwks_substrate_config as cfg_mod
import lgwks_tongue as T

# A fixed two-question agenda (model-emitted plan, here pinned). Nodes are plain
# alnum so the _agenda_node injection-guard keeps both (verified: agenda_total == 2).
_AGENDA = {
    "summary": "s",
    "agenda": [
        {"id": "Q1", "node": "alpha", "question": "is alpha true", "why": "derisk a"},
        {"id": "Q2", "node": "beta", "question": "is beta true", "why": "derisk b"},
    ],
}


def _run(td: str, *, token_budget: int, max_rounds: int = 3):
    """Drive run_auto fully offline/deterministically; return (AutoResult, result.json dict)."""
    cfg_mod.RUN_ROOT = Path(td) / "sub"
    cfg = R.AutoConfig(
        objective="probe-obj", purpose="p", start="seed",
        crawl_mode="estimate", max_rounds=max_rounds, token_budget=token_budget,
        guide_text="", fanout=1, degrade_consent=True, project="probe",
    )
    with mock.patch.object(T, "compile_research_plan", lambda *a, **k: _AGENDA), \
         mock.patch.object(T, "compile_hypotheses", lambda *a, **k: None), \
         mock.patch.object(T, "reason_over_findings", lambda *a, **k: None), \
         mock.patch.object(T, "contrarian", lambda *a, **k: None), \
         mock.patch.object(R, "_crawl", lambda cfg, frontier: ("", False, [])):
        res = R.run_auto(cfg, emit=lambda *a: None)
    rj = json.loads((Path(res.out_dir) / "result.json").read_text(encoding="utf-8"))
    return res, rj


class TestRunAutoGoldenTrajectory(unittest.TestCase):
    def setUp(self):
        self._orig_root = cfg_mod.RUN_ROOT
        self.addCleanup(lambda: setattr(cfg_mod, "RUN_ROOT", self._orig_root))

    def test_frontier_dry_trajectory(self):
        """Planning rounds: agenda walk → drain → EIG expansion → frontier-dry stop."""
        with tempfile.TemporaryDirectory() as td:
            res, rj = _run(td, token_budget=1_000_000)
        self.assertEqual(res.rounds, 3)
        self.assertEqual(res.stop_reason, "frontier_dry")
        self.assertEqual(res.surviving, ["H0", "H1"])
        self.assertEqual(res.spent, 20_000)
        self.assertTrue(res.ledger_intact)
        self.assertEqual(res.integrity_mode, "unanchored")
        # result.json product signal
        self.assertEqual(rj["evidence_rounds"], 0)
        self.assertEqual(rj["agenda_total"], 2)
        self.assertEqual(rj["agenda_covered"], 2)
        self.assertEqual(rj["guide_verdicts"], {"supported": 0, "contradicted": 0, "unverified": 2})
        self.assertEqual(
            rj["plan_summary"],
            "0 supported · 0 contradicted · 2 unverified  (of 2 guide assumptions)",
        )
        self.assertTrue(rj["chain_consistent"])

    def test_trajectory_is_deterministic(self):
        """Two independent runs produce byte-identical result.json (ignoring run_id)."""
        with tempfile.TemporaryDirectory() as td1:
            _, rj1 = _run(td1, token_budget=1_000_000)
        with tempfile.TemporaryDirectory() as td2:
            _, rj2 = _run(td2, token_budget=1_000_000)
        rj1.pop("run_id", None)
        rj2.pop("run_id", None)
        self.assertEqual(rj1, rj2)

    def test_budget_exhausted_trajectory(self):
        """Budget exhausts on the first charge → early budget_exhausted stop after 1 round."""
        with tempfile.TemporaryDirectory() as td:
            res, _ = _run(td, token_budget=1)
        self.assertEqual(res.rounds, 1)
        self.assertEqual(res.stop_reason, "budget_exhausted")
        self.assertEqual(res.surviving, [])
        self.assertEqual(res.spent, 2_000)
        self.assertTrue(res.ledger_intact)


if __name__ == "__main__":
    unittest.main()
