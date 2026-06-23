"""lgwks_model_port — the one runtime gateway every cognition request flows through.

The single source of truth for *how* the engine thinks, the way
`lgwks_model_mesh` is the single source of truth for *which* models exist. Before
this module the resolve-invoke-degrade dance was re-derived in every caller
(entity_graph T2/T3, ingest embed, the daemon), each with its own threshold, its
own try/except, and its own — inconsistent — answer for "what happens when the
model isn't there." This collapses all of that into one harness.

THE LADDER (Director's law). A role request escalates through trust tiers in
order, *preferring determinism* — the probabilistic model is the last resort, not
the default:

    deterministic  →  sensor  →  generative
    (math)            (symbolic/narrow ML)   (LLM — last resort, even when present)

These are the mesh's own locked `trust_class` names (no new vocabulary). A lower
tier that resolves with enough confidence WINS; the harness only escalates to a
more probabilistic tier when the cheaper, more trustworthy one cannot answer.

LAW IS TRUTH. The harness never hardcodes a model id. It asks
`lgwks_model_mesh.model_name_for_role(role, trust_class=...)` for the pinned id,
so the model name lives in exactly one place (the law) and runtime cannot drift
from it.

NEVER FABRICATE (INV-3 / fail-closed). If no tier can answer, the envelope is
`mode="deferred"` with `value=None` — the harness defers to the human/agent
rather than invent an answer. Honors the `LGWKS_NO_MODELS` kill-switch: with it
set, only the deterministic tier runs; everything else degrades or defers.

OUTPUT. Every call returns one uniform envelope (`lgwks.model.port.v1`) carrying
the winning tier, the law model id, the trust class, the value, and a full
`escalation` trace of what was tried — so a caller (or the daemon's training
ledger) can read exactly how an answer was reached.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

import lgwks_model_mesh as mesh

SCHEMA = "lgwks.model.port.v1"


@runtime_checkable
class Embedder(Protocol):
    """The shared contract for a single-text embedding provider (#152).

    Both lgwks_apple.embed_one and lgwks_openrouter_embed.embed_one conform: call
    with text → a list[float] (the vector) or None, and NEVER raise (None signals
    "unavailable / failed", so callers fail closed without try/except). Provider-
    specific config (model, dims, timeout) rides on their own keyword defaults; the
    one shared, substitutable shape is embed_one(text).

    The implicit contract that previously lived in two parallel signatures is now
    explicit and machine-checked — tests/test_embedder_contract.py pins the runtime
    behaviour; providers bind `_: Embedder = embed_one` under TYPE_CHECKING for
    static conformance without taking a runtime dependency on this module.
    """

    def __call__(self, text: str) -> list[float] | None: ...

# The escalation order is owned by the law (mesh), not re-stated here.
TIER_ORDER = mesh.TIER_ORDER  # ("deterministic", "sensor", "generative")

# Tiers that load weights / touch a model artifact. The kill-switch suppresses
# exactly these; the deterministic tier is always pure code and always runs.
_WEIGHT_TIERS = frozenset({"sensor", "generative"})


def models_suppressed() -> bool:
    """True when LGWKS_NO_MODELS is set — only the deterministic tier may run.

    The one kill-switch for the whole layer (was honored only by the reasoning
    port before). Any truthy value engages it; unset/empty disengages.
    """
    return bool(os.environ.get("LGWKS_NO_MODELS"))


def _model_timeout() -> float:
    """Wall-clock cap (seconds) for a single weight-tier rung. A model load or
    download that exceeds this is treated as a failed rung — the harness escalates
    or defers instead of hanging the whole CLI. 0/negative disables the cap.

    Default 25s: a cold model load that hasn't produced an answer by then is, for
    an interactive `lgwks review`, indistinguishable from a hang. Override with
    LGWKS_MODEL_TIMEOUT for batch contexts that can afford a long cold start.
    """
    try:
        return float(os.environ.get("LGWKS_MODEL_TIMEOUT", "25"))
    except ValueError:
        return 25.0


def _run_bounded(run: Callable[[], Any], timeout: float) -> Any:
    """Run `run()` on a daemon thread, raising TimeoutError if it outlives
    `timeout`. The abandoned thread is a daemon so it cannot keep the process
    alive after the CLI returns. timeout<=0 runs inline (no cap)."""
    if timeout <= 0:
        return run()
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = run()
        except BaseException as exc:  # propagate the real rung failure to the caller
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True, name="lgwks-model-rung")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"model rung exceeded {timeout:g}s wall-clock")
    if "error" in box:
        raise box["error"]
    return box.get("result")


@dataclass
class Attempt:
    """One rung of the ladder.

    trust_class : which tier this rung is (decides escalation order + kill-switch).
    run         : zero-arg callable. Return a non-None result to RESOLVE this rung;
                  return None to ESCALATE to the next; raising is caught and treated
                  as an escalation (recorded as an error in the trace).
    confidence  : optional callable(result) -> float in [0,1]. A resolved rung only
                  WINS if confidence >= threshold; otherwise the harness escalates
                  but remembers the result as a fallback if nothing better answers.
    model       : law model id for telemetry (None for pure-code deterministic rungs).
    """
    trust_class: str
    run: Callable[[], Any]
    confidence: Callable[[Any], float] | None = None
    model: str | None = None
    label: str = ""


def _envelope(role: str, **kw: Any) -> dict[str, Any]:
    env: dict[str, Any] = {
        "schema": SCHEMA,
        "role": role,
        "ok": False,
        "mode": "deferred",
        "tier": None,
        "model": None,
        "trust": None,
        "value": None,
        "confidence": None,
        "escalation": [],
        "why": "",
    }
    env.update(kw)
    return env


def escalate(
    role: str,
    attempts: list[Attempt],
    *,
    threshold: float = 0.0,
    defer_why: str = "no tier could answer",
) -> dict[str, Any]:
    """Run the ladder for `role` and return one `lgwks.model.port.v1` envelope.

    Attempts are tried in trust-tier order (deterministic → sensor → generative),
    regardless of the order passed in — the law owns precedence, not the caller.
    The first rung that resolves AT OR ABOVE `threshold` wins. A resolved-but-
    below-threshold rung is held as a fallback: if no higher-confidence answer
    ever arrives, the best below-threshold result is returned as `mode=degraded`
    rather than fabricating or losing it. If nothing resolves at all → deferred.
    """
    ordered = sorted(attempts, key=lambda a: mesh.tier_rank(a.trust_class))
    suppressed = models_suppressed()
    trace: list[dict[str, Any]] = []
    best_fallback: tuple[float, Attempt, Any] | None = None

    for att in ordered:
        if suppressed and att.trust_class in _WEIGHT_TIERS:
            trace.append({"tier": att.trust_class, "model": att.model,
                          "label": att.label, "outcome": "suppressed",
                          "why": "LGWKS_NO_MODELS"})
            continue
        try:
            if att.trust_class in _WEIGHT_TIERS:
                # weight tiers load/run a model — bound them so a stuck load or
                # download degrades to a defer instead of hanging the CLI
                result = _run_bounded(att.run, _model_timeout())
            else:
                result = att.run()  # deterministic tier is pure code; never capped
        except Exception as exc:  # a rung failing is an escalation, never a crash
            trace.append({"tier": att.trust_class, "model": att.model,
                          "label": att.label, "outcome": "error",
                          "why": f"{type(exc).__name__}: {exc}"})
            continue
        if result is None:
            trace.append({"tier": att.trust_class, "model": att.model,
                          "label": att.label, "outcome": "unavailable"})
            continue
        conf = att.confidence(result) if att.confidence else 1.0
        if conf >= threshold:
            trace.append({"tier": att.trust_class, "model": att.model,
                          "label": att.label, "outcome": "resolved", "confidence": conf})
            return _envelope(
                role, ok=True, mode=att.trust_class, tier=att.trust_class,
                model=att.model, trust=att.trust_class, value=result,
                confidence=conf, escalation=trace,
                why=f"resolved at {att.trust_class} tier"
                    + (f" ({att.model})" if att.model else ""),
            )
        trace.append({"tier": att.trust_class, "model": att.model, "label": att.label,
                      "outcome": "below_threshold", "confidence": conf})
        if best_fallback is None or conf > best_fallback[0]:
            best_fallback = (conf, att, result)

    if best_fallback is not None:
        conf, att, result = best_fallback
        return _envelope(
            role, ok=True, mode="degraded", tier=att.trust_class, model=att.model,
            trust=att.trust_class, value=result, confidence=conf, escalation=trace,
            why=f"no tier met threshold {threshold}; returning best effort "
                f"({att.trust_class}, conf={conf:.2f})",
        )

    # Nothing answered — fail closed. Never fabricate (INV-3).
    return _envelope(role, ok=False, mode="deferred", escalation=trace,
                     why=defer_why + (" [LGWKS_NO_MODELS]" if suppressed else ""))


# ── Role helpers — wire the existing backends into the ladder ──────────────────
# Each helper builds the rungs from real code/models, pins model ids from the law,
# and hands them to escalate(). Callers ask for the ROLE, never a backend.

def extract_entities(text: str, entity_types: list[str] | None = None) -> dict[str, Any]:
    """role=extract — pull entity mentions, escalating det regex → CoreML → Foundation.

    deterministic : T1 regex enumeration (lgwks_entity_graph.extract_mentions) — zero deps.
    sensor        : T2 CoreML schema classifier (lgwks_coreml) — narrow, local, auditable.
    generative    : T3 Apple Foundation Models structured extraction (lgwks_foundation).

    Resolves at the cheapest tier that returns mentions. Value is a list of
    {"type","text","start","end"} dicts; deferred (value=None) if every tier is empty.
    """
    types = entity_types

    def _t1() -> list[dict[str, Any]] | None:
        import lgwks_entity_graph as eg
        ms = eg.extract_mentions(text)
        if types:
            ms = [m for m in ms if m.entity_type in types]
        return [{"type": m.entity_type, "text": m.text, "start": m.start, "end": m.end}
                for m in ms] or None

    def _t3() -> list[dict[str, Any]] | None:
        # Apple Foundation Models (generative) for the ambiguous long tail; it
        # internally degrades to NaturalLanguage NER when FM is absent.
        import lgwks_foundation
        fm = lgwks_foundation.extract_entities(text, entity_types=types)
        if fm.status != "ok" or not fm.entities:
            return None
        return [{"type": e.type, "text": e.text, "start": e.start, "end": e.end}
                for e in fm.entities]

    return escalate("extract", [
        Attempt("deterministic", _t1, label="regex"),
        Attempt("generative", _t3,
                model=mesh.model_name_for_role("extract", trust_class="generative",
                                               default="apple.foundation_models"),
                label="foundation"),
    ], defer_why="no entities found by any tier")


def classify(text: str, *, threshold: float = 0.60) -> dict[str, Any]:
    """role=classify — assign a schema label, escalating to the narrow ML sensor.

    deterministic : (none today) — there is no zero-model schema rule, so this role
                    starts at the sensor tier and defers when no model is present.
    sensor        : CoreML TF-IDF/LogReg page classifier (lgwks_coreml) — local, auditable.

    Resolves only when the sensor clears `threshold`; otherwise deferred (the chunk
    keeps schema=UNKNOWN rather than being mislabelled). Value: {"schema","confidence"}.
    """
    def _coreml() -> dict[str, Any] | None:
        import lgwks_coreml
        res = lgwks_coreml.classify_page(text)
        if res.get("source") in ("no_model", "empty_input"):
            return None
        return {"schema": res.get("schema", "UNKNOWN"),
                "confidence": float(res.get("confidence", 0.0))}

    return escalate("classify", [
        Attempt("sensor", _coreml,
                confidence=lambda r: r.get("confidence", 0.0),
                model=mesh.model_name_for_role("classify", trust_class="sensor"),
                label="coreml"),
    ], threshold=threshold, defer_why="no schema classifier available")


def embed(text: str = "", *, modality: str = "text",
          media: Any = None) -> dict[str, Any]:
    """role=embed — one multimodal vector (text/image/video), as a port envelope.

    Embedding is the role where the deterministic tier is ALWAYS present (the
    feature-hash / perceptual-fingerprint audit vector) and the sensor tier is the
    real semantic answer (the VL Eye). So this does not single-winner escalate —
    it returns BOTH vectors and reports which tier produced the *semantic* one:
    `mode="sensor"` when the Eye answered, `mode="degraded"` (audit vector only,
    is_semantic=False) when no model was reachable. Never deferred — an audit
    vector always exists.
    """
    import lgwks_run
    dual = lgwks_run.embed_dual(text, embed_on=True, modality=modality, media=media)
    sem = dual.get("sem")
    eye = mesh.model_name_for_role("embed", trust_class="sensor")
    if sem and sem.get("vector"):
        return _envelope(
            "embed", ok=True, mode="sensor", tier="sensor", model=eye, trust="sensor",
            value=dual, confidence=1.0,
            escalation=[{"tier": "deterministic", "outcome": "resolved", "label": "audit"},
                        {"tier": "sensor", "outcome": "resolved", "model": eye}],
            why=f"semantic vector from the Eye ({eye})",
        )
    return _envelope(
        "embed", ok=True, mode="degraded", tier="deterministic", model=None,
        trust="deterministic", value=dual, confidence=1.0,
        escalation=[{"tier": "deterministic", "outcome": "resolved", "label": "audit"},
                    {"tier": "sensor", "outcome": "unavailable", "model": eye}],
        why="no model reachable; deterministic audit vector only (NOT semantic)",
    )


def reason(prompt: str, **kw: Any) -> dict[str, Any]:
    """role=proposal — delegate to the reasoning port, re-dressed as a port envelope.

    The reasoning port is already a ladder (local OLMo → agent handoff → deferred);
    this wraps its result in the uniform `lgwks.model.port.v1` shape so a caller
    reads one envelope schema for every role. No model name is hardcoded — the
    pinned generative proposal model comes from the law.
    """
    import lgwks_reasoning_port as rp
    r = rp.reason(prompt, **kw)
    mode_map = {"local": "generative", "agent_handoff": "generative", "deferred": "deferred"}
    mode = mode_map.get(r.get("mode", ""), "deferred")
    return _envelope(
        "proposal", ok=bool(r.get("ok")), mode=mode, tier=mode,
        model=r.get("model") or mesh.model_name_for_role("proposal", trust_class="generative"),
        trust="generative" if mode != "deferred" else None,
        value=r if mode != "deferred" else None,
        escalation=[{"tier": "generative", "outcome": r.get("mode"),
                     "model": r.get("model")}],
        why=f"reasoning port → {r.get('mode')}",
    )


if __name__ == "__main__":  # manual smoke
    import json
    import sys
    text = " ".join(sys.argv[1:]) or "Contact admin@example.com about $4,200 due 2026-06-15."
    print(json.dumps(extract_entities(text), indent=2, default=str))
