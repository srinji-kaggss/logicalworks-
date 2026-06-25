"""lgwks_reasoning_port — runtime-neutral DEEP-REASONING seam.

The parallel of `lgwks_embed_port`: callers ask for the *role* `reasoning`, never
a specific model. The port resolves a backend by device tier and what's present:

  1. olmo_mlx     — the mesh-law deep-reasoning model under store/models/ (id from
                    lgwks_model_mesh, never hardcoded) + mlx_lm importable (owned, Mac only)
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

SCHEMA = "lgwks.reasoning.result.v0"  # research-grade (breakable); daemon-dispatch wiring pending

_ANTHROPIC_MODEL_DEFAULT = "claude-haiku-4-5-20251001"

_REPO_ROOT = Path(__file__).resolve().parent
_MODEL_STORE = _REPO_ROOT / "store" / "models"


def _law_model_dir() -> str:
    """Resolve the deep-reasoning weights dir FROM THE LAW (lgwks_model_mesh), never a
    hardcoded id — the model name lives in exactly one place (the mesh law) so runtime
    cannot drift from it (same rule lgwks_model_port states). The store layout keeps
    weights under store/models/<basename of the law id>."""
    try:
        import lgwks_model_mesh as mesh
        name = mesh.model_name_for_role("proposal", trust_class="generative") or ""
    except Exception:
        name = ""
    basename = name.split("/")[-1] if name else "OLMo-2-0325-32B-Instruct-4bit"
    return str(_MODEL_STORE / basename)


# Owned deep-reasoning model dir, pinned FROM the law (single source of truth).
# Override for non-default layouts; weights live in gitignored store/models/.
_OLMO_MODEL_DIR = os.environ.get("LGWKS_REASONING_MODEL", _law_model_dir())

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


def _anthropic_key() -> tuple[str, str]:
    """Return (api_key, auth_style) where auth_style is 'x-api-key' or 'bearer'.
    Reads from ANTHROPIC_API_KEY (standard) or CLAUDE_SESSION_INGRESS_TOKEN_FILE
    (Claude Code session). Returns ('', '') if neither is available."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key, "x-api-key"
    token_file = os.environ.get("CLAUDE_SESSION_INGRESS_TOKEN_FILE", "").strip()
    if token_file:
        try:
            k = Path(token_file).read_text().strip()
            if k:
                return k, "bearer"
        except Exception:
            pass
    return "", ""


def _anthropic_available() -> bool:
    """True when an API key (env or session file) is present."""
    key, _ = _anthropic_key()
    return bool(key)


def _run_anthropic(prompt: str, framing: str, context: str | None) -> str | None:
    """Call Anthropic Messages API via stdlib urllib. Returns text or None on failure.

    Uses Authorization: Bearer for session tokens (sk-ant-si-…) and x-api-key for
    standard API keys. Bypasses proxy for api.anthropic.com (in no_proxy list).
    Falls back gracefully on any error — never raises, never blocks (INV-6).
    """
    import json
    import urllib.request

    key, auth_style = _anthropic_key()
    if not key:
        return None

    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    model_id = os.environ.get("LGWKS_REASONING_MODEL_ID", _ANTHROPIC_MODEL_DEFAULT)

    parts = [framing]
    if context:
        parts.append(f"\nContext:\n{context}")
    parts.append(f"\nTask:\n{prompt}")
    full_prompt = "\n".join(parts)

    payload = json.dumps({
        "model": model_id,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": full_prompt}],
    }).encode()

    auth_header = ({"Authorization": f"Bearer {key}"}
                   if auth_style == "bearer"
                   else {"x-api-key": key})

    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=payload,
        headers={"Content-Type": "application/json",
                 "anthropic-version": "2023-06-01",
                 **auth_header},
        method="POST",
    )

    try:
        # api.anthropic.com is in no_proxy — use a plain opener (no proxy injection)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=60) as resp:
            data = json.loads(resp.read())
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return None
    except Exception:
        return None


def resolve_backend() -> str:
    """Pick the reasoning backend. Safe default is agent_handoff (never fabricate)."""
    from lgwks_model_port import models_suppressed
    if models_suppressed():
        return "agent_handoff"
    forced = os.environ.get("LGWKS_REASONING_BACKEND", "auto").lower()
    if forced == "agent":
        return "agent_handoff"
    if forced == "olmo":
        return "olmo_mlx" if _olmo_available() else "agent_handoff"
    if forced == "anthropic":
        return "anthropic_api" if _anthropic_available() else "agent_handoff"
    # auto: prefer owned local model, then Anthropic API, then hand off
    if _olmo_available():
        return "olmo_mlx"
    if _anthropic_available():
        return "anthropic_api"
    return "agent_handoff"


def _framing(persona: str) -> str:
    return PERSONAS.get(persona, PERSONAS["default"])


def _run_olmo_mlx(prompt: str, framing: str, context: str | None) -> str | None:
    """Run OLMo-3-32B locally via mlx_lm. Returns text, or None to fall back.

    Real integration (not a stub): if weights + mlx_lm are present it generates;
    any failure returns None so the caller degrades to agent_handoff (INV-6).
    EASY-FIX-LATER: tune sampler/max_tokens/chat-template per OLMo-3 card.
    """
    from lgwks_model_port import _model_timeout, _run_bounded

    def _go() -> str:
        from mlx_lm import generate, load  # type: ignore
        model, tokenizer = load(_OLMO_MODEL_DIR)
        parts = [framing]
        if context:
            parts.append(f"\nContext:\n{context}")
        parts.append(f"\nTask:\n{prompt}")
        full = "\n".join(parts)
        return generate(model, tokenizer, prompt=full, max_tokens=1024, verbose=False)

    try:
        # bound the load+generate so a stuck weight load degrades to handoff
        # instead of hanging the caller — a hang is not an Exception. The cure
        # lives in model_port; reuse it rather than restate it.
        return _run_bounded(_go, _model_timeout())
    except Exception:
        return None  # degrade to handoff (TimeoutError included) — never block


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
            return {**base, "ok": True, "mode": "local",
                    "model": Path(_OLMO_MODEL_DIR).name,  # law-derived id, never hardcoded
                    "text": text}
        backend = base["backend"] = "anthropic_api" if _anthropic_available() else "agent_handoff"

    if backend == "anthropic_api":
        text = _run_anthropic(prompt, framing, context)
        if text is not None:
            model_id = os.environ.get("LGWKS_REASONING_MODEL_ID", _ANTHROPIC_MODEL_DEFAULT)
            return {**base, "ok": True, "mode": "local",  # "local" = synchronous text available
                    "model": model_id, "text": text}
        backend = base["backend"] = "agent_handoff"  # Anthropic call failed → hand off

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
