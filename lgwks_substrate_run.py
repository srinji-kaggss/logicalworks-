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
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import lgwks_run
import lgwks_sqlite
import lgwks_substrate_config as config
import lgwks_substrate_crawl as crawl
import lgwks_substrate_db as db
import lgwks_substrate_io as io
import lgwks_substrate_text as text
import lgwks_substrate_vector as vector
import lgwks_entity_graph as entity_graph
from lgwks_substrate_config import EmbeddingProviderUnavailable, RUN_ROOT, GLOBAL_FACT_DB, UPCOMING_EFFECTIVE_DATE, VERSION_BUCKETS


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
    return "file"


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


def build_run(args: argparse.Namespace) -> dict[str, Any]:
    source_kind = _source_type(args.target, args.source_type)
    run_id = f"{io._slug(args.project or Path(args.target).name)}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if source_kind == "url":
        docs, frontier = crawl._crawl_site(
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
        )
    else:
        docs = _build_from_local(Path(args.target).resolve(), source_kind, args.max_files, args.max_chars)
        frontier = []

    source_rows: list[dict[str, Any]] = []
    doc_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    fact_vector_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    graph_input_rows: list[dict[str, Any]] = []
    provider_counts: Counter[str] = Counter()
    semantic_vectors = 0

    for idx, doc in enumerate(docs, start=1):
        source_identity = f"{doc['source']}|{doc['discovered_by']}|{doc['depth']}|{idx}"
        source_id = f"src-{io._sha(source_identity)[:16]}"
        doc_id = f"doc-{io._sha(source_identity + doc['title'])[:16]}"
        source_rows.append({
            "source_id": source_id,
            "source": doc["source"],
            "title": doc["title"],
            "discovered_by": doc["discovered_by"],
            "depth": doc["depth"],
        })
        doc_rows.append({
            "document_id": doc_id,
            "source_id": source_id,
            "title": doc["title"],
            "source": doc["source"],
            "word_count": len(__import__("re").findall(r"\S+", doc["text"])),
        })
        for pos, piece in enumerate(text._chunk_text(doc["text"], size=args.chunk_words, overlap=args.chunk_overlap)):
            chunk_id = f"chunk-{io._sha(doc_id + str(pos) + piece)[:16]}"
            fact_score = text._fact_score(piece)
            stem = text._stem_text(piece, args.fact_threshold)
            chunk_kind = text._chunk_kind(piece, fact_score)
            chunk_row = {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "source": doc["source"],
                "url": doc["source"] if source_kind == "url" else "",
                "text": piece,
                "stem_text": stem,
                "hash": io._sha(piece),
                "fact_score": fact_score,
                "chunk_kind": chunk_kind,
                "position": pos,
            }
            chunk_rows.append(chunk_row)
            graph_input_rows.append({
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "url": chunk_row["url"],
                "text": piece,
                "hash": chunk_row["hash"],
                "schema": chunk_kind.upper(),
            })
            if stem:
                fact_rows.append({
                    "fact_id": f"fact-{io._sha(chunk_id + stem)[:16]}",
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "fact_text": stem,
                    "fact_score": fact_score,
                    "chunk_kind": chunk_kind,
                })
                for sentence in text._fact_sentences(stem, args.fact_threshold):
                    dual = lgwks_run.embed_dual(sentence, embed_on=True)
                    # deterministic fact vector (always present; audit trail)
                    fdet = dual["det"]
                    provider_counts[fdet["provider"]] += 1
                    fact_vector_rows.append({
                        "fact_hash": io._sha(sentence),
                        "fact_text": sentence,
                        "provider": fdet["provider"],
                        "dims": fdet["dims"],
                        "vector": fdet["vector"],
                        "fact_score": text._fact_score(sentence),
                        "chunk_kind": chunk_kind,
                    })
                    # semantic fact vector (primary; feeds NeoBERT / downstream ML)
                    if dual["sem"]:
                        fsem = dual["sem"]
                        provider_counts[fsem["provider"]] += 1
                        semantic_vectors += 1
                        fact_vector_rows.append({
                            "fact_hash": io._sha(sentence),
                            "fact_text": sentence,
                            "provider": fsem["provider"],
                            "dims": fsem["dims"],
                            "vector": fsem["vector"],
                            "fact_score": text._fact_score(sentence),
                            "chunk_kind": chunk_kind,
                        })

            vector_text = stem or piece
            dual = lgwks_run.embed_dual(vector_text, embed_on=True)
            # deterministic chunk vector (always present)
            cdet = dual["det"]
            provider_counts[cdet["provider"]] += 1
            vector_rows.append({
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
            })
            # semantic chunk vector (primary; feeds NeoBERT)
            if dual["sem"]:
                csem = dual["sem"]
                provider_counts[csem["provider"]] += 1
                semantic_vectors += 1
                vector_rows.append({
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
                })

    io._emit_jsonl(run_dir / "sources.jsonl", source_rows)
    io._emit_jsonl(run_dir / "documents.jsonl", doc_rows)
    io._emit_jsonl(run_dir / "chunks.jsonl", chunk_rows)
    io._emit_jsonl(run_dir / "facts.jsonl", fact_rows)
    io._emit_jsonl(run_dir / "vectors.jsonl", vector_rows)
    if frontier:
        io._emit_jsonl(run_dir / "frontier.jsonl", frontier)
        io._emit_json(run_dir / "crawl_map.json", crawl._crawl_map(frontier))

    db_path = run_dir / "graph.db"
    graph_db = entity_graph.GraphDB(db_path)
    entity_graph.ingest_chunks(graph_db, graph_input_rows)
    graph_json = run_dir / "graph.json"
    graph_mmd = run_dir / "graph.mmd"
    graph_db.export_json(graph_json)
    graph_db.export_mermaid(graph_mmd)
    stats = graph_db.stats()
    graph_db.close()

    index_db = run_dir / "substrate.db"
    db._build_index_db(
        index_db,
        source_rows=source_rows,
        doc_rows=doc_rows,
        chunk_rows=chunk_rows,
        fact_rows=fact_rows,
        vector_rows=vector_rows,
        frontier=frontier,
    )
    db._upsert_global_fact_vectors(GLOBAL_FACT_DB, run_id=run_id, fact_vectors=fact_vector_rows)

    _unique_providers = dict(provider_counts)
    _unique_dims: set[int] = {row["dims"] for row in vector_rows if row.get("dims")}
    _ambiguous_vs = len(_unique_providers) > 1 or len(_unique_dims) > 1
    if _ambiguous_vs:
        _canonical_provider = ""
        _canonical_dims = 0
    else:
        _canonical_provider = next(iter(_unique_providers), "")
        _canonical_dims = next(iter(_unique_dims), 0)
    _canonical_model = args.embed_model or ""
    _is_semantic = semantic_vectors > 0

    vector_space: dict[str, Any] = {
        "provider_requested": args.embed_provider,
        "model_requested": _canonical_model,
        "providers_used": _unique_providers,
        "canonical_provider": _canonical_provider,
        "canonical_model": _canonical_model,
        "dims": _canonical_dims,
        "semantic": _is_semantic,
        "ambiguous": _ambiguous_vs,
    }

    manifest = {
        "schema": "lgwks.substrate.run.v0",
        "run_id": run_id,
        "target": args.target,
        "source_type": source_kind,
        "project": args.project or io._slug(Path(args.target).name),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "embedding": {
            "provider_requested": args.embed_provider,
            "model_requested": args.embed_model,
            "providers_used": dict(provider_counts),
            "semantic_vectors": semantic_vectors,
            "total_vectors": len(vector_rows),
            "global_fact_vectors_written": len(fact_vector_rows),
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
            "sources": len(source_rows),
            "documents": len(doc_rows),
            "chunks": len(chunk_rows),
            "facts": len(fact_rows),
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
            "graph_db": "graph.db",
            "graph_json": "graph.json",
            "graph_mermaid": "graph.mmd",
            "substrate_db": "substrate.db",
        },
        "global_artifacts": {
            "fact_vector_db": str(GLOBAL_FACT_DB),
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def query_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run).resolve()
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
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            text = row.get("fact_text", row.get("text", ""))
            if args.match.lower() in text.lower():
                rows.append(row)
                if len(rows) >= args.limit:
                    break
    payload = {
        "schema": "lgwks.substrate.query.v0",
        "run": str(run_dir),
        "kind": args.kind,
        "match": args.match,
        "rows": rows,
    }
    if args.neighbors:
        graph_db = entity_graph.GraphDB(run_dir / "graph.db")
        try:
            node, err = entity_graph._resolve_single_node(graph_db, args.neighbors)
            if err:
                payload["graph_error"] = err
            else:
                payload["node"] = node
                payload["neighbors"] = graph_db.neighbors(node["node_id"], limit=args.limit)
        finally:
            graph_db.close()
    return payload


def baseline_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run).resolve()
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
