"""lgwks_lfm2_extract — strict schema fill via LFM2-1.2B-Extract (GGUF, llama.cpp).

//why: the v2 crawler emits raw text + typed media; LFM2-Extract structures the
text into typed fields via a strict JSON-Schema. LFM2 fills; it does not score.
Scoring is I5 (deterministic RESCAL). This module is order-1: unstructured →
structured, never scores or ranks. Non-conformant output is rejected, never stored.

When llama-cli / the model are absent (dev, CI, any machine without the model
stack), fill_schema() falls back to _stdlib_fill() — stdlib-only, deterministic,
noisy but never None. Callers can distinguish via result["source"].
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


SCHEMA_VERSION = "lgwks.lfm2_extract.v1"

DEFAULT_MODEL_GLOB = "LFM2*Extract*.gguf"
DEFAULT_STORE_DIR = "store/models"
MAX_CONTENT_CHARS = 4000
MAX_NEW_TOKENS = 512


class SchemaFillError(ValueError):
    """Raised when LFM2-Extract output fails JSON-Schema validation.

    Never store non-conformant fills — the contract is strict by design.
    """


def find_lfm2_model(store_dir: str = DEFAULT_STORE_DIR) -> str | None:
    """Search store_dir for an LFM2-Extract GGUF model. Returns path or None."""
    p = Path(store_dir)
    if not p.is_dir():
        return None
    for pattern in (DEFAULT_MODEL_GLOB, "lfm2*.gguf", "LFM2*.gguf"):
        matches = list(p.glob(pattern))
        if matches:
            return str(matches[0])
    return None


def fill_schema(
    page_dict: dict,
    schema: dict,
    *,
    model_path: str | None = None,
    timeout_s: int = 60,
) -> dict | None:
    """Fill `schema` from page content using LFM2-Extract via llama.cpp.

    Parameters
    ----------
    page_dict:
        A Page dict from the v2 crawler (must have `title`, `url`, `text` keys).
    schema:
        A JSON-Schema dict defining the strict structure to fill.
    model_path:
        Path to the GGUF model. If None, auto-discovers in store/models/.
    timeout_s:
        Subprocess timeout in seconds.

    Returns
    -------
    A dict conforming to `schema`. Source is indicated by result["source"]:
      "lfm2"        — model ran and output validated
      "stdlib"      — llama-cli or model absent; deterministic stdlib fill

    Raises
    ------
    SchemaFillError
        If the model output fails JSON-Schema validation. Never returns
        non-conformant data. (Does not apply to the stdlib fallback path.)
    """
    binary = shutil.which("llama-cli") or shutil.which("llama.cpp")
    if binary is None:
        return _stdlib_fill(page_dict)

    if model_path is None:
        model_path = find_lfm2_model()
    if model_path is None or not Path(model_path).exists():
        return _stdlib_fill(page_dict)

    content = _build_content(page_dict)
    prompt = (
        "Fill the following JSON schema from this web page content. "
        "Return ONLY valid JSON, no prose, no markdown fences.\n\n"
        f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"Content:\n{content}"
    )

    cmd = [
        binary,
        "--model", model_path,
        "--prompt", prompt,
        "--json-schema", json.dumps(schema),
        "-n", str(MAX_NEW_TOKENS),
        "--no-display-prompt",
        "--log-disable",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    raw = proc.stdout.strip()
    if not raw:
        return None

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SchemaFillError(f"LFM2-Extract output is not valid JSON: {e}") from e

    _validate(result, schema)
    result.setdefault("source", "lfm2")
    return result


# ── internal ──────────────────────────────────────────────────────────────────

# Common English stopwords for the topic extractor — no external deps needed.
_STOPWORDS = frozenset(
    "a an the and or but in on at to of for is are was were be been "
    "have has had do does did will would could should may might this "
    "that these those with from by into about over after before its "
    "it he she they we you i me my their our your his her".split()
)


def _stdlib_fill(page_dict: dict) -> dict:
    """Deterministic stdlib-only fill. Noisy but always runnable.

    Used when llama-cli is absent (dev, CI, model not downloaded). Never None.
    Caller can detect this path via result["source"] == "stdlib".
    """
    title = (page_dict.get("title") or "").strip()
    text = (page_dict.get("text") or page_dict.get("markdown") or "").strip()

    summary = text[:500].strip()

    # Heuristic entities: runs of title-cased words (2+ word sequences).
    import re  # noqa: PLC0415
    raw_entities = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    # Deduplicate preserving first-seen order; cap at 10.
    seen: set[str] = set()
    entities: list[str] = []
    for e in raw_entities:
        if e not in seen:
            seen.add(e)
            entities.append(e)
        if len(entities) >= 10:
            break

    # Heuristic topics: top-5 non-stopword content words by frequency.
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    topics = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]]

    return {
        "title": title,
        "summary": summary,
        "entities": entities,
        "topics": topics,
        "source": "stdlib",
    }


def _build_content(page_dict: dict) -> str:
    title = page_dict.get("title", "")
    url = page_dict.get("url", "")
    text = page_dict.get("text", "") or page_dict.get("markdown", "")
    text = text[:MAX_CONTENT_CHARS]
    return f"Title: {title}\nURL: {url}\n\n{text}"


def _validate(data: dict, schema: dict) -> None:
    """Validate data against schema. Raises SchemaFillError on failure."""
    try:
        import jsonschema  # noqa: PLC0415
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            raise SchemaFillError(
                f"LFM2-Extract output failed schema validation: {e.message}"
            ) from e
    except ImportError:
        # jsonschema not installed — do a minimal required-keys check
        required = schema.get("required", [])
        missing = [k for k in required if k not in data]
        if missing:
            raise SchemaFillError(
                f"LFM2-Extract output missing required keys: {missing}"
            )
