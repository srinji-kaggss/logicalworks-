"""lgwks_substrate_run — build, query, and baseline orchestration for substrate runs.

Defense-in-Depth:
- Layer 1 (entry): args.target validated as existing path or well-formed URL.
- Layer 2 (business): source_type auto-detection falls through path→dir→repo→file.
- Layer 3 (environment): EmbeddingProviderUnavailable caught at CLI boundary, not propagated raw.
- Layer 4 (debug): manifest.json includes full artifact inventory and vector-space metadata.
"""

from __future__ import annotations

import argparse
import json
import lgwks_clock as _clock  # canonical timestamps (#223 foundation-bypass)
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import lgwks_run
import lgwks_sqlite
import lgwks_storage
import lgwks_substrate_config as config
import lgwks_substrate_crawl as crawl
import lgwks_substrate_io as io
import lgwks_substrate_text as text
import lgwks_substrate_vector as vector
from lgwks_substrate_config import EmbeddingProviderUnavailable, RUN_ROOT, UPCOMING_EFFECTIVE_DATE, VERSION_BUCKETS


def _parse_iso_date(value: str) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def _source_type(target: str, forced: str) -> str:
    if forced != "auto":
        return forced
    if "://" in target:
        return "url"
    path = Path(target)
    if path.is_dir():
        if (path / ".git").exists():
            return "repo"
        return "folder"
    if path.exists():
        return "file"
    raise ValueError(
        f"target {target!r} is not a URL, an existing file, or an existing directory. "
        f"Pass a URL (https://...) or a valid local path."
    )


def _build_from_local(root: Path, source_type: str, max_files: int, max_chars: int) -> list[dict[str, Any]]:
    if source_type == "file":
        t = io._read_text(root, max_chars)
        return [{
            "source": str(root),
            "title": root.name,
            "text": t,
            "html_len": 0,
            "depth": 0,
            "discovered_by": "seed",
        }] if t else []
    docs: list[dict[str, Any]] = []
    for path in io._iter_text_files(root, max_files):
        t = io._read_text(path, max_chars)
        if not t.strip():
            continue
        docs.append({
            "source": str(path),
            "title": str(path.relative_to(root)),
            "text": t,
            "html_len": 0,
            "depth": 0,
            "discovered_by": "filesystem",
        })
    return docs


def _provider_unavailable_payload(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    return {
        "schema": "lgwks.substrate.error.v0",
        "ok": False,
        "target": getattr(args, "target", ""),
        "project": getattr(args, "project", ""),
        "error": "embedding provider unavailable",
        "detail": str(exc),
        "embedding": {
            "provider_requested": getattr(args, "embed_provider", ""),
            "model_requested": getattr(args, "embed_model", ""),
        },
    }


def _policy_pack_gaps(
    manifest: dict[str, Any],
    facts: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
    buckets: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    counts = manifest.get("counts", {}) if isinstance(manifest.get("counts", {}), dict) else {}
    if int(counts.get("documents") or 0) == 0:
        gaps.append({
            "id": "no-documents",
            "severity": "high",
            "reason": "substrate run captured no documents; authenticated baseline is not usable yet",
            "next_action": "complete human auth handoff and rerun substrate map",
        })
    if int(counts.get("facts") or 0) == 0 or not facts:
        gaps.append({
            "id": "no-facts",
            "severity": "high",
            "reason": "no fact rows were extracted for Current / Upcoming / Previous classification",
            "next_action": "rerun with authenticated content and inspect extraction profile",
        })
    auth_blockers = [
        row for row in frontier
        if str(row.get("status", "")) in {"auth_failed", "auth_exhausted", "auth_saved_but_failed", "error", "blocked"}
    ]
    if auth_blockers:
        gaps.append({
            "id": "auth-frontier-blockers",
            "severity": "high",
            "reason": f"{len(auth_blockers)} frontier entries ended in blocked/auth/error states",
            "next_action": "review frontier.jsonl, renew the browser session, and rerun the blocked URLs",
        })
    if not buckets["Upcoming"]:
        gaps.append({
            "id": "missing-upcoming-v36",
            "severity": "medium",
            "reason": "no V36/upcoming facts were found; V36 must remain Upcoming until 2026-06-15",
            "next_action": "add or crawl V36-specific source pages before treating the baseline as complete",
        })
    if not buckets["Previous"]:
        gaps.append({
            "id": "missing-previous-layer",
            "severity": "medium",
            "reason": "no previous/legacy facts were found for regression comparison",
            "next_action": "crawl prior-version or archived standard pages, or record that none are available",
        })
    return gaps


@dataclass
class _BuildRows:
    source_rows: list[dict[str, Any]] = field(default_factory=list)
    doc_rows: list[dict[str, Any]] = field(default_factory=list)
    chunk_rows: list[dict[str, Any]] = field(default_factory=list)
    fact_rows: list[dict[str, Any]] = field(default_factory=list)
    fact_vector_rows: list[dict[str, Any]] = field(default_factory=list)
    vector_rows: list[dict[str, Any]] = field(default_factory=list)
    graph_input_rows: list[dict[str, Any]] = field(default_factory=list)
    provider_counts: Counter[str] = field(default_factory=Counter)
    semantic_vectors: int = 0
    chunk_by_content: dict[str, dict[str, Any]] = field(default_factory=dict)


def _project_name(args: argparse.Namespace) -> str:
    return args.project or io._slug(Path(args.target).name)


def _new_run_dir(args: argparse.Namespace) -> tuple[str, Path]:
    run_id = f"{_project_name(args)}-{_clock.stamp_compact()}"  # canonical UTC stamp (#223; was local)
    run_dir = RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def _load_build_docs(args: argparse.Namespace, source_kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source_kind == "url":
        return crawl._crawl_site(
            args.target,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            browser_engine=args.browser_engine,
            login_if_needed=args.login_if_needed,
            login_url=args.login_url,
            success_selector=args.success_selector,
            max_auto_bypass_attempts=args.max_auto_bypass_attempts,
            max_auth_handoffs=args.max_auth_handoffs,
            click_discovery=bool(getattr(args, "click_discovery", False)),
            max_clicks_per_page=int(getattr(args, "max_clicks_per_page", 20)),
            crawl_mode=getattr(args, "crawl_mode", "link-then-click"),
            embed_screenshots=bool(getattr(args, "embed_screenshots", False)),
        )
    return _build_from_local(Path(args.target).resolve(), source_kind, args.max_files, args.max_chars), []


def _append_source_doc_rows(rows: _BuildRows, doc: dict[str, Any], idx: int) -> tuple[str, str]:
    source_identity = f"{doc['source']}|{doc['discovered_by']}|{doc['depth']}|{idx}"
    source_id = f"src-{io._sha(source_identity)[:16]}"
    doc_id = f"doc-{io._sha(source_identity + doc['title'])[:16]}"
    rows.source_rows.append({
        "source_id": source_id,
        "source": doc["source"],
        "title": doc["title"],
        "discovered_by": doc["discovered_by"],
        "depth": doc["depth"],
    })
    rows.doc_rows.append({
        "document_id": doc_id,
        "source_id": source_id,
        "title": doc["title"],
        "source": doc["source"],
        "word_count": len(re.findall(r"\S+", doc["text"])),
    })
    return source_id, doc_id


def _append_fact_vectors(
    rows: _BuildRows,
    *,
    sentence: str,
    chunk_kind: str,
    tok_id: str,
    gate: Any,
    args: argparse.Namespace,
    run_id: str,
    chunk_id: str,
) -> None:
    dual = lgwks_run.embed_dual(
        sentence,
        embed_on=True,
        provider=args.embed_provider,
        model=args.embed_model,
    )
    fdet = dual["det"]
    rows.provider_counts[fdet["provider"]] += 1
    rows.fact_vector_rows.append({
        "fact_hash": io._sha(sentence),
        "fact_text": sentence,
        "provider": fdet["provider"],
        "dims": fdet["dims"],
        "vector": fdet["vector"],
        "fact_score": text._fact_score(sentence),
        "chunk_kind": chunk_kind,
        "tokenization_id": tok_id,   # #165: lineage tag (artifact_cid == fact_hash)
    })
    gate.ingest_fact(io._sha(sentence), sentence, chunk_kind, capability="ingest_fact_sentence", meta={"chunk_id": chunk_id}, run_id=run_id)

    if dual["sem"]:
        fsem = dual["sem"]
        rows.provider_counts[fsem["provider"]] += 1
        rows.semantic_vectors += 1
        rows.fact_vector_rows.append({
            "fact_hash": io._sha(sentence),
            "fact_text": sentence,
            "provider": fsem["provider"],
            "dims": fsem["dims"],
            "vector": fsem["vector"],
            "fact_score": text._fact_score(sentence),
            "chunk_kind": chunk_kind,
            "tokenization_id": tok_id,   # #165
        })


def _append_chunk_vectors(
    rows: _BuildRows,
    *,
    vector_text: str,
    chunk_id: str,
    doc_id: str,
    fact_score: float,
    chunk_kind: str,
    tok_id: str,
    args: argparse.Namespace,
) -> None:
    dual = lgwks_run.embed_dual(
        vector_text,
        embed_on=True,
        provider=args.embed_provider,
        model=args.embed_model,
    )
    cdet = dual["det"]
    rows.provider_counts[cdet["provider"]] += 1
    rows.vector_rows.append({
        "vector_id": f"vec-{io._sha(chunk_id + cdet['provider'])[:16]}",
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "provider": cdet["provider"],
        "is_semantic": False,
        "dims": cdet["dims"],
        "vector_text": vector_text[:2000],
        "vector": cdet["vector"],
        "fact_score": fact_score,
        "chunk_kind": chunk_kind,
        "tokenization_id": tok_id,   # #165
        "artifact_cid": chunk_id,    # #165
    })
    if dual["sem"]:
        csem = dual["sem"]
        rows.provider_counts[csem["provider"]] += 1
        rows.semantic_vectors += 1
        rows.vector_rows.append({
            "vector_id": f"vec-{io._sha(chunk_id + csem['provider'])[:16]}",
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "provider": csem["provider"],
            "is_semantic": True,
            "dims": csem["dims"],
            "vector_text": vector_text[:2000],
            "vector": csem["vector"],
            "fact_score": fact_score,
            "chunk_kind": chunk_kind,
            "tokenization_id": tok_id,   # #165
            "artifact_cid": chunk_id,    # #165
        })


def _ingest_text_chunks(
    rows: _BuildRows,
    *,
    doc: dict[str, Any],
    doc_id: str,
    source_kind: str,
    tok_id: str,
    gate: Any,
    args: argparse.Namespace,
    run_id: str,
) -> None:
    for pos, piece in enumerate(text._chunk_text(doc["text"], size=args.chunk_words, overlap=args.chunk_overlap)):
        content_hash = io._sha(piece)
        chunk_id = f"chunk-{content_hash[:16]}"
        chunk_url = doc["source"] if source_kind == "url" else ""
        occurrence = {"document_id": doc_id, "position": pos, "url": chunk_url}
        seen = rows.chunk_by_content.get(chunk_id)
        if seen is not None:
            seen["row"]["provenance"].append(occurrence)
            rows.graph_input_rows.append({
                "chunk_id": chunk_id,
                "artifact_cid": chunk_id,
                "document_id": doc_id,
                "url": chunk_url,
                "text": piece,
                "hash": content_hash,
                "schema": seen["chunk_kind"].upper(),
            })
            continue

        fact_score = text._fact_score(piece)
        stem = text._stem_text(piece, args.fact_threshold)
        chunk_kind = text._chunk_kind(piece, fact_score)
        chunk_row = {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "source": doc["source"],
            "url": chunk_url,
            "text": piece,
            "stem_text": stem,
            "hash": content_hash,
            "fact_score": fact_score,
            "chunk_kind": chunk_kind,
            "position": pos,
            "provenance": [occurrence],
            "tokenization_id": tok_id,   # #165: lineage tag for the relational projection
            "artifact_cid": chunk_id,    # #165: tape fact cid (chunk_id IS the chunk's tape cid)
        }
        rows.chunk_rows.append(chunk_row)
        rows.chunk_by_content[chunk_id] = {"row": chunk_row, "chunk_kind": chunk_kind}
        gate.ingest_fact(chunk_id, piece, chunk_kind, capability="ingest_chunk", meta={"doc_id": doc_id, "pos": pos}, run_id=run_id)
        rows.graph_input_rows.append({
            "chunk_id": chunk_id,
            "artifact_cid": chunk_id,  # #275: per-row tape back-link (cid == chunk_id)
            "document_id": doc_id,
            "url": chunk_url,
            "text": piece,
            "hash": content_hash,
            "schema": chunk_kind.upper(),
        })
        if stem:
            rows.fact_rows.append({
                "fact_id": f"fact-{io._sha(chunk_id + stem)[:16]}",
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "fact_text": stem,
                "fact_score": fact_score,
                "chunk_kind": chunk_kind,
                "tokenization_id": tok_id,   # #165
                "artifact_cid": chunk_id,    # #165: derived from the chunk's tape entry
            })
            for sentence in text._fact_sentences(stem, args.fact_threshold):
                _append_fact_vectors(rows, sentence=sentence, chunk_kind=chunk_kind, tok_id=tok_id,
                                     gate=gate, args=args, run_id=run_id, chunk_id=chunk_id)

        _append_chunk_vectors(rows, vector_text=stem or piece, chunk_id=chunk_id, doc_id=doc_id,
                              fact_score=fact_score, chunk_kind=chunk_kind, tok_id=tok_id, args=args)


def _ingest_media_items(rows: _BuildRows, *, doc: dict[str, Any], doc_id: str, tok_id: str) -> None:
    media_items = list(doc.get("media", []))
    screenshot_b64 = doc.get("screenshot_b64") or ""
    if screenshot_b64:
        media_items.append({"url": doc["source"] + "#screenshot", "label": "[screenshot] " + doc["title"], "modality": "image"})
    if not media_items:
        return

    import lgwks_multimodal
    for media_item in media_items:
        m_url = media_item["url"]
        m_label = media_item["label"] or f"[{media_item['modality']}] {doc['title']}"
        m_modality = media_item["modality"]
        m_chunk_id = f"chunk-{io._sha(doc_id + m_url)[:16]}"
        m_b64 = screenshot_b64 if m_url.endswith("#screenshot") else None
        m_mime = doc.get("screenshot_mime") or "image/png" if m_url.endswith("#screenshot") else ""
        if not m_b64:
            continue

        rows.chunk_rows.append({
            "chunk_id": m_chunk_id,
            "document_id": doc_id,
            "source": doc["source"],
            "url": m_url,
            "text": m_label,
            "stem_text": "",
            "hash": io._sha(m_b64),
            "fact_score": 0.0,
            "chunk_kind": m_modality,
            "position": -1,
            "tokenization_id": tok_id,   # #165
            "artifact_cid": m_chunk_id,  # #165
        })

        mm = lgwks_multimodal.embed_media(
            image_b64=m_b64 if m_modality == "image" else None,
            video_b64=m_b64 if m_modality == "video" else None,
            image_mime=m_mime if m_modality == "image" else "",
            video_mime=m_mime if m_modality == "video" else "",
            caption=m_label,
        )
        idet = mm["det"]
        rows.provider_counts[idet["provider"]] += 1
        rows.vector_rows.append({
            "vector_id": f"vec-{io._sha(m_chunk_id + idet['provider'])[:16]}",
            "chunk_id": m_chunk_id, "document_id": doc_id,
            "provider": idet["provider"], "is_semantic": False,
            "dims": idet["dims"], "vector_text": m_label[:2000],
            "vector": idet["vector"], "fact_score": 0.0, "chunk_kind": m_modality,
            "tokenization_id": tok_id, "artifact_cid": m_chunk_id,  # #165
        })
        if mm.get("sem"):
            isem = mm["sem"]
            rows.provider_counts[isem["provider"]] += 1
            rows.semantic_vectors += 1
            rows.vector_rows.append({
                "vector_id": f"vec-{io._sha(m_chunk_id + isem['provider'])[:16]}",
                "chunk_id": m_chunk_id, "document_id": doc_id,
                "provider": isem["provider"], "is_semantic": True,
                "dims": isem["dims"], "vector_text": m_label[:2000],
                "vector": isem["vector"], "fact_score": 0.0, "chunk_kind": m_modality,
                "tokenization_id": tok_id, "artifact_cid": m_chunk_id,  # #165
            })
            rows.graph_input_rows.append({
                "chunk_id": m_chunk_id, "document_id": doc_id,
                "url": m_url, "text": m_label,
                "hash": isem.get("cid", ""),
                "schema": m_modality.upper(),
            })
            rows.fact_rows.append({
                "fact_id": f"fact-{io._sha(doc_id + m_chunk_id + m_modality)[:16]}",
                "i_cid": doc_id, "k": m_modality, "j_cid": m_chunk_id,
                "confidence_score": 1.0, "schema": "lgwks.score.record.v1"
            })


def _ingest_docs(
    *,
    docs: list[dict[str, Any]],
    source_kind: str,
    tok_id: str,
    gate: Any,
    args: argparse.Namespace,
    run_id: str,
) -> _BuildRows:
    rows = _BuildRows()
    for idx, doc in enumerate(docs, start=1):
        _, doc_id = _append_source_doc_rows(rows, doc, idx)
        _ingest_text_chunks(rows, doc=doc, doc_id=doc_id, source_kind=source_kind,
                            tok_id=tok_id, gate=gate, args=args, run_id=run_id)
        _ingest_media_items(rows, doc=doc, doc_id=doc_id, tok_id=tok_id)
    return rows


def _write_concepts(run_dir: Path, rows: _BuildRows, args: argparse.Namespace) -> None:
    # ── Concept extraction (what things mean, not just what was said) ────────────
    if rows.chunk_rows:
        import lgwks_concept as concept_mod
        cg = concept_mod.extract_from_chunks(rows.chunk_rows, domain_hints=getattr(args, "concept_hints", None))
        cg.export_json(run_dir / "concepts.json")
        concept_vector_rows = [
            {
                "concept_id": c.concept_id,
                "concept_slug": c.slug,
                "label": c.label,
                "type": c.concept_type,
                "definition": c.definition,
                "aliases": c.aliases,
                "attributes": c.attributes,
                "occurrences": c.occurrences,
                "confidence": c.confidence,
                "source_chunks": c.source_chunks,
            }
            for c in cg._by_slug.values()
        ]
        io._emit_jsonl(run_dir / "concepts.jsonl", concept_vector_rows)
    else:
        io._emit_jsonl(run_dir / "concepts.jsonl", [])


def _write_run_jsonl(run_dir: Path, rows: _BuildRows, frontier: list[dict[str, Any]]) -> None:
    io._emit_jsonl(run_dir / "sources.jsonl", rows.source_rows)
    io._emit_jsonl(run_dir / "documents.jsonl", rows.doc_rows)
    io._emit_jsonl(run_dir / "chunks.jsonl", rows.chunk_rows)
    io._emit_jsonl(run_dir / "facts.jsonl", rows.fact_rows)
    io._emit_jsonl(run_dir / "vectors.jsonl", rows.vector_rows)
    if frontier:
        io._emit_jsonl(run_dir / "frontier.jsonl", frontier)
        io._emit_json(run_dir / "crawl_map.json", crawl._crawl_map(frontier))


def _project_gate_state(gate: Any, rows: _BuildRows, frontier: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    # State Fabric: the entity graph is the gate-owned, cumulative GraphFabric
    # projection (the per-run graph.db was removed in #169). Exports + stats are
    # sourced from the cumulative graph; `query --neighbors` reads it via the gate.
    # #165 step 2: tag the cumulative graph with this gate's tier (world ⊕ tenant
    # ownership). #275: each graph_input_row now carries its own artifact_cid (= its
    # chunk_id, which is the chunk's tape fact cid), so ingest_chunk stamps per-row
    # tape provenance rather than one last-writer cid for the whole batch. The
    # batch-level tier is the gate's tenant; per-row artifact_cid wins via
    # ingest_chunk's `artifact_cid or chunk.get("artifact_cid")`.
    gate.graph_fabric.ingest_chunks(rows.graph_input_rows, tier=gate.tenant_id)
    graph_json = run_dir / "graph.json"
    graph_mmd = run_dir / "graph.mmd"
    gate.graph_fabric.export_json(graph_json)
    gate.graph_fabric.export_mermaid(graph_mmd)
    stats = gate.graph_fabric.stats()

    # State Fabric: fact embedding vectors accumulate in the gate's world-tier
    # VectorFabric (the cross-run GLOBAL_FACT_DB was removed in #170). Idempotent
    # by content-address, so re-ingesting an identical fact vector is a no-op.
    gate.vector_fabric.ingest_fact_vectors(rows.fact_vector_rows)

    # State Fabric: the relational surface is the gate-owned, cumulative
    # RelationalProjection (the per-run substrate.db / _build_index_db was deleted;
    # this is now the single relational store, parity-tested in
    # tests/test_substrate_gate_projection.py).
    gate.relational.project_run(
        source_rows=rows.source_rows,
        doc_rows=rows.doc_rows,
        chunk_rows=rows.chunk_rows,
        fact_rows=rows.fact_rows,
        vector_rows=rows.vector_rows,
        frontier=frontier,
    )
    return stats


def _vector_space(args: argparse.Namespace, rows: _BuildRows) -> dict[str, Any]:
    _unique_providers = dict(rows.provider_counts)
    _unique_dims: set[int] = {row["dims"] for row in rows.vector_rows if row.get("dims")}
    # Dual-vector runs (det 256-d + sem 4096-d) are intentionally bilingual, not ambiguous.
    # Ambiguity means >1 semantic provider flapping OR >2 dims (model switching mid-run).
    _ambiguous_vs = len(_unique_providers) > 2 or len(_unique_dims) > 2
    if _ambiguous_vs:
        _canonical_provider = ""
        _canonical_dims = 0
    else:
        # Prefer semantic provider as canonical (not deterministic fallback)
        _canonical_provider = next(
            (p for p in _unique_providers if "deterministic" not in p),
            next(iter(_unique_providers), "")
        )
        _canonical_dims = next(
            (row["dims"] for row in rows.vector_rows if row.get("dims") and "deterministic" not in row.get("provider", "")),
            next(iter(_unique_dims), 0)
        )
    _canonical_model = args.embed_model or ""
    _is_semantic = rows.semantic_vectors > 0

    return {
        "provider_requested": args.embed_provider,
        "model_requested": _canonical_model,
        "providers_used": _unique_providers,
        "canonical_provider": _canonical_provider,
        "canonical_model": _canonical_model,
        "dims": _canonical_dims,
        "semantic": _is_semantic,
        "ambiguous": _ambiguous_vs,
    }


def _build_manifest(
    *,
    args: argparse.Namespace,
    run_id: str,
    run_dir: Path,
    source_kind: str,
    rows: _BuildRows,
    frontier: list[dict[str, Any]],
    stats: dict[str, Any],
    gate: Any,
) -> dict[str, Any]:
    vector_space = _vector_space(args, rows)
    return {
        "schema": "lgwks.substrate.run.v0",
        "run_id": run_id,
        "target": args.target,
        "source_type": source_kind,
        "project": _project_name(args),
        "created_at": _clock.now_iso(),  # canonical UTC ISO (#223; Z→+00:00, completes #151)
        "embedding": {
            "provider_requested": args.embed_provider,
            "model_requested": args.embed_model,
            "providers_used": dict(rows.provider_counts),
            "semantic_vectors": rows.semantic_vectors,
            "total_vectors": len(rows.vector_rows),
            "global_fact_vectors_written": len(rows.fact_vector_rows),
        },
        "vector_space": vector_space,
        "auth": {
            "login_if_needed": bool(args.login_if_needed),
            "login_url": args.login_url,
            "success_selector": args.success_selector or "",
            "max_auto_bypass_attempts": args.max_auto_bypass_attempts,
            "max_auth_handoffs": args.max_auth_handoffs,
            "browser_engine": args.browser_engine,
            "click_discovery": bool(getattr(args, "click_discovery", False)),
            "max_clicks_per_page": int(getattr(args, "max_clicks_per_page", 20)),
            "crawl_mode": getattr(args, "crawl_mode", "link-then-click"),
            "click_telemetry": getattr(frontier, "click_telemetry", {}),
        },
        "click_telemetry": getattr(frontier, "click_telemetry", {}),
        "counts": {
            "sources": len(rows.source_rows),
            "documents": len(rows.doc_rows),
            "chunks": len(rows.chunk_rows),
            "facts": len(rows.fact_rows),
            "frontier": len(frontier),
            "graph_nodes": stats["nodes"],
            "graph_edges": stats["edges"],
        },
        "artifacts": {
            "root": str(run_dir),
            "sources": "sources.jsonl",
            "documents": "documents.jsonl",
            "chunks": "chunks.jsonl",
            "facts": "facts.jsonl",
            "vectors": "vectors.jsonl",
            "frontier": "frontier.jsonl" if frontier else "",
            "crawl_map": "crawl_map.json" if frontier else "",
            "graph_db": str(gate.graph_fabric.db_path),  # gate-owned cumulative graph store
            "graph_json": "graph.json",
            "graph_mermaid": "graph.mmd",
            "substrate_db": str(gate.relational.path),  # gate-owned cumulative relational store
        },
        "global_artifacts": {
            "fact_vector_db": str(gate.vector_fabric.path),  # gate world-tier vector store (#170)
        },
    }


def build_run(args: argparse.Namespace) -> dict[str, Any]:
    source_kind = _source_type(args.target, args.source_type)
    run_id, run_dir = _new_run_dir(args)
    docs, frontier = _load_build_docs(args, source_kind)

    gate = lgwks_storage.get_gate(args.project or Path(args.target).name)
    try:
        # #165 Phase 2: every row that lands in a projection carries its tape provenance
        # — tokenization_id (which analyzer named it) + artifact_cid (the tape fact cid
        # it derives from). Chunks/facts are ingested via gate.ingest_fact, which uses the
        # default word_regex tokenizer, so that id is the lineage tag for every derived
        # vector. artifact_cid is the chunk/fact's own tape cid (== chunk_id / sha(text)),
        # so a vector is content-addressed back to the exact tape entry it embeds.
        tok_id = gate.tokenizers.default_word_regex_id()
        rows = _ingest_docs(docs=docs, source_kind=source_kind, tok_id=tok_id, gate=gate, args=args, run_id=run_id)
        _write_concepts(run_dir, rows, args)
        _write_run_jsonl(run_dir, rows, frontier)
        stats = _project_gate_state(gate, rows, frontier, run_dir)
        manifest = _build_manifest(
            args=args,
            run_id=run_id,
            run_dir=run_dir,
            source_kind=source_kind,
            rows=rows,
            frontier=frontier,
            stats=stats,
            gate=gate,
        )
    finally:
        gate.close()
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def query_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = io._resolve_run_dir(args.run)
    if not run_dir.exists():
        return {
            "schema": "lgwks.substrate.query.v0",
            "run": str(run_dir),
            "kind": args.kind,
            "match": args.match,
            "rows": [],
            "error": f"no substrate run resolved for {args.run!r}; "
            f"list available runs under {config.RUN_ROOT}",
        }
    if getattr(args, "vector", ""):
        return vector._vector_search(
            run_dir,
            args.vector,
            args.limit,
            args.embed_provider,
            args.embed_model,
            force_cross_space=getattr(args, "force_cross_space", False),
        )
    rows: list[dict[str, Any]] = []
    path = run_dir / ("facts.jsonl" if args.kind == "facts" else "chunks.jsonl")
    payload: dict[str, Any] = {
        "schema": "lgwks.substrate.query.v0",
        "run": str(run_dir),
        "kind": args.kind,
        "match": args.match,
        "rows": rows,
    }
    if not path.exists():
        # The run resolved (e.g. to a cumulative gate dir) but has no JSONL export
        # for this kind — say so rather than returning a silent empty result.
        payload["error"] = (
            f"no {path.name} under {run_dir}; this looks like a gate store without a "
            f"JSONL export — run `substrate build` for this project to produce one"
        )
        return payload
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        text = row.get("fact_text", row.get("text", ""))
        if args.match.lower() in text.lower():
            rows.append(row)
            if len(rows) >= args.limit:
                break
    if args.neighbors:
        # #169: neighbors resolve against the gate's cumulative graph, not a per-run
        # graph.db. The run manifest names the project whose gate owns the graph.
        import lgwks_fabric_reader as reader_mod

        manifest = io._load_run_manifest(run_dir)
        project = manifest.get("project") or run_dir.name
        gate, reader = reader_mod.open_reader(project)
        try:
            node, err = reader.graph_resolve_node(args.neighbors)
            if err:
                payload["graph_error"] = err
            else:
                payload["node"] = node
                payload["neighbors"] = reader.graph_neighbors(node["node_id"], limit=args.limit)
        finally:
            gate.close()
    return payload


def baseline_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = io._resolve_run_dir(args.run)
    manifest = io._load_run_manifest(run_dir)
    facts = io._read_jsonl(run_dir / "facts.jsonl")
    frontier = io._read_jsonl(run_dir / "frontier.jsonl")
    as_of = _parse_iso_date(args.as_of)
    buckets = text._bucket_facts(facts, as_of=as_of, limit=args.limit)
    gaps = _policy_pack_gaps(manifest, facts, frontier, buckets)
    payload = {
        "schema": "lgwks.substrate.baseline.v0",
        "ok": bool(manifest) and bool(facts) and not any(gap["severity"] == "high" for gap in gaps),
        "run": str(run_dir),
        "run_id": manifest.get("run_id", run_dir.name),
        "target": manifest.get("target", ""),
        "project": manifest.get("project", ""),
        "as_of": as_of.isoformat(),
        "version_policy": {
            "order": list(VERSION_BUCKETS),
            "upcoming_label": "V36",
            "upcoming_effective_date": UPCOMING_EFFECTIVE_DATE.isoformat(),
            "rule": "V36 is Upcoming before 2026-06-15 and Current on/after 2026-06-15",
        },
        "counts": manifest.get("counts", {}),
        "embedding": manifest.get("embedding", {}),
        "auth": manifest.get("auth", {}),
        "frontier_status_counts": crawl._frontier_status_counts(frontier),
        "sections": [{"name": name, "facts": buckets[name]} for name in VERSION_BUCKETS],
        "policy_pack_gaps": gaps,
        "artifacts": {
            "manifest": str(run_dir / "manifest.json"),
            "facts": str(run_dir / "facts.jsonl"),
            "frontier": str(run_dir / "frontier.jsonl") if (run_dir / "frontier.jsonl").exists() else "",
            "crawl_map": str(run_dir / "crawl_map.json") if (run_dir / "crawl_map.json").exists() else "",
            "graph_json": str(run_dir / "graph.json") if (run_dir / "graph.json").exists() else "",
            "substrate_db": str(run_dir / "substrate.db") if (run_dir / "substrate.db").exists() else "",
        },
    }
    if args.write:
        out_path = run_dir / "baseline.json"
        io._emit_json(out_path, payload)
        payload["artifacts"]["baseline"] = str(out_path)
    return payload


# ── CLI command wrappers ────────────────────────────────────────────────────

def build_command(args: argparse.Namespace) -> int:
    try:
        payload = build_run(args)
    except EmbeddingProviderUnavailable as exc:
        print(json.dumps(_provider_unavailable_payload(args, exc), indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


def map_command(args: argparse.Namespace) -> int:
    try:
        payload = build_run(args)
    except EmbeddingProviderUnavailable as exc:
        print(json.dumps(_provider_unavailable_payload(args, exc), indent=2))
        return 1
    artifacts = payload["artifacts"]
    root = Path(artifacts["root"])
    summary = {
        "schema": "lgwks.substrate.map.v0",
        "run_id": payload["run_id"],
        "target": payload["target"],
        "crawl_map": str(root / artifacts["crawl_map"]) if artifacts.get("crawl_map") else "",
        "substrate_db": str(root / artifacts["substrate_db"]),
        "graph_json": str(root / artifacts["graph_json"]),
        "counts": payload["counts"],
        "embedding": payload["embedding"],
        "auth": payload["auth"],
        "global_artifacts": payload.get("global_artifacts", {}),
    }
    print(json.dumps(summary, indent=2))
    return 0


def query_command(args: argparse.Namespace) -> int:
    print(json.dumps(query_run(args), indent=2))
    return 0


def baseline_command(args: argparse.Namespace) -> int:
    print(json.dumps(baseline_run(args), indent=2))
    return 0


# ── Parser registration ──────────────────────────────────────────────────────

def add_parser(sub) -> None:
    p = sub.add_parser("substrate", help="deterministic crawl+vector substrate for local or web content")
    ps = p.add_subparsers(dest="substrate_command", required=True)

    def _add_build_args(cmd) -> None:
        cmd.add_argument("target")
        cmd.add_argument("--project", default="")
        cmd.add_argument("--source-type", choices=["auto", "url", "file", "folder", "repo"], default="auto")
        cmd.add_argument("--max-pages", type=int, default=25)
        cmd.add_argument("--max-depth", type=int, default=2)
        cmd.add_argument("--max-files", type=int, default=250)
        cmd.add_argument("--max-chars", type=int, default=120_000)
        cmd.add_argument("--chunk-words", type=int, default=320)
        cmd.add_argument("--chunk-overlap", type=int, default=48)
        cmd.add_argument("--fact-threshold", type=float, default=0.6)
        cmd.add_argument("--embed-provider", choices=["auto", "ollama", "openrouter-vl", "deterministic", "apple-local"], default="auto")
        cmd.add_argument("--embed-model", default="",
                         help="optional explicit embedding model id; openrouter-vl defaults to NVIDIA Nemotron Embed VL")
        cmd.add_argument("--login-if-needed", action=argparse.BooleanOptionalAction, default=True,
                         help="for URL targets, detect auth walls, open a browser, save session, then resume")
        cmd.add_argument("--login-url", default="",
                         help="optional explicit login URL; defaults to the target URL when auth is detected")
        cmd.add_argument("--auth-selector", dest="success_selector", default=None,
                         help="optional CSS selector for auto-detected post-auth success on SPAs")
        cmd.add_argument("--max-auto-bypass-attempts", type=int, default=3,
                         help="global retry budget before escalating a blocker to the human browser handoff")
        cmd.add_argument("--max-auth-handoffs", type=int, default=3,
                         help="how many times the crawler may pause for human auth before giving up")
        cmd.add_argument("--chromium", dest="browser_engine", action="store_const", const="chromium",
                         default="webkit", help="use Chromium instead of WebKit (for Chrome-cookie compatibility or anti-detection flag)")
        cmd.add_argument("--click-discovery", action="store_true", default=False,
                         help="deterministically click visible controls and record no-access/dead branches")
        cmd.add_argument("--max-clicks-per-page", type=int, default=20,
                         help="max visible controls to click per rendered page when --click-discovery is enabled")
        cmd.add_argument("--crawl-mode", choices=["link-only", "link-then-click", "click-heavy"], default="link-then-click",
                         help="crawl mode: link-only (no clicks), link-then-click (click only when href extraction is weak), click-heavy (always click visible controls)")
        cmd.add_argument("--embed-screenshots", action="store_true", default=False,
                         help="capture one screenshot per page and embed it via the paid media endpoint "
                              "(google/gemini-embedding-2, ~1290 tok/image). OFF by default — every page "
                              "is a billable image embed; text always embeds free via local ollama")
        cmd.add_argument("--json", action="store_true", help="structured JSON output (always on for substrate; flag for compatibility)")

    build = ps.add_parser("build", help="build a substrate run from a url, file, folder, or repo")
    _add_build_args(build)
    build.set_defaults(func=build_command)

    map_run = ps.add_parser("map", help="one deep pass: crawl map + chunks + vectors + graph + substrate db")
    _add_build_args(map_run)
    map_run.set_defaults(func=map_command)

    query = ps.add_parser("query", help="query a substrate run")
    query.add_argument("run")
    query.add_argument("--kind", choices=["facts", "chunks"], default="facts")
    query.add_argument("--match", default="")
    query.add_argument("--neighbors", help="also resolve graph neighbors for a node label/id")
    query.add_argument("--vector", default="", help="semantic/vector query text over stored chunk vectors")
    query.add_argument(
        "--embed-provider",
        default="",
        help=(
            "embedding provider for vector query. When omitted (default), the provider recorded in "
            "the run manifest is used. Explicit values: auto, ollama, openrouter-vl, deterministic, apple-local. "
            "If the explicit value does not match the stored vector space, the query fails closed "
            "unless --force-cross-space is supplied."
        ),
    )
    query.add_argument("--embed-model", default="", help="optional explicit embedding model id for vector query")
    query.add_argument(
        "--force-cross-space",
        action="store_true",
        default=False,
        help=(
            "allow querying with a provider/model that does not match the stored vector space. "
            "Scores will be cross-space and not semantically comparable. Use only for debugging."
        ),
    )
    query.add_argument("--limit", type=int, default=20)
    query.set_defaults(func=query_command)

    baseline = ps.add_parser("baseline", help="summarize a substrate run as Current / Upcoming / Previous baseline")
    baseline.add_argument("run")
    baseline.add_argument("--as-of", default="", help="YYYY-MM-DD date for version classification; defaults to today")
    baseline.add_argument("--limit", type=int, default=20, help="max facts per version section")
    baseline.add_argument("--write", action="store_true", help="write baseline.json into the run directory")
    baseline.set_defaults(func=baseline_command)
