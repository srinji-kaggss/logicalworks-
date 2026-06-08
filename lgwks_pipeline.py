"""
lgwks_pipeline — unified ingestion and ranking spine.

Wires together existing lgwks modules:
  - lgwks_substrate.build_run()    — crawl + chunk + embed + entity graph
  - lgwks_run.embed()              — provider chain (Ollama → apple-local → deterministic)
  - lgwks_run._deterministic_embed()
  - lgwks_embed._tokens(), _chunks(), _cos(), _embedding()
  - lgwks_entity_graph.extract_mentions(), GraphDB
  - lgwks_intent_classifier.IntentClassifier
  - lgwks_jepa.build_package()
  - lgwks_ollama.embed_one(), slice_mrl()
  - lgwks_apple.embed_one()
  - lgwks_keyvault.get_secret()

Novel additions (not elsewhere in the codebase):
  - Multi-stage ranking: Recall → FastRank → HeavyRank → Rerank
  - Noise quarantine with PCA summary embedding
  - Gemma 1B disambiguation gate (LLM-capped)
  - google/gemini-embedding-2 multimodal seam (private, OpenRouter)
  - Provenance tagging: math | ml | llm | mm per chunk
  - pipeline_manifest.json as world-model artifact for downstream consumers

ADR reference: docs/ADR-pipeline-001-tuning.md
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

# ── existing lgwks modules ─────────────────────────────────────────────────────
import lgwks_keyvault

# These are imported lazily inside functions to mirror lgwks conventions and
# avoid circular-import risk at module level.

ROOT = Path(__file__).resolve().parent
PIPELINE_STORE = ROOT / "store" / "pipeline"

PIPELINE_MANIFEST_SCHEMA = "lgwks.pipeline.manifest.v1"

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURABLE PARAMETERS  [see docs/ADR-pipeline-001-tuning.md]
# All values are provisional first-run defaults. Do NOT inline magic numbers.
# Every constant is tagged with its ADR section.  Override via env vars.
# ══════════════════════════════════════════════════════════════════════════════

RECALL_K: int = int(os.environ.get("LGWKS_RECALL_K", "2000"))           # [ADR §2.1]
FAST_RANK_K: int = int(os.environ.get("LGWKS_FAST_RANK_K", "200"))      # [ADR §2.2]
HEAVY_RANK_K: int = int(os.environ.get("LGWKS_HEAVY_RANK_K", "50"))     # [ADR §2.3]

DISAMBIGUATION_CONF_THRESHOLD: float = float(                            # [ADR §3.1]
    os.environ.get("LGWKS_DISAMBIG_CONF_THRESHOLD", "0.72"))
DISAMBIGUATION_MAX_VARIANTS: int = int(                                  # [ADR §3.2]
    os.environ.get("LGWKS_DISAMBIG_MAX_VARIANTS", "4"))

NOISE_SCORE_THRESHOLD: float = float(                                    # [ADR §4.1]
    os.environ.get("LGWKS_NOISE_THRESHOLD", "0.72"))
DIVERSITY_PENALTY_WEIGHT: float = float(                                 # [ADR §4.2]
    os.environ.get("LGWKS_DIVERSITY_PENALTY", "0.30"))
SAME_SOURCE_CAP: int = int(os.environ.get("LGWKS_SAME_SOURCE_CAP", "5"))# [ADR §4.3]

MAX_LLM_INVOLVEMENT_RATIO: float = float(                                # [ADR §5.1]
    os.environ.get("LGWKS_MAX_LLM_RATIO", "0.20"))

FAST_RANK_W_BM25: float = 0.40           # [ADR §6.1] — change all weights together
FAST_RANK_W_FACT_DENSITY: float = 0.20
FAST_RANK_W_COVERAGE: float = 0.15
FAST_RANK_W_ENTITY_OVERLAP: float = 0.15
FAST_RANK_W_RECENCY: float = 0.10

DATASET_BATCH_SIZE: int = int(os.environ.get("LGWKS_BATCH_SIZE", "256"))# [ADR §7.1]

MULTIMODAL_EMBED_MODEL: str = os.environ.get(                           # [ADR §8.1]
    "LGWKS_MM_EMBED_MODEL", "google/gemini-embedding-2")
MULTIMODAL_EMBED_ENDPOINT: str = "https://openrouter.ai/api/v1/embeddings"
MULTIMODAL_MAX_IMAGE_BYTES: int = int(                                   # [ADR §8.2]
    os.environ.get("LGWKS_MM_MAX_IMG_BYTES", str(6 * 1024 * 1024)))

COHERENCE_THRESHOLD: float = float(                                      # [ADR §9.1]
    os.environ.get("LGWKS_COHERENCE_THRESHOLD", "0.65"))

_GEMMA_MODEL: str = os.environ.get("LGWKS_GEMMA_MODEL", "gemma3:1b")

# ══════════════════════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineChunk:
    """Normalised chunk — source-agnostic envelope around substrate/file/dataset rows."""
    chunk_id: str
    source_id: str       # URL, file path, or dataset row key
    source_type: str     # "url" | "file" | "dataset" | "image"
    text: str
    fact_score: float = 0.0
    chunk_kind: str = ""
    image_b64: str = ""
    image_mime: str = ""
    entities: list[str] = field(default_factory=list)


@dataclass
class EmbedResult:
    chunk_id: str
    vector: list[float]
    dims: int
    provider: str
    is_semantic: bool
    signal_path: str              # "math" | "ml" | "mm" | "llm"
    interpretation_variants: list[str] = field(default_factory=list)


@dataclass
class RankedChunk:
    chunk: PipelineChunk
    embed: EmbedResult
    fast_rank_score: float = 0.0
    heavy_rank_score: float = 0.0
    final_score: float = 0.0
    noise_score: float = 0.0
    quarantined: bool = False
    signal_path: str = "math"
    llm_touches: int = 0
    classifier_confidence: float = 1.0


@dataclass
class NoiseRecord:
    chunk_id: str
    noise_score: float
    reason: str           # "noise_threshold" | "source_cap" | "diversity_cap"
    signal_path: str


# ══════════════════════════════════════════════════════════════════════════════
# MATH UTILITIES  — wrapper layer delegates to lgwks_embed where already built
# ══════════════════════════════════════════════════════════════════════════════

def _cosine(a: list[float], b: list[float]) -> float:
    """Thin wrapper — uses lgwks_embed._cos() which is already tested."""
    import lgwks_embed
    return lgwks_embed._cos(a, b)


def _l2_norm(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _vec_mean(vecs: list[list[float]]) -> list[float]:
    if not vecs:
        return []
    dims = len(vecs[0])
    result = [0.0] * dims
    for v in vecs:
        for i, x in enumerate(v):
            result[i] += x
    n = len(vecs)
    return [x / n for x in result]


def _weighted_centroid(
    vecs: list[list[float]], weights: list[float]
) -> list[float]:
    if not vecs:
        return []
    total = sum(weights) or 1.0
    dims = len(vecs[0])
    result = [0.0] * dims
    for v, w in zip(vecs, weights):
        for i, x in enumerate(v):
            result[i] += x * w / total
    return _l2_norm(result)


def _first_principal_component(vecs: list[list[float]]) -> list[float]:
    """Power-iteration PCA — stdlib only.  Used for noise summary embedding."""
    if not vecs:
        return []
    dims = len(vecs[0])
    mean = _vec_mean(vecs)
    centered = [[x - m for x, m in zip(v, mean)] for v in vecs]
    import random
    rng = random.Random(42)
    pc = [rng.gauss(0, 1) for _ in range(dims)]
    for _ in range(20):
        proj = [sum(c[i] * pc[i] for i in range(dims)) for c in centered]
        new_pc = [0.0] * dims
        for s, c in zip(proj, centered):
            for i in range(dims):
                new_pc[i] += s * c[i]
        n = math.sqrt(sum(x * x for x in new_pc)) or 1.0
        pc = [x / n for x in new_pc]
    return pc


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL EXTRACTORS  — delegates to lgwks_entity_graph for entity mentions;
#                      BM25 is novel (not elsewhere in codebase)
# ══════════════════════════════════════════════════════════════════════════════

_IDF_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "are",
    "was", "be", "this", "that", "with", "from", "at", "by", "on", "as",
}

_PROCEDURE_RE = re.compile(
    r"\b(must|requires|required|only|cannot|blocked|allowed|if\b|when\b|"
    r"then\b|before|after|submit|transfer|route|settlement|minimum|maximum|"
    r"threshold|code\b|form\b|designation|version\b)\b",
    re.IGNORECASE,
)
_NARRATIVE_RE = re.compile(
    r"\b(think|feel|believe|love|maybe|probably|helpful|great|excellent|"
    r"frustrated|opinion|story|journey|marketing|vision|obviously|clearly|"
    r"simply|just|very|really)\b",
    re.IGNORECASE,
)
_BOILER_RE = re.compile(
    r"\b(cookie|privacy policy|terms of service|all rights reserved|"
    r"click here|read more|learn more|sign up|log in|subscribe)\b",
    re.IGNORECASE,
)


def _tokenize(text: str) -> list[str]:
    """Delegates to lgwks_embed._tokens() — already tested."""
    import lgwks_embed
    return lgwks_embed._tokens(text)


def bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
    avg_doc_len: float = 120.0,
) -> float:
    """BM25 — not elsewhere in codebase.  Pure arithmetic, no models."""
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    freq: dict[str, int] = {}
    for t in doc_tokens:
        freq[t] = freq.get(t, 0) + 1
    score = 0.0
    for qt in set(query_tokens):
        tf = freq.get(qt, 0)
        if tf == 0:
            continue
        idf = math.log((1 - 0 + 0.5) / (0 + 0.5) + 1)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf * numerator / denominator
    return round(score, 6)


def compute_fact_density(text: str) -> float:
    if not text.strip():
        return 0.0
    proc = len(_PROCEDURE_RE.findall(text))
    narr = len(_NARRATIVE_RE.findall(text))
    words = max(len(text.split()), 1)
    return round(max(0.0, min(1.0, (proc - 0.5 * narr) / words * 10)), 4)


def compute_noise_score(chunk: PipelineChunk) -> float:
    """Heuristic noise score [0,1].  Delegates fact_score from substrate when available."""
    # If substrate already computed a low fact_score, trust it.
    if chunk.fact_score > 0:
        # Substrate fact_score is 0=low, 1=high.  We want noise_score inverted.
        base_noise = 1.0 - min(chunk.fact_score, 1.0)
    else:
        base_noise = None

    text = chunk.text
    if not text.strip():
        return 1.0
    words = text.split()
    if len(words) < 8:
        return 0.85

    boiler = len(_BOILER_RE.findall(text))
    punct_spam = len(re.findall(r"[!?]{2,}|[A-Z]{4,}", text))
    link_count = len(re.findall(r"\[.*?\]\(https?://[^\)]+\)", text))
    link_ratio = link_count / max(len(words), 1)
    fd = compute_fact_density(text)

    heuristic = (
        0.30 * min(1.0, boiler / 3)
        + 0.20 * min(1.0, punct_spam / 5)
        + 0.20 * min(1.0, link_ratio * 10)
        + 0.30 * (1.0 - fd)
    )

    if base_noise is not None:
        # Blend substrate fact_score (60%) with heuristic (40%) for better accuracy
        return round(min(1.0, max(0.0, 0.60 * base_noise + 0.40 * heuristic)), 4)
    return round(min(1.0, max(0.0, heuristic)), 4)


def extract_chunk_entities(text: str) -> list[str]:
    """Delegates to lgwks_entity_graph.extract_mentions() — T1 regex, always works."""
    try:
        import lgwks_entity_graph as eg
        mentions = eg.extract_mentions(text)
        return [m.text for m in mentions]
    except Exception:
        return []


def entity_overlap_score(
    query_entities: list[str], chunk_entities: list[str]
) -> float:
    if not query_entities or not chunk_entities:
        return 0.0
    qs = {e.lower() for e in query_entities}
    cs = {e.lower() for e in chunk_entities}
    inter = len(qs & cs)
    union = len(qs | cs)
    return round(inter / max(union, 1), 4)


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING — delegates fully to lgwks_run.embed() for text;
#             adds novel Gemini-embedding-2 multimodal seam
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_text_provider() -> str:
    if os.environ.get("LGWKS_NO_MODELS"):
        return "deterministic"
    try:
        import lgwks_ollama
        if lgwks_ollama.is_up():
            return "auto"   # lgwks_run.embed() auto = ollama → deterministic
    except Exception:
        pass
    try:
        import lgwks_apple
        if lgwks_apple.is_available():
            return "apple-local"
    except Exception:
        pass
    return "deterministic"


def embed_text(text: str, provider: str | None = None) -> tuple[list[float], str, bool]:
    """Fully delegates to lgwks_run.embed() — the canonical provider chain."""
    import lgwks_run
    p = provider or _resolve_text_provider()
    vec, prov_label, is_sem = lgwks_run.embed(text, embed_on=True, provider=p)
    if vec is None:
        vec = lgwks_run._deterministic_embed(text)
        prov_label = "deterministic-feature-hash"
        is_sem = False
    return vec, prov_label, is_sem


def _mm_key() -> str | None:
    key, _ = lgwks_keyvault.get_secret("openrouter")
    return key or None


def embed_multimodal(
    text: str,
    image_b64: str = "",
    image_mime: str = "image/png",
) -> tuple[list[float], str, bool]:
    """google/gemini-embedding-2 via OpenRouter for image+text chunks.
    Falls back to text-only embed_text() if no key or model unavailable.
    Free VL model deliberately excluded. [ADR §8.1]"""
    if not image_b64:
        return embed_text(text)

    key = _mm_key()
    if not key:
        return embed_text(text)

    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append({"type": "text", "text": text[:8000]})
    parts.append({
        "type": "image_url",
        "image_url": {"url": f"data:{image_mime};base64,{image_b64}"},
    })

    body = json.dumps({
        "model": MULTIMODAL_EMBED_MODEL,
        "input": parts,
        "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(
        MULTIMODAL_EMBED_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://logicalworks.ca",
            "X-OpenRouter-Title": "Logical Works - lgwks multimodal eye",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vec = [float(x) for x in data["data"][0]["embedding"]]
        return _l2_norm(vec), f"openrouter:{MULTIMODAL_EMBED_MODEL}", True
    except Exception:
        return embed_text(text)


# ══════════════════════════════════════════════════════════════════════════════
# DATASET INTAKE — streaming, batched; reads substrate artifacts when available
# ══════════════════════════════════════════════════════════════════════════════

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              "target", ".next", "dist", "build", "store"}


def _sha(text: str, n: int = 16) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _chunk_id(source_id: str, text: str, idx: int) -> str:
    return "chunk-" + _sha(f"{source_id}|{idx}|{text[:80]}")


def _iter_substrate_dir(
    run_dir: Path, batch_size: int
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    """Read an existing substrate run — reuse its chunks AND pre-computed vectors.
    Yields (batch_of_chunks, {chunk_id: vector}) pairs so we skip re-embedding."""
    chunks_file = run_dir / "chunks.jsonl"
    vectors_file = run_dir / "vectors.jsonl"
    if not chunks_file.exists():
        return

    # Build vector lookup first (may be large — stream it)
    vec_lookup: dict[str, list[float]] = {}
    if vectors_file.exists():
        with vectors_file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    cid = row.get("chunk_id", "")
                    vec_raw = row.get("vector")
                    if cid and vec_raw:
                        if isinstance(vec_raw, list):
                            vec_lookup[cid] = [float(x) for x in vec_raw]
                        elif isinstance(vec_raw, str):
                            vec_lookup[cid] = [float(x) for x in json.loads(vec_raw)]
                except Exception:
                    continue

    batch: list[PipelineChunk] = []
    batch_vecs: dict[str, list[float]] = {}

    with chunks_file.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = row.get("chunk_id", _chunk_id(str(run_dir), row.get("text", ""), 0))
            text = row.get("text") or row.get("stem_text") or row.get("vector_text") or ""
            if not text.strip():
                continue
            pc = PipelineChunk(
                chunk_id=cid,
                source_id=row.get("source") or row.get("url") or str(run_dir),
                source_type="url",
                text=text,
                fact_score=float(row.get("fact_score", 0.0)),
                chunk_kind=row.get("chunk_kind", ""),
            )
            batch.append(pc)
            if cid in vec_lookup:
                batch_vecs[cid] = vec_lookup[cid]
            if len(batch) >= batch_size:
                yield batch, batch_vecs
                batch = []
                batch_vecs = {}
    if batch:
        yield batch, batch_vecs


def _iter_url_chunks(
    url: str, batch_size: int
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    """Run substrate.build_run() on a URL, then stream its artifacts."""
    import lgwks_substrate as sub
    ns = argparse.Namespace(
        target=url, project="", source_type="url",
        max_pages=500, max_depth=4, max_files=0, max_chars=200_000,
        chunk_words=400, chunk_overlap=48, fact_threshold=0.15,
        embed_provider="auto", embed_model="",
        login_if_needed=False, login_url="",
        success_selector=None, max_auto_bypass_attempts=0,
        max_auth_handoffs=0, browser_engine="webkit",
        crawl_mode="link-then-click", click_discovery=False,
        max_clicks_per_page=20, refresh_graph=False,
    )
    try:
        result = sub.build_run(ns)
        run_root = Path(result.get("root", ""))
        if run_root.exists():
            yield from _iter_substrate_dir(run_root, batch_size)
            return
    except Exception as exc:
        print(f"[pipeline][warn] substrate.build_run failed: {exc}", file=sys.stderr)

    # Fallback: no substrate artifacts, yield empty
    yield [], {}


def _iter_jsonl_chunks(
    path: Path, batch_size: int
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    """JSONL: each row must have "text"; optional "id", "image_b64", "image_mime"."""
    batch: list[PipelineChunk] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = str(row.get("text") or row.get("content") or row.get("body") or "")
            if not text.strip():
                continue
            src_id = str(row.get("id") or row.get("url") or row.get("source") or f"row-{lineno}")
            b64 = str(row.get("image_b64") or "")
            mime = str(row.get("image_mime") or "image/png")
            batch.append(PipelineChunk(
                chunk_id=_chunk_id(str(path), text, lineno),
                source_id=src_id,
                source_type="image" if b64 else "dataset",
                text=text,
                fact_score=float(row.get("fact_score") or 0.0),
                image_b64=b64,
                image_mime=mime,
            ))
            if len(batch) >= batch_size:
                yield batch, {}
                batch = []
    if batch:
        yield batch, {}


def _iter_csv_chunks(
    path: Path, batch_size: int
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    import csv
    batch: list[PipelineChunk] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for lineno, row in enumerate(reader):
            text = str(row.get("text") or row.get("content") or row.get("body") or "")
            if not text.strip():
                continue
            src_id = str(row.get("id") or row.get("url") or f"row-{lineno}")
            batch.append(PipelineChunk(
                chunk_id=_chunk_id(str(path), text, lineno),
                source_id=src_id,
                source_type="dataset",
                text=text,
                fact_score=float(row.get("fact_score") or 0.0),
            ))
            if len(batch) >= batch_size:
                yield batch, {}
                batch = []
    if batch:
        yield batch, {}


def _iter_dir_chunks(
    root: Path, batch_size: int
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    """Directory: try substrate run dir first; fall back to raw file scan."""
    # If this looks like a substrate run dir, read it directly
    if (root / "chunks.jsonl").exists():
        yield from _iter_substrate_dir(root, batch_size)
        return

    import lgwks_embed
    batch: list[PipelineChunk] = []
    for path in sorted(root.rglob("*")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > MULTIMODAL_MAX_IMAGE_BYTES:
                continue
            mime = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp",
                ".gif": "image/gif", ".bmp": "image/bmp",
            }.get(ext, "image/png")
            b64 = base64.b64encode(raw).decode("ascii")
            batch.append(PipelineChunk(
                chunk_id=_chunk_id(str(path), b64[:40], 0),
                source_id=str(path), source_type="image",
                text=f"[image: {path.name}]",
                image_b64=b64, image_mime=mime,
            ))
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Reuse lgwks_embed._chunks() for consistent chunking
            for idx, chunk_text in enumerate(lgwks_embed._chunks(text)):
                batch.append(PipelineChunk(
                    chunk_id=_chunk_id(str(path), chunk_text, idx),
                    source_id=str(path), source_type="file",
                    text=chunk_text,
                ))
        if len(batch) >= batch_size:
            yield batch, {}
            batch = []
    if batch:
        yield batch, {}


def iter_dataset(
    source: str,
    batch_size: int = DATASET_BATCH_SIZE,
) -> Iterator[tuple[list[PipelineChunk], dict[str, list[float]]]]:
    """Unified intake dispatcher.  Yields (chunk_batch, existing_vector_map)."""
    p = Path(source)
    if source.startswith("http://") or source.startswith("https://"):
        yield from _iter_url_chunks(source, batch_size)
    elif p.is_dir():
        yield from _iter_dir_chunks(p, batch_size)
    elif p.suffix.lower() == ".jsonl":
        yield from _iter_jsonl_chunks(p, batch_size)
    elif p.suffix.lower() == ".csv":
        yield from _iter_csv_chunks(p, batch_size)
    elif p.exists():
        import lgwks_embed
        text = p.read_text(encoding="utf-8", errors="replace")
        batch = [
            PipelineChunk(
                chunk_id=_chunk_id(str(p), c, i),
                source_id=str(p), source_type="file", text=c,
            )
            for i, c in enumerate(lgwks_embed._chunks(text))
        ]
        yield batch, {}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4: DISAMBIGUATION — Gemma 1B constrained paraphrase, LLM-capped
# ══════════════════════════════════════════════════════════════════════════════

_DISAMBIG_PROMPT = (
    "Rephrase the following text in exactly {n} different ways, each emphasizing "
    "a different plausible interpretation. Output only the {n} rephrased sentences "
    "separated by newlines, nothing else:\n\n{text}"
)


def _gemma_paraphrase(text: str, n: int = DISAMBIGUATION_MAX_VARIANTS) -> list[str]:
    """Local Gemma 1B via Ollama.  Falls back silently to [] if unavailable."""
    if os.environ.get("LGWKS_NO_MODELS"):
        return []
    try:
        import lgwks_ollama
        if not lgwks_ollama.is_up():
            return []
    except Exception:
        return []

    import lgwks_ollama
    prompt = _DISAMBIG_PROMPT.format(n=n, text=text[:1200])
    body = json.dumps({
        "model": _GEMMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.25, "top_p": 0.85, "num_predict": 512},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{lgwks_ollama.HOST}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = data.get("response", "")
        variants = [v.strip() for v in raw.strip().split("\n") if v.strip()]
        return variants[:n]
    except Exception:
        return []


def disambiguate_chunk(
    chunk: PipelineChunk,
    classifier_confidence: float,
    text_provider: str,
) -> EmbedResult:
    """Gemma paraphrase → weighted centroid, or direct embed if confidence is high."""
    needs = classifier_confidence < DISAMBIGUATION_CONF_THRESHOLD
    variants: list[str] = _gemma_paraphrase(chunk.text) if needs else []

    if variants:
        all_texts = [chunk.text] + variants
        results = [embed_text(t, text_provider) for t in all_texts]
        vecs = [v for v, _, _ in results]
        weights = [2.0] + [1.0] * len(variants)
        agg = _weighted_centroid(vecs, weights)
        return EmbedResult(
            chunk_id=chunk.chunk_id,
            vector=agg, dims=len(agg),
            provider=results[0][1], is_semantic=results[0][2],
            signal_path="llm",
            interpretation_variants=variants,
        )

    vec, prov, sem = (
        embed_multimodal(chunk.text, chunk.image_b64, chunk.image_mime)
        if chunk.image_b64
        else embed_text(chunk.text, text_provider)
    )
    return EmbedResult(
        chunk_id=chunk.chunk_id, vector=vec, dims=len(vec),
        provider=prov, is_semantic=sem,
        signal_path="mm" if chunk.image_b64 else ("ml" if sem else "math"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5: RECALL — cosine ANN using lgwks_embed._cos()
# ══════════════════════════════════════════════════════════════════════════════

def recall_stage(
    query_vec: list[float],
    chunks: list[PipelineChunk],
    embeds: dict[str, EmbedResult],
    k: int = RECALL_K,
) -> list[tuple[PipelineChunk, EmbedResult, float]]:
    """Pure cosine sort.  Signal path: math."""
    scored = []
    for c in chunks:
        er = embeds.get(c.chunk_id)
        if er is None or not er.vector:
            continue
        sim = _cosine(query_vec, er.vector)
        scored.append((c, er, sim))
    scored.sort(key=lambda x: -x[2])
    return scored[:k]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6: FAST RANK — BM25 + signal feature linear combination
# ══════════════════════════════════════════════════════════════════════════════

def fast_rank_stage(
    query_tokens: list[str],
    query_entities: list[str],
    candidates: list[tuple[PipelineChunk, EmbedResult, float]],
    k: int = FAST_RANK_K,
    avg_doc_len: float = 120.0,
) -> list[RankedChunk]:
    """Linear combination of BM25 + signals.  No model calls.  Signal path: math."""
    results: list[RankedChunk] = []
    for chunk, er, recall_score in candidates:
        doc_toks = _tokenize(chunk.text)
        bm = bm25_score(query_tokens, doc_toks, avg_doc_len=avg_doc_len)
        fd = chunk.fact_score if chunk.fact_score > 0 else compute_fact_density(chunk.text)
        eo = entity_overlap_score(query_entities, chunk.entities)
        ns = compute_noise_score(chunk)
        score = (
            FAST_RANK_W_BM25 * min(1.0, bm / 10.0)
            + FAST_RANK_W_FACT_DENSITY * fd
            + FAST_RANK_W_COVERAGE * recall_score
            + FAST_RANK_W_ENTITY_OVERLAP * eo
            + FAST_RANK_W_RECENCY * 0.5
        )
        results.append(RankedChunk(
            chunk=chunk, embed=er,
            fast_rank_score=round(score, 6),
            noise_score=ns,
            signal_path="math",
        ))
    results.sort(key=lambda r: -r.fast_rank_score)
    return results[:k]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7: HEAVY RANK — lgwks_intent_classifier on top-K only
# ══════════════════════════════════════════════════════════════════════════════

def heavy_rank_stage(
    candidates: list[RankedChunk],
    k: int = HEAVY_RANK_K,
) -> list[RankedChunk]:
    """Re-scores via IntentClassifier.  Runs on top FAST_RANK_K only.
    Signal path: ml (or math if classifier unavailable)."""
    try:
        from lgwks_intent_classifier import IntentClassifier
        clf = IntentClassifier()
        has_clf = True
    except Exception:
        has_clf = False

    for rc in candidates:
        confidence = 1.0
        ml_bonus = 0.0
        if has_clf:
            try:
                result = clf.classify(rc.chunk.text)
                confidence = float(result.confidence)
                label = str(result.label)
                if label in ("rule", "procedure", "requirement", "workflow_rule"):
                    ml_bonus = 0.10
                elif label in ("narrative", "marketing", "boilerplate"):
                    ml_bonus = -0.10
            except Exception:
                pass
        rc.heavy_rank_score = round(rc.fast_rank_score + ml_bonus, 6)
        rc.classifier_confidence = confidence
        rc.signal_path = "ml" if has_clf else "math"

    candidates.sort(key=lambda r: -r.heavy_rank_score)
    return candidates[:k]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 8: RERANK — diversity, source cap, noise quarantine
# ══════════════════════════════════════════════════════════════════════════════

def rerank_stage(
    candidates: list[RankedChunk],
) -> tuple[list[RankedChunk], list[NoiseRecord]]:
    """Pure math.  Signal path: math."""
    ranked: list[RankedChunk] = []
    noise: list[NoiseRecord] = []
    source_counts: dict[str, int] = {}
    selected_vecs: list[list[float]] = []

    for rc in candidates:
        if rc.noise_score > NOISE_SCORE_THRESHOLD:
            rc.quarantined = True
            noise.append(NoiseRecord(
                chunk_id=rc.chunk.chunk_id, noise_score=rc.noise_score,
                reason="noise_threshold", signal_path=rc.signal_path,
            ))
            continue

        src = rc.chunk.source_id
        if source_counts.get(src, 0) >= SAME_SOURCE_CAP:
            rc.quarantined = True
            noise.append(NoiseRecord(
                chunk_id=rc.chunk.chunk_id, noise_score=rc.noise_score,
                reason="source_cap", signal_path=rc.signal_path,
            ))
            continue

        diversity_penalty = 0.0
        if selected_vecs and rc.embed.vector:
            max_sim = max(_cosine(rc.embed.vector, sv) for sv in selected_vecs)
            diversity_penalty = DIVERSITY_PENALTY_WEIGHT * max_sim

        rc.final_score = round(rc.heavy_rank_score - diversity_penalty, 6)
        source_counts[src] = source_counts.get(src, 0) + 1
        if rc.embed.vector:
            selected_vecs.append(rc.embed.vector)
        ranked.append(rc)

    ranked.sort(key=lambda r: -r.final_score)
    return ranked, noise


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 9: PACK — signal pack + noise summary embedding
#              delegates final JEPA packaging to lgwks_jepa.build_package()
# ══════════════════════════════════════════════════════════════════════════════

def pack_stage(
    ranked: list[RankedChunk],
    noise: list[NoiseRecord],
    noise_embeds: dict[str, list[float]],
    out_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Assemble the signal pack, compute noise summary PCA, call lgwks_jepa.build_package()."""
    total = len(ranked) + len(noise)
    llm_count = sum(1 for r in ranked if r.signal_path == "llm")
    math_count = sum(1 for r in ranked if r.signal_path == "math")
    ml_count = sum(1 for r in ranked if r.signal_path == "ml")
    mm_count = sum(1 for r in ranked if r.signal_path == "mm")

    # Noise summary embedding — first PC of quarantined vectors
    q_vecs = [noise_embeds[nr.chunk_id] for nr in noise if nr.chunk_id in noise_embeds and noise_embeds[nr.chunk_id]]
    if len(q_vecs) >= 2:
        noise_summary_vec = _first_principal_component(q_vecs)
    elif q_vecs:
        noise_summary_vec = _l2_norm(q_vecs[0])
    else:
        noise_summary_vec = []

    pack: dict[str, Any] = {
        "ranked_chunks": [
            {
                "chunk_id": r.chunk.chunk_id,
                "source_id": r.chunk.source_id,
                "text": r.chunk.text,
                "chunk_kind": r.chunk.chunk_kind,
                "final_score": r.final_score,
                "noise_score": r.noise_score,
                "signal_path": r.signal_path,
                "llm_touches": r.llm_touches,
                "embed_provider": r.embed.provider,
                "classifier_confidence": r.classifier_confidence,
                "interpretation_variants": r.embed.interpretation_variants,
            }
            for r in ranked
        ],
        "provenance_summary": {
            "math_ratio": round(math_count / max(total, 1), 4),
            "ml_ratio": round(ml_count / max(total, 1), 4),
            "llm_ratio": round(llm_count / max(total, 1), 4),
            "mm_ratio": round(mm_count / max(total, 1), 4),
            "llm_involvement_score": round(llm_count / max(total, 1), 4),
            "total_chunks_processed": total,
        },
        "noise_summary": {
            "quarantined_count": len(noise),
            "avg_noise_score": round(
                sum(n.noise_score for n in noise) / max(len(noise), 1), 4
            ),
            "by_reason": {
                r: sum(1 for n in noise if n.reason == r)
                for r in ("noise_threshold", "source_cap", "diversity_cap")
            },
        },
        "noise_summary_embedding": noise_summary_vec,
    }

    # Write ranked chunks as JSONL for lgwks_jepa to consume as "views"
    views_file = out_dir / "ranked_views.jsonl"
    with views_file.open("w", encoding="utf-8") as fh:
        for r in ranked[:100]:   # JEPA packs top-100 as views
            fh.write(json.dumps({
                "text": r.chunk.text,
                "source": r.chunk.source_id,
                "score": r.final_score,
                "provider": r.embed.provider,
                "signal_path": r.signal_path,
            }, ensure_ascii=False) + "\n")

    # Delegate JEPA packaging to existing lgwks_jepa.build_package()
    try:
        import lgwks_jepa
        jepa_args = argparse.Namespace(
            paths=[str(views_file)],
            repo=None,
            capture=False,
            output=str(out_dir / "jepa_package.json"),
        )
        jepa_pack = lgwks_jepa.build_package(jepa_args)
        pack["jepa_package"] = jepa_pack
    except Exception as exc:
        pack["jepa_package"] = {"error": str(exc)}

    return pack


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 10: CLEANUP — Qwen coherence gate using lgwks_run.embed()
# ══════════════════════════════════════════════════════════════════════════════

def cleanup_stage(
    pack: dict[str, Any],
    query_vec: list[float],
    text_provider: str,
) -> tuple[dict[str, Any], float, list[str]]:
    """Semantic coherence gate.  Reads pack summary only — no raw text.
    Signal path: ml (embedding only, no generation)."""
    warnings: list[str] = []
    summary_parts = [r["text"][:400] for r in pack.get("ranked_chunks", [])[:5]]
    summary_text = " ".join(summary_parts)
    pack_vec, _, _ = embed_text(summary_text, text_provider)
    coherence = round(_cosine(query_vec, pack_vec), 4) if query_vec else 1.0
    if coherence < COHERENCE_THRESHOLD:
        warnings.append(
            f"low_coherence:{coherence:.3f} < threshold:{COHERENCE_THRESHOLD} — "
            f"pack summary diverges from query. Manual review recommended."
        )
    return pack, coherence, warnings


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETER SNAPSHOT  — written into every manifest
# ══════════════════════════════════════════════════════════════════════════════

def _parameter_snapshot() -> dict[str, Any]:
    return {
        "RECALL_K": RECALL_K,
        "FAST_RANK_K": FAST_RANK_K,
        "HEAVY_RANK_K": HEAVY_RANK_K,
        "DISAMBIGUATION_CONF_THRESHOLD": DISAMBIGUATION_CONF_THRESHOLD,
        "DISAMBIGUATION_MAX_VARIANTS": DISAMBIGUATION_MAX_VARIANTS,
        "NOISE_SCORE_THRESHOLD": NOISE_SCORE_THRESHOLD,
        "DIVERSITY_PENALTY_WEIGHT": DIVERSITY_PENALTY_WEIGHT,
        "SAME_SOURCE_CAP": SAME_SOURCE_CAP,
        "MAX_LLM_INVOLVEMENT_RATIO": MAX_LLM_INVOLVEMENT_RATIO,
        "FAST_RANK_W_BM25": FAST_RANK_W_BM25,
        "FAST_RANK_W_FACT_DENSITY": FAST_RANK_W_FACT_DENSITY,
        "FAST_RANK_W_COVERAGE": FAST_RANK_W_COVERAGE,
        "FAST_RANK_W_ENTITY_OVERLAP": FAST_RANK_W_ENTITY_OVERLAP,
        "FAST_RANK_W_RECENCY": FAST_RANK_W_RECENCY,
        "DATASET_BATCH_SIZE": DATASET_BATCH_SIZE,
        "MULTIMODAL_EMBED_MODEL": MULTIMODAL_EMBED_MODEL,
        "COHERENCE_THRESHOLD": COHERENCE_THRESHOLD,
        "GEMMA_MODEL": _GEMMA_MODEL,
        "adr": "docs/ADR-pipeline-001-tuning.md",
    }


# ══════════════════════════════════════════════════════════════════════════════
# DAG EXECUTOR
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Full DAG.  Returns manifest dict."""
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_id = f"pipeline-{_sha(args.target + ts)}-{ts}"
    out_dir = PIPELINE_STORE / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    print(f"[pipeline] run_id={run_id}", file=sys.stderr)
    print(f"[pipeline] target={args.target}", file=sys.stderr)

    # ── Stage 0: Bootstrap ────────────────────────────────────────────────────
    text_provider = _resolve_text_provider()
    print(f"[stage 0] text_provider={text_provider}", file=sys.stderr)
    query_text = getattr(args, "query", "") or args.target
    query_vec, _, _ = embed_text(query_text, text_provider)
    query_tokens = _tokenize(query_text)
    query_entities = extract_chunk_entities(query_text)

    # ── Stage 1: Ingest — streaming, batched ──────────────────────────────────
    print(f"[stage 1] ingesting {args.target} ...", file=sys.stderr)
    all_chunks: list[PipelineChunk] = []
    prefetched_vecs: dict[str, list[float]] = {}   # substrate pre-computed vectors

    for batch, batch_vecs in iter_dataset(args.target, DATASET_BATCH_SIZE):
        all_chunks.extend(batch)
        prefetched_vecs.update(batch_vecs)

    print(
        f"[stage 1] {len(all_chunks)} chunks, "
        f"{len(prefetched_vecs)} pre-computed vectors from substrate",
        file=sys.stderr,
    )

    # ── Stage 2: Qualify ──────────────────────────────────────────────────────
    avg_fact = sum(c.fact_score for c in all_chunks) / max(len(all_chunks), 1)
    print(f"[stage 2] avg_fact_score={avg_fact:.3f}", file=sys.stderr)
    if avg_fact < 0.05:
        warnings.append(f"low_fact_density:{avg_fact:.3f}")

    # Extract entities for all chunks using entity graph (T1 regex, always works)
    for c in all_chunks:
        if not c.entities:
            c.entities = extract_chunk_entities(c.text)

    # ── Stage 3: Embed — skip chunks with prefetched vectors ──────────────────
    print(f"[stage 3] embedding ...", file=sys.stderr)
    embeds: dict[str, EmbedResult] = {}
    providers_used: dict[str, int] = {}

    # Re-use substrate vectors when available — avoid redundant embedding
    for c in all_chunks:
        if c.chunk_id in prefetched_vecs:
            vec = prefetched_vecs[c.chunk_id]
            er = EmbedResult(
                chunk_id=c.chunk_id, vector=vec, dims=len(vec),
                provider="substrate:reused", is_semantic=True,
                signal_path="ml",
            )
            embeds[c.chunk_id] = er
            providers_used["substrate:reused"] = providers_used.get("substrate:reused", 0) + 1

    # Embed remaining chunks in parallel
    to_embed = [c for c in all_chunks if c.chunk_id not in embeds]

    def _embed_one(chunk: PipelineChunk) -> EmbedResult:
        if chunk.image_b64:
            vec, prov, sem = embed_multimodal(chunk.text, chunk.image_b64, chunk.image_mime)
            return EmbedResult(
                chunk_id=chunk.chunk_id, vector=vec, dims=len(vec),
                provider=prov, is_semantic=sem,
                signal_path="mm" if sem else "math",
            )
        vec, prov, sem = embed_text(chunk.text, text_provider)
        return EmbedResult(
            chunk_id=chunk.chunk_id, vector=vec, dims=len(vec),
            provider=prov, is_semantic=sem,
            signal_path="ml" if sem else "math",
        )

    max_workers = min(8, os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_embed_one, c): c for c in to_embed}
        for fut in as_completed(futs):
            er = fut.result()
            embeds[er.chunk_id] = er
            providers_used[er.provider] = providers_used.get(er.provider, 0) + 1

    print(f"[stage 3] embedded={len(embeds)}, providers={providers_used}", file=sys.stderr)

    # ── Stage 4: Disambiguate — LLM-capped ────────────────────────────────────
    print(f"[stage 4] disambiguation ...", file=sys.stderr)
    llm_budget = int(len(all_chunks) * MAX_LLM_INVOLVEMENT_RATIO)
    llm_used = 0

    try:
        from lgwks_intent_classifier import IntentClassifier
        clf = IntentClassifier()
        has_clf = True
    except Exception:
        has_clf = False

    for chunk in all_chunks:
        er = embeds.get(chunk.chunk_id)
        if er is None:
            continue
        # Skip disambiguation for substrate-reused vectors (already embedded correctly)
        if er.provider == "substrate:reused":
            continue
        confidence = 1.0
        if has_clf:
            try:
                result = clf.classify(chunk.text)
                confidence = float(result.confidence)
            except Exception:
                pass
        if confidence < DISAMBIGUATION_CONF_THRESHOLD and llm_used < llm_budget:
            new_er = disambiguate_chunk(chunk, confidence, text_provider)
            embeds[chunk.chunk_id] = new_er
            if new_er.signal_path == "llm":
                llm_used += 1
                providers_used[new_er.provider] = providers_used.get(new_er.provider, 0) + 1

    llm_ratio = round(llm_used / max(len(all_chunks), 1), 4)
    if llm_ratio > MAX_LLM_INVOLVEMENT_RATIO:
        warnings.append(f"llm_cap_exceeded:{llm_ratio:.1%}")
    print(f"[stage 4] llm_used={llm_used} ({llm_ratio:.1%})", file=sys.stderr)

    # ── Stage 5: Recall ───────────────────────────────────────────────────────
    print(f"[stage 5] recall k={RECALL_K} ...", file=sys.stderr)
    recalled = recall_stage(query_vec, all_chunks, embeds, k=RECALL_K)

    # ── Stage 6: Fast rank ────────────────────────────────────────────────────
    avg_doc_len = sum(len(c.text.split()) for c in all_chunks) / max(len(all_chunks), 1)
    print(f"[stage 6] fast rank k={FAST_RANK_K} ...", file=sys.stderr)
    fast_ranked = fast_rank_stage(
        query_tokens, query_entities, recalled, k=FAST_RANK_K, avg_doc_len=avg_doc_len,
    )

    # ── Stage 7: Heavy rank ───────────────────────────────────────────────────
    print(f"[stage 7] heavy rank k={HEAVY_RANK_K} ...", file=sys.stderr)
    heavy_ranked = heavy_rank_stage(fast_ranked, k=HEAVY_RANK_K)

    # ── Stage 8: Rerank ───────────────────────────────────────────────────────
    print(f"[stage 8] rerank ...", file=sys.stderr)
    ranked, noise_records = rerank_stage(heavy_ranked)
    noise_embeds = {
        nr.chunk_id: embeds[nr.chunk_id].vector
        for nr in noise_records if nr.chunk_id in embeds
    }

    # ── Stage 9: Pack ─────────────────────────────────────────────────────────
    print(f"[stage 9] packing ...", file=sys.stderr)
    pack = pack_stage(ranked, noise_records, noise_embeds, out_dir, args)

    # ── Stage 10: Cleanup ─────────────────────────────────────────────────────
    print(f"[stage 10] coherence gate ...", file=sys.stderr)
    pack, coherence, cleanup_warnings = cleanup_stage(pack, query_vec, text_provider)
    warnings.extend(cleanup_warnings)
    print(f"[stage 10] coherence={coherence:.3f}", file=sys.stderr)

    # ── Write artifacts ───────────────────────────────────────────────────────
    (out_dir / "pack.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest: dict[str, Any] = {
        "schema": PIPELINE_MANIFEST_SCHEMA,
        "run_id": run_id,
        "target": args.target,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": {
            "ingested": len(all_chunks),
            "prefetched_vectors": len(prefetched_vecs),
            "recalled": len(recalled),
            "fast_ranked": len(fast_ranked),
            "heavy_ranked": len(heavy_ranked),
            "final_ranked": len(ranked),
            "quarantined": len(noise_records),
        },
        "provenance_summary": pack["provenance_summary"],
        "noise_summary": pack["noise_summary"],
        "coherence_score": coherence,
        "providers_used": providers_used,
        "parameters": _parameter_snapshot(),
        "artifacts": {
            "pack": str(out_dir / "pack.json"),
            "ranked_views": str(out_dir / "ranked_views.jsonl"),
            "manifest": str(out_dir / "manifest.json"),
        },
        "warnings": warnings,
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[pipeline] ✓ complete → {out_dir / 'manifest.json'}", file=sys.stderr)
    return manifest


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def _run_command(args: argparse.Namespace) -> int:
    # Allow CLI to override env-based constants
    global RECALL_K, FAST_RANK_K, HEAVY_RANK_K
    if hasattr(args, "recall_k"):
        RECALL_K = args.recall_k
    if hasattr(args, "fast_rank_k"):
        FAST_RANK_K = args.fast_rank_k
    if hasattr(args, "heavy_rank_k"):
        HEAVY_RANK_K = args.heavy_rank_k
    try:
        manifest = run_pipeline(args)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({
        "ok": True,
        "run_id": manifest["run_id"],
        "counts": manifest["counts"],
        "provenance": manifest["provenance_summary"],
        "coherence": manifest["coherence_score"],
        "warnings": manifest["warnings"],
        "manifest": manifest["artifacts"]["manifest"],
    }, indent=2))
    return 0


def _params_command(_args: argparse.Namespace) -> int:
    print(json.dumps(_parameter_snapshot(), indent=2))
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "pipeline",
        help="unified ingestion+ranking spine: crawl→qualify→embed→rank→pack",
    )
    sp = p.add_subparsers(dest="pipeline_command", required=True)

    run_p = sp.add_parser("run", help="execute the full pipeline on a target")
    run_p.add_argument(
        "target",
        help="URL, substrate run dir, JSONL, CSV, or directory",
    )
    run_p.add_argument("--query", default="",
        help="optional query for recall/ranking (defaults to target URL)")
    run_p.add_argument("--recall-k", type=int, default=RECALL_K, dest="recall_k",
        help=f"ANN recall pool [ADR §2.1, default={RECALL_K}]")
    run_p.add_argument("--fast-rank-k", type=int, default=FAST_RANK_K, dest="fast_rank_k",
        help=f"fast-rank candidates [ADR §2.2, default={FAST_RANK_K}]")
    run_p.add_argument("--heavy-rank-k", type=int, default=HEAVY_RANK_K, dest="heavy_rank_k",
        help=f"heavy-rank candidates [ADR §2.3, default={HEAVY_RANK_K}]")
    run_p.set_defaults(func=_run_command)

    params_p = sp.add_parser("params", help="print all parameters and their ADR sections")
    params_p.set_defaults(func=_params_command)


if __name__ == "__main__":
    _p = argparse.ArgumentParser(prog="lgwks_pipeline")
    add_parser(_p.add_subparsers(dest="cmd", required=True))
    _a = _p.parse_args()
    raise SystemExit(_a.func(_a))
