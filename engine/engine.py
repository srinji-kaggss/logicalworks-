"""engine — the ONE canonical orchestrator entrypoint (the Membrane Engine).

Collapses the five prior peer orchestrators (lgwks_do / lgwks_workflows /
lgwks_agent / lgwks_research / lgwks_workflow_aetherius) into a single loop:

    perceive  →  sanitize (membrane)  →  plan  →  gate  →  dispatch (ENQUEUE)

Design: docs/membrane-engine-thesis.md. The keystone fix (gap-analysis G4) is
that dispatch ENQUEUES work items through the daemon's one registry+queue rather
than running phases inline — so every run gets the daemon's durability, ledger,
worktrees, and replay. Surfaces (CLI / TUI / API) call this; none re-implement it.

What is wired now (real): perceive (canonical lgwks_agent.worldview), the membrane
SANITIZE stage (engine.membrane_sanitize), plan (canonical lgwks_agent.compile_plan),
and dispatch→enqueue through lgwks_daemon_store. The MEASURE-stage probes (intent/
harm/injection directions) and the PULSE wire-grammar binding are the documented
roadmap, stubbed behind stable seams here — not faked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ENGINE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ENGINE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "lgwks.engine.run.v1"


# ── Membrane: SANITIZE (real) ───────────────────────────────────────────────
def sanitize(text: str) -> tuple[str, float]:
    """Strip hidden-payload codepoint classes; return (clean_text, payload_ratio).
    The one boundary that protects every model-facing crossing (redesign #1)."""
    from engine.membrane_sanitize import sanitize as _san  # type: ignore
    clean, _, ratio = _san(text)
    return clean, ratio


# ── Membrane: MEASURE (seam — roadmap) ──────────────────────────────────────
def measure(text: str) -> dict[str, Any]:
    """Linear probes over the crossing: intent / harm / injection directions + Δ.
    Roadmap (docs/membrane-engine-thesis.md §2). Seam returns the payload-ratio
    signal we DO have today, so callers can already gate on it."""
    _, ratio = sanitize(text)
    return {
        "payload_ratio": ratio,
        "intent": None, "harm": None, "injection": None,  # probe seams (roadmap)
        "confidence": 0.0, "note": "MEASURE probes are roadmap; payload_ratio is live",
    }


# ── Perceive + Plan (canonical, delegated — not duplicated) ─────────────────
def perceive(intent: str, repo: Path | None = None, top: int = 5) -> dict[str, Any]:
    import lgwks_agent
    return lgwks_agent.worldview(intent, repo, top)


def plan(intent: str, wv: dict[str, Any]) -> dict[str, Any]:
    import lgwks_agent
    return lgwks_agent.compile_plan(intent, wv)


# ── Dispatch: ENQUEUE through the one registry+queue (the keystone, G4) ─────
def dispatch(plan_obj: dict[str, Any], *, tenant_id: str = "local",
             session_id: str = "engine", agent_id: str = "engine",
             enqueue: bool = True) -> dict[str, Any]:
    """Translate a plan into daemon work items and ENQUEUE them. Falls back to
    returning the plan (no inline execution) if the daemon store is unavailable —
    a surface must never silently become a loop."""
    try:
        import lgwks_daemon_store as ds
    except Exception as exc:  # pragma: no cover - import guard
        return {"enqueued": False, "reason": f"daemon_store unavailable: {exc}", "plan": plan_obj}

    kinds = ds.WORK_KINDS
    items, skipped = [], []
    for i, step in enumerate(plan_obj.get("steps", [])):
        kind = _step_to_kind(step)
        if kind in kinds:
            items.append({
                "item_id": f"{session_id}:{i}:{kind}",
                "tenant_id": tenant_id, "session_id": session_id, "agent_id": agent_id,
                "kind": kind, "payload": step.get("args", {}),
            })
        else:
            skipped.append({"step": step.get("verb"), "reason": f"no WORK_KIND for '{kind}'"})

    if not enqueue:
        return {"enqueued": False, "items": items, "skipped": skipped, "plan": plan_obj}

    store = ds.DaemonEventStore(_REPO_ROOT)
    accepted = []
    for it in items:
        try:
            ok = store.enqueue(it)
            accepted.append({"item_id": it["item_id"], "kind": it["kind"], "ok": ok})
        except Exception as exc:  # QueueFull / validation surface, not silent
            accepted.append({"item_id": it["item_id"], "kind": it["kind"], "ok": False, "error": str(exc)})
    return {"enqueued": True, "accepted": accepted, "skipped": skipped}


def _step_to_kind(step: dict[str, Any]) -> str:
    """Map a plan step's verb to a daemon WORK_KIND (the one capability registry)."""
    verb = str(step.get("verb", "")).lower()
    return {
        "ingest": "ingest_file", "codebase": "index_run", "research": "research_run",
        "crawl": "research_run", "review": "workflow",
    }.get(verb, "custom")


# ── The one loop entrypoint ─────────────────────────────────────────────────
def run(intent: str, *, repo: Path | None = None, top: int = 5,
        execute: bool = False, **ids: str) -> dict[str, Any]:
    """perceive → sanitize → plan → gate → dispatch(enqueue). The single door."""
    clean_intent, ratio = sanitize(intent)
    out: dict[str, Any] = {"schema": SCHEMA, "intent": clean_intent, "payload_ratio": ratio}
    if ratio > 0.02:  # membrane: refuse a payload-like intent (redesign #1)
        out.update(blocked=True, block_reason="intent quarantined by membrane (payload-like)")
        return out
    wv = perceive(clean_intent, repo, top)
    p = plan(clean_intent, wv)
    out.update(worldview=wv, plan=p, measure=measure(clean_intent))
    if (wv.get("risk") or {}).get("verdict") == "block":
        out.update(blocked=True, block_reason="risk gate blocked the intent")
        return out
    if execute:
        out["dispatch"] = dispatch(
            p,
            tenant_id=ids.get("tenant_id", "local"),
            session_id=ids.get("session_id", "engine"),
            agent_id=ids.get("agent_id", "engine"),
        )
    return out
