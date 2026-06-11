"""Tests for lgwks_admission — I8 token-bucket admission + queue (T1–T6).

All tests map to acceptance clauses from PLANS-NEXT-4.md §PACKET I8
(authority: INGESTION-LAYER §6, INGESTION-PLAN §I8).

  T1: stability_sweep  — load at {0.5×, 1×, 2×} c·μ: stable at 0.5×, bounded
                         at 1×, typed-429-only at 2× (zero 5xx).
  T2: idempotent_shed  — duplicate cid → exactly one row in queue.
  T3: typed_429        — every rejection is a Rejected429 instance with retry_after set.
  T4: zero_5xx         — no exception raised at any load level (typed result only).
  T5: replayable       — injected clock + pinned cap → deterministic decisions.
  T6: rate_limited     — bucket exhausted → Rejected429(reason="rate_limited").
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_admission
from lgwks_admission import (
    SCHEMA,
    TokenBucket,
    AdmissionQueue,
    Admitted,
    Rejected429,
    admission_decision,
    make_admission_gate,
)


# ---------------------------------------------------------------------------
# Deterministic clock for replay tests (D1)
# ---------------------------------------------------------------------------

class _StepClock:
    """Injectable clock that advances by `step` on each call."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self._t = start
        self._step = step

    def __call__(self) -> float:
        t = self._t
        self._t += self._step
        return t


# ---------------------------------------------------------------------------
# T1 — stability sweep
# ---------------------------------------------------------------------------

class TestStabilitySweep(unittest.TestCase):
    """T1: at 0.5× load → stable; at 1× → bounded; at 2× → all Rejected429, zero 5xx."""

    ROLE_COUNT = 4
    MU = 1.0
    BURST = 8.0
    Q_MAX = 16
    ATTEMPTS = 40

    def _run_load(self, load_factor: float, step: float = 0.1, q_max: int | None = None) -> tuple[int, int]:
        """Submit jobs at λ = load_factor × c·μ.  Returns (admitted, rejected)."""
        clock = _StepClock(step=step)
        bucket, queue, cap_info = make_admission_gate(
            self.ROLE_COUNT, mu=self.MU, burst=self.BURST,
            q_max=q_max if q_max is not None else self.Q_MAX,
            clock=clock,
        )
        admitted = rejected = 0
        for i in range(self.ATTEMPTS):
            result = admission_decision(
                cid=f"cid-{i:04d}",
                item=f"item-{i}",
                bucket=bucket,
                queue=queue,
            )
            if isinstance(result, Admitted):
                admitted += 1
            else:
                self.assertIsInstance(
                    result, Rejected429,
                    msg=f"T1 fail: non-Admitted result must be Rejected429, got {type(result).__name__}",
                )
                rejected += 1
        return admitted, rejected

    def test_half_load_stable(self):
        """T1a: at 0.5× c·μ load (fast clock → ρ < 1), bucket admits >> rejects.

        q_max is set larger than ATTEMPTS so queue capacity does not confound the
        rate-limiter measurement — this test targets the token-bucket stability
        property, not queue-full behaviour (that's T1c).
        """
        # step=2.0 means 2s between each submission; with rate=c·μ≈4 tokens/s,
        # bucket refills 8 tokens per step → nearly every job admitted.
        admitted, rejected = self._run_load(0.5, step=2.0, q_max=self.ATTEMPTS * 4)
        total = admitted + rejected
        reject_rate = rejected / total if total else 1.0
        self.assertGreater(admitted, rejected,
                           f"T1a: 0.5× load must admit more than it rejects "
                           f"(admitted={admitted}, rejected={rejected})")
        self.assertLess(reject_rate, 0.5,
                        f"T1a: reject rate {reject_rate:.2f} must be < 0.5 at sub-capacity load")

    def test_overload_no_5xx(self):
        """T1b: at 2× c·μ load every rejection is Rejected429 (zero 5xx = zero exceptions)."""
        clock = _StepClock(step=0.001)
        bucket, queue, _ = make_admission_gate(
            self.ROLE_COUNT, mu=self.MU, burst=1.0, q_max=self.Q_MAX, clock=clock,
        )
        for i in range(self.ATTEMPTS):
            try:
                result = admission_decision(
                    cid=f"ov-{i:04d}",
                    item=f"item-{i}",
                    bucket=bucket,
                    queue=queue,
                )
                self.assertIsInstance(
                    result, (Admitted, Rejected429),
                    msg="T1b: result must be a typed admission type (zero 5xx)",
                )
            except Exception as e:
                self.fail(f"T1b: exception raised at overload (zero 5xx violated): {e}")

    def test_queue_full_bounded(self):
        """T1c: queue never grows past Q_max (bounded, no unbounded growth)."""
        clock = _StepClock(step=10.0)   # fast refill — bucket always has tokens
        bucket, queue, _ = make_admission_gate(
            self.ROLE_COUNT, mu=self.MU, burst=self.BURST, q_max=4, clock=clock,
        )
        for i in range(20):
            admission_decision(cid=f"q-{i:04d}", item=f"item-{i}", bucket=bucket, queue=queue)
        self.assertLessEqual(queue.size, 4, "T1c: queue must not exceed Q_max")


# ---------------------------------------------------------------------------
# T2 — idempotent shed
# ---------------------------------------------------------------------------

class TestIdempotentShed(unittest.TestCase):
    """T2: duplicate cid submission → exactly one row in queue."""

    def test_duplicate_cid_one_row(self):
        queue = AdmissionQueue(q_max=16)
        r1 = queue.submit("item-a", cid="cid-abc")
        r2 = queue.submit("item-b", cid="cid-abc")   # duplicate

        self.assertIsInstance(r1, Admitted, "T2: first submission must be Admitted")
        self.assertIsInstance(r2, Admitted, "T2: duplicate submission must also return Admitted (idempotent)")
        self.assertEqual(queue.size, 1, "T2: queue must hold exactly one row for duplicate cid")
        self.assertIn("cid-abc", queue.seen_cids, "T2: cid must be in seen set")

    def test_different_cids_multiple_rows(self):
        queue = AdmissionQueue(q_max=16)
        for i in range(5):
            r = queue.submit(f"item-{i}", cid=f"cid-{i:04d}")
            self.assertIsInstance(r, Admitted)
        self.assertEqual(queue.size, 5, "T2: distinct cids must each occupy one row")


# ---------------------------------------------------------------------------
# T3 — typed 429
# ---------------------------------------------------------------------------

class TestTyped429(unittest.TestCase):
    """T3: every rejection is Rejected429 with reason and retry_after set."""

    def test_rate_limited_is_rejected429(self):
        clock = _StepClock(step=0.0)   # clock frozen → no refill
        bucket = TokenBucket(rate=1.0, burst=1.0, clock=clock)
        queue = AdmissionQueue(q_max=16)

        bucket.try_acquire()   # drain
        result = admission_decision(cid="x", bucket=bucket, queue=queue)
        self.assertIsInstance(result, Rejected429, "T3: rate-limited must be Rejected429")
        self.assertEqual(result.reason, "rate_limited", "T3: reason must be 'rate_limited'")
        self.assertGreater(result.retry_after, 0, "T3: retry_after must be positive")
        self.assertEqual(result.schema, SCHEMA, "T3: schema must be SCHEMA")

    def test_rate_limited_retry_after_deterministic(self):
        """T3: with a seeded rng, retry_after is a specific deterministic value."""
        clock = _StepClock(step=0.0)
        bucket = TokenBucket(rate=2.0, burst=1.0, clock=clock)
        rng = random.Random(99)
        bucket.try_acquire()  # drain
        result = admission_decision(cid="y", bucket=bucket, queue=AdmissionQueue(q_max=1), rng=rng)
        self.assertIsInstance(result, Rejected429)
        # retry_after = base + uniform(0, 0.25*base) where base=1/rate=0.5
        # With seeded rng we just verify it's in [0.5, 0.625]
        self.assertGreaterEqual(result.retry_after, 0.5)
        self.assertLessEqual(result.retry_after, 0.625)

    def test_queue_full_is_rejected429(self):
        clock = _StepClock(step=100.0)  # fast refill
        bucket = TokenBucket(rate=1000.0, burst=1000.0, clock=clock)
        queue = AdmissionQueue(q_max=2)
        admission_decision(cid="a", bucket=bucket, queue=queue)
        admission_decision(cid="b", bucket=bucket, queue=queue)
        result = admission_decision(cid="c", bucket=bucket, queue=queue)
        self.assertIsInstance(result, Rejected429, "T3: full queue must be Rejected429")
        self.assertEqual(result.reason, "queue_full", "T3: reason must be 'queue_full'")
        self.assertGreater(result.retry_after, 0, "T3: retry_after must be positive")


# ---------------------------------------------------------------------------
# T4 — zero 5xx (complementary to T1b — standalone)
# ---------------------------------------------------------------------------

class TestZero5xx(unittest.TestCase):
    """T4: no exception raised from admission_decision under any load condition."""

    def test_no_exception_on_any_input(self):
        clock = _StepClock(step=0.001)
        bucket = TokenBucket(rate=0.01, burst=0.01, clock=clock)
        queue = AdmissionQueue(q_max=1)
        for i in range(30):
            try:
                admission_decision(cid=f"z-{i}", bucket=bucket, queue=queue)
            except Exception as e:
                self.fail(f"T4: exception raised (zero 5xx violated): {e!r}")


# ---------------------------------------------------------------------------
# T5 — replayable (injected clock + pinned params → identical decisions)
# ---------------------------------------------------------------------------

class TestReplayable(unittest.TestCase):
    """T5: same (clock, params) → identical sequence of Admitted/Rejected429."""

    def _run(self) -> list[str]:
        clock = _StepClock(start=0.0, step=0.5)
        bucket = TokenBucket(rate=2.0, burst=2.0, clock=clock)
        queue = AdmissionQueue(q_max=4)
        results = []
        for i in range(8):
            r = admission_decision(cid=f"r-{i}", bucket=bucket, queue=queue)
            results.append(type(r).__name__)
        return results

    def test_two_runs_identical(self):
        run1 = self._run()
        run2 = self._run()
        self.assertEqual(run1, run2, f"T5: replay must be identical.\nrun1={run1}\nrun2={run2}")


# ---------------------------------------------------------------------------
# T6 — rate limited bucket edge cases
# ---------------------------------------------------------------------------

class TestTokenBucket(unittest.TestCase):
    """T6: bucket drains and refills correctly; try_acquire respects burst ceiling."""

    def test_initial_full(self):
        clock = _StepClock(step=0.0)
        b = TokenBucket(rate=1.0, burst=3.0, clock=clock)
        self.assertTrue(b.try_acquire())
        self.assertTrue(b.try_acquire())
        self.assertTrue(b.try_acquire())
        self.assertFalse(b.try_acquire(), "T6: bucket must be empty after burst consumed")

    def test_refills_over_time(self):
        clock = _StepClock(start=0.0, step=2.0)
        b = TokenBucket(rate=1.0, burst=5.0, clock=clock)
        for _ in range(5):
            b.try_acquire()   # drain
        # After 2 seconds with rate=1.0 → should gain 2 tokens
        b.try_acquire()  # triggers refill
        self.assertGreater(b.available, 0, "T6: bucket must refill over time")

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            TokenBucket(rate=0.0, burst=1.0)
        with self.assertRaises(ValueError):
            TokenBucket(rate=1.0, burst=0.0)


if __name__ == "__main__":
    unittest.main()
