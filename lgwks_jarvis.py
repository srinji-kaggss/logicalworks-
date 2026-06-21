"""lgwks_jarvis — legacy deterministic research graph crawler.

The Jarvis crawler is intentionally boring at its core: bounded crawl, stable
IDs, deterministic feature hashing, SQLite records, and explicit frontier
questions. Neural/LLM providers can improve ranking later without owning truth.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import html
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Any, Optional

import lgwks_sqlite

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "vision" / "research" / "research-network" / "runs"
SCHEMA_VERSION = "jarvis-crawl/2"
DEFAULT_DIMS = 256
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "for", "from", "has", "have", "if", "in", "into", "is", "it", "its",
    "may", "more", "not", "of", "on", "or", "our", "that", "the", "their",
    "this", "to", "was", "we", "with", "will", "you", "your", "using",
}
SEMANTIC_TYPES = {
    "state": ("state", "transition", "snapshot", "event", "temporal", "lifecycle"),
    "machine": ("system", "machine", "runtime", "compiler", "kernel", "protocol"),
    "constraint": ("limit", "bound", "latency", "memory", "throughput", "cost"),
    "topology": ("graph", "node", "edge", "path", "route", "network", "dependency"),
    "evidence": ("study", "paper", "standard", "specification", "benchmark", "dataset"),
    "risk": ("failure", "security", "risk", "unsafe", "attack", "bottleneck"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, limit: int = 48) -> str:
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or "jarvis-crawl")[:limit].strip("-") or "jarvis-crawl"


def sha(value: str, n: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:n]


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_+\-.]{1,}", text.lower()) if t not in STOPWORDS]


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def normalize_url(url: str, base: str | None = None) -> str | None:
    if base:
        url = urllib.parse.urljoin(base, url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    clean = parsed._replace(fragment="")
    return urllib.parse.urlunparse(clean)


def same_site(url: str, origin: str) -> bool:
    return urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(origin).netloc


def parse_keywords(raw: list[str], keyword_opt: str | None) -> list[str]:
    parts: list[str] = []
    if raw:
        for value in raw:
            parts.extend(re.split(r"[\n,;]+", value))
    if keyword_opt:
        parts.extend(re.split(r"[\n,;]+", keyword_opt))
    return [p.strip() for p in parts if p.strip()]


def deterministic_embedding(text: str, dims: int = DEFAULT_DIMS) -> list[float]:
    vec = [0.0] * dims
    toks = tokens(text)
    features = toks[:]
    features.extend(" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1)))
    features.extend(" ".join(toks[i:i + 3]) for i in range(max(0, len(toks) - 2)))
    for feat in features:
        digest = hashlib.blake2b(feat.encode("utf-8", errors="ignore"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    # Canonical cosine (lgwks_vecmath) — this used to be a bare dot product, which
    # conflates magnitude with similarity for the non-unit Eye vectors fed here.
    # Routed to the one source of truth so it can never drift again.
    import lgwks_vecmath
    return lgwks_vecmath.cosine(a, b)


def query_variants(keywords: list[str]) -> list[str]:
    base = " ".join(keywords)
    variants = [
        base,
        f"{base} formal model state transition graph",
        f"{base} architecture implementation protocol specification",
        f"{base} failure modes constraints bottlenecks",
        f"{base} temporal graph event snapshot topology",
        f"{base} benchmark dataset standard",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for value in variants:
        value = " ".join(value.split())
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


class TextHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title: list[str] = []
        self.text: list[str] = []
        self.links: list[str] = []
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        self._tag_stack.append(tag)
        if tag == "a":
            attrs_map = dict(attrs)
            href = attrs_map.get("href")
            if href:
                url = normalize_url(href, self.base_url)
                if url:
                    self.links.append(url)

    def handle_endtag(self, tag: str):
        for i in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[i] == tag:
                del self._tag_stack[i:]
                break

    def handle_data(self, data: str):
        if any(tag in {"script", "style", "noscript", "svg"} for tag in self._tag_stack):
            return
        clean = " ".join(html.unescape(data).split())
        if not clean:
            return
        if self._tag_stack and self._tag_stack[-1] == "title":
            self.title.append(clean)
        self.text.append(clean)


@dataclass
class FetchResult:
    url: str
    title: str
    text: str
    links: list[str]
    status: str
    error: str = ""
    elapsed: float = 0.0


def fetch_url(url: str, timeout: int = 20) -> FetchResult:
    started = time.time()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "lgwks-jarvis-crawl/0.1 (+local deterministic research bot)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.4",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(2_500_000)
        if "text/plain" in content_type or url.endswith((".txt", ".md")):
            text = raw.decode("utf-8", errors="replace")
            title = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1] or url
            links: list[str] = []
        else:
            parser = TextHTMLParser(url)
            parser.feed(raw.decode("utf-8", errors="replace"))
            title = " ".join(parser.title).strip() or urllib.parse.urlparse(url).netloc
            text = "\n".join(parser.text)
            links = list(dict.fromkeys(parser.links))
        return FetchResult(url=url, title=title[:180], text=text, links=links, status="ok", elapsed=time.time() - started)
    except Exception as exc:
        return FetchResult(url=url, title=url, text="", links=[], status="error", error=str(exc), elapsed=time.time() - started)


def run_googler(query: str, limit: int) -> list[str]:
    exe = shutil.which("googler")
    if not exe:
        return []
    cmd = [exe, "--json", "-n", str(limit), query]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=30)
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout or "[]")
        urls = [item.get("url") for item in data if isinstance(item, dict)]
        return [u for u in urls if isinstance(u, str) and normalize_url(u)]
    except Exception:
        return []


def fallback_search_url(query: str) -> str:
    encoded = urllib.parse.urlencode({"q": query})
    return f"https://html.duckduckgo.com/html/?{encoded}"


def chunk_text(text: str, size: int = 450, overlap: int = 70) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(words), step):
        piece = " ".join(words[start:start + size])
        if piece:
            chunks.append(piece)
        if start + size >= len(words):
            break
    return chunks


def concept_terms(texts: Iterable[str], max_terms: int = 80) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        toks = tokens(text)
        counts.update(toks)
        counts.update(" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1)))
        counts.update(" ".join(toks[i:i + 3]) for i in range(max(0, len(toks) - 2)))
    for term in list(counts):
        if len(term) < 3 or re.fullmatch(r"\d+", term):
            del counts[term]
    return Counter(dict(counts.most_common(max_terms)))


def semantic_type_scores(text: str) -> dict[str, float]:
    toks = set(tokens(text))
    scores = {}
    for kind, anchors in SEMANTIC_TYPES.items():
        scores[kind] = round(sum(1 for anchor in anchors if anchor in toks) / max(1, len(anchors)), 4)
    return scores


class JarvisDB:
    def __init__(self, path: Path):
        self.path = path
        self.conn = lgwks_sqlite.connect(path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.commit()
        self.conn.close()

    def init(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            create table if not exists meta(key text primary key, value text not null);
            create table if not exists runs(
              run_id text primary key,
              name text not null,
              created_at text not null,
              schema_version text not null,
              manifest_path text not null,
              prompt text not null,
              keyword_json text not null,
              config_json text not null
            );
            create table if not exists sources(
              id text primary key,
              run_id text not null,
              url text not null,
              title text not null,
              axis text not null,
              tier text not null,
              raw_path text,
              status text not null,
              error text,
              elapsed_seconds real not null default 0,
              discovered_by text not null default 'seed',
              score real not null default 0
            );
            create table if not exists documents(
              id text primary key,
              run_id text not null,
              source_id text not null,
              title text not null,
              path text not null,
              content_sha256 text not null,
              word_count integer not null,
              chunk_count integer not null
            );
            create table if not exists chunks(
              id text primary key,
              run_id text not null,
              document_id text not null,
              source_id text not null,
              position integer not null,
              text text not null,
              content_sha256 text not null,
              word_count integer not null,
              semantic_type_json text not null
            );
            create table if not exists embeddings(
              id text primary key,
              run_id text not null,
              scope text not null,
              target_id text not null,
              provider text not null,
              model text not null,
              dimensions integer not null,
              vector_json text not null
            );
            create table if not exists nodes(
              id text primary key,
              run_id text not null,
              kind text not null,
              label text not null,
              weight real not null,
              metadata_json text not null
            );
            create table if not exists edges(
              id text primary key,
              run_id text not null,
              from_id text not null,
              to_id text not null,
              kind text not null,
              weight real not null,
              evidence text,
              metadata_json text not null
            );
            create table if not exists understandings(
              id text primary key,
              run_id text not null,
              created_at text not null,
              scope text not null,
              before_snapshot_id text,
              after_snapshot_id text,
              summary text not null,
              coverage_score real not null,
              uncertainty_score real not null,
              evidence_json text not null,
              schema_json text not null
            );
            create table if not exists question_events(
              id text primary key,
              run_id text not null,
              created_at text not null,
              drill_id text not null,
              ask_index integer not null,
              question text not null,
              what_were_you_thinking text not null,
              expected_information_gain real not null,
              answered integer not null default 0,
              answer text
            );
            create table if not exists snapshots(
              id text primary key,
              run_id text not null,
              created_at text not null,
              phase text not null,
              page_count integer not null,
              chunk_count integer not null,
              node_count integer not null,
              edge_count integer not null,
              frontier_json text not null,
              top_terms_json text not null
            );
            create table if not exists drills(
              id text primary key,
              run_id text not null,
              keyword text not null,
              state text not null,
              target_pages integer not null,
              crawled_pages integer not null,
              ask_count integer not null,
              compute_estimate_seconds real not null,
              metadata_json text not null
            );
            create table if not exists crawl_events(
              id text primary key,
              run_id text not null,
              created_at text not null,
              url text not null,
              status text not null,
              elapsed_seconds real not null,
              detail_json text not null
            );
            create table if not exists compressed_nodes(
              id text primary key,
              run_id text not null,
              reason text not null,
              source_node_json text not null,
              compressed_label text not null,
              metadata_json text not null
            );
            """
        )
        self.migrate_legacy()
        cur.execute("insert or replace into meta(key,value) values('schema_version', ?)", (SCHEMA_VERSION,))
        self.conn.commit()

    def _safe_ident(self, name: str) -> str:
        """Validate SQL identifier to prevent injection (H7)."""
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_]+", name):
            raise ValueError(f"malicious SQL identifier: {name!r}")
        return name

    def columns(self, table: str) -> set[str]:
        self._safe_ident(table)
        try:
            rows = self.conn.execute(f"pragma table_info({table})").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {row[1] for row in rows}

    def add_column_if_missing(self, table: str, column: str, definition: str):
        self._safe_ident(table)
        self._safe_ident(column)
        if column not in self.columns(table):
            self.conn.execute(f"alter table {table} add column {column} {definition}")

    def migrate_legacy(self):
        embedding_cols = self.columns("embeddings")
        if embedding_cols and "id" not in embedding_cols:
            legacy_name = f"embeddings_legacy_{int(time.time())}"
            self.conn.execute(f"alter table embeddings rename to {legacy_name}")
            self.conn.execute(
                """
                create table embeddings(
                  id text primary key,
                  run_id text not null,
                  scope text not null,
                  target_id text not null,
                  provider text not null,
                  model text not null,
                  dimensions integer not null,
                  vector_json text not null
                )
                """
            )
            self.conn.execute(
                f"""
                insert or replace into embeddings(id, run_id, scope, target_id, provider, model, dimensions, vector_json)
                select 'emb-' || chunk_id, run_id, 'chunk', chunk_id, provider, model, dimensions, vector_json
                from {legacy_name}
                """
            )
        if self.columns("runs"):
            self.add_column_if_missing("runs", "schema_version", "text not null default 'legacy'")
            self.add_column_if_missing("runs", "prompt", "text not null default ''")
            self.add_column_if_missing("runs", "keyword_json", "text not null default '[]'")
            self.add_column_if_missing("runs", "config_json", "text not null default '{}'")
        if self.columns("sources"):
            self.add_column_if_missing("sources", "error", "text")
            self.add_column_if_missing("sources", "elapsed_seconds", "real not null default 0")
            self.add_column_if_missing("sources", "discovered_by", "text not null default 'legacy'")
            self.add_column_if_missing("sources", "score", "real not null default 0")
        if self.columns("chunks"):
            self.add_column_if_missing("chunks", "semantic_type_json", "text not null default '{}'")

    def insert(self, table: str, row: dict):
        self._safe_ident(table)
        keys = list(row)
        for k in keys:
            self._safe_ident(k)
        placeholders = ",".join("?" for _ in keys)
        cols = ",".join(keys)
        updates = ",".join(f"{k}=excluded.{k}" for k in keys if k != "id")
        sql = f"insert into {table}({cols}) values({placeholders})"
        if "id" in row:
            sql += f" on conflict(id) do update set {updates}"
        self.conn.execute(sql, [row[k] for k in keys])

    def count(self, table: str, run_id: str) -> int:
        self._safe_ident(table)
        return int(self.conn.execute(f"select count(*) from {table} where run_id=?", (run_id,)).fetchone()[0])


def make_snapshot(db: JarvisDB, run_id: str, phase: str, frontier: list[str], terms: Counter[str]) -> str:
    snap_id = f"snapshot-{sha(run_id + phase + utc_now() + str(time.time()))}"
    db.insert(
        "snapshots",
        {
            "id": snap_id,
            "run_id": run_id,
            "created_at": utc_now(),
            "phase": phase,
            "page_count": db.count("documents", run_id),
            "chunk_count": db.count("chunks", run_id),
            "node_count": db.count("nodes", run_id),
            "edge_count": db.count("edges", run_id),
            "frontier_json": json.dumps(frontier[:50], sort_keys=True),
            "top_terms_json": json.dumps(terms.most_common(30), sort_keys=True),
        },
    )
    return snap_id


def emit_embedding(db: JarvisDB, run_id: str, scope: str, target_id: str, text: str):
    existing = db.conn.execute(
        "select 1 from embeddings where run_id=? and scope=? and target_id=? limit 1",
        (run_id, scope, target_id),
    ).fetchone()
    if existing:
        return
    db.insert(
        "embeddings",
        {
            "id": f"emb-{sha(run_id + scope + target_id)}",
            "run_id": run_id,
            "scope": scope,
            "target_id": target_id,
            "provider": "deterministic-feature-hash",
            "model": f"hashing-vectorizer-{DEFAULT_DIMS}",
            "dimensions": DEFAULT_DIMS,
            "vector_json": json.dumps(deterministic_embedding(text), separators=(",", ":")),
        },
    )


def estimate_seconds(max_pages: int, workers: int, keyword_count: int, prior_seconds_per_page: float = 8.0) -> float:
    crawl = (max_pages * prior_seconds_per_page) / max(1, workers)
    expansion = max(0, keyword_count - 1) * 2.0
    processing = max_pages * 0.6
    return round(crawl + expansion + processing, 1)


def build_seed_urls(source: str | None, keywords: list[str], max_pages: int, search_expansion: bool) -> tuple[list[tuple[str, str]], list[str]]:
    seeds: list[tuple[str, str]] = []
    warnings: list[str] = []
    if source and normalize_url(source):
        seeds.append((normalize_url(source) or source, "seed"))
        if keywords and search_expansion:
            host = urllib.parse.urlparse(source).netloc
            for variant in query_variants(keywords):
                for url in run_googler(f"site:{host} {variant}", min(5, max_pages)):
                    seeds.append((url, "googler-site-expansion"))
    else:
        terms = keywords[:]
        if source:
            terms.insert(0, source)
        if not terms:
            raise SystemExit("jarvis crawl needs a website URL or at least one keyword")
        found: list[str] = []
        for variant in query_variants(terms):
            found.extend(run_googler(variant, min(5, max_pages)))
        if found:
            for url in found[:max_pages]:
                seeds.append((url, "googler-keyword"))
        else:
            warnings.append("googler was unavailable or returned no JSON results; seeded a bounded fallback search page")
            seeds.append((fallback_search_url(" ".join(terms)), "fallback-search"))
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url, origin in seeds:
        clean = normalize_url(url)
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append((clean, origin))
    return deduped, warnings


def score_page(result: FetchResult, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    haystack = (result.title + "\n" + result.text).lower()
    return float(sum(haystack.count(k.lower()) for k in keywords))


def write_jsonl(path: Path, rows: Iterable[dict]):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _import_substrate():
    """Seam: import the substrate auth-aware runtime lazily (patchable in tests)."""
    import lgwks_substrate as _sub
    return _sub


def _crawl_via_substrate(args: argparse.Namespace) -> dict:
    """Bridge (#34): delegate a URL crawl to the substrate auth-aware mapping runtime.

    Maps Jarvis crawl args onto lgwks_substrate.build_run() args and returns a
    Jarvis-compatible summary dict. The substrate module is fetched through the
    _import_substrate() seam so tests can mock it without touching the network.
    """
    sub = _import_substrate()
    run_name = args.name or slugify(args.source)

    # Build a synthetic Namespace that satisfies substrate's build_run contract.
    sub_args = argparse.Namespace(
        target=args.source,
        project=run_name,
        source_type="auto",
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_files=250,
        max_chars=120_000,
        chunk_words=getattr(args, "chunk_words", 320),
        chunk_overlap=getattr(args, "chunk_overlap", 48),
        fact_threshold=0.6,
        embed_provider=getattr(args, "embed_provider", "deterministic"),
        embed_model=getattr(args, "embed_model", ""),
        login_if_needed=getattr(args, "login_if_needed", True),
        login_url=getattr(args, "login_url", ""),
        success_selector=getattr(args, "auth_selector", None),
        max_auto_bypass_attempts=3,
        max_auth_handoffs=3,
        browser_engine=("chromium" if getattr(args, "chromium", False) else "webkit"),
        click_discovery=bool(getattr(args, "click_discovery", False)),
        max_clicks_per_page=int(getattr(args, "max_clicks_per_page", 20)),
        crawl_mode=getattr(args, "crawl_mode", "link-then-click"),
    )
    try:
        manifest = sub.build_run(sub_args)
    except Exception as exc:
        # Surface substrate failures (e.g. embedding provider unavailable) as the
        # canonical structured error manifest rather than crashing the bridge.
        if exc.__class__.__name__ == "EmbeddingProviderUnavailable":
            return sub._provider_unavailable_payload(sub_args, exc)
        raise
    arts = manifest.get("artifacts", {})
    root = arts.get("root", "")

    return {
        "schema": "lgwks.jarvis.substrate_crawl.v0",
        "engine": "substrate",
        "run_id": manifest.get("run_id", ""),
        "target": manifest.get("target", args.source),
        "substrate_manifest": str(Path(root) / "manifest.json") if root else "",
        "crawl_map": str(Path(root) / arts["crawl_map"]) if arts.get("crawl_map") and root else "",
        "substrate_db": str(Path(root) / arts["substrate_db"]) if arts.get("substrate_db") and root else "",
        "graph_json": str(Path(root) / arts["graph_json"]) if arts.get("graph_json") and root else "",
        "counts": manifest.get("counts", {}),
        "embedding": manifest.get("embedding", {}),
        "auth": manifest.get("auth", {}),
    }


def crawl_command(args: argparse.Namespace) -> int:
    keywords = parse_keywords(args.keyword_terms, args.keywords)
    source = args.source
    run_name = args.name or slugify(source or " ".join(keywords))
    run_id = f"{run_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    estimate = estimate_seconds(args.max_pages, args.workers, len(keywords))
    if getattr(args, "estimate_only", False):
        print(json.dumps({"estimated_seconds": estimate, "estimated_minutes": round(estimate / 60, 2)}, indent=2))
        return 0

    # --- Engine dispatch (#34): URL sources default to the substrate auth-aware
    # runtime; --engine legacy or keyword-only sources stay on the deterministic
    # Jarvis crawler below. ---
    engine = getattr(args, "engine", "substrate")
    if source and engine != "legacy":
        payload = _crawl_via_substrate(args)
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok", True) else 1

    run_dir = RUN_ROOT / run_id
    raw_dir = run_dir / "raw"
    records_dir = run_dir / "records"
    graph_dir = run_dir / "graph"
    gnn_dir = run_dir / "gnn"
    db_dir = run_dir / "db"
    for directory in (raw_dir, records_dir, graph_dir, gnn_dir, db_dir):
        directory.mkdir(parents=True, exist_ok=True)

    db = JarvisDB(db_dir / "research.sqlite")
    db.init()
    manifest_path = run_dir / "run-manifest.json"
    config = {
        "max_pages": args.max_pages,
        "max_depth": args.max_depth,
        "workers": args.workers,
        "same_site": not getattr(args, "include_external", False),
        "search_expansion": getattr(args, "search_expansion", False),
        "compress_limit": getattr(args, "compress_limit", 96),
        "similarity_threshold": getattr(args, "similarity_threshold", 0.72),
    }
    db.insert(
        "runs",
        {
            "run_id": run_id,
            "name": run_name,
            "created_at": utc_now(),
            "schema_version": SCHEMA_VERSION,
            "manifest_path": str(manifest_path),
            "prompt": getattr(args, "prompt", ""),
            "keyword_json": json.dumps(keywords, sort_keys=True),
            "config_json": json.dumps(config, sort_keys=True),
        },
    )

    seeds, warnings = build_seed_urls(source, keywords, args.max_pages, getattr(args, "search_expansion", False))
    if not seeds:
        raise SystemExit("no seed URLs found")

    estimated_msg = f"Estimated compute: {estimate}s ({round(estimate / 60, 2)} min) for {args.max_pages} pages @ {args.workers} workers"
    print(estimated_msg)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    before_id = make_snapshot(db, run_id, "before-crawl", [u for u, _ in seeds], Counter())
    queue: deque[tuple[str, int, str]] = deque((url, 0, origin) for url, origin in seeds)
    seen: set[str] = set()
    fetched: list[FetchResult] = []
    source_rows: list[dict] = []
    doc_rows: list[dict] = []
    chunk_rows: list[dict] = []
    node_rows: list[dict] = []
    edge_rows: list[dict] = []
    chunk_vectors: dict[str, list[float]] = {}
    chunk_texts: dict[str, str] = {}
    chunk_to_doc: dict[str, str] = {}
    seen_chunk_hashes: set[str] = set()

    while queue and len(seen) < args.max_pages:
        batch: list[tuple[str, int, str]] = []
        while queue and len(batch) < args.workers and len(seen) + len(batch) < args.max_pages:
            url, depth, origin = queue.popleft()
            clean = normalize_url(url)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            batch.append((clean, depth, origin))
        if not batch:
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {pool.submit(fetch_url, url): (url, depth, origin) for url, depth, origin in batch}
            for future in concurrent.futures.as_completed(future_map):
                url, depth, origin = future_map[future]
                result = future.result()
                fetched.append(result)
                event_id = f"event-{sha(run_id + url)}"
                db.insert(
                    "crawl_events",
                    {
                        "id": event_id,
                        "run_id": run_id,
                        "created_at": utc_now(),
                        "url": url,
                        "status": result.status,
                        "elapsed_seconds": round(result.elapsed, 3),
                        "detail_json": json.dumps({"error": result.error, "depth": depth, "origin": origin}, sort_keys=True),
                    },
                )
                if result.status == "ok":
                    print(f"crawled [{len(fetched)}/{args.max_pages}] {url} ({round(result.elapsed, 2)}s)")
                else:
                    print(f"failed  [{len(fetched)}/{args.max_pages}] {url}: {result.error}", file=sys.stderr)
                if result.status == "ok" and depth < args.max_depth:
                    for link in result.links:
                        if link in seen:
                            continue
                        if not getattr(args, "include_external", False) and source and normalize_url(source) and not same_site(link, source):
                            continue
                        queue.append((link, depth + 1, "site-link"))

    for idx, result in enumerate(fetched, start=1):
        source_id = f"source-{sha(result.url)}"
        raw_path = raw_dir / f"{idx:03d}-{slugify(result.title or result.url)}.md"
        body = f"# {result.title}\n\nSource: {result.url}\n\n{result.text}\n"
        raw_path.write_text(body, encoding="utf-8")
        source_row = {
            "id": source_id,
            "run_id": run_id,
            "url": result.url,
            "title": result.title,
            "axis": "keyword" if keywords else "site",
            "tier": "primary",
            "raw_path": str(raw_path),
            "status": result.status,
            "error": result.error,
            "elapsed_seconds": round(result.elapsed, 3),
            "discovered_by": "crawl",
            "score": score_page(result, keywords),
        }
        db.insert("sources", source_row)
        source_rows.append(source_row)
        if result.status != "ok" or not result.text.strip():
            continue
        doc_id = f"doc-{sha(result.url + result.text)}"
        chunks = chunk_text(result.text, getattr(args, "chunk_words", 450), getattr(args, "chunk_overlap", 70))
        doc_row = {
            "id": doc_id,
            "run_id": run_id,
            "source_id": source_id,
            "title": result.title,
            "path": str(raw_path),
            "content_sha256": hashlib.sha256(result.text.encode("utf-8", errors="ignore")).hexdigest(),
            "word_count": word_count(result.text),
            "chunk_count": len(chunks),
        }
        db.insert("documents", doc_row)
        doc_rows.append(doc_row)
        emit_embedding(db, run_id, "document", doc_id, result.text[:20_000])
        for pos, chunk in enumerate(chunks):
            # Content-addressed chunk identity: identical content collapses to one
            # node + one embedding across documents/positions. Provenance (which doc
            # contained the chunk, and where) is preserved as doc->chunk containment
            # edges, so dedup is lossless. Mirrors lgwks_substrate_run.build_run — one
            # canonical dedup primitive, not a parallel scheme.
            content_sha = hashlib.sha256(chunk.encode("utf-8", errors="ignore")).hexdigest()
            chunk_id = f"chunk-{content_sha[:16]}"
            occurrence_edge = {
                "id": f"edge-{sha(doc_id + chunk_id)}",
                "run_id": run_id,
                "from_id": doc_id,
                "to_id": chunk_id,
                "kind": "contains",
                "weight": 1.0,
                "evidence": None,
                "metadata_json": json.dumps({"position": pos}, sort_keys=True),
            }
            db.insert("edges", occurrence_edge)
            edge_rows.append(occurrence_edge)
            if content_sha in seen_chunk_hashes:
                # Duplicate content this run: provenance recorded via the edge above;
                # do not re-insert the row or re-embed identical content.
                continue
            seen_chunk_hashes.add(content_sha)
            stype = semantic_type_scores(chunk)
            chunk_row = {
                "id": chunk_id,
                "run_id": run_id,
                "document_id": doc_id,
                "source_id": source_id,
                "position": pos,
                "text": chunk,
                "content_sha256": content_sha,
                "word_count": word_count(chunk),
                "semantic_type_json": json.dumps(stype, sort_keys=True),
            }
            db.insert("chunks", chunk_row)
            chunk_rows.append(chunk_row)
            vector = deterministic_embedding(chunk)
            chunk_vectors[chunk_id] = vector
            chunk_texts[chunk_id] = chunk
            chunk_to_doc[chunk_id] = doc_id
            emit_embedding(db, run_id, "chunk", chunk_id, chunk)

    terms = concept_terms((row["text"] for row in chunk_rows), getattr(args, "max_terms", 80))
    for term, weight in terms.items():
        node_id = f"term-{sha(term)}"
        metadata = {
            "term": term,
            "semantic_type": max(semantic_type_scores(term), key=semantic_type_scores(term).get),
            "source": "deterministic-ngram",
        }
        row = {
            "id": node_id,
            "run_id": run_id,
            "kind": "concept",
            "label": term,
            "weight": float(weight),
            "metadata_json": json.dumps(metadata, sort_keys=True),
        }
        db.insert("nodes", row)
        node_rows.append(row)
        emit_embedding(db, run_id, "understanding-node", node_id, term)

    term_ids = {row["label"]: row["id"] for row in node_rows}
    for chunk_id, text in chunk_texts.items():
        present = [term for term in term_ids if term in text.lower()]
        for term in present[:12]:
            edge_id = f"edge-{sha(chunk_id + term)}"
            row = {
                "id": edge_id,
                "run_id": run_id,
                "from_id": chunk_id,
                "to_id": term_ids[term],
                "kind": "mentions",
                "weight": float(text.lower().count(term)),
                "evidence": text[:240],
                "metadata_json": json.dumps({"fusion_signal": "lexical"}, sort_keys=True),
            }
            db.insert("edges", row)
            edge_rows.append(row)

    chunk_items = list(chunk_vectors.items())
    for i, (left_id, left_vec) in enumerate(chunk_items):
        for right_id, right_vec in chunk_items[i + 1:i + 80]:
            if chunk_to_doc.get(left_id) == chunk_to_doc.get(right_id):
                continue
            score = cosine(left_vec, right_vec)
            if score >= getattr(args, "similarity_threshold", 0.72):
                edge_id = f"edge-{sha(left_id + right_id)}"
                row = {
                    "id": edge_id,
                    "run_id": run_id,
                    "from_id": left_id,
                    "to_id": right_id,
                    "kind": "late_fusion_similarity",
                    "weight": round(score, 4),
                    "evidence": None,
                    "metadata_json": json.dumps({"fusion_signal": "hash_embedding", "threshold": getattr(args, "similarity_threshold", 0.72)}, sort_keys=True),
                }
                db.insert("edges", row)
                edge_rows.append(row)

    compress_limit = getattr(args, "compress_limit", 96)
    if len(node_rows) > compress_limit:
        for row in sorted(node_rows, key=lambda r: r["weight"])[: len(node_rows) - compress_limit]:
            label = json.loads(row["metadata_json"]).get("semantic_type", "compressed")
            compressed = {
                "id": f"compressed-{sha(run_id + row['id'])}",
                "run_id": run_id,
                "reason": "compute_limit_low_weight_concept",
                "source_node_json": json.dumps(row, sort_keys=True),
                "compressed_label": label,
                "metadata_json": json.dumps({"compress_limit": compress_limit}, sort_keys=True),
            }
            db.insert("compressed_nodes", compressed)

    frontier_terms = [term for term, _ in terms.most_common(20)]
    after_id = make_snapshot(db, run_id, "after-crawl", list(queue), terms)
    coverage = min(1.0, len(doc_rows) / max(1, args.max_pages))
    uncertainty = round(1.0 - coverage + (0.15 if warnings else 0), 4)
    understanding_summary = (
        f"Mapped {len(doc_rows)} documents and {len(chunk_rows)} chunks into {len(node_rows)} concept nodes. "
        f"Dominant terms: {', '.join(frontier_terms[:8])}."
    )
    understanding_id = f"understanding-{sha(run_id + understanding_summary)}"
    understanding_schema = {
        "research_understanding": {
            "tracked_separately_from_questions": True,
            "late_fusion_signals": ["lexical", "hash_embedding", "temporal_snapshot"],
            "semantic_types": sorted(SEMANTIC_TYPES),
        }
    }
    db.insert(
        "understandings",
        {
            "id": understanding_id,
            "run_id": run_id,
            "created_at": utc_now(),
            "scope": "crawl",
            "before_snapshot_id": before_id,
            "after_snapshot_id": after_id,
            "summary": understanding_summary,
            "coverage_score": round(coverage, 4),
            "uncertainty_score": uncertainty,
            "evidence_json": json.dumps({"top_terms": frontier_terms[:20], "source_count": len(source_rows)}, sort_keys=True),
            "schema_json": json.dumps(understanding_schema, sort_keys=True),
        },
    )
    emit_embedding(db, run_id, "research-understanding", understanding_id, understanding_summary)

    drill_keywords = keywords or [slugify(source or run_name)]
    for keyword in drill_keywords:
        drill_id = f"drill-{sha(run_id + keyword)}"
        db.insert(
            "drills",
            {
                "id": drill_id,
                "run_id": run_id,
                "keyword": keyword,
                "state": "complete" if coverage >= 0.95 else "frontier-open",
                "target_pages": args.max_pages,
                "crawled_pages": len(doc_rows),
                "ask_count": 3,
                "compute_estimate_seconds": estimate,
                "metadata_json": json.dumps({"coverage_score": coverage, "uncertainty_score": uncertainty}, sort_keys=True),
            },
        )
        questions = next_questions(keyword, frontier_terms, source_rows, uncertainty)
        for ask_index, (question, thought, gain) in enumerate(questions, start=1):
            qid = f"question-{sha(drill_id + str(ask_index) + question)}"
            db.insert(
                "question_events",
                {
                    "id": qid,
                    "run_id": run_id,
                    "created_at": utc_now(),
                    "drill_id": drill_id,
                    "ask_index": ask_index,
                    "question": question,
                    "what_were_you_thinking": thought,
                    "expected_information_gain": gain,
                    "answered": 0,
                    "answer": None,
                },
            )
            emit_embedding(db, run_id, "question-trace", qid, f"{question}\n{thought}")

    db.conn.commit()
    write_jsonl(records_dir / "sources.jsonl", source_rows)
    write_jsonl(records_dir / "documents.jsonl", doc_rows)
    write_jsonl(records_dir / "chunks.jsonl", chunk_rows)
    write_jsonl(records_dir / "nodes.jsonl", node_rows)
    write_jsonl(records_dir / "edges.jsonl", edge_rows)
    write_gnn_exports(gnn_dir, run_id, node_rows, edge_rows, db)
    write_graph(graph_dir, run_id, node_rows, edge_rows)
    report_path = write_report(run_dir, run_id, estimate, understanding_summary, terms, source_rows, doc_rows, edge_rows, warnings)

    manifest = {
        "run_id": run_id,
        "name": run_name,
        "created_at": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "prompt": getattr(args, "prompt", ""),
        "keywords": keywords,
        "estimated_compute_seconds": estimate,
        "artifacts": {
            "root": str(run_dir),
            "database": str(db.path),
            "report": str(report_path),
            "mermaid": str(graph_dir / "research-map.mmd"),
            "html": str(graph_dir / "research-map.html"),
            "gnn": str(gnn_dir),
        },
        "counts": {
            "sources": len(source_rows),
            "documents": len(doc_rows),
            "chunks": len(chunk_rows),
            "nodes": len(node_rows),
            "edges": len(edge_rows),
            "questions": len(drill_keywords) * 3,
        },
        "config": config,
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    db.close()
    print(f"run: {run_id}")
    print(f"report: {report_path}")
    print(f"db: {db_dir / 'research.sqlite'}")
    return 0


def next_questions(keyword: str, frontier_terms: list[str], sources: list[dict], uncertainty: float) -> list[tuple[str, str, float]]:
    top = ", ".join(frontier_terms[:6]) or keyword
    failed = [s["url"] for s in sources if s["status"] != "ok"]
    missing_evidence = "failed or thin pages" if failed else "unlinked high-weight concepts"
    return [
        (
            f"What concrete mechanism links `{keyword}` to the highest-weight concepts ({top})?",
            "The map has nouns; this question tries to force typed edges, mutators, and causal transitions.",
            round(0.35 + uncertainty * 0.3, 3),
        ),
        (
            f"Which source would falsify or sharply constrain the current `{keyword}` interpretation?",
            f"Research understanding and confidence must diverge when evidence is missing; current weak spot: {missing_evidence}.",
            round(0.3 + uncertainty * 0.25, 3),
        ),
        (
            f"What should be crawled next to separate implementation facts from naming or marketing around `{keyword}`?",
            "The next drill should bias toward standards, code, benchmarks, and failure reports rather than summary pages.",
            round(0.25 + uncertainty * 0.2, 3),
        ),
    ]


def write_gnn_exports(gnn_dir: Path, run_id: str, nodes: list[dict], edges: list[dict], db: JarvisDB):
    with (gnn_dir / "nodes.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "label", "kind", "weight"])
        for row in nodes:
            writer.writerow([row["id"], row["label"], row["kind"], row["weight"]])
    with (gnn_dir / "edges.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source", "target", "kind", "weight"])
        for row in edges:
            writer.writerow([row["from_id"], row["to_id"], row["kind"], row["weight"]])
    features = []
    for row in db.conn.execute("select target_id, scope, dimensions, vector_json from embeddings where run_id=?", (run_id,)):
        if row["scope"] in {"understanding-node", "research-understanding", "question-trace"}:
            features.append({"id": row["target_id"], "scope": row["scope"], "dimensions": row["dimensions"], "vector": json.loads(row["vector_json"])})
    write_jsonl(gnn_dir / "features.jsonl", features)
    (gnn_dir / "tensor-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "node_file": "nodes.csv",
                "edge_file": "edges.csv",
                "feature_file": "features.jsonl",
                "fusion": "late lexical + deterministic embedding + temporal snapshot",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (gnn_dir / "README.md").write_text(
        "# GNN Export\n\nNodes and edges are deterministic crawler outputs. `features.jsonl` stores separately vectorized understanding and question-trace records.\n",
        encoding="utf-8",
    )


def write_graph(graph_dir: Path, run_id: str, nodes: list[dict], edges: list[dict]):
    top_nodes = sorted(nodes, key=lambda r: r["weight"], reverse=True)[:40]
    allowed = {row["id"] for row in top_nodes}
    lines = ["graph TD"]
    for row in top_nodes:
        label = row["label"].replace('"', "'")
        lines.append(f'  {row["id"].replace("-", "_")}["{label}"]')
    for row in sorted(edges, key=lambda r: r["weight"], reverse=True)[:120]:
        if row["from_id"] in allowed and row["to_id"] in allowed:
            lines.append(f'  {row["from_id"].replace("-", "_")} -->|{row["kind"]}| {row["to_id"].replace("-", "_")}')
    mermaid = "\n".join(lines) + "\n"
    (graph_dir / "research-map.mmd").write_text(mermaid, encoding="utf-8")
    (graph_dir / "research-map.html").write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(run_id)} research map</title>
<script type="module">import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs'; mermaid.initialize({{startOnLoad:true}});</script>
<pre class="mermaid">
{html.escape(mermaid)}
</pre>
""",
        encoding="utf-8",
    )


def write_report(run_dir: Path, run_id: str, estimate: float, summary: str, terms: Counter[str], sources: list[dict], docs: list[dict], edges: list[dict], warnings: list[str]) -> Path:
    path = run_dir / "REPORT.md"
    failed = [s for s in sources if s["status"] != "ok"]
    lines = [
        f"# Jarvis Crawl Report: {run_id}",
        "",
        f"- Created: {utc_now()}",
        f"- Estimated compute: {estimate}s ({round(estimate / 60, 2)} min)",
        f"- Sources attempted: {len(sources)}",
        f"- Documents ingested: {len(docs)}",
        f"- Edges emitted: {len(edges)}",
        f"- Schema: `{SCHEMA_VERSION}`",
        "",
        "## Understanding",
        "",
        summary,
        "",
        "## Top Concepts",
        "",
    ]
    lines.extend(f"- `{term}` - {weight}" for term, weight in terms.most_common(30))
    lines.extend(["", "## Question Trace", "", "Three deterministic frontier questions are stored in `question_events` and vectorized separately from research-understanding rows."])
    if failed:
        lines.extend(["", "## Crawl Failures", ""])
        lines.extend(f"- `{s['url']}`: {s['error']}" for s in failed)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", "## Interpretation Boundary", "", "This is a deterministic map, not a claim verifier. Promotion still requires validator or human acceptance."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def remap_db_command(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    db_path = run_dir / "db" / "research.sqlite"
    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")
    db = JarvisDB(db_path)
    db.init()
    run_id_row = db.conn.execute("select run_id from runs limit 1").fetchone()
    run_id = run_id_row["run_id"] if run_id_row else run_dir.name
    terms = Counter()
    chunk_rows = db.conn.execute("select id, text from chunks where run_id=?", (run_id,)).fetchall()
    for row in chunk_rows:
        emit_embedding(db, run_id, "chunk", row["id"], row["text"])
        terms.update(concept_terms([row["text"]], 20))
    before = make_snapshot(db, run_id, "remap-before", [], terms)
    after = make_snapshot(db, run_id, "remap-after", [], terms)
    summary = f"Remapped legacy DB to {SCHEMA_VERSION}; separated research understanding and question trace schemas."
    understanding_id = f"understanding-{sha(run_id + summary)}"
    db.insert(
        "understandings",
        {
            "id": understanding_id,
            "run_id": run_id,
            "created_at": utc_now(),
            "scope": "remap",
            "before_snapshot_id": before,
            "after_snapshot_id": after,
            "summary": summary,
            "coverage_score": 1.0 if chunk_rows else 0.0,
            "uncertainty_score": 0.0 if chunk_rows else 1.0,
            "evidence_json": json.dumps({"legacy_chunks": len(chunk_rows)}, sort_keys=True),
            "schema_json": json.dumps({"schema_version": SCHEMA_VERSION, "remapped": True}, sort_keys=True),
        },
    )
    emit_embedding(db, run_id, "research-understanding", understanding_id, summary)
    db.close()
    print(f"remapped: {db_path}")
    return 0


def add_parser(sub):
    """Integrate Jarvis with a subparser."""
    j = sub.add_parser("jarvis", help="legacy deterministic research graph crawler")
    js = j.add_subparsers(dest="jarvis_cmd", required=True)
    
    crawl = js.add_parser("crawl", help="crawl a website or keyword frontier")
    crawl.add_argument("source", nargs="?", help="website URL or keyword seed")
    crawl.add_argument("keyword_terms", nargs="*", help="additional keywords")
    crawl.add_argument("--keywords", help="newline/comma/semicolon-delimited keywords")
    crawl.add_argument("--prompt", default="map the machine-state understanding", help="research intent")
    crawl.add_argument("--name", help="run name prefix")
    crawl.add_argument("--max-pages", type=int, default=12)
    crawl.add_argument("--max-depth", type=int, default=2)
    crawl.add_argument("--workers", type=int, default=2)
    crawl.add_argument("--include-external", action="store_true")
    crawl.add_argument("--search-expansion", action="store_true")
    crawl.add_argument("--chunk-words", type=int, default=450)
    crawl.add_argument("--chunk-overlap", type=int, default=70)
    crawl.add_argument("--max-terms", type=int, default=120)
    crawl.add_argument("--compress-limit", type=int, default=96)
    crawl.add_argument("--similarity-threshold", type=float, default=0.72)
    crawl.add_argument("--estimate-only", action="store_true")
    crawl.set_defaults(func=crawl_command)
    
    remap = js.add_parser("remap-db", help="upgrade run database")
    remap.add_argument("run_dir")
    remap.set_defaults(func=remap_db_command)
