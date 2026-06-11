"""lgwks_admission — token-bucket admission + idempotent queue (I8).

No compute, no scoring, no model layer — queue/admission/isolation ONLY.
Controls whether/when a job is admitted and deduplicates by cid.

Authority: spec/second-harness/INGESTION-PLAN.md §I8
           spec/second-harness/INGESTION-LAYER.md §6
Schema:    lgwks.admission.v1   (family: harness)
Issue:     I8

Formula (INGESTION-PLAN §I8):
    c   = compute_worker_cap(role_count)["computed_cap"]
    ρ   = λ / (c·μ)          # utilization; STABLE requires ρ < 1
    admission: token bucket, refill rate c·μ, burst capacity B
    Q ≥ Q_max  ⇒  reject with typed 429 + Retry-After
    duplicate cid  ⇒  ONE row (idempotent shed)

Decisions:
    D1: injectable clock (Callable[[], float]) mirrors probe_host env-override
        discipline — deterministic replay without changing any CLI signature.
    D2: Retry-After jitter reuses the crawler backoff pattern (base + 25 % uniform
        noise); do not reinvent.
    D3: μ, B, Q_max are pre-registered config inputs, never tuned under test.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import lgwks_workercap

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.admission.v1"

# Pre-registered knobs (D3: pin, never fiddle under test; override via caller).
DEFAULT_MU: float = 1.0      # service rate per worker μ (jobs/s per slot)
DEFAULT_BURST: float = 4.0   # burst capacity B (token bucket ceiling)
DEFAULT_Q_MAX: int = 32      # bounded queue max size Q_max
DEFAULT_ROLE_COUNT: int = 4  # default role count if not specified


# ---------------------------------------------------------------------------
# Admission result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Admitted:
    """Job admitted (or already present — idempotent)."""
    cid: str
    schema: str = SCHEMA
    status: str = "admitted"


@dataclass(frozen=True)
class Rejected429:
    """Rate-limited or queue full. retry_after is jittered Retry-After (seconds)."""
    cid: str
    reason: str       # "rate_limited" | "queue_full" | "duplicate_shed"
    retry_after: float
    schema: str = SCHEMA
    status: str = "rejected_429"


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """Token-bucket rate limiter with injectable clock.

    rate  = c·μ (tokens/s): the refill rate equals concurrency cap × service rate.
    burst = B   (tokens):   maximum instantaneous burst allowed.

    //why injectable clock: wall-clock reads are non-deterministic for replay.
    Mirror probe_host's env-pinnable discipline (D1).
    """

    rate: float
    burst: float
    _clock: Callable[[], float] = field(default_factory=lambda: time.monotonic, repr=False)
    _tokens: float = field(init=False)
    _last: float = field(init=False)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError(f"TokenBucket rate must be > 0, got {self.rate!r}")
        if self.burst <= 0:
            raise ValueError(f"TokenBucket burst must be > 0, got {self.burst!r}")
        self._tokens = float(self.burst)
        self._last = self._clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last = now

    def try_acquire(self, n: float = 1.0) -> bool:
        """Attempt to consume n tokens. Returns True on success, False if insufficient."""
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    @property
    def available(self) -> float:
        """Available token count after a refill pass."""
        self._refill()
        return self._tokens


# ---------------------------------------------------------------------------
# Queue (bounded, idempotent dedup by cid)
# ---------------------------------------------------------------------------

class AdmissionQueue:
    """Bounded FIFO queue with idempotent cid deduplication.

    submit(item, cid) → Admitted | Rejected429
      - Duplicate cid: returns Admitted (already present — one row, idempotent).
      - Full queue: returns Rejected429(reason="queue_full") with jittered Retry-After.
    """

    def __init__(self, q_max: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        if q_max < 1:
            raise ValueError(f"q_max must be >= 1, got {q_max}")
        self._q_max = q_max
        self._items: list[tuple[str, Any]] = []   # (cid, item) in FIFO order
        self._seen: set[str] = set()
        self._clock = clock

    def submit(self, item: Any, *, cid: str) -> Admitted | Rejected429:
        """Submit item with the given cid. Duplicate → idempotent Admitted."""
        if cid in self._seen:
            # //why: idempotent shed — cid is the dedup key from I1; identical input
            # bytes → identical cid → second submission is a no-op (not an error).
            return Admitted(cid=cid, status="admitted")

        if len(self._items) >= self._q_max:
            return Rejected429(
                cid=cid,
                reason="queue_full",
                retry_after=_jitter(1.0),
            )

        self._items.append((cid, item))
        self._seen.add(cid)
        return Admitted(cid=cid)

    def pop(self) -> tuple[str, Any] | None:
        """Pop next (cid, item) FIFO pair, or None if empty."""
        if not self._items:
            return None
        return self._items.pop(0)

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def seen_cids(self) -> frozenset[str]:
        return frozenset(self._seen)


# ---------------------------------------------------------------------------
# Retry-After jitter (reuses crawler backoff pattern — D2)
# ---------------------------------------------------------------------------

def _jitter(base: float) -> float:
    """base + uniform(0, 0.25·base) — same anti-thundering-herd pattern as the crawler."""
    return base + random.uniform(0.0, base * 0.25)


# ---------------------------------------------------------------------------
# Admission decision
# ---------------------------------------------------------------------------

def admission_decision(
    *,
    cid: str,
    item: Any = None,
    bucket: TokenBucket,
    queue: AdmissionQueue,
) -> Admitted | Rejected429:
    """Full admission gate: token-bucket → queue enqueue.

    Stability guarantee (INGESTION-PLAN §I8):
      ρ = λ/(c·μ) < 1 → stable throughput; rate-limit rejects at saturation.
      Q ≥ Q_max → Rejected429(reason="queue_full"); never unbounded growth.
      Duplicate cid → Admitted (idempotent, zero 5xx).
    """
    if not bucket.try_acquire():
        retry = _jitter(1.0 / bucket.rate if bucket.rate > 0 else 1.0)
        return Rejected429(cid=cid, reason="rate_limited", retry_after=retry)

    return queue.submit(item, cid=cid)


# ---------------------------------------------------------------------------
# Factory (wires compute_worker_cap → TokenBucket + Queue)
# ---------------------------------------------------------------------------

def make_admission_gate(
    role_count: int = DEFAULT_ROLE_COUNT,
    *,
    mu: float = DEFAULT_MU,
    burst: float = DEFAULT_BURST,
    q_max: int = DEFAULT_Q_MAX,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[TokenBucket, AdmissionQueue, dict]:
    """Build a TokenBucket + Queue sized from compute_worker_cap.

    Returns (bucket, queue, cap_info) where cap_info carries the full breakdown
    for audit/logging.  mu/burst/q_max are pre-registered — inject, don't tune.
    """
    cap_info = lgwks_workercap.compute_worker_cap(role_count)
    c = cap_info["computed_cap"]
    rate = float(c) * mu   # token refill rate = c·μ
    bucket = TokenBucket(rate=rate, burst=burst, _clock=clock)
    queue = AdmissionQueue(q_max=q_max, clock=clock)
    return bucket, queue, cap_info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("admission", help="token-bucket admission + queue info (I8)")
    sp = p.add_subparsers(dest="admission_cmd", required=True)

    info_p = sp.add_parser("info", help="show admission gate constants and computed cap")
    info_p.add_argument("--role-count", type=int, default=DEFAULT_ROLE_COUNT,
                        metavar="N", help=f"role count (default: {DEFAULT_ROLE_COUNT})")
    info_p.add_argument("--mu", type=float, default=DEFAULT_MU, metavar="MU",
                        help=f"service rate per worker μ (default: {DEFAULT_MU})")
    info_p.add_argument("--burst", type=float, default=DEFAULT_BURST, metavar="B",
                        help=f"burst capacity B (default: {DEFAULT_BURST})")
    info_p.add_argument("--q-max", type=int, default=DEFAULT_Q_MAX, metavar="Q",
                        help=f"queue max Q_max (default: {DEFAULT_Q_MAX})")
    info_p.set_defaults(func=_cmd_info)


def _cmd_info(args) -> int:
    import json as _json

    _, _, cap_info = make_admission_gate(
        role_count=getattr(args, "role_count", DEFAULT_ROLE_COUNT),
        mu=getattr(args, "mu", DEFAULT_MU),
        burst=getattr(args, "burst", DEFAULT_BURST),
        q_max=getattr(args, "q_max", DEFAULT_Q_MAX),
    )
    mu = getattr(args, "mu", DEFAULT_MU)
    c = cap_info["computed_cap"]
    rate = c * mu

    out = {
        "schema": SCHEMA,
        "computed_cap": c,
        "mu": mu,
        "rate_c_mu": rate,
        "burst": getattr(args, "burst", DEFAULT_BURST),
        "q_max": getattr(args, "q_max", DEFAULT_Q_MAX),
        "utilization_at_half_load": 0.5 if rate > 0 else None,
        "utilization_at_full_load": 1.0 if rate > 0 else None,
        "stability_note": "rho < 1 required; at 2x load all rejects are typed 429 (zero 5xx)",
        "p3_to_p0_trigger": "escalates to P0 before any multi-tenant or network exposure",
        "host": cap_info["host"],
        "cap_basis": cap_info["cap_basis"],
    }
    print(_json.dumps(out, indent=2))
    return 0
