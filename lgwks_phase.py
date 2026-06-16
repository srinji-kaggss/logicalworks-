"""
lgwks_phase — canonical phase-result type and exit-code→verdict policy.

One source of truth for the orchestration-run primitive shared by every multi-phase
runner (`lgwks do`, `lgwks workflows`): a phase carries a name, an ok flag, an exit
code, optional findings/artifact, and — for runners that bill model usage — token and
cost estimates. The verdict policy maps the worst phase exit code to a single verdict
string. Do not re-declare PhaseResult or re-spell this exit-code ladder at call sites.

Exit-code ladder (worst wins): 3 → deny, 1 → danger, 2 → degraded, 4 → error, else pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhaseResult:
    name: str
    ok: bool
    exit_code: int
    findings_count: int = 0
    message: str = ""
    artifact: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0       # estimated tokens for this phase (0 for on-device)
    cost_cents: float = 0.0    # estimated cost (0 for on-device, >0 for API calls)


def verdict_from_phases(phases: list[PhaseResult]) -> str:
    """Reduce a phase sequence to one verdict by worst exit code (deny > danger > …)."""
    codes = [p.exit_code for p in phases]
    if any(c == 3 for c in codes):
        return "deny"
    if any(c == 1 for c in codes):
        return "danger"
    if any(c == 2 for c in codes):
        return "degraded"
    if any(c == 4 for c in codes):
        return "error"
    return "pass"
