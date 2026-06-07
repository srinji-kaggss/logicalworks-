"""
lgwks_openrouter — cloud Tongue via OpenRouter (Issue #7).

Why cloud for the Tongue: generation is intentionally not tied to a local Ollama model. OpenRouter
is the vendor-AGNOSTIC seam: one endpoint, many models, swappable via LGWKS_TONGUE_MODEL or an
explicit caller-supplied model. The Eye stays LOCAL (qwen3-embedding); only generation goes cloud
when the user configures it.

Trust: the API key is resolved just-in-time from lgwks_keyvault (Keychain), NEVER from source/logs.
The key is scrubbed from every error string. Fails closed to None → caller drops to the
deterministic skeleton. Anti-slop: response_format=json_object + strict schema in-prompt; a response
that does not parse as JSON is a fallback, never trusted prose.

Grounded against OpenRouter docs (/websites/openrouter_ai, 2026-05-31): POST
https://openrouter.ai/api/v1/chat/completions, Authorization: Bearer <key>, OpenAI-compatible body.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import lgwks_keyvault

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
# Swappable. Default = preferred free model; override per-run with LGWKS_TONGUE_MODEL or pass an
# explicit model to generate_json(..., model=...). Explicit models are used alone.
DEFAULT_MODEL = os.environ.get("LGWKS_TONGUE_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
# Free models throttle independently and unpredictably (HTTP 429 upstream). The Tongue tries the
# preferred model FIRST, then rotates through other free models on a retryable error — so a single
# throttled provider degrades to another FREE model, not to the deterministic skeleton. All :free.
FREE_FALLBACKS = [
    "poolside/laguna-m.1:free",
    "moonshotai/kimi-k2.6:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]
# App-attribution headers (OpenRouter rankings); declared as research, not commercial.
_REFERER = "https://logicalworks.ca"
_TITLE = "Logical Works - lgwks research instrument"   # ASCII only: HTTP headers are latin-1


def is_configured() -> bool:
    """Cloud Tongue is available only if a key resolves AND the kill-switch is off."""
    if os.environ.get("LGWKS_NO_MODELS"):   # hermetic kill-switch (tests/CI) — forces fallback
        return False
    return lgwks_keyvault.is_configured("openrouter")


def _models_to_try(model: str | None) -> list[str]:
    """Preferred model first, then free fallbacks (deduped). An explicit `model` is used ALONE —
    the caller asked for a specific one, so we do not silently route around it."""
    if model:
        return [model]
    seen, order = set(), []
    for m in [DEFAULT_MODEL, *FREE_FALLBACKS]:
        if m not in seen:
            seen.add(m)
            order.append(m)
    return order


_LAST_USAGE = 0   # total_tokens of the most recent successful call — read by generate_json_metered


def _call_one(model: str, prompt: str, schema_hint: str, key: str, timeout: int) -> tuple[dict | None, bool]:
    """One attempt. Returns (parsed_json_or_None, retryable). retryable=True means rotate to the next
    free model (429 throttle / 5xx); False means stop (success, or a non-retryable client error)."""
    global _LAST_USAGE
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON. No prose, no markdown."},
            {"role": "user", "content": f"{prompt}\n\nReturn ONLY valid JSON matching: {schema_hint}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        # Cap output: the hypothesis envelope is small JSON. Without this, models default to a huge
        # max_tokens (e.g. 64k) and low-credit accounts hit HTTP 402. Override via LGWKS_TONGUE_MAXTOK.
        "max_tokens": int(os.environ.get("LGWKS_TONGUE_MAXTOK", "4000")),
    }).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": _REFERER,
        "X-OpenRouter-Title": _TITLE,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None, e.code in (429, 500, 502, 503, 504)   # throttle / upstream → try next free model
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, True   # transient network → worth trying another model
    try:
        parsed = json.loads(data["choices"][0]["message"]["content"])
        _LAST_USAGE = int(data.get("usage", {}).get("total_tokens", 0) or 0)
        return parsed, False
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None, False   # answered but unparseable → not a throttle; do not spin the chain


def generate_json_metered(prompt: str, schema_hint: str, model: str | None = None,
                          timeout: int = 60) -> tuple[dict | None, int]:
    """Like generate_json, but also returns total_tokens spent (0 on failure) for budget accounting."""
    out = generate_json(prompt, schema_hint, model, timeout)
    return out, (_LAST_USAGE if out is not None else 0)


def take_usage() -> int:
    """Return total_tokens of the last cloud call and zero the counter (so the loop can meter each
    Tongue call without double-counting). Local-Ollama calls don't set it → reads as 0 (free)."""
    global _LAST_USAGE
    n, _LAST_USAGE = _LAST_USAGE, 0
    return n


def generate_json(prompt: str, schema_hint: str, model: str | None = None,
                  timeout: int = 60) -> dict | None:
    """Forced-JSON cloud generation (the Tongue). Tries the preferred model then rotates through free
    fallbacks on retryable errors. Returns parsed dict, or None to signal deterministic fallback.
    Never logs the error body (it may echo the key)."""
    if os.environ.get("LGWKS_NO_MODELS"):
        return None
    key, _ = lgwks_keyvault.get_secret("openrouter")
    if not key:
        return None
    for m in _models_to_try(model):
        out, retryable = _call_one(m, prompt, schema_hint, key, timeout)
        if out is not None:
            return out
        if not retryable:
            return None   # genuine answer-shaped failure (bad JSON / non-retryable 4xx) → fail closed
    return None           # every free model throttled → fall back to local/deterministic
