"""Tests for lgwks_rank — I6 cubic node centrality + AI-discrepancy δ (T1–T5).

TDD: tests written first. All five map to acceptance clauses from the I6 spec
(issue #60, authority: INGESTION-LAYER §4.3).

  T1: convergence       — power iteration reaches ‖Δx‖ < 1e-9 on both eval graphs
  T2: seed-stability    — same inputs → byte-identical ranking across two runs
  T3: order-collapse    — under relation-collapse (all w_k=1, Tk summed), cubic
                          stationary order matches spectral eigenvector of collapsed
                          (summed, symmetrized) adjacency to pre-registered tolerance
  T4: delta-distribution — top-decile nodes get lane="human" on both eval graphs
  T5: determinism/replay — same tensor → identical RankRecord set
"""

from __future__ import annotations

import json
import math
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_rank
from lgwks_rank import (
    SCHEMA,
    DELTA_HUMAN_PERCENTILE,
    RankRecord,
    build_tensor,
    power_iteration,
    compute_rank_ai,
    compute_delta,
    rank_graph,
)

# ---------------------------------------------------------------------------
# Paths to eval corpora
# ---------------------------------------------------------------------------

GRAPH_LW = Path.home() / "ingestion_results" / "logicalworks-_graph" / "graph.json"
GRAPH_OS = Path.home() / "ingestion_results" / "logic-os-kernel_graph" / "graph.json"


# ---------------------------------------------------------------------------
# Synthetic deterministic fixture (used for unit tests to avoid large file I/O
# where spec allows; T1/T2 also run against real graphs)
# ---------------------------------------------------------------------------

def _make_synthetic_graph(n_nodes: int = 12, seed: int = 42) -> dict:
    """Build a small deterministic graph with all 8 relation types."""
    import random
    rng = random.Random(seed)
    relations = [
        "calls", "contains", "method", "inherits",
        "uses", "rationale_for", "imports_from", "case_of",
    ]
    nodes = [{"id": f"n{i}"} for i in range(n_nodes)]
    links = []
    # Generate ~2 edges per relation type
    for rel in relations:
        for _ in range(3):
            src = rng.randint(0, n_nodes - 1)
            tgt = rng.randint(0, n_nodes - 1)
            while tgt == src:
                tgt = rng.randint(0, n_nodes - 1)
            links.append({
                "source": f"n{src}",
                "target": f"n{tgt}",
                "relation": rel,
                "confidence_score": rng.uniform(0.5, 1.0),
                "weight": 1.0,
            })
    return {"nodes": nodes, "links": links}


class TestBuildTensor(unittest.TestCase):
    """Sanity checks on the sparse tensor builder."""

    def test_nodes_indexed(self):
        g = _make_synthetic_graph()
        node_ids, T_k = build_tensor(g)
        self.assertGreater(len(node_ids), 0)
        self.assertIsInstance(T_k, dict)

    def test_symmetrized(self):
        """T_k[i][j] == T_k[j][i] after symmetrization (directed:false)."""
        g = _make_synthetic_graph()
        node_ids, T_k = build_tensor(g)
        idx = {nid: i for i, nid in enumerate(node_ids)}
        for rel, rows in T_k.items():
            for i, cols in rows.items():
                for j, val in cols.items():
                    rev = T_k[rel].get(j, {}).get(i, 0.0)
                    self.assertAlmostEqual(val, rev, places=10,
                        msg=f"T_k[{rel}][{i}][{j}]={val} != T_k[{rel}][{j}][{i}]={rev}")

    def test_confidence_weight(self):
        """Edge weight = confidence_score from graph data."""
        g = {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{
            "source": "a", "target": "b", "relation": "calls",
            "confidence_score": 0.75, "weight": 1.0,
        }]}
        node_ids, T_k = build_tensor(g)
        idx = {nid: i for i, nid in enumerate(node_ids)}
        i, j = idx["a"], idx["b"]
        # After symmetrization: T[i][j] = T[j][i] = (0.75 + 0.0) / 2 = 0.375
        val = T_k["calls"].get(i, {}).get(j, 0.0)
        self.assertAlmostEqual(val, 0.375, places=10)


class TestPowerIteration(unittest.TestCase):
    """T1 + T2 on synthetic fixture."""

    def test_convergence_synthetic(self):
        """T1 (synthetic): power iteration converges (‖Δx‖ < 1e-9) within max_iter."""
        g = _make_synthetic_graph()
        node_ids, T_k = build_tensor(g)
        x, iters, delta = power_iteration(node_ids, T_k)
        self.assertLess(delta, 1e-9,
            f"synthetic: did not converge after {iters} iterations (‖Δx‖={delta:.2e})")
        self.assertEqual(len(x), len(node_ids))

    def test_convergence_lw_graph(self):
        """T1 (real): logicalworks- graph converges."""
        if not GRAPH_LW.exists():
            self.skipTest(f"eval graph not found: {GRAPH_LW}")
        g = json.loads(GRAPH_LW.read_text())
        node_ids, T_k = build_tensor(g)
        x, iters, delta = power_iteration(node_ids, T_k)
        self.assertLess(delta, 1e-9,
            f"lgwks graph: did not converge after {iters} iters (‖Δx‖={delta:.2e})")

    def test_convergence_os_graph(self):
        """T1 (real): logic-os-kernel graph converges."""
        if not GRAPH_OS.exists():
            self.skipTest(f"eval graph not found: {GRAPH_OS}")
        g = json.loads(GRAPH_OS.read_text())
        node_ids, T_k = build_tensor(g)
        x, iters, delta = power_iteration(node_ids, T_k)
        self.assertLess(delta, 1e-9,
            f"os graph: did not converge after {iters} iters (‖Δx‖={delta:.2e})")

    def test_seed_stability_synthetic(self):
        """T2 (synthetic): same inputs → byte-identical centrality vector."""
        g = _make_synthetic_graph()
        node_ids, T_k = build_tensor(g)
        x1, _, _ = power_iteration(node_ids, T_k)
        x2, _, _ = power_iteration(node_ids, T_k)
        self.assertEqual(x1, x2, "centrality vectors differ between runs on same input")

    def test_seed_stability_real(self):
        """T2 (real): logicalworks- graph → identical centrality both runs."""
        if not GRAPH_LW.exists():
            self.skipTest(f"eval graph not found: {GRAPH_LW}")
        g = json.loads(GRAPH_LW.read_text())
        node_ids, T_k = build_tensor(g)
        x1, _, _ = power_iteration(node_ids, T_k)
        x2, _, _ = power_iteration(node_ids, T_k)
        self.assertEqual(x1, x2, "centrality vectors differ between runs on real graph")


class TestOrderCollapse(unittest.TestCase):
    """T3: relation-collapse test (cubic stationary ~ spectral eigenvector)."""

    def _leading_eigenvector(self, n: int, adj: dict) -> list[float]:
        """Power iteration on order-2 collapsed adjacency (plain matrix)."""
        # Seed uniform
        x = [1.0 / math.sqrt(n)] * n
        for _ in range(5000):
            # y = A x
            y = [0.0] * n
            for i, cols in adj.items():
                for j, val in cols.items():
                    y[i] += val * x[j]
            norm = math.sqrt(sum(v * v for v in y))
            if norm < 1e-12:
                break
            x_new = [v / norm for v in y]
            delta = math.sqrt(sum((a - b) ** 2 for a, b in zip(x_new, x)))
            x = x_new
            if delta < 1e-12:
                break
        return x

    def test_order_collapse(self):
        """T3: under uniform w_k, cubic stationary = spectral eigenvector of summed adj.

        Tolerance: Kendall tau correlation >= 0.95 between rank orders.
        Pre-registered: 0.95 (top-level rank agreement; absolute vector may differ by sign).
        """
        g = _make_synthetic_graph(n_nodes=20, seed=7)
        node_ids, T_k = build_tensor(g)
        n = len(node_ids)

        # Cubic stationary via rank_graph
        x_cubic, _, _ = power_iteration(node_ids, T_k)

        # Collapsed adjacency: sum T_k over all relations
        collapsed: dict[int, dict[int, float]] = {}
        for rel, rows in T_k.items():
            for i, cols in rows.items():
                if i not in collapsed:
                    collapsed[i] = {}
                for j, val in cols.items():
                    collapsed[i][j] = collapsed[i].get(j, 0.0) + val

        x_spectral = self._leading_eigenvector(n, collapsed)

        # Rank both by descending value
        rank_cubic = sorted(range(n), key=lambda i: -x_cubic[i])
        rank_spectral = sorted(range(n), key=lambda i: -x_spectral[i])

        # Kendall tau correlation of rank positions
        pos_cubic = [0] * n
        pos_spectral = [0] * n
        for pos, node_idx in enumerate(rank_cubic):
            pos_cubic[node_idx] = pos
        for pos, node_idx in enumerate(rank_spectral):
            pos_spectral[node_idx] = pos

        concordant = 0
        discordant = 0
        for i in range(n):
            for j in range(i + 1, n):
                c = (pos_cubic[i] - pos_cubic[j]) * (pos_spectral[i] - pos_spectral[j])
                if c > 0:
                    concordant += 1
                elif c < 0:
                    discordant += 1

        pairs = concordant + discordant
        tau = (concordant - discordant) / pairs if pairs > 0 else 0.0
        self.assertGreaterEqual(tau, 0.95,
            f"T3: rank correlation (Kendall tau={tau:.4f}) below pre-registered threshold 0.95")


class TestDeltaDistribution(unittest.TestCase):
    """T4: top-decile δ nodes get lane='human'."""

    def _check_graph(self, g: dict, label: str):
        records = rank_graph(g)
        self.assertGreater(len(records), 0, f"{label}: no records returned")

        # Verify schema_id on every record
        for r in records:
            self.assertEqual(r.schema_id, SCHEMA, f"{label}: unexpected schema_id")

        # Human-lane nodes must be exactly the top-decile of δ
        deltas = sorted([r.delta for r in records], reverse=True)
        n = len(deltas)
        # top decile: at least ceil(n * DELTA_HUMAN_PERCENTILE) largest δ values
        threshold_count = max(1, int(math.ceil(n * DELTA_HUMAN_PERCENTILE)))
        min_delta_human = deltas[threshold_count - 1]  # smallest δ in top-decile

        human_records = [r for r in records if r.lane == "human"]
        auto_records  = [r for r in records if r.lane == "auto"]

        # Every human node must have δ >= min_delta_human
        for r in human_records:
            self.assertGreaterEqual(r.delta, min_delta_human,
                f"{label}: human-lane record with δ={r.delta} below threshold {min_delta_human}")

        # Count sanity: at least threshold_count human nodes
        self.assertGreaterEqual(len(human_records), threshold_count,
            f"{label}: expected ≥{threshold_count} human-lane records, got {len(human_records)}")

    def test_delta_distribution_synthetic(self):
        """T4 (synthetic)."""
        g = _make_synthetic_graph(n_nodes=30, seed=99)
        self._check_graph(g, "synthetic")

    def test_delta_distribution_lw(self):
        """T4 (real): logicalworks- graph."""
        if not GRAPH_LW.exists():
            self.skipTest(f"eval graph not found: {GRAPH_LW}")
        g = json.loads(GRAPH_LW.read_text())
        self._check_graph(g, "lgwks")

    def test_delta_distribution_os(self):
        """T4 (real): logic-os-kernel graph."""
        if not GRAPH_OS.exists():
            self.skipTest(f"eval graph not found: {GRAPH_OS}")
        g = json.loads(GRAPH_OS.read_text())
        self._check_graph(g, "os")


class TestDeterminismReplay(unittest.TestCase):
    """T5: same tensor → identical RankRecord set."""

    def _records_to_key(self, records: list[RankRecord]) -> frozenset:
        return frozenset(
            (r.node_cid, r.centrality, r.rank_det, r.rank_ai, r.delta, r.lane)
            for r in records
        )

    def test_determinism_synthetic(self):
        """T5 (synthetic): two rank_graph calls on same data → identical records.

        //why seed=7: determinism is only meaningful on a converging graph. seed=17 has a
        near-degenerate spectral gap that does not converge under the strict 1e-9 vector
        tolerance — that case is covered by test_degenerate_graph_fails_loud below.
        """
        g = _make_synthetic_graph(n_nodes=20, seed=7)
        r1 = rank_graph(g)
        r2 = rank_graph(g)
        self.assertEqual(self._records_to_key(r1), self._records_to_key(r2),
            "T5: rank_graph returned different records on same input")

    def test_degenerate_graph_fails_loud(self):
        """Harden: a genuinely non-converging graph raises RankError, never silent garbage.

        seed=17/n=20 plateaus above the 1e-9 vector tolerance even at full MAX_ITER
        (near-degenerate eigenvalues). The guard must fail loud rather than return an
        untrustworthy ranking. Robust eigenvalue/Rayleigh-quotient convergence is the
        recommended I6.1 follow-up; until then, loud failure is the honest contract.
        """
        g = _make_synthetic_graph(n_nodes=20, seed=17)
        with self.assertRaises(lgwks_rank.RankError):
            rank_graph(g)

    def test_determinism_real(self):
        """T5 (real): logicalworks- graph."""
        if not GRAPH_LW.exists():
            self.skipTest(f"eval graph not found: {GRAPH_LW}")
        g = json.loads(GRAPH_LW.read_text())
        r1 = rank_graph(g)
        r2 = rank_graph(g)
        self.assertEqual(self._records_to_key(r1), self._records_to_key(r2),
            "T5 (real): rank_graph returned different records on same input")


class TestOutputContract(unittest.TestCase):
    """Verify output contract shape: lgwks.rank.record.v1."""

    def test_record_fields(self):
        """RankRecord has exactly the contracted fields."""
        g = _make_synthetic_graph()
        records = rank_graph(g)
        for r in records:
            self.assertIsInstance(r.node_cid, str)
            self.assertIsInstance(r.centrality, float)
            self.assertIsInstance(r.rank_det, int)
            self.assertIsInstance(r.rank_ai, int)
            self.assertIsInstance(r.delta, int)
            self.assertIn(r.lane, ("auto", "human"))
            self.assertEqual(r.schema_id, "lgwks.rank.record.v1")

    def test_centrality_positive(self):
        """Centrality values are non-negative (power iteration on non-negative T)."""
        g = _make_synthetic_graph()
        records = rank_graph(g)
        for r in records:
            self.assertGreaterEqual(r.centrality, 0.0,
                f"centrality negative for node {r.node_cid}")

    def test_rank_range(self):
        """rank_det and rank_ai are 1-indexed and within [1, n]."""
        g = _make_synthetic_graph(n_nodes=15)
        records = rank_graph(g)
        n = len(records)
        for r in records:
            self.assertGreaterEqual(r.rank_det, 1)
            self.assertLessEqual(r.rank_det, n)
            self.assertGreaterEqual(r.rank_ai, 1)
            self.assertLessEqual(r.rank_ai, n)


class TestHardening(unittest.TestCase):
    """Harden pass: non-convergence must fail loud; degenerate AI signal flagged."""

    def test_nonconvergence_raises(self):
        # max_iter=1 on a non-trivial graph cannot reach 1e-9 → rank_graph must raise loud.
        g = _make_synthetic_graph(n_nodes=20, seed=3)
        with self.assertRaises(lgwks_rank.RankError):
            rank_graph(g, max_iter=1)

    def test_convergence_does_not_raise(self):
        # Full max_iter converges → no raise.
        g = _make_synthetic_graph(n_nodes=20, seed=3)
        records = rank_graph(g)  # default MAX_ITER
        self.assertEqual(len(records), 20)

    def test_degenerate_ai_signal_detected(self):
        # All edges same confidence → no AI-signal variance → degenerate.
        g = {
            "nodes": [{"id": f"n{i}"} for i in range(5)],
            "links": [{"source": "n0", "target": f"n{j}", "relation": "calls",
                       "confidence_score": 1.0} for j in range(1, 5)],
        }
        node_ids, _ = build_tensor(g)
        self.assertTrue(lgwks_rank.ai_signal_degenerate(g, node_ids))

    def test_varied_ai_signal_not_degenerate(self):
        g = {
            "nodes": [{"id": f"n{i}"} for i in range(5)],
            "links": [{"source": "n0", "target": f"n{j}", "relation": "calls",
                       "confidence_score": 0.3 + 0.1 * j} for j in range(1, 5)],
        }
        node_ids, _ = build_tensor(g)
        self.assertFalse(lgwks_rank.ai_signal_degenerate(g, node_ids))


if __name__ == "__main__":
    unittest.main()
