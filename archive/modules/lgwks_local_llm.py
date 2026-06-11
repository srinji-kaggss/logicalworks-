"""
lgwks_local_llm — Local LLM inference bridge via Ollama (Docker Desktop).

No cloud. Runs entirely offline. Fallbacks gracefully if Ollama is not active.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"


def available() -> bool:
    """Check if local Ollama server is active and reachable."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def generate(
    prompt: str,
    model: str = "qwen2.5-coder:1.5b",
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Generate text completion from the local Ollama instance."""
    if not available():
        return {
            "ok": False,
            "text": "",
            "model": "",
            "tokens": 0,
            "reason": "Ollama not available. Ensure Ollama is running on port 11434.",
        }

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "text": data.get("response", ""),
                "model": model,
                "tokens": data.get("eval_count", 0),
                "reason": "ollama-local",
            }
    except Exception as exc:
        return {
            "ok": False,
            "text": "",
            "model": "",
            "tokens": 0,
            "reason": f"Ollama request error: {exc}",
        }
