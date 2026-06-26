"""deprecated_heads — the canonical registry of retired orchestrator HEADS.

A "head" is an orchestrator's autonomous entrypoint — the thing that made it one
of the five peer orchestrators. These heads are KILLED: marked dead, frozen as
boilerplate, and scheduled for absorption into the daemon, which is the single
source of truth (SoT) for orchestration. The leaf logic is retained (not deleted)
so the daemon can absorb it; see engine/DAEMON-ABSORPTION-LOG.md for the per-head
absorption plan.

This registry is enforced by tests/test_deprecated_heads.py — a head listed here
must carry `_DEPRECATED_HEAD = True` in its module, and a head marked `deleted`
must not exist as a module. The gate is additive (it can only tighten).
"""
from __future__ import annotations

# module -> {capabilities, absorb_into (daemon work kind/handler), status}
DEPRECATED_HEADS: dict[str, dict] = {
    "lgwks_workflow_aetherius": {
        "capabilities": ["synthesis chambers: synthesis/dialectic/valuation/refinement/ingestion"],
        "absorb_into": "daemon work kind 'workflow' → a synthesis handler",
        "status": "deleted",  # module removed (PR #324/#325)
    },
    "lgwks_workflows": {
        "capabilities": [
            "ops workflow {research,deep-research,quick-scan,code,govern,cleanup,"
            "ship,prove,extract,compare,audit-trail,health-check,onboard,migration-check}"
        ],
        "absorb_into": "daemon work kinds: research_run / workflow / index_run; "
                       "leaf helpers become work-item handlers",
        "status": "head_killed_boilerplate",  # flagged; CLI registration kept as deprecated shim
    },
    "lgwks_do": {
        "capabilities": ["composite phases: code, research, govern, cleanup, ship"],
        "absorb_into": "daemon work kind 'workflow'; _run_review/_do_code/etc. become handlers",
        "status": "head_killed_boilerplate",  # already headless at CLI; now flagged
    },
    "lgwks_route": {
        "capabilities": ["map / engine / route / refine (RETIRED — folded into agent front door)"],
        "absorb_into": "front door → engine.dispatch → daemon (no separate route head)",
        "status": "head_killed_boilerplate",  # only its own test imports it
    },
}

# The single source of truth for orchestration going forward.
ORCHESTRATION_SOT = "lgwks_daemon"


def is_deprecated_head(module_name: str) -> bool:
    return module_name in DEPRECATED_HEADS
