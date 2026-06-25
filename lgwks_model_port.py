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
rather than invent an answer.

TIER CEILING ("threshold, not chain"). A caller sets `escalate(..., ceiling=...)`
to cap how high the ladder may climb for a request — the per-request codification
of "don't reach the expensive, less-trustworthy tier until truly needed." The
`LGWKS_NO_MODELS` kill-switch is the special case `ceiling="deterministic"` (only
the deterministic tier runs); it is not a second control, just the most
restrictive ceiling, so both flow through one suppression path.

OUTPUT. Every call returns one uniform envelope (`lgwks.model.port.v1`) carrying
the winning tier, the law model id, the trust class, the value, and a full
`escalation` trace of what was tried — so a caller (or the daemon's training
ledger) can read exactly how an answer was reached.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

import lgwks_model_mesh as mesh
import lgwks_substrate_config as _cfg  # canonical repo ROOT — one source of truth

SCHEMA = "lgwks.model.port.v1"
SELECTION_SCHEMA = "lgwks.model.selection.v1"


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

# Tiers that load weights / touch a model artifact. These are the hang-class
# rungs that must run under a wall-clock bound; the deterministic tier is always
# pure code and runs uncapped. (Suppression is decided by the tier ceiling, not
# by this set — see escalate().)
_WEIGHT_TIERS = frozenset({"sensor", "generative"})


def models_suppressed() -> bool:
    """True when LGWKS_NO_MODELS is set — the env form of `ceiling="deterministic"`.

    The one kill-switch for the whole layer (was honored only by the reasoning
    port before). `escalate` reads this as the most restrictive tier ceiling, so
    the switch and the per-request `ceiling` param share a single suppression path
    rather than being two parallel controls. Any truthy value engages it;
    unset/empty disengages.
    """
    return bool(os.environ.get("LGWKS_NO_MODELS"))


# ── Locality axis — WHERE a role runs (orthogonal to the trust-tier ladder) ──
# The ladder above chooses WHICH tier answers (deterministic→sensor→generative).
# This axis chooses WHERE that tier's model lives, and it is the ONE selector:
#   LOCAL     — the on-device Model Mesh (MESH_LAW) + lgwks_model_hub. Privacy-
#               first, no network. The DEFAULT.
#   CLOUD     — the models.dev catalog (lgwks_models_dev). Used ONLY when the user
#               opts in (LGWKS_MODEL_LOCALITY=cloud, or an explicit locality= arg).
#   AETHERIUS — the future end-of-ingestion model; reserved slot, DEFERRED
#               ("data is a whole workstream"). Resolves to None today.
LOCAL = "local"
CLOUD = "cloud"
AETHERIUS = "aetherius"
LOCALITIES = (LOCAL, CLOUD, AETHERIUS)

# The selector's durable choice (locality + per-role model). Lives in the state
# dir beside the models.dev cache; the TUI (S3 #338) reads/writes it through the
# `lgwks models` CLI — there is NO model state in the Rust side, only a projection.
SELECTION_PATH = _cfg.ROOT / ".lgwks" / "model-selection.json"


def load_selection() -> dict[str, Any]:
    """The persisted selection, or {} when absent/corrupt (never raises)."""
    try:
        data = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_selection(sel: dict[str, Any]) -> dict[str, Any]:
    """Atomically persist the selection (tmp + os.replace). Returns it."""
    sel.setdefault("schema", SELECTION_SCHEMA)
    SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SELECTION_PATH.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sel, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, SELECTION_PATH)  # concurrent reader sees old-or-new, never partial
    return sel


def active_locality() -> str:
    """The chosen locality, by precedence: env LGWKS_MODEL_LOCALITY > persisted
    selection > LOCAL. The default is the private local plane (no network); an
    unknown value falls back to LOCAL (fail-safe — never silently to the cloud)."""
    val = os.environ.get("LGWKS_MODEL_LOCALITY") or load_selection().get("locality") or LOCAL
    val = str(val).strip().lower()
    return val if val in LOCALITIES else LOCAL


def set_locality(locality: str) -> dict[str, Any]:
    """Persist the active locality (the TUI/CLI writes here). Rejects unknowns."""
    loc = str(locality).strip().lower()
    if loc not in LOCALITIES:
        raise ValueError(f"locality must be one of {LOCALITIES} (got {locality!r})")
    sel = load_selection()
    sel["locality"] = loc
    return _save_selection(sel)


def set_model(role: str, ref: str, *, locality: str | None = None) -> dict[str, Any]:
    """Persist the chosen model `ref` for `role`, optionally switching locality.
    The id is stored verbatim (a law name for local, a models.dev ref for cloud)
    — resolve_model maps it to a runtime id at call time."""
    sel = load_selection()
    sel.setdefault("models", {})[role] = ref
    if locality is not None:
        loc = str(locality).strip().lower()
        if loc not in LOCALITIES:
            raise ValueError(f"locality must be one of {LOCALITIES} (got {locality!r})")
        sel["locality"] = loc
    return _save_selection(sel)


def _hub_key(law_name: str | None) -> str | None:
    """Map a MESH_LAW model name to its lgwks_model_hub catalog key.

    Convention, true for every current_law entry: the hub key is the law name
    minus its org prefix (`mlx-community/ModernBERT-base-mlx-4bit` →
    `ModernBERT-base-mlx-4bit`; `Qwen/Qwen3-VL-Embedding-8B` →
    `Qwen3-VL-Embedding-8B`). Reconstructable by hand — split on '/'. If a future
    law name breaks the convention, hub.load_model fails closed with a clear
    "unknown model" error rather than embedding silently wrong."""
    return law_name.split("/")[-1] if law_name else None


def resolve_model(role: str, *, locality: str | None = None,
                  trust_class: str = "sensor") -> dict[str, Any] | None:
    """Resolve the model for `role` on the chosen locality — the ONE selector
    across the locality axis. Returns a descriptor, or None to DEFER.

      LOCAL  → the pinned MESH_LAW model for (role, trust_class); `runtime_id` is
               the model_hub catalog key. Pure data + string work; no network.
      CLOUD  → a normalized models.dev card for the configured cloud ref
               (env `LGWKS_CLOUD_<ROLE>_MODEL`). Opt-in: None when unconfigured or
               unreachable — never silently falls back to local.
      AETHERIUS → reserved; None today (the model is deferred).

    The model id ALWAYS comes from the law (local) or the card (cloud) — never a
    literal at the call site (#222). Callers read `descriptor["runtime_id"]`.
    """
    loc = locality or active_locality()
    if loc == CLOUD:
        # cloud ref by precedence: env > persisted selection (never guess a model)
        ref = (os.environ.get(f"LGWKS_CLOUD_{role.upper()}_MODEL")
               or (load_selection().get("models") or {}).get(role))
        if not ref:
            return None  # cloud is opt-in AND must be configured; defer otherwise
        import lgwks_models_dev as md
        card = md.resolve(ref)
        if not card:
            return None  # unknown/unreachable cloud ref → defer, do not fabricate
        return {"role": role, "locality": CLOUD, "law_name": ref,
                "runtime_id": ref, "card": card}
    if loc == AETHERIUS:
        return None  # reserved slot — no model/training here yet
    law_name = mesh.model_name_for_role(role, trust_class=trust_class)
    if not law_name:
        return None
    return {"role": role, "locality": LOCAL, "law_name": law_name,
            "runtime_id": _hub_key(law_name)}


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
    ceiling: str = "generative",
    defer_why: str = "no tier could answer",
) -> dict[str, Any]:
    """Run the ladder for `role` and return one `lgwks.model.port.v1` envelope.

    Attempts are tried in trust-tier order (deterministic → sensor → generative),
    regardless of the order passed in — the law owns precedence, not the caller.
    The first rung that resolves AT OR ABOVE `threshold` wins. A resolved-but-
    below-threshold rung is held as a fallback: if no higher-confidence answer
    ever arrives, the best below-threshold result is returned as `mode=degraded`
    rather than fabricating or losing it. If nothing resolves at all → deferred.

    `threshold` (how good must a rung be to win) and `ceiling` (how far up the
    ladder we may climb) together are the full "set threshold, not chain" knob:
    the caller declares intent; the law owns precedence; the harness obeys both.

    `ceiling` is the highest trust tier this request may use — the caller's
    codification of "don't reach the expensive, less-trustworthy tier until truly
    needed." It must be one of the locked `trust_class` names
    (`deterministic` | `sensor` | `generative`); the default `generative` is
    today's behaviour (no rung is ever above it → zero change for existing
    callers). A rung above the ceiling is skipped with `outcome="above_ceiling"`.
    The `LGWKS_NO_MODELS` kill-switch is NOT a parallel control: it is exactly
    `ceiling="deterministic"`, and both funnel through the one rank comparison
    below — one mechanism, not two. An unknown ceiling raises (fail loud) rather
    than silently permitting the LLM.
    """
    if ceiling not in mesh.TIER_ORDER:
        raise ValueError(
            f"ceiling {ceiling!r} is not a trust_class; "
            f"expected one of {mesh.TIER_ORDER}"
        )
    ordered = sorted(attempts, key=lambda a: mesh.tier_rank(a.trust_class))
    # The kill-switch collapses to the most restrictive ceiling. After this line
    # there is a single notion of "how high may we climb": effective_ceiling.
    effective_ceiling = "deterministic" if models_suppressed() else ceiling
    ceiling_rank = mesh.tier_rank(effective_ceiling)
    # Did the ceiling actually hold the ladder below its top? Only then do we
    # annotate the deferred envelope — default generative leaves it untouched.
    restricted = ceiling_rank < mesh.tier_rank("generative")
    trace: list[dict[str, Any]] = []
    best_fallback: tuple[float, Attempt, Any] | None = None

    for att in ordered:
        # Skip a rung above the ceiling — but only when the ceiling actually
        # restricts (below generative). At the default top ceiling nothing is ever
        # skipped, so an unknown/miscatalogued trust_class (which sorts last) keeps
        # its pre-ceiling behaviour: default is a provable identity. When the caller
        # DOES restrict, an unknown tier outranks the ceiling and is skipped —
        # fail-closed, never silently let past.
        if restricted and mesh.tier_rank(att.trust_class) > ceiling_rank:
            trace.append({"tier": att.trust_class, "model": att.model,
                          "label": att.label, "outcome": "above_ceiling",
                          "why": f"ceiling={effective_ceiling}"})
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

    # Nothing answered — fail closed. Never fabricate (INV-3). When the ceiling
    # held the ladder down (whether via the param or the NO_MODELS kill-switch),
    # record WHY the upper tiers were never reached so the training ledger can read
    # that the LLM was declined by policy, not merely unavailable.
    return _envelope(role, ok=False, mode="deferred", escalation=trace,
                     why=defer_why + (f" [ceiling={effective_ceiling}]" if restricted else ""))


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
          media: Any = None, locality: str | None = None) -> dict[str, Any]:
    """role=embed — one multimodal vector (text/image/video), as a port envelope.

    Embedding is the role where the deterministic tier is ALWAYS present (the
    feature-hash / perceptual-fingerprint audit vector) and the sensor tier is the
    real semantic answer (the VL Eye). So this does not single-winner escalate —
    it returns BOTH vectors and reports which tier produced the *semantic* one:
    `mode="sensor"` when the Eye answered, `mode="degraded"` (audit vector only,
    is_semantic=False) when no model was reachable. Never deferred — an audit
    vector always exists.

    `locality` picks the plane via the ONE selector (LOCAL Mesh default ⊕ CLOUD
    models.dev opt-in); the Eye's id is resolved from the law / card by
    `resolve_model`, never a literal. CLOUD routes through the existing remote
    seam and degrades to the audit vector if it is unconfigured/unreachable.
    """
    loc = locality or active_locality()
    sel = resolve_model("embed", locality=loc)
    eye = (sel["law_name"] if sel else
           mesh.model_name_for_role("embed", trust_class="sensor"))
    provider = "openrouter-vl" if loc == CLOUD else "auto"
    import lgwks_run
    dual = lgwks_run.embed_dual(text, embed_on=True, provider=provider,
                                modality=modality, media=media)
    sem = dual.get("sem")
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


# ── Unified two-plane catalog (the selector's view; the TUI projects this) ──
def catalog(*, provider: str | None = None) -> dict[str, Any]:
    """The unified model catalog across the locality axis — what the selector and
    the TUI render. Offline-safe (cloud reads the cached models.dev snapshot; a
    cold/empty cache just yields an empty cloud plane). Loads no model.

      local  — MESH_LAW current-law entries grouped by role (the on-device Mesh).
      cloud  — models.dev providers with model counts; `--provider` drills into
               that provider's model ids. Marked opt-in; local is the default.
    """
    sel = load_selection()
    local = [
        {"role": e.get("role"), "law_name": e.get("name"),
         "runtime_id": _hub_key(e.get("name")), "trust_class": e.get("trust_class"),
         "notes": e.get("notes")}
        for e in mesh.MESH_LAW
        if e.get("status") == "current_law" and e.get("name")
    ]
    local.sort(key=lambda r: (r["role"] or "", r["law_name"] or ""))

    cloud: dict[str, Any] = {"opt_in": True, "providers": [], "models": [], "degraded": False}
    try:
        import lgwks_models_dev as md
        snap = md.refresh()  # offline-first: served from cache, never raises
        cloud["degraded"] = bool(snap.get("degraded"))
        if provider is not None:
            cloud["models"] = md.models(provider)
        else:
            provs = snap.get("providers") or {}
            cloud["providers"] = sorted(
                ({"id": pid, "models": len((pmeta or {}).get("models") or {})}
                 for pid, pmeta in provs.items()),
                key=lambda p: p["id"],
            )
    except Exception:
        cloud["degraded"] = True  # cloud plane unavailable — local is unaffected

    return {
        "schema": "lgwks.model.catalog.v1",
        "active_locality": active_locality(),
        "default_locality": LOCAL,
        "selection": sel.get("models") or {},
        "local": local,
        "cloud": cloud,
    }


# ── CLI: `lgwks models` — the one selection surface (read + write) ──────────
def add_parser(sub: Any) -> None:
    p = sub.add_parser("models", help="model selector — list/choose across local Mesh + cloud models.dev")
    s = p.add_subparsers(dest="action", required=True)
    lp = s.add_parser("list", help="unified two-plane catalog (local Mesh + cloud)")
    lp.add_argument("--provider", default=None, help="drill into one cloud provider's models")
    lp.add_argument("--json", action="store_true")
    g = s.add_parser("get", help="active locality + current per-role selection")
    g.add_argument("--json", action="store_true")
    lo = s.add_parser("locality", help="set the active plane (local|cloud|aetherius)")
    lo.add_argument("value", choices=list(LOCALITIES))
    u = s.add_parser("use", help="choose a model for a role (and optionally its locality)")
    u.add_argument("ref", help="law name (local) or providerID/modelID (cloud)")
    u.add_argument("--role", default="embed")
    u.add_argument("--locality", default=None, choices=list(LOCALITIES))
    p.set_defaults(func=_run)  # dispatcher convention: args.func(args)


def _run(args: Any) -> int:
    if args.action == "list":
        print(json.dumps(catalog(provider=getattr(args, "provider", None)), indent=2))
        return 0
    if args.action == "get":
        sel = load_selection()
        print(json.dumps({"schema": SELECTION_SCHEMA, "active_locality": active_locality(),
                          "default_locality": LOCAL, "selection": sel.get("models") or {}}, indent=2))
        return 0
    if args.action == "locality":
        print(json.dumps(set_locality(args.value), indent=2))
        return 0
    if args.action == "use":
        print(json.dumps(set_model(args.role, args.ref, locality=args.locality), indent=2))
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="lgwks models")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add_parser(sub)
    args = parser.parse_args(["models", *(argv if argv is not None else sys.argv[1:])])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
