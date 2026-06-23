"""engine — the ONE canonical orchestrator entrypoint (the Membrane Engine).

Collapses the prior peer orchestrators (lgwks_do / lgwks_workflows /
lgwks_route — heads killed; lgwks_workflow_aetherius — deleted) into one loop,
with lgwks_agent + lgwks_research kept as the canonical perceive/plan/research
primitives it delegates to:

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
import time
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


def _canonical_db(repo_root: Path) -> Path:
    """The ONE event-store db location — exactly what the daemon drains
    (lgwks_daemon._paths(root).db). Enqueuing anywhere else means the running
    daemon never sees the item. (DaemonEventStore takes the db FILE, not a dir.)"""
    import lgwks_daemon as _d
    return _d._paths(Path(repo_root).resolve()).db


# ── Dispatch: ENQUEUE through the one registry+queue (the keystone, G4) ─────
def dispatch(plan_obj: dict[str, Any], *, repo_root: Path | None = None,
             tenant_id: str = "local", session_id: str = "engine",
             agent_id: str = "engine", enqueue: bool = True) -> dict[str, Any]:
    """Translate a plan into daemon work items and ENQUEUE them into the canonical
    store the daemon drains. Falls back to returning the plan (no inline execution)
    if the daemon store is unavailable — a surface must never silently become a loop."""
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

    store = ds.DaemonEventStore(_canonical_db(repo_root or _REPO_ROOT))
    accepted = []
    try:
        for it in items:
            try:
                ok = store.enqueue(it)
                accepted.append({"item_id": it["item_id"], "kind": it["kind"], "ok": ok})
            except Exception as exc:  # QueueFull / validation surface, not silent
                accepted.append({"item_id": it["item_id"], "kind": it["kind"], "ok": False, "error": str(exc)})
    finally:
        store.close()
    return {"enqueued": True, "accepted": accepted, "skipped": skipped}


def _step_to_kind(step: dict[str, Any]) -> str:
    """Map a plan step's verb to a daemon WORK_KIND (the one capability registry)."""
    verb = str(step.get("verb", "")).lower()
    return {
        "ingest": "ingest_file", "codebase": "index_run", "research": "research_run",
        "crawl": "research_run", "review": "workflow",
    }.get(verb, "custom")


def _canonical_tenant(repo_root: Path) -> str:
    """The ONE tenant resolution — the same `repo:<name>` the daemon drains
    (lgwks_daemon._tenant_for). Enqueuing under any other tenant (e.g. a bare
    "local") would mean the running daemon never dequeues it and an await hangs."""
    import lgwks_daemon as _d
    return _d._tenant_for(_d._paths(Path(repo_root).resolve()))


# ── Dispatch + AWAIT: out-of-band execution under the control plane (option b) ─
def dispatch_and_await(plan_obj: dict[str, Any], *, repo_root: Path | None = None,
                       tenant_id: str | None = None, session_id: str = "engine",
                       agent_id: str = "engine", timeout_s: float = 300.0,
                       poll_s: float = 0.2, autostart: bool = False) -> dict[str, Any]:
    """Enqueue work, then let the DAEMON (the out-of-band control plane) execute
    it and block-poll each item to a terminal state — keeping the calling surface
    synchronous while execution happens under the daemon's authority, not the
    caller's process. This is the security boundary: the request lane can only
    PROPOSE (enqueue, subject to admission control + the daemon's gates); it never
    executes work in its own (possibly adversarial-input-handling) context.

    Fail-closed: if the daemon is not running we do NOT silently drain in-process
    (that would hand back the weaker in-caller isolation). We return executed=False
    with a clear reason unless autostart=True (then we spawn the control plane)."""
    root = Path(repo_root or _REPO_ROOT).resolve()
    tenant = tenant_id or _canonical_tenant(root)

    enq = dispatch(plan_obj, repo_root=root, tenant_id=tenant,
                   session_id=session_id, agent_id=agent_id, enqueue=True)
    if not enq.get("enqueued"):
        return {**enq, "executed": False, "reason": enq.get("reason", "enqueue failed")}
    item_ids = [a["item_id"] for a in enq.get("accepted", []) if a.get("ok")]
    if not item_ids:
        return {**enq, "executed": False, "reason": "nothing enqueued (all steps skipped)"}

    import lgwks_daemon as _d
    daemon = _d.SessionDaemon(root)
    if not daemon.status().get("alive"):
        if not autostart:
            return {**enq, "executed": False, "downgrade": "fail_closed",
                    "reason": "daemon not running; execution requires the out-of-band "
                              "control plane. Start it (`lgwks ops daemon start`) or pass "
                              "autostart=True. Refusing to drain in-process (weaker isolation)."}
        try:
            daemon.start()
        except Exception as exc:  # control plane could not be brought up
            return {**enq, "executed": False, "downgrade": "fail_closed",
                    "reason": f"daemon autostart failed: {exc}"}

    import lgwks_daemon_store as ds
    store = ds.DaemonEventStore(_canonical_db(root))
    results: dict[str, Any] = {}
    try:
        pending = set(item_ids)
        deadline = time.time() + timeout_s
        while pending and time.time() < deadline:
            for iid in list(pending):
                it = store.get_item(iid)
                if it and it["status"] in ("done", "failed"):
                    results[iid] = it
                    pending.discard(iid)
            if pending:
                time.sleep(poll_s)
    finally:
        store.close()

    timed_out = sorted(pending)
    ok = not timed_out and all(r["status"] == "done" for r in results.values())
    return {"executed": True, "rc": 0 if ok else 1, "tenant_id": tenant,
            "items": results, "timed_out": timed_out, "skipped": enq.get("skipped", [])}


# ── The one loop entrypoint ─────────────────────────────────────────────────
def run(intent: str, *, repo: Path | None = None, top: int = 5,
        execute: bool = False, autostart: bool = False, **ids: str) -> dict[str, Any]:
    """perceive → sanitize → plan → gate → dispatch+await. The single door.

    With execute=True the work runs under the daemon control plane (option b):
    enqueue, then block until the daemon completes each item. The door stays
    synchronous; execution is out-of-band. No daemon → fail-closed (see
    dispatch_and_await), never an in-process bypass."""
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
        out["dispatch"] = dispatch_and_await(
            p, repo_root=repo,
            tenant_id=ids.get("tenant_id"),
            session_id=ids.get("session_id", "engine"),
            agent_id=ids.get("agent_id", "engine"),
            autostart=autostart,
        )
    return out
