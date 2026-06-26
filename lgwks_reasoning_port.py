"""lgwks_reasoning_port — runtime-neutral DEEP-REASONING seam.

Callers ask for the *role* `reasoning`, never a specific model. The port resolves
a backend via the canonical ladder (`lgwks_model_port.escalate`) when a model
rung is present, and falls to `agent_handoff` (the working agent) when it isn't.

  1. olmo_mlx     — the mesh-law deep-reasoning model under store/models/ (id from
                     lgwks_model_mesh, never hardcoded) + mlx_lm importable (owned, Mac only)
  2. cloud_tongue — OPT-IN cloud plane (LGWKS_MODEL_LOCALITY=cloud). The model is
                     SELECTED through the models.dev catalog (lgwks_model_port.resolve_model
                     on the CLOUD plane) and EXECUTED through the OpenRouter Tongue
                     (lgwks_openrouter). Cloud providers (incl. Anthropic) are reached
                     ONLY through this canonical seam — never a direct provider/api call.
                     Defers (→ agent_handoff) when unconfigured; never silently chosen.
  3. agent_handoff — hand the request to the WORKING AGENT (Claude / Codex /
                     Gemini — operator's pick). This IS the frontier path (INV-5).
  4. deferred     — no model AND no agent → defer to human. NEVER fabricate.

No network calls on the LOCAL plane (the default). The cloud_tongue tier is the only
networked path and is opt-in. The port returns a proposal (synchronous text) or a
handoff/deferral envelope. The daemon/gate decides; the human authorizes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SCHEMA = "lgwks.reasoning.result.v0"

_REPO_ROOT = Path(__file__).resolve().parent
_MODEL_STORE = _REPO_ROOT / "store" / "models"


def _law_model_dir() -> str:
    try:
        import lgwks_model_mesh as mesh
        name = mesh.model_name_for_role("proposal", trust_class="generative") or ""
    except Exception:
        name = ""
    basename = name.split("/")[-1] if name else "OLMo-2-0325-32B-Instruct-4bit"
    return str(_MODEL_STORE / basename)


_OLMO_MODEL_DIR = os.environ.get("LGWKS_REASONING_MODEL", _law_model_dir())

PERSONAS: dict[str, str] = {
    "default": (
        "Reason carefully and PROPOSE; do not act. State assumptions explicitly "
        "and DEFER when uncertain. The gate and the human hold authority."
    ),
    "co_scientist": (
        "You are a curious, contrarian, ownership-driven co-scientist. Form "
        "hypotheses, attack them, demand evidence, and name what is missing. "
        "Propose and question — never decide. The gate and the human hold authority."
    ),
}


def _olmo_available() -> bool:
    if not Path(_OLMO_MODEL_DIR).exists():
        return False
    import importlib.util
    return importlib.util.find_spec("mlx_lm") is not None


def _cloud_available() -> bool:
    """Cloud reasoning is OPT-IN and must be configured end to end: a cloud model
    SELECTED through the models.dev catalog (resolve_model on the CLOUD plane returns
    a card, else None) AND a reachable OpenRouter Tongue key. Cloud providers are
    reached ONLY through this canonical seam — never a direct provider/api call."""
    from lgwks_model_port import CLOUD, resolve_model
    if resolve_model("proposal", locality=CLOUD) is None:
        return False
    import lgwks_openrouter
    return lgwks_openrouter.is_configured()


def resolve_backend() -> str:
    """Thin selector — the kill-switch, locality (opt-in cloud), and forcing belong
    to the canonical port, not a reimplemented ladder."""
    from lgwks_model_port import CLOUD, active_locality, models_suppressed
    if models_suppressed():
        return "agent_handoff"
    forced = os.environ.get("LGWKS_REASONING_BACKEND", "auto").lower()
    if forced == "agent":
        return "agent_handoff"
    if forced == "olmo":
        return "olmo_mlx" if _olmo_available() else "agent_handoff"
    if forced == "cloud":
        return "cloud_tongue" if _cloud_available() else "agent_handoff"
    # auto: the locality axis picks the plane (LOCAL default ⊕ CLOUD opt-in). When
    # the user opts into cloud, route there — but never silently fall back to a local
    # model; hand off if the cloud seam isn't configured.
    if active_locality() == CLOUD:
        return "cloud_tongue" if _cloud_available() else "agent_handoff"
    return "olmo_mlx" if _olmo_available() else "agent_handoff"


def _run_cloud(prompt: str, framing: str, context: str | None) -> tuple[str, str] | None:
    """Deep reasoning on the CLOUD plane via the canonical seam: the model id comes
    from the models.dev card (never hardcoded here), execution goes through the
    OpenRouter Tongue (lgwks_openrouter). Returns (text, model_ref) or None to fall
    back to agent_handoff. Never raises."""
    from lgwks_model_port import CLOUD, resolve_model
    sel = resolve_model("proposal", locality=CLOUD)
    if not sel:
        return None
    model_ref = sel["runtime_id"]  # models.dev-selected slug; never a literal here
    try:
        import lgwks_openrouter
        parts = [framing]
        if context:
            parts.append(f"\nContext:\n{context}")
        parts.append(f"\nTask:\n{prompt}")
        schema_hint = '{"reasoning": "<full analysis and proposal as one string>"}'
        out = lgwks_openrouter.generate_json("\n".join(parts), schema_hint, model=model_ref)
    except Exception:
        return None
    if out and isinstance(out.get("reasoning"), str) and out["reasoning"].strip():
        return out["reasoning"], model_ref
    return None


def _framing(persona: str) -> str:
    return PERSONAS.get(persona, PERSONAS["default"])


def _run_olmo_mlx(prompt: str, framing: str, context: str | None) -> str | None:
    from lgwks_model_port import _model_timeout, _run_bounded

    def _go() -> str:
        from mlx_lm import generate, load  # type: ignore
        model, tokenizer = load(_OLMO_MODEL_DIR)
        parts = [framing]
        if context:
            parts.append(f"\nContext:\n{context}")
        parts.append(f"\nTask:\n{prompt}")
        return generate(model, tokenizer, prompt="\n".join(parts), max_tokens=1024, verbose=False)

    try:
        return _run_bounded(_go, _model_timeout())
    except Exception:
        return None


def reason(
    prompt: str,
    *,
    context: str | None = None,
    persona: str = "default",
    agent: str | None = None,
) -> dict[str, Any]:
    framing = _framing(persona)
    backend = resolve_backend()
    base: dict[str, Any] = {"schema": SCHEMA, "persona": persona, "backend": backend}

    if backend == "olmo_mlx":
        text = _run_olmo_mlx(prompt, framing, context)
        if text is not None:
            return {**base, "ok": True, "mode": "local",
                    "model": Path(_OLMO_MODEL_DIR).name, "text": text}
        backend = base["backend"] = "agent_handoff"

    if backend == "cloud_tongue":
        out = _run_cloud(prompt, framing, context)
        if out is not None:
            text, model_ref = out
            return {**base, "ok": True, "mode": "cloud", "model": model_ref, "text": text}
        backend = base["backend"] = "agent_handoff"  # cloud unreachable → hand off

    target = agent or os.environ.get("LGWKS_AGENT") or "working_agent"
    if target and target != "none":
        return {
            **base, "ok": True, "mode": "agent_handoff", "model": None,
            "handoff": {"to": target, "reason": "deep_reasoning_exceeds_local_tier",
                        "request": {"prompt": prompt, "framing": framing, "context": context}},
        }

    return {**base, "ok": False, "mode": "deferred", "model": None,
            "deferred": {"to": "human", "why": "no local reasoning model and no agent available"}}


if __name__ == "__main__":
    import json, sys
    p = " ".join(sys.argv[1:]) or "Is this change safe to merge?"
    print(json.dumps(reason(p, persona="co_scientist"), indent=2))
