"""lgwks_reasoning_port — runtime-neutral DEEP-REASONING seam.

The parallel of `lgwks_embed_port`: callers ask for the *role* `reasoning`, never
a specific model. The port resolves a backend by device tier and what's present:

  1. olmo_mlx     — store/models/Olmo-3-1125-32B-4bit + mlx_lm importable
                    (owned, re-engineerable, ~18GB → ~32GB+ Mac only)
  2. agent_handoff — hand the request to the WORKING AGENT (Claude / Codex /
                    Gemini — operator's pick), which is already a daemon client.
                    This REPLACES the old "rented brain": the frontier layer IS
                    the agent on top of the daemon.
  3. deferred     — no local model AND no agent in the loop → defer to the human.
                    NEVER fabricate (INV-3 / fail-closed).

No network calls here. The port never executes actions — it returns a proposal
(local text) or a handoff/deferral envelope. The daemon/gate decides; the human
authorizes. Specialized roles (co-scientist, …) are PERSONAS — prompt/harness
framing applied here, not separate weights.

Honors LGWKS_NO_MODELS (kill-switch → agent_handoff) and
LGWKS_REASONING_BACKEND (force "olmo" | "agent" | "auto", default auto).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SCHEMA = "lgwks.reasoning.result.v1"

_REPO_ROOT = Path(__file__).resolve().parent
_MODEL_STORE = _REPO_ROOT / "store" / "models"
# Pinned owned deep-reasoning model (MODEL-RUNTIME-FINALIZATION §8). Override for
# non-default layouts; weights live in gitignored store/models/ (setup step).
_OLMO_MODEL_DIR = os.environ.get(
    "LGWKS_REASONING_MODEL",
    str(_MODEL_STORE / "Olmo-3-1125-32B-4bit"),
)

# Personas are HARNESS framing, not models. Specializing a role = editing these
# (or adding one), never swapping weights. Framing is prepended for the local
# backend and carried verbatim in the handoff envelope for the agent.
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
    """True iff the OLMo weights are present AND mlx_lm is importable."""
    if not Path(_OLMO_MODEL_DIR).exists():
        return False
    import importlib.util
    return importlib.util.find_spec("mlx_lm") is not None


def resolve_backend() -> str:
    """Pick the reasoning backend. Safe default is agent_handoff (never fabricate)."""
    if os.environ.get("LGWKS_NO_MODELS"):
        return "agent_handoff"
    forced = os.environ.get("LGWKS_REASONING_BACKEND", "auto").lower()
    if forced == "agent":
        return "agent_handoff"
    if forced == "olmo":
        return "olmo_mlx" if _olmo_available() else "agent_handoff"
    # auto: prefer the owned local model when it's actually present, else hand off
    return "olmo_mlx" if _olmo_available() else "agent_handoff"


def _framing(persona: str) -> str:
    return PERSONAS.get(persona, PERSONAS["default"])


def _run_olmo_mlx(prompt: str, framing: str, context: str | None) -> str | None:
    """Run OLMo-3-32B locally via mlx_lm. Returns text, or None to fall back.

    Real integration (not a stub): if weights + mlx_lm are present it generates;
    any failure returns None so the caller degrades to agent_handoff (INV-6).
    EASY-FIX-LATER: tune sampler/max_tokens/chat-template per OLMo-3 card.
    """
    try:
        from mlx_lm import generate, load  # type: ignore
        model, tokenizer = load(_OLMO_MODEL_DIR)
        parts = [framing]
        if context:
            parts.append(f"\nContext:\n{context}")
        parts.append(f"\nTask:\n{prompt}")
        full = "\n".join(parts)
        return generate(model, tokenizer, prompt=full, max_tokens=1024, verbose=False)
    except Exception:
        return None  # degrade to handoff — never block, never fabricate


def reason(
    prompt: str,
    *,
    context: str | None = None,
    persona: str = "default",
    agent: str | None = None,
) -> dict[str, Any]:
    """Deep-reasoning entry point. Returns a proposal or a handoff/deferral envelope.

    Modes: `local` (OLMo proposed text) · `agent_handoff` (surface to the working
    agent) · `deferred` (no local model + no agent → human). Deterministic in the
    non-local paths (safe to test without weights).
    """
    framing = _framing(persona)
    backend = resolve_backend()
    base: dict[str, Any] = {"schema": SCHEMA, "persona": persona, "backend": backend}

    if backend == "olmo_mlx":
        text = _run_olmo_mlx(prompt, framing, context)
        if text is not None:
            return {**base, "ok": True, "mode": "local", "model": "Olmo-3-1125-32B-4bit",
                    "text": text}
        backend = base["backend"] = "agent_handoff"  # OLMo failed → hand off

    # agent_handoff: the frontier layer is the working agent (operator's pick).
    target = agent or os.environ.get("LGWKS_AGENT") or "working_agent"
    if target and target != "none":
        return {
            **base, "ok": True, "mode": "agent_handoff", "model": None,
            "handoff": {
                "to": target,
                "reason": "deep_reasoning_exceeds_local_tier",
                "request": {"prompt": prompt, "framing": framing, "context": context},
            },
        }

    # no local model AND no agent in the loop → defer to human; never fabricate.
    return {
        **base, "ok": False, "mode": "deferred", "model": None,
        "deferred": {"to": "human", "why": "no local reasoning model and no agent available"},
    }


if __name__ == "__main__":  # manual smoke
    import json, sys
    p = " ".join(sys.argv[1:]) or "Is this change safe to merge?"
    print(json.dumps(reason(p, persona="co_scientist"), indent=2))
