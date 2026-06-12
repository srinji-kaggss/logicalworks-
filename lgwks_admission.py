"""lgwks_admission — token-bucket admission + idempotent queue (I8 / I8-hardening L3).

No compute, no scoring, no model layer — queue/admission/isolation ONLY.
Controls whether/when a job is admitted and deduplicates by cid.

L3 (issue #89): TenantAdmissionGate adds capability-FIRST, per-tenant admission
with fair leasing ≤ c on top of the single-operator global path below.

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
    D2: Retry-After jitter reuses the crawler backoff pattern (base + 25% uniform
        noise); jitter RNG is injectable for deterministic tests.
    D3: μ, B, Q_max are pre-registered config inputs, never tuned under test.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import lgwks_capability
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
    reason: str       # "rate_limited" | "queue_full"
    retry_after: float
    schema: str = SCHEMA
    status: str = "rejected_429"


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """Token-bucket rate limiter with injectable clock (D1).

    rate  = c·μ (tokens/s): the refill rate equals concurrency cap × service rate.
    burst = B   (tokens):   maximum instantaneous burst allowed.

    //why injectable clock: wall-clock reads are non-deterministic for replay.
    Mirror probe_host's env-pinnable discipline.
    """

    def __init__(
        self,
        rate: float,
        burst: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError(f"TokenBucket rate must be > 0, got {rate!r}")
        if burst <= 0:
            raise ValueError(f"TokenBucket burst must be > 0, got {burst!r}")
        self.rate = rate
        self.burst = burst
        self._clock = clock
        self._tokens = float(burst)
        self._last = clock()

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
      - Duplicate cid: Admitted (already present — one row, idempotent shed).
      - Full queue:    Rejected429(reason="queue_full") with jittered Retry-After.
    """

    def __init__(
        self,
        q_max: int,
        *,
        rng: random.Random | None = None,
    ) -> None:
        if q_max < 1:
            raise ValueError(f"q_max must be >= 1, got {q_max}")
        self._q_max = q_max
        self._items: deque[tuple[str, Any]] = deque()   # (cid, item) FIFO
        self._seen: set[str] = set()
        self._rng = rng   # injectable for deterministic tests (D2)

    def submit(self, item: Any, *, cid: str) -> Admitted | Rejected429:
        """Submit item with the given cid. Duplicate → idempotent Admitted."""
        if cid in self._seen:
            # //why idempotent shed: cid is the dedup key from I1. Identical
            # input bytes → identical cid → second submission is a no-op.
            return Admitted(cid=cid)

        if len(self._items) >= self._q_max:
            return Rejected429(
                cid=cid,
                reason="queue_full",
                retry_after=_jitter(1.0, rng=self._rng),
            )

        self._items.append((cid, item))
        self._seen.add(cid)
        return Admitted(cid=cid)

    def pop(self) -> tuple[str, Any] | None:
        """Pop next (cid, item) FIFO pair in O(1), or None if empty."""
        if not self._items:
            return None
        return self._items.popleft()

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def seen_cids(self) -> frozenset[str]:
        return frozenset(self._seen)


# ---------------------------------------------------------------------------
# Retry-After jitter — injectable RNG for deterministic tests (D2)
# ---------------------------------------------------------------------------

def _jitter(base: float, *, rng: random.Random | None = None) -> float:
    """base + uniform(0, 0.25·base) — anti-thundering-herd, same pattern as crawler.

    rng: injectable Random instance for deterministic replay (D2). Uses the
    global random module when None, which is fine for production (jitter purpose
    is spread, not security); tests that need determinism inject a seeded rng.
    """
    r: Any = rng if rng is not None else random
    return base + r.uniform(0.0, base * 0.25)


# ---------------------------------------------------------------------------
# Admission decision
# ---------------------------------------------------------------------------

def admission_decision(
    *,
    cid: str,
    item: Any = None,
    bucket: TokenBucket,
    queue: AdmissionQueue,
    rng: random.Random | None = None,
) -> Admitted | Rejected429:
    """Full admission gate: token-bucket → queue enqueue.

    Stability guarantee (INGESTION-PLAN §I8):
      ρ = λ/(c·μ) < 1 → stable; rate-limit rejects at saturation.
      Q ≥ Q_max → Rejected429(reason="queue_full"); never unbounded.
      Duplicate cid → Admitted (idempotent, zero 5xx).

    rng: injectable for deterministic replay of Retry-After values (D2).
    """
    if not bucket.try_acquire():
        base = 1.0 / bucket.rate if bucket.rate > 0 else 1.0
        return Rejected429(cid=cid, reason="rate_limited", retry_after=_jitter(base, rng=rng))

    return queue.submit(item, cid=cid)


# ---------------------------------------------------------------------------
# L3 — per-tenant admission (issue #89, ARCH-two-db-multitenant L3)
# ---------------------------------------------------------------------------
#
# The functions above are the single-operator P3 default path (one global bucket
# + queue) and stay intact. TenantAdmissionGate is the multi-tenant destination:
#
#   1. Capability-FIRST ordering (fixes fail-open). require_scope(TENANT_RW) runs
#      before any token is touched — an uncapped / invalid-sig / wrong-scope
#      request raises CapabilityError and consumes NOTHING (no token, no queue slot).
#   2. Per-tenant bucket + queue. Each validated tenant gets its own independent
#      TokenBucket (rate per_tenant_rate, default c·μ) and bounded AdmissionQueue
#      (per-tenant q_max). One tenant's flood drains only its own bucket/queue, so
#      it cannot starve another tenant's admission.
#   3. Fair leasing ≤ c. lease()/release() bound *concurrent in-flight* work: a
#      lease is granted only if total in-flight < c AND the tenant's in-flight <
#      its fair ceiling ⌈c / active_tenants⌉. This is what enforces ≤ c and the
#      max-min fair split across tenants.
#
# Durable WAL backing of the queue + crash-durable lease/reap is L4 (next step);
# this gate is in-memory but exposes the lease interface L4 will persist.


class TenantAdmissionGate:
    """Multi-tenant admission: capability-gated, per-tenant buckets, fair leasing ≤ c.

    key is the HMAC capability key (REQUIRED — no keyless path, mirrors
    lgwks_capability.guard's D3). Every admit() validates a CapabilityToken with
    the TENANT_RW scope BEFORE touching rate/queue state.
    """

    def __init__(
        self,
        *,
        key: bytes,
        role_count: int = DEFAULT_ROLE_COUNT,
        mu: float = DEFAULT_MU,
        burst: float = DEFAULT_BURST,
        q_max: int = DEFAULT_Q_MAX,
        per_tenant_rate: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        store_path: Any = None,
        lease_ttl: float = 30.0,
    ) -> None:
        if not key:
            raise ValueError("TenantAdmissionGate requires a non-empty capability key")
        cap_info = lgwks_workercap.compute_worker_cap(role_count)
        self._key = key
        self._c = int(cap_info["computed_cap"])
        self._mu = mu
        self._burst = burst
        self._q_max = q_max
        # //why default per-tenant rate = c·μ: each tenant gets an independent full
        # service-rate bucket. Aggregate is bounded by the lease ceiling (≤ c), not
        # by shrinking each bucket — so adding a tenant never throttles existing ones.
        self._rate = per_tenant_rate if per_tenant_rate is not None else float(self._c) * mu
        self._clock = clock
        self._rng = rng
        self.cap_info = cap_info
        self._tenants: dict[str, tuple[TokenBucket, AdmissionQueue]] = {}
        self._inflight: dict[str, int] = {}
        # L4 opt-in: when store_path is set, the per-process token bucket still
        # rate-limits, but the QUEUE (and the lease COUNT behind fair leasing) move
        # to a crash-durable, cross-process SQLite table. self.store is the daemon's
        # handle for durable lease()/complete()/reap(). When None, the L3 in-memory
        # path is the single-operator P3 default (backward compat).
        self.store = None
        if store_path is not None:
            import lgwks_admission_store  # lazy — avoid an import cycle
            self.store = lgwks_admission_store.DurableAdmissionQueue(
                store_path, key=key, role_count=role_count, q_max=q_max,
                lease_ttl=lease_ttl, clock=clock, rng=rng,
            )

    # -- internal --------------------------------------------------------
    def _lane(self, tenant: str) -> tuple[TokenBucket, AdmissionQueue]:
        lane = self._tenants.get(tenant)
        if lane is None:
            lane = (
                TokenBucket(rate=self._rate, burst=self._burst, clock=self._clock),
                AdmissionQueue(q_max=self._q_max, rng=self._rng),
            )
            self._tenants[tenant] = lane
            self._inflight.setdefault(tenant, 0)
        return lane

    def _verified_tenant(self, token: lgwks_capability.CapabilityToken) -> str:
        # require_scope raises CapabilityError on bad sig / empty / world / missing
        # scope, and returns query_fn(tenant) on success. We just echo the tenant.
        return lgwks_capability.require_scope(
            token, lgwks_capability.TENANT_RW, lambda t: t, self._key
        )

    def fair_ceiling(self) -> int:
        """Per-tenant in-flight ceiling ⌈c / active_tenants⌉ (≥ 1)."""
        active = max(1, len(self._tenants))
        return max(1, math.ceil(self._c / active))

    # -- admission (capability-FIRST) ------------------------------------
    def admit(
        self,
        token: lgwks_capability.CapabilityToken,
        *,
        cid: str,
        item: Any = None,
    ) -> Admitted | Rejected429:
        """Capability-gate → per-tenant bucket → per-tenant queue.

        Raises CapabilityError (no token consumed, no queue slot) if the token is
        invalid or lacks tenant:rw. Otherwise returns Admitted | Rejected429 exactly
        like admission_decision, but scoped to the token's tenant.
        """
        tenant = self._verified_tenant(token)   # FIRST — closes fail-open
        bucket, queue = self._lane(tenant)
        if not bucket.try_acquire():
            base = 1.0 / bucket.rate if bucket.rate > 0 else 1.0
            return Rejected429(
                cid=cid, reason="rate_limited", retry_after=_jitter(base, rng=self._rng)
            )
        if self.store is not None:
            # rate passed (per-process); durable, cross-process queue owns admission.
            return self.store.enqueue(token, cid=cid, item=item, now=self._clock())
        return queue.submit(item, cid=cid)

    # -- fair leasing ≤ c (concurrency) ----------------------------------
    def lease(self, token: lgwks_capability.CapabilityToken) -> bool:
        """Grant one in-flight worker slot iff total < c AND tenant < fair ceiling.

        Capability-gated (TENANT_RW). Returns False when at capacity — the caller
        leaves the job queued and retries after a release(). True consumes a slot.
        """
        tenant = self._verified_tenant(token)
        self._lane(tenant)  # ensure the tenant counts toward the active set
        total = sum(self._inflight.values())
        if total >= self._c:
            return False
        if self._inflight.get(tenant, 0) >= self.fair_ceiling():
            return False
        self._inflight[tenant] = self._inflight.get(tenant, 0) + 1
        return True

    def release(self, token: lgwks_capability.CapabilityToken) -> None:
        """Release one in-flight slot held by the token's tenant (idempotent floor at 0)."""
        tenant = self._verified_tenant(token)
        self._inflight[tenant] = max(0, self._inflight.get(tenant, 0) - 1)

    @property
    def in_flight(self) -> int:
        return sum(self._inflight.values())

    def tenant_in_flight(self, tenant: str) -> int:
        return self._inflight.get(tenant, 0)


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
    rng: random.Random | None = None,
) -> tuple[TokenBucket, AdmissionQueue, dict]:
    """Build a TokenBucket + Queue sized from compute_worker_cap.

    Returns (bucket, queue, cap_info). mu/burst/q_max are pre-registered.
    rng: injectable for test replay; leave None in production.
    """
    cap_info = lgwks_workercap.compute_worker_cap(role_count)
    c = cap_info["computed_cap"]
    rate = float(c) * mu
    bucket = TokenBucket(rate=rate, burst=burst, clock=clock)
    queue = AdmissionQueue(q_max=q_max, rng=rng)
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
        "stability_note": "rho < 1 required; at 2x load all rejects are typed 429 (zero 5xx)",
        "p3_to_p0_trigger": "escalates to P0 before any multi-tenant or network exposure",
        "multi_tenant_L3": {
            "gate": "TenantAdmissionGate",
            "ordering": "capability(tenant:rw) -> per-tenant bucket -> per-tenant queue",
            "per_tenant_rate_default": rate,
            "per_tenant_q_max": getattr(args, "q_max", DEFAULT_Q_MAX),
            "fair_leasing": "in-flight <= c; per-tenant ceiling = ceil(c / active_tenants)",
            "note": "fail-open closed: invalid/missing cap consumes no token, no queue slot",
        },
        "host": cap_info["host"],
        "cap_basis": cap_info["cap_basis"],
    }
    print(_json.dumps(out, indent=2))
    return 0
