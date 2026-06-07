"""
lgwks_ollama — local Ollama provider for the Eye (embeddings), Issue #7.

stdlib-only client (urllib) so the project keeps zero pip deps. Every call FAILS CLOSED to a
fallback signal — if Ollama is down or the model is missing, the caller drops to the deterministic
provider and the run never fails (FACTORY_SPEC: "missing provider must fall back to deterministic").

Local roster:
  Eye    = qwen3-embedding:8b   (4096-d; full vector — Ollama has no MRL dim param, slice client-side)

Generation is routed through OpenRouter (`lgwks_openrouter`) or deterministic fallback, not through
a local Ollama reasoning model.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HOST = "http://localhost:11434"
EYE_MODEL = "qwen3-embedding:8b"


def _post(path: str, payload: dict, timeout: int) -> dict | None:
    try:
        req = urllib.request.Request(
            f"{HOST}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def is_up(timeout: int = 2) -> bool:
    if os.environ.get("LGWKS_NO_MODELS"):   # hermetic kill-switch: forces all fallbacks (tests/CI)
        return False
    try:
        with urllib.request.urlopen(f"{HOST}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _have_model(name: str, timeout: int = 2) -> bool:
    data = _post("/api/tags", {}, timeout) or {}
    return any(str(m.get("name", "")).split(":")[0] == name.split(":")[0]
               for m in data.get("models", []))


_eye_ready = False


def ensure_eye_model(model: str = EYE_MODEL) -> bool:
    """Pull the local embedding model on start so local embed works out of the box (Director's spec:
    'embedding model is downloaded on start for local embed'). No-op if already present or Ollama is
    down. The Eye stays LOCAL — only the Tongue goes cloud. Returns True if the model is ready.
    Memoised: the per-chunk caller pays the /api/tags check at most once per process."""
    global _eye_ready
    if _eye_ready:
        return True
    if os.environ.get("LGWKS_NO_MODELS") or not is_up():
        return False
    if _have_model(model):
        _eye_ready = True
        return True
    print(f"  Eye: pulling {model} (one-time local download)…", flush=True)
    try:
        import subprocess
        proc = subprocess.run(["ollama", "pull", model], timeout=3600)
        if proc.returncode == 0:
            _eye_ready = True
        return proc.returncode == 0
    except Exception:
        return False


def embed_one(text: str, model: str = EYE_MODEL, timeout: int = 60) -> list[float] | None:
    """Real semantic embedding (the Eye). Returns the full native vector, or None to signal fallback."""
    if os.environ.get("LGWKS_NO_MODELS"):
        return None
    data = _post("/api/embed", {"model": model, "input": text[:8000]}, timeout)
    if not data:
        return None
    vecs = data.get("embeddings") or ([data["embedding"]] if "embedding" in data else None)
    if not vecs or not vecs[0]:
        return None
    return [float(x) for x in vecs[0]]


def slice_mrl(vec: list[float], dims: int) -> list[float]:
    """Matryoshka client-side truncation (Ollama returns full 4096; we slice for the hot graph)."""
    return vec[:dims] if dims and dims < len(vec) else vec
