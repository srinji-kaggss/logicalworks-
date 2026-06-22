"""
lgwks_openrouter_embed — optional remote embedding seam via OpenRouter.

This is intentionally not the default Eye. The substrate stays local-first; this provider exists as
an explicit second path for remote multimodal/text embedding models such as NVIDIA's Nemotron Embed VL.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import lgwks_keyvault
import lgwks_openrouter

if TYPE_CHECKING:
    from lgwks_model_port import Embedder  # contract only (#152)

ENDPOINT = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_MODEL = os.environ.get("LGWKS_EYE_REMOTE_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2:free")
_REFERER = "https://logicalworks.ca"
_TITLE = "Logical Works - lgwks substrate eye"

# Same OpenRouter provider, same kill-switch + keyvault check — one source of truth.
is_configured = lgwks_openrouter.is_configured


def embed_one(
    text: str,
    model: str = DEFAULT_MODEL,
    *,
    input_type: str = "search_document",
    timeout: int = 60,
) -> list[float] | None:
    from lgwks_model_port import models_suppressed
    if models_suppressed():
        return None
    key, _ = lgwks_keyvault.get_secret("openrouter")
    if not key:
        return None
    body = json.dumps({
        "model": model,
        "input": text[:32_000],
        "encoding_format": "float",
        "input_type": input_type,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": _REFERER,
            "X-OpenRouter-Title": _TITLE,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    try:
        vec = data["data"][0]["embedding"]
        return [float(x) for x in vec]
    except (KeyError, IndexError, TypeError, ValueError):
        return None


if TYPE_CHECKING:
    _conforms_embedder: Embedder = embed_one  # static conformance to the shared contract (#152)
