"""lgwks_reasoning_port — runtime-neutral DEEP-REASONING seam.

Callers ask for the *role* `reasoning`, never a specific model. The port resolves
a backend via the canonical ladder (`lgwks_model_port.escalate`) when a model
rung is present, and falls to `agent_handoff` (the working agent) when it isn't.

  1. olmo_mlx     — the mesh-law deep-reasoning model under store/models/ (id from
                     lgwks_model_mesh, never hardcoded) + mlx_lm importable (owned, Mac only)
  2. agent_handoff — hand the request to the WORKING AGENT (Claude / Codex /
                     Gemini — operator's pick). This IS the frontier path (INV-5).
  3. deferred     — no local model AND no agent → defer to human. NEVER fabricate.

No network calls. The port returns a proposal (local text) or a handoff/deferral
envelope. The daemon/gate decides; the human authorizes.
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


def resolve_backend() -> str:
    """Thin selector — the kill-switch and forcing belong to the canonical port,
    not a reimplemented ladder. One check, one env-var, one availability probe."""
    from lgwks_model_port import models_suppressed
    if models_suppressed():
        return "agent_handoff"
    forced = os.environ.get("LGWKS_REASONING_BACKEND", "auto").lower()
    if forced == "agent":
        return "agent_handoff"
    if forced == "olmo":
        return "olmo_mlx" if _olmo_available() else "agent_handoff"
    return "olmo_mlx" if _olmo_available() else "agent_handoff"


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
