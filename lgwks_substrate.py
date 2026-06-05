"""lgwks_substrate — deterministic crawl+vector substrate for files, folders, repos, and sites.

This is the CLI-first knowledge layer that AI agents should consume instead of scraping ad hoc.
It produces replayable artifacts: clean chunks, STEM-lean facts, semantic vectors, and a local graph.

Runtime principles:
  - generation-free execution path
  - local embeddings only (Qwen Eye via Ollama or deterministic fallback if explicitly requested)
  - host-scoped browser sessions for authenticated sites
  - stable IDs + jsonl/sqlite artifacts for downstream AI or human query layers
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
from collections import Counter, deque
from pathlib import Path
from typing import Any

import lgwks_browser
import lgwks_entity_graph as entity_graph
import lgwks_run
from lgwks_html import html_to_markdown

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "substrate"
TEXT_EXT = {
    ".txt", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".csv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt", ".swift", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".sh", ".bash", ".zsh", ".sql", ".lua", ".r",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", ".next", "dist", "build", "store"}
NUMERIC_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b|\$\s*\d[\d,]*(?:\.\d+)?")
CODE_RE = re.compile(r"\b(?:[A-Z]{2,}\d{0,4}|T\d{4}|TR\d{2}|[A-Z]{2,5})\b")
REF_RE = re.compile(r"\b(?:s\.?\s*\d+(?:\.\d+)?|\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
PROCEDURE_TERMS = {
    "must", "requires", "required", "only", "cannot", "blocked", "allowed", "if",
    "when", "then", "before", "after", "submit", "transfer", "route", "settlement",
    "minimum", "maximum", "threshold", "code", "form", "designation", "version",
}
NARRATIVE_TERMS = {
    "think", "feel", "believe", "love", "maybe", "probably", "helpful", "great",
    "excellent", "frustrated", "opinion", "story", "journey", "marketing", "vision",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _slug(text: str, limit: int = 64) -> str:
    return (re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip(".-") or "substrate")[:limit]


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


def _iter_text_files(root: Path, max_files: int) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if len(out) >= max_files:
            break
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if p.is_file() and p.suffix.lower() in TEXT_EXT and p.stat().st_size <= 2_000_000:
            out.append(p)
    return sorted(out)


def _read_text(path: Path, max_chars: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _crawl_site(base_url: str, *, max_pages: int, max_depth: int, browser_engine: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed = urllib.parse.urlparse(base_url)
    base_host = parsed.hostname or ""
    seen: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque([(base_url, 0, "seed")])
    docs: list[dict[str, Any]] = []
    frontier: list[dict[str, Any]] = []
    while queue and len(docs) < max_pages:
        url, depth, discovered_by = queue.popleft()
        clean = urllib.parse.urldefrag(url)[0]
        if not clean or clean in seen:
            continue
        seen.add(clean)
        if not lgwks_browser._remote_allowed(clean):
            frontier.append({"url": clean, "depth": depth, "status": "blocked", "discovered_by": discovered_by})
            continue
        rendered = lgwks_browser.render(
            clean,
            max_chars=120_000,
            use_session=True,
            wait_ms=2500,
            with_html=True,
            browser_engine=browser_engine,
        )
        if not rendered.get("ok") or not rendered.get("html"):
            frontier.append({
                "url": clean, "depth": depth, "status": "error", "reason": rendered.get("reason", ""),
                "discovered_by": discovered_by,
            })
            continue
        markdown, title, links = html_to_markdown(rendered["html"], clean)
        docs.append({
            "source": clean,
            "title": title or clean,
            "text": markdown or rendered.get("text", ""),
            "html_len": len(rendered["html"]),
            "depth": depth,
            "discovered_by": discovered_by,
        })
        frontier.append({
            "url": clean, "depth": depth, "status": "ok", "links_found": len(links),
            "discovered_by": discovered_by,
        })
        if depth >= max_depth:
            continue
        for link in links:
            href = urllib.parse.urldefrag(link.get("href", ""))[0]
            host = urllib.parse.urlparse(href).hostname or ""
            if href and host == base_host and href not in seen:
                queue.append((href, depth + 1, clean))
    return docs, frontier


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _fact_score(text: str) -> float:
    low = text.lower()
    words = re.findall(r"\b\w+\b", low)
    if not words:
        return 0.0
    numeric = len(NUMERIC_RE.findall(text))
    codes = len(CODE_RE.findall(text))
    refs = len(REF_RE.findall(text))
    procedure = sum(1 for w in words if w in PROCEDURE_TERMS)
    narrative = sum(1 for w in words if w in NARRATIVE_TERMS)
    score = 0.0
    score += min(0.35, numeric * 0.08)
    score += min(0.2, codes * 0.05)
    score += min(0.15, refs * 0.05)
    score += min(0.3, procedure / max(6.0, len(words) / 8.0))
    score -= min(0.25, narrative / max(4.0, len(words) / 10.0))
    return round(max(0.0, min(1.0, score)), 4)


def _chunk_kind(text: str, fact_score: float) -> str:
    low = text.lower()
    if fact_score >= 0.7:
        return "stem_fact"
    if any(term in low for term in ("must", "requires", "submit", "blocked", "allowed", "route", "workflow")):
        return "workflow_rule"
    if any(term in low for term in ("rrsp", "rrif", "tfsa", "fundserv", "form", "account")):
        return "business_context"
    return "narrative_context"


def _stem_text(text: str, threshold: float) -> str:
    chosen: list[str] = []
    for sentence in _split_sentences(text):
        s = _fact_score(sentence)
        if s >= threshold or NUMERIC_RE.search(sentence) or REF_RE.search(sentence) or CODE_RE.search(sentence):
            chosen.append(sentence)
    return " ".join(chosen).strip()


def _chunk_text(text: str, size: int = 320, overlap: int = 48) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step = max(1, size - overlap)
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return out


def _emit_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _build_from_local(root: Path, source_type: str, max_files: int, max_chars: int) -> list[dict[str, Any]]:
    if source_type == "file":
        text = _read_text(root, max_chars)
        return [{
            "source": str(root),
            "title": root.name,
            "text": text,
            "html_len": 0,
            "depth": 0,
            "discovered_by": "seed",
        }] if text else []
    docs: list[dict[str, Any]] = []
    for path in _iter_text_files(root, max_files):
        text = _read_text(path, max_chars)
        if not text.strip():
            continue
        docs.append({
            "source": str(path),
            "title": str(path.relative_to(root)),
            "text": text,
            "html_len": 0,
            "depth": 0,
            "discovered_by": "filesystem",
        })
    return docs


def build_run(args: argparse.Namespace) -> dict[str, Any]:
    source_kind = _source_type(args.target, args.source_type)
    run_id = f"{_slug(args.project or Path(args.target).name)}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if source_kind == "url":
        docs, frontier = _crawl_site(
            args.target,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            browser_engine=args.browser_engine,
        )
    else:
        docs = _build_from_local(Path(args.target).resolve(), source_kind, args.max_files, args.max_chars)
        frontier = []

    source_rows: list[dict[str, Any]] = []
    doc_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    graph_input_rows: list[dict[str, Any]] = []
    provider_counts: Counter[str] = Counter()
    semantic_vectors = 0

    for idx, doc in enumerate(docs, start=1):
        source_id = f"src-{_sha(doc['source'])[:16]}"
        doc_id = f"doc-{_sha(doc['source'] + doc['title'])[:16]}"
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
            "word_count": len(re.findall(r"\S+", doc["text"])),
        })
        for pos, piece in enumerate(_chunk_text(doc["text"], size=args.chunk_words, overlap=args.chunk_overlap)):
            chunk_id = f"chunk-{_sha(doc_id + str(pos) + piece)[:16]}"
            fact_score = _fact_score(piece)
            stem = _stem_text(piece, args.fact_threshold)
            chunk_kind = _chunk_kind(piece, fact_score)
            chunk_row = {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "source": doc["source"],
                "url": doc["source"] if source_kind == "url" else "",
                "text": piece,
                "stem_text": stem,
                "hash": _sha(piece),
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
                    "fact_id": f"fact-{_sha(chunk_id + stem)[:16]}",
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "fact_text": stem,
                    "fact_score": fact_score,
                    "chunk_kind": chunk_kind,
                })
            vector_text = stem or piece
            vector, provider, is_semantic = lgwks_run.embed(vector_text, embed_on=True, provider=args.embed_provider)
            provider_counts[provider] += 1
            if is_semantic:
                semantic_vectors += 1
            vector_rows.append({
                "vector_id": f"vec-{_sha(chunk_id + provider)[:16]}",
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "provider": provider,
                "is_semantic": is_semantic,
                "dims": len(vector or []),
                "vector_text": vector_text[:2000],
                "vector": vector,
                "fact_score": fact_score,
                "chunk_kind": chunk_kind,
            })

    _emit_jsonl(run_dir / "sources.jsonl", source_rows)
    _emit_jsonl(run_dir / "documents.jsonl", doc_rows)
    _emit_jsonl(run_dir / "chunks.jsonl", chunk_rows)
    _emit_jsonl(run_dir / "facts.jsonl", fact_rows)
    _emit_jsonl(run_dir / "vectors.jsonl", vector_rows)
    if frontier:
        _emit_jsonl(run_dir / "frontier.jsonl", frontier)

    db_path = run_dir / "graph.db"
    db = entity_graph.GraphDB(db_path)
    entity_graph.ingest_chunks(db, graph_input_rows)
    graph_json = run_dir / "graph.json"
    graph_mmd = run_dir / "graph.mmd"
    db.export_json(graph_json)
    db.export_mermaid(graph_mmd)
    stats = db.stats()
    db.close()

    manifest = {
        "schema": "lgwks.substrate.run.v0",
        "run_id": run_id,
        "target": args.target,
        "source_type": source_kind,
        "project": args.project or _slug(Path(args.target).name),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "embedding": {
            "provider_requested": args.embed_provider,
            "providers_used": dict(provider_counts),
            "semantic_vectors": semantic_vectors,
            "total_vectors": len(vector_rows),
        },
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
            "graph_db": "graph.db",
            "graph_json": "graph.json",
            "graph_mermaid": "graph.mmd",
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def query_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run).resolve()
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
        db = entity_graph.GraphDB(run_dir / "graph.db")
        node, err = entity_graph._resolve_single_node(db, args.neighbors)
        if err:
            payload["graph_error"] = err
        else:
            payload["node"] = node
            payload["neighbors"] = db.neighbors(node["node_id"], limit=args.limit)
        db.close()
    return payload


def build_command(args: argparse.Namespace) -> int:
    payload = build_run(args)
    print(json.dumps(payload, indent=2))
    return 0


def query_command(args: argparse.Namespace) -> int:
    print(json.dumps(query_run(args), indent=2))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("substrate", help="deterministic crawl+vector substrate for local or web content")
    ps = p.add_subparsers(dest="substrate_command", required=True)

    build = ps.add_parser("build", help="build a substrate run from a url, file, folder, or repo")
    build.add_argument("target")
    build.add_argument("--project", default="")
    build.add_argument("--source-type", choices=["auto", "url", "file", "folder", "repo"], default="auto")
    build.add_argument("--max-pages", type=int, default=25)
    build.add_argument("--max-depth", type=int, default=2)
    build.add_argument("--max-files", type=int, default=250)
    build.add_argument("--max-chars", type=int, default=120_000)
    build.add_argument("--chunk-words", type=int, default=320)
    build.add_argument("--chunk-overlap", type=int, default=48)
    build.add_argument("--fact-threshold", type=float, default=0.6)
    build.add_argument("--embed-provider", choices=["auto", "ollama", "deterministic"], default="auto")
    build.add_argument("--webkit", dest="browser_engine", action="store_const", const="webkit",
                       default="chromium", help="use WebKit for authenticated Safari-session sites")
    build.set_defaults(func=build_command)

    query = ps.add_parser("query", help="query a substrate run")
    query.add_argument("run")
    query.add_argument("--kind", choices=["facts", "chunks"], default="facts")
    query.add_argument("--match", required=True)
    query.add_argument("--neighbors", help="also resolve graph neighbors for a node label/id")
    query.add_argument("--limit", type=int, default=20)
    query.set_defaults(func=query_command)
