"""
lgwks_workercap — computed worker-slot ceiling from a probed host profile.

Replaces the former `MAX_CONCURRENT_WORKERS = 4` constant with the formula
recorded in SPEC-geometric-cli-translator-v1 §7. The always-on Deep ML Model
reserve is a named, recorded input to the math, not a comment.

Director decisions (2026-06-01):
  - Formula cap is a *ceiling/headroom*. Active concurrency stays bound to the
    number of defined mapper roles; a bigger host raises recorded headroom but
    does not invent phantom slots.
  - Host capacity is probed live (auto-scale). Replay safety is preserved by
    stamping the observed values into the artifact and making the probe
    injectable: env override `LGWKS_HOST_RAM_GIB` / `LGWKS_HOST_CPU` pins the
    host so the same inputs reproduce the same artifact on any machine.
"""

from __future__ import annotations

import math
import os

# Named reserves (GiB unless noted). //why: 8 GiB Deep ML reserve is the
# enforced invariant the cap math must subtract — not prose. Bumping any of
# these is a deliberate edit recorded in the emitted artifact.
RESERVES = {
    "os_and_apps_gib": 6,
    "always_on_deep_ml_model_gib": 8,
    "safety_gib": 2,
    "per_worker_gib": 2,
    "cpu_reserve_for_model_and_system": 5,
    "cpu_per_worker": 1,
}


def probe_host() -> dict:
    """Observe host capacity. Live probe by default; env override pins it.

    //why env override, not a config file: a single deploy needs one host read,
    and tests/replay need a deterministic injection point without changing any
    CLI signature. `source` records which path was taken so the artifact is
    honest about whether the numbers were measured or pinned.
    """
    ram_env = os.environ.get("LGWKS_HOST_RAM_GIB")
    cpu_env = os.environ.get("LGWKS_HOST_CPU")
    if ram_env is not None and cpu_env is not None:
        return {"ram_total_gib": int(ram_env), "cpu_total": int(cpu_env), "source": "override"}
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        ram_total_gib = int((page_size * phys_pages) / (1024 ** 3))
    except (ValueError, OSError, AttributeError):
        # //why: a host that cannot report RAM must not silently get a generous
        # cap. Fall back to the smallest viable profile, flagged in `source`.
        return {"ram_total_gib": 0, "cpu_total": os.cpu_count() or 1, "source": "probe-unavailable"}
    return {"ram_total_gib": ram_total_gib, "cpu_total": os.cpu_count() or 1, "source": "probed"}


def compute_worker_cap(role_count: int, *, host: dict | None = None,
                       reserves: dict | None = None) -> dict:
    """Return the full cap breakdown. `computed_cap` is the spawnable ceiling.

    spawnable = clamp(min(memory_headroom, cpu_headroom, role_count), 1, role_count)
    so the active slots are bound to roles that actually exist while the raw
    formula headroom is recorded separately for a future larger host.
    """
    host = host or probe_host()
    reserves = reserves or RESERVES
    ram = host["ram_total_gib"]
    cpu = host["cpu_total"]

    ram_available = ram - reserves["os_and_apps_gib"] - reserves["always_on_deep_ml_model_gib"] \
        - reserves["safety_gib"]
    memory_cap = max(0, math.floor(ram_available / reserves["per_worker_gib"]))
    cpu_cap = max(0, math.floor((cpu - reserves["cpu_reserve_for_model_and_system"])
                                / reserves["cpu_per_worker"]))
    formula_headroom = min(memory_cap, cpu_cap)
    # //why: ceiling bound to roles (Director decision), then floored at 1 so a
    # constrained host still runs one worker rather than deadlocking at 0.
    computed_cap = max(1, min(formula_headroom, role_count))

    return {
        "schema": "lgwks-worker-cap/1",
        "host": host,
        "reserves": dict(reserves),
        "ram_available_for_workers_gib": ram_available,
        "memory_cap": memory_cap,
        "cpu_cap": cpu_cap,
        "formula_headroom": formula_headroom,
        "role_count": role_count,
        "computed_cap": computed_cap,
        "cap_basis": "role_count" if formula_headroom >= role_count else "host_capacity",
    }
