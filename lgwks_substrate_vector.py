"""lgwks_substrate_vector — vector search, vector space identity, and cross-space guards.

Defense-in-Depth:
- Layer 1 (entry): reject empty queries or missing vector files before attempting search.
- Layer 2 (business): vector space mismatch detection prevents semantically invalid comparisons.
- Layer 3 (environment): force_cross_space flag required explicitly (not default) for mixed spaces.
- Layer 4 (debug): every search result includes provider, dims, and cross-space warning metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lgwks_run
from lgwks_substrate_config import EmbeddingProviderUnavailable
from lgwks_substrate_io import _load_run_manifest, _read_jsonl
from lgwks_vecmath import dot as _dot


def _provider_matches_vector_space(requested: str, canonical: str) -> bool:
    """Return whether a CLI provider token names the stored provider space.

    Build/query args use coarse selectors like "ollama" and "deterministic",
    while stored vectors record resolved labels from lgwks_run.embed().
    """
    if requested == canonical:
        return True
    if requested == "deterministic" and canonical == "deterministic-feature-hash":
        return True
    if requested == "ollama" and canonical.startswith("ollama:"):
        return True
    if requested == "openrouter-vl" and canonical.startswith("openrouter:"):
        return True
    if requested == "apple-local" and canonical.startswith("apple-local:"):
        return True
    return False


def _model_matches_vector_space(requested: str, canonical_model: str, canonical_provider: str) -> bool:
    if requested == canonical_model:
        return True
    if not canonical_model and ":" in canonical_provider:
        return requested == canonical_provider.split(":", 1)[1]
    return False


def _query_embed_args(provider: str, model: str) -> tuple[str, str]:
    """Convert stored provider labels back into embed() selector args."""
    if provider == "deterministic-feature-hash":
        return "deterministic", model
    if provider.startswith("ollama:"):
        return "ollama", model or provider.split(":", 1)[1]
    if provider.startswith("openrouter:"):
        return "openrouter-vl", model or provider.split(":", 1)[1]
    if provider.startswith("apple-local:"):
        return "apple-local", model or provider.split(":", 1)[1]
    return provider or "auto", model


def _stored_vector_space(run_dir: Path) -> dict[str, Any]:
    """Return stored vector-space metadata for a run.

    Priority:
    1. manifest.json → vector_space (canonical).
    2. Fallback: inspect vectors.jsonl for a homogeneous single provider.
    3. If ambiguous or missing, returns {"ambiguous": True, "error": ...}.
    """
    manifest = _load_run_manifest(run_dir)
    if manifest and "vector_space" in manifest:
        return manifest["vector_space"]

    vector_file = run_dir / "vectors.jsonl"
    if not vector_file.exists():
        return {"ambiguous": True, "error": "no manifest.json and no vectors.jsonl found"}

    from collections import Counter
    providers: Counter[str] = Counter()
    dims_seen: set[int] = set()
    semantic_seen: set[bool] = set()
    for line in vector_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        p = row.get("provider", "")
        d = row.get("dims", 0)
        s = bool(row.get("is_semantic", False))
        if p:
            providers[p] += 1
        if d:
            dims_seen.add(d)
        semantic_seen.add(s)

    if not providers:
        return {"ambiguous": True, "error": "vectors.jsonl is empty or has no provider metadata"}

    if len(providers) > 1 or len(dims_seen) > 1:
        return {
            "ambiguous": True,
            "error": "mixed providers or dims in vectors.jsonl; cannot derive a single canonical space",
            "providers_used": dict(providers),
        }

    canonical_provider = next(iter(providers))
    canonical_dims = next(iter(dims_seen)) if dims_seen else 0
    is_semantic = (True in semantic_seen)
    return {
        "canonical_provider": canonical_provider,
        "canonical_model": "",
        "dims": canonical_dims,
        "semantic": is_semantic,
        "providers_used": dict(providers),
        "source": "vectors.jsonl fallback (no manifest)",
    }


def _vector_search(
    run_dir: Path,
    text: str,
    limit: int,
    provider: str,
    model: str,
    *,
    force_cross_space: bool = False,
) -> dict[str, Any]:
    """Semantic vector search over a substrate run."""
    vector_file = run_dir / "vectors.jsonl"
    if not vector_file.exists():
        return {
            "schema": "lgwks.substrate.vector_query.v0",
            "ok": False,
            "run": str(run_dir),
            "query": text,
            "rows": [],
            "error": f"missing vector artifact: {vector_file}",
        }

    stored_vs = _stored_vector_space(run_dir)

    if stored_vs.get("ambiguous"):
        if not force_cross_space:
            return {
                "schema": "lgwks.substrate.vector_query.v0",
                "ok": False,
                "run": str(run_dir),
                "query": text,
                "rows": [],
                "error": "ambiguous stored vector space",
                "stored_vector_space": stored_vs,
                "hint": "rerun substrate build with a single provider, or pass --force-cross-space",
            }

    user_specified_provider = bool(provider)
    user_specified_model = bool(model)
    resolved_provider = provider
    resolved_model = model

    if not stored_vs.get("ambiguous"):
        canonical_provider = stored_vs.get("canonical_provider", "")
        canonical_model = stored_vs.get("canonical_model", "")
        if not user_specified_provider:
            resolved_provider = canonical_provider
        if not user_specified_model:
            resolved_model = canonical_model

        mismatch = (
            (user_specified_provider and not _provider_matches_vector_space(resolved_provider, canonical_provider))
            or (user_specified_model and resolved_model and not _model_matches_vector_space(
                resolved_model, canonical_model, canonical_provider
            ))
        )
        if mismatch and not force_cross_space:
            return {
                "schema": "lgwks.substrate.vector_query.v0",
                "ok": False,
                "run": str(run_dir),
                "query": text,
                "rows": [],
                "error": "embedding provider mismatch",
                "stored_vector_space": stored_vs,
                "requested_vector_space": {"provider": resolved_provider, "model": resolved_model},
                "hint": "rerun without --embed-provider / --embed-model, or pass --force-cross-space",
            }
    else:
        requested_vs = {"provider": resolved_provider, "model": resolved_model}

    embed_provider, embed_model = _query_embed_args(resolved_provider, resolved_model)
    query_dims = stored_vs.get("dims") if not stored_vs.get("ambiguous") else None
    query_vec, query_provider, semantic = lgwks_run.embed(
        text,
        embed_on=True,
        provider=embed_provider,
        model=(embed_model or None),
        dims=(int(query_dims) if query_dims else None),
    )
    if not query_vec:
        return {
            "schema": "lgwks.substrate.vector_query.v0",
            "ok": False,
            "run": str(run_dir),
            "query": text,
            "rows": [],
            "error": "query vector unavailable",
            "resolved_query_provider": query_provider,
            "stored_vector_space": stored_vs,
        }

    rows: list[dict[str, Any]] = []
    for line in vector_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        vec = row.get("vector") or []
        if not vec:
            continue
        score = _dot(query_vec, vec[:len(query_vec)])
        rows.append({
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "provider": row["provider"],
            "chunk_kind": row["chunk_kind"],
            "fact_score": row["fact_score"],
            "score": round(float(score), 6),
            "text": row["vector_text"],
        })
    rows.sort(key=lambda item: item["score"], reverse=True)

    result: dict[str, Any] = {
        "schema": "lgwks.substrate.vector_query.v0",
        "ok": True,
        "run": str(run_dir),
        "query": text,
        "query_vector_space": {
            "provider": query_provider,
            "model": resolved_model or "",
            "semantic": semantic,
        },
        "stored_vector_space": stored_vs,
        "rows": rows[:limit],
    }
    if force_cross_space:
        result["cross_space_forced"] = True
        result["warning"] = "scores are cross-space and not semantically comparable"
    return result
