"""lgwks_substrate — deterministic crawl+vector substrate for files, folders, repos, and sites.

This is the CLI-first knowledge layer that AI agents should consume instead of scraping ad hoc.
It produces replayable artifacts: clean chunks, STEM-lean facts, semantic vectors, and a local graph.

Runtime principles:
  - generation-free execution path
  - local embeddings by default (Qwen Eye via Ollama or deterministic fallback if explicitly requested)
  - optional remote multimodal embeddings as an explicit second provider
  - host-scoped browser sessions for authenticated sites
  - stable IDs + jsonl/sqlite artifacts for downstream AI or human query layers
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
import urllib.parse
from collections import Counter, deque
from datetime import date
from pathlib import Path
from typing import Any

import lgwks_browser
import lgwks_entity_graph as entity_graph
import lgwks_run
import lgwks_sqlite
from lgwks_html import html_to_markdown

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "substrate"
GLOBAL_ROOT = ROOT / "store" / "substrate-global"
GLOBAL_FACT_DB = GLOBAL_ROOT / "fact_vectors.db"


class EmbeddingProviderUnavailable(RuntimeError):
    """Raised when an explicitly requested semantic embedding provider cannot produce vectors."""


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
AUTH_GATE_RE = re.compile(
    r"\b("
    r"sign in|log in|login|password|multi-factor|two-factor|passkey|touch id|face id|verify identity|"
    r"one-time code|magic link|otp|captcha|cloudflare|checking your browser|verify you are human|"
    r"access denied|enable javascript|challenge|bot detection|unusual traffic"
    r")\b",
    re.I,
)
STRONG_AUTH_GATE_RE = re.compile(
    r"\b("
    r"sign in|log in|password|multi-factor|two-factor|passkey|touch id|face id|verify identity|"
    r"one-time code|magic link|otp|captcha|cloudflare|checking your browser|verify you are human|"
    r"go to sign in|access denied|enable javascript|challenge|bot detection|unusual traffic"
    r")\b",
    re.I,
)
UPCOMING_EFFECTIVE_DATE = date(2026, 6, 15)
VERSION_BUCKETS = ("Current", "Upcoming", "Previous")
PREVIOUS_VERSION_RE = re.compile(r"\bV(?:3[0-5]|[12]\d)\b", re.I)


def _parse_iso_date(value: str) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _version_bucket(text: str, *, as_of: date) -> str:
    low = text.lower()
    if "v36" in low:
        return "Upcoming" if as_of < UPCOMING_EFFECTIVE_DATE else "Current"
    if "upcoming" in low or "future" in low or "effective june 15, 2026" in low or "effective 2026-06-15" in low:
        return "Upcoming"
    if "previous" in low or "prior" in low or "retired" in low or "legacy" in low or "deprecated" in low or "superseded" in low:
        return "Previous"
    if PREVIOUS_VERSION_RE.search(text):
        return "Previous"
    return "Current"


def _bucket_facts(facts: list[dict[str, Any]], *, as_of: date, limit: int) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in VERSION_BUCKETS}
    sorted_facts = sorted(
        facts,
        key=lambda row: (float(row.get("fact_score") or 0), row.get("fact_id", "")),
        reverse=True,
    )
    for row in sorted_facts:
        text = str(row.get("fact_text", ""))
        if not text.strip():
            continue
        bucket = _version_bucket(text, as_of=as_of)
        if len(buckets[bucket]) >= limit:
            continue
        buckets[bucket].append({
            "fact_id": row.get("fact_id", ""),
            "chunk_id": row.get("chunk_id", ""),
            "document_id": row.get("document_id", ""),
            "fact_score": row.get("fact_score", 0),
            "chunk_kind": row.get("chunk_kind", ""),
            "text": text,
        })
    return buckets


def _frontier_status_counts(frontier: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in frontier:
        status = str(row.get("status", "") or "unknown")
        counts[status] += 1
    return dict(counts)


def _policy_pack_gaps(manifest: dict[str, Any], facts: list[dict[str, Any]], frontier: list[dict[str, Any]], buckets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
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


def _looks_like_login_gate(title: str, text: str, url: str) -> bool:
    low_url = url.lower()
    if any(term in low_url for term in ("/login", "/signin", "signin", "authenticate", "sso")):
        return True
    title_sample = title.strip()
    if title_sample and AUTH_GATE_RE.search(title_sample):
        return True
    sample = text[:2500].strip()
    if STRONG_AUTH_GATE_RE.search(sample):
        return True
    # A body that merely mentions "login" can be authenticated content
    # ("access these services using your login"). Treat bare login/logins as
    # a gate only when repeated or paired with an obvious form/challenge term.
    weak_hits = re.findall(r"\blogins?\b", sample, flags=re.I)
    return len(weak_hits) >= 2 and bool(re.search(r"\b(username|user id|password|submit|remote logins?)\b", sample, re.I))


def _crawl_site(
    base_url: str,
    *,
    max_pages: int,
    max_depth: int,
    browser_engine: str,
    login_if_needed: bool,
    login_url: str,
    success_selector: str | None,
    max_auto_bypass_attempts: int,
    max_auth_handoffs: int,
    click_discovery: bool,
    max_clicks_per_page: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed = urllib.parse.urlparse(base_url)
    base_host = parsed.hostname or ""
    seen: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque([(base_url, 0, "seed")])
    docs: list[dict[str, Any]] = []
    frontier: list[dict[str, Any]] = []
    blocker_retries_used = 0
    url_attempts: Counter[str] = Counter()
    auth_handoffs = 0
    while queue and len(docs) < max_pages:
        url, depth, discovered_by = queue.popleft()
        clean = urllib.parse.urldefrag(url)[0]
        if not clean or clean in seen:
            continue
        seen.add(clean)
        url_attempts[clean] += 1
        attempt = url_attempts[clean]
        if not lgwks_browser._remote_allowed(clean):
            frontier.append({"url": clean, "depth": depth, "status": "blocked", "discovered_by": discovered_by})
            continue
        rendered = lgwks_browser.render(
            clean,
            max_chars=120_000,
            use_session=True,
            wait_ms=min(9000, 2500 + ((attempt - 1) * 2500)),
            with_html=True,
            browser_engine=browser_engine,
        )
        if not rendered.get("ok") or not rendered.get("html"):
            if blocker_retries_used < max_auto_bypass_attempts:
                blocker_retries_used += 1
                seen.discard(clean)
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "retrying_blocker",
                    "reason": rendered.get("reason", ""),
                    "attempt": attempt,
                    "discovered_by": discovered_by,
                })
                queue.appendleft((clean, depth, discovered_by))
                continue
            frontier.append({
                "url": clean, "depth": depth, "status": "error", "reason": rendered.get("reason", ""),
                "discovered_by": discovered_by,
            })
            continue
        markdown, title, links = html_to_markdown(rendered["html"], clean)
        if login_if_needed and _looks_like_login_gate(title or "", markdown or rendered.get("text", ""), clean):
            if blocker_retries_used < max_auto_bypass_attempts:
                blocker_retries_used += 1
                seen.discard(clean)
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "retrying_gate",
                    "reason": "advanced bypass retry before human handoff",
                    "attempt": attempt,
                    "discovered_by": discovered_by,
                })
                queue.appendleft((clean, depth, discovered_by))
                continue
            if auth_handoffs >= max_auth_handoffs:
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "auth_exhausted",
                    "reason": "auth handoff limit reached",
                    "discovered_by": discovered_by,
                })
                continue
            auth_target = login_url or clean
            # //why: headed WebKit on macOS often fails to surface a visible window,
            # making human auth completion impossible. Chromium headed is reliable.
            manual_engine = "chromium"
            login_result = lgwks_browser.save_session(
                auth_target,
                success_selector=success_selector,
                browser_engine=manual_engine,
                manual=True,
            )
            auth_handoffs += 1
            if not login_result.get("ok"):
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "auth_failed",
                    "reason": login_result.get("reason", ""),
                    "discovered_by": discovered_by,
                })
                continue
            # Verify the saved session actually resolves the login gate in headless mode.
            # Some sites (financial portals, Cloudflare) reject headless even with valid cookies,
            # so we verify once rather than looping infinitely.
            verify = lgwks_browser.render(
                clean,
                max_chars=120_000,
                use_session=True,
                wait_ms=5000,
                with_html=True,
                browser_engine=browser_engine,
            )
            if verify.get("ok") and verify.get("html"):
                v_md, v_title, _ = html_to_markdown(verify["html"], clean)
                if not _looks_like_login_gate(v_title or "", v_md or verify.get("text", ""), clean):
                    seen.discard(clean)
                    queue.appendleft((clean, depth, discovered_by))
                    frontier.append({
                        "url": clean,
                        "depth": depth,
                        "status": "auth_verified",
                        "reason": login_result.get("reason", ""),
                        "discovered_by": discovered_by,
                    })
                    continue
            frontier.append({
                "url": clean,
                "depth": depth,
                "status": "auth_saved_but_failed",
                "reason": (
                    "session saved but headless render still shows a login gate; "
                    "site may block headless browsers or auth was incomplete — "
                    "try omitting --webkit, or capture the session in a normal browser and copy cookies"
                ),
                "discovered_by": discovered_by,
            })
            continue
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
        if click_discovery:
            click_rows = lgwks_browser.discover_clicks(
                clean,
                max_clicks=max_clicks_per_page,
                wait_ms=2500,
                browser_engine=browser_engine,
            )
            for row in click_rows:
                cand = row.get("candidate", {})
                label = cand.get("text") or cand.get("href") or "click"
                final_url = urllib.parse.urldefrag(row.get("final_url") or clean)[0]
                status = row.get("status", "error")
                frontier.append({
                    "url": final_url or clean,
                    "depth": depth + 1,
                    "status": f"click_{status}",
                    "reason": row.get("reason", label),
                    "discovered_by": clean,
                    "links_found": 0,
                })
                if status != "ok" or not row.get("html"):
                    continue
                c_md, c_title, c_links = html_to_markdown(row["html"], final_url or clean)
                if login_if_needed and _looks_like_login_gate(c_title or "", c_md or row.get("text", ""), final_url or clean):
                    frontier.append({
                        "url": final_url or clean,
                        "depth": depth + 1,
                        "status": "click_gate",
                        "reason": label,
                        "discovered_by": clean,
                        "links_found": len(c_links),
                    })
                    continue
                docs.append({
                    "source": final_url or f"{clean}#click-{cand.get('id', '')}",
                    "title": c_title or label,
                    "text": c_md or row.get("text", ""),
                    "html_len": row.get("html_len", 0),
                    "depth": depth + 1,
                    "discovered_by": clean,
                })
                final_host = urllib.parse.urlparse(final_url).hostname or ""
                if final_url and final_host == base_host and final_url not in seen:
                    queue.append((final_url, depth + 1, clean))
                if len(docs) >= max_pages:
                    break
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


def _emit_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def _crawl_map(frontier: list[dict[str, Any]]) -> dict[str, Any]:
    # frontier is append-only: same URL may appear multiple times (retry → auth → ok).
    # Take the LAST entry per URL as the canonical state; the graph/embed layer reconciles.
    url_state: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    for row in frontier:
        url = row.get("url", "")
        if url:
            url_state[url] = {
                "url": url,
                "depth": row.get("depth", 0),
                "status": row.get("status", ""),
                "links_found": row.get("links_found", 0),
            }
        parent = row.get("discovered_by", "")
        if parent and parent not in {"seed", "filesystem"} and url:
            key = (parent, url)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"from": parent, "to": url})
    return {"schema": "lgwks.substrate.crawl_map.v0", "nodes": list(url_state.values()), "edges": edges}


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _fact_sentences(text: str, threshold: float) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        s = _fact_score(sentence)
        if s >= threshold or NUMERIC_RE.search(sentence) or REF_RE.search(sentence) or CODE_RE.search(sentence):
            clean = sentence.strip()
            if clean and clean not in seen:
                seen.add(clean)
                out.append(clean)
    return out


def _build_index_db(
    path: Path,
    *,
    source_rows: list[dict[str, Any]],
    doc_rows: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
    fact_rows: list[dict[str, Any]],
    vector_rows: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
) -> None:
    conn = lgwks_sqlite.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS sources;
        DROP TABLE IF EXISTS documents;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS facts;
        DROP TABLE IF EXISTS vectors;
        DROP TABLE IF EXISTS frontier;
        DROP TABLE IF EXISTS chunk_fts;
        DROP TABLE IF EXISTS fact_fts;

        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            discovered_by TEXT,
            depth INTEGER
        );
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY,
            source_id TEXT,
            title TEXT,
            source TEXT,
            word_count INTEGER
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT,
            source TEXT,
            url TEXT,
            text TEXT,
            stem_text TEXT,
            hash TEXT,
            fact_score REAL,
            chunk_kind TEXT,
            position INTEGER
        );
        CREATE TABLE facts (
            fact_id TEXT PRIMARY KEY,
            chunk_id TEXT,
            document_id TEXT,
            fact_text TEXT,
            fact_score REAL,
            chunk_kind TEXT
        );
        CREATE TABLE vectors (
            vector_id TEXT PRIMARY KEY,
            chunk_id TEXT,
            document_id TEXT,
            provider TEXT,
            is_semantic INTEGER,
            dims INTEGER,
            vector_text TEXT,
            vector_json TEXT,
            fact_score REAL,
            chunk_kind TEXT
        );
        CREATE TABLE frontier (
            url TEXT,
            depth INTEGER,
            status TEXT,
            reason TEXT,
            discovered_by TEXT,
            links_found INTEGER
        );
        CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id, text, stem_text, source, tokenize='porter unicode61');
        CREATE VIRTUAL TABLE fact_fts USING fts5(fact_id, fact_text, chunk_kind, tokenize='porter unicode61');
        """
    )
    cur.executemany(
        "INSERT INTO sources(source_id, source, title, discovered_by, depth) VALUES(?,?,?,?,?)",
        [(r["source_id"], r["source"], r["title"], r["discovered_by"], r["depth"]) for r in source_rows],
    )
    cur.executemany(
        "INSERT INTO documents(document_id, source_id, title, source, word_count) VALUES(?,?,?,?,?)",
        [(r["document_id"], r["source_id"], r["title"], r["source"], r["word_count"]) for r in doc_rows],
    )
    cur.executemany(
        "INSERT INTO chunks(chunk_id, document_id, source, url, text, stem_text, hash, fact_score, chunk_kind, position) VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["chunk_id"], r["document_id"], r["source"], r["url"], r["text"], r["stem_text"], r["hash"], r["fact_score"], r["chunk_kind"], r["position"]) for r in chunk_rows],
    )
    cur.executemany(
        "INSERT INTO facts(fact_id, chunk_id, document_id, fact_text, fact_score, chunk_kind) VALUES(?,?,?,?,?,?)",
        [(r["fact_id"], r["chunk_id"], r["document_id"], r["fact_text"], r["fact_score"], r["chunk_kind"]) for r in fact_rows],
    )
    cur.executemany(
        "INSERT INTO vectors(vector_id, chunk_id, document_id, provider, is_semantic, dims, vector_text, vector_json, fact_score, chunk_kind) VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["vector_id"], r["chunk_id"], r["document_id"], r["provider"], int(bool(r["is_semantic"])), r["dims"], r["vector_text"], _json_cell(r["vector"]), r["fact_score"], r["chunk_kind"]) for r in vector_rows],
    )
    cur.executemany(
        "INSERT INTO frontier(url, depth, status, reason, discovered_by, links_found) VALUES(?,?,?,?,?,?)",
        [(r.get("url", ""), r.get("depth", 0), r.get("status", ""), r.get("reason", ""), r.get("discovered_by", ""), r.get("links_found", 0)) for r in frontier if r.get("url")],
    )
    cur.executemany(
        "INSERT INTO chunk_fts(chunk_id, text, stem_text, source) VALUES(?,?,?,?)",
        [(r["chunk_id"], r["text"], r["stem_text"], r["source"]) for r in chunk_rows],
    )
    cur.executemany(
        "INSERT INTO fact_fts(fact_id, fact_text, chunk_kind) VALUES(?,?,?)",
        [(r["fact_id"], r["fact_text"], r["chunk_kind"]) for r in fact_rows],
    )
    conn.commit()
    conn.close()


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _upsert_global_fact_vectors(
    path: Path,
    *,
    run_id: str,
    fact_vectors: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = lgwks_sqlite.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS fact_vectors (
            fact_hash TEXT PRIMARY KEY,
            fact_text TEXT NOT NULL,
            provider TEXT NOT NULL,
            dims INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            first_seen_run TEXT NOT NULL,
            last_seen_run TEXT NOT NULL,
            seen_count INTEGER NOT NULL,
            max_fact_score REAL NOT NULL,
            chunk_kind TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS fact_vectors_fts USING fts5(
            fact_hash, fact_text, chunk_kind, tokenize='porter unicode61'
        );
        """
    )
    for row in fact_vectors:
        fact_hash = row["fact_hash"]
        current = cur.execute(
            "SELECT seen_count, max_fact_score FROM fact_vectors WHERE fact_hash = ?",
            (fact_hash,),
        ).fetchone()
        if current:
            seen_count, max_fact_score = current
            cur.execute(
                """
                UPDATE fact_vectors
                SET last_seen_run = ?, seen_count = ?, max_fact_score = ?, provider = ?, dims = ?, vector_json = ?, chunk_kind = ?
                WHERE fact_hash = ?
                """,
                (
                    run_id,
                    int(seen_count) + 1,
                    max(float(max_fact_score), float(row["fact_score"])),
                    row["provider"],
                    row["dims"],
                    _json_cell(row["vector"]),
                    row["chunk_kind"],
                    fact_hash,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO fact_vectors(
                    fact_hash, fact_text, provider, dims, vector_json, first_seen_run, last_seen_run,
                    seen_count, max_fact_score, chunk_kind
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fact_hash,
                    row["fact_text"],
                    row["provider"],
                    row["dims"],
                    _json_cell(row["vector"]),
                    run_id,
                    run_id,
                    1,
                    row["fact_score"],
                    row["chunk_kind"],
                ),
            )
            cur.execute(
                "INSERT INTO fact_vectors_fts(fact_hash, fact_text, chunk_kind) VALUES(?,?,?)",
                (fact_hash, row["fact_text"], row["chunk_kind"]),
            )
    conn.commit()
    conn.close()



def _load_run_manifest(run_dir: Path) -> dict[str, Any]:
    """Load manifest.json from a substrate run directory. Returns empty dict if missing."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stored_vector_space(run_dir: Path) -> dict[str, Any]:
    """Return the stored vector-space metadata for a run.

    Source of truth priority:
    1. manifest.json → vector_space field (stable, canonical).
    2. Fallback: inspect vectors.jsonl for a homogeneous single provider.
    3. If ambiguous or missing, returns {"ambiguous": True, "error": <reason>}.
    """
    manifest = _load_run_manifest(run_dir)
    if manifest and "vector_space" in manifest:
        return manifest["vector_space"]

    # Fallback: inspect vectors.jsonl directly.
    vector_file = run_dir / "vectors.jsonl"
    if not vector_file.exists():
        return {"ambiguous": True, "error": "no manifest.json and no vectors.jsonl found"}

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


def _provider_matches_vector_space(requested: str, canonical: str) -> bool:
    """Return whether a CLI provider token names the stored provider space.

    Build/query args use coarse provider selectors like "ollama" and "deterministic",
    while stored vectors record the resolved provider labels returned by lgwks_run.embed().
    Compare the identity of the resulting space, not the literal CLI token.
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


def _vector_search(
    run_dir: Path,
    text: str,
    limit: int,
    provider: str,
    model: str,
    *,
    force_cross_space: bool = False,
) -> dict[str, Any]:
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

    # --- Vector-space identity check -----------------------------------------
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

    # Determine the effective query provider/model.
    # Empty string means the user did not specify — resolve from stored space.
    user_specified_provider = bool(provider)  # True only when explicitly passed
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

        # Mismatch check: if the user explicitly asked for a different provider/model.
        requested_vs = {"provider": resolved_provider, "model": resolved_model}
        mismatch = (
            (user_specified_provider and not _provider_matches_vector_space(resolved_provider, canonical_provider)) or
            (user_specified_model and resolved_model and not _model_matches_vector_space(
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
                "requested_vector_space": requested_vs,
                "hint": "rerun without --embed-provider / --embed-model, or pass --force-cross-space",
            }
    else:
        requested_vs = {"provider": resolved_provider, "model": resolved_model}

    # --- Embed the query ------------------------------------------------------
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

    # --- Score stored vectors -------------------------------------------------
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
            login_if_needed=args.login_if_needed,
            login_url=args.login_url,
            success_selector=args.success_selector,
            max_auto_bypass_attempts=args.max_auto_bypass_attempts,
            max_auth_handoffs=args.max_auth_handoffs,
            click_discovery=bool(getattr(args, "click_discovery", False)),
            max_clicks_per_page=int(getattr(args, "max_clicks_per_page", 20)),
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
        source_id = f"src-{_sha(source_identity)[:16]}"
        doc_id = f"doc-{_sha(source_identity + doc['title'])[:16]}"
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
                for sentence in _fact_sentences(stem, args.fact_threshold):
                    fact_vec, fact_provider, fact_semantic = lgwks_run.embed(
                        sentence,
                        embed_on=True,
                        provider=args.embed_provider,
                        model=(args.embed_model or None),
                        dims=0,
                    )
                    if fact_vec is None and args.embed_provider == "apple-local":
                        raise EmbeddingProviderUnavailable(
                            f"apple-local provider unavailable for model {args.embed_model or 'default'}"
                        )
                    provider_counts[fact_provider] += 1
                    if fact_semantic:
                        semantic_vectors += 1
                    fact_vector_rows.append({
                        "fact_hash": _sha(sentence),
                        "fact_text": sentence,
                        "provider": fact_provider,
                        "dims": len(fact_vec or []),
                        "vector": fact_vec,
                        "fact_score": _fact_score(sentence),
                        "chunk_kind": chunk_kind,
                    })
            vector_text = stem or piece
            vector, provider, is_semantic = lgwks_run.embed(
                vector_text,
                embed_on=True,
                provider=args.embed_provider,
                model=(args.embed_model or None),
                dims=0,
            )
            if vector is None and args.embed_provider == "apple-local":
                raise EmbeddingProviderUnavailable(
                    f"apple-local provider unavailable for model {args.embed_model or 'default'}"
                )
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
        _emit_json(run_dir / "crawl_map.json", _crawl_map(frontier))

    db_path = run_dir / "graph.db"
    db = entity_graph.GraphDB(db_path)
    entity_graph.ingest_chunks(db, graph_input_rows)
    graph_json = run_dir / "graph.json"
    graph_mmd = run_dir / "graph.mmd"
    db.export_json(graph_json)
    db.export_mermaid(graph_mmd)
    stats = db.stats()
    db.close()
    index_db = run_dir / "substrate.db"
    _build_index_db(
        index_db,
        source_rows=source_rows,
        doc_rows=doc_rows,
        chunk_rows=chunk_rows,
        fact_rows=fact_rows,
        vector_rows=vector_rows,
        frontier=frontier,
    )
    _upsert_global_fact_vectors(GLOBAL_FACT_DB, run_id=run_id, fact_vectors=fact_vector_rows)

    # Derive canonical vector-space descriptor from the completed build.
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
        "project": args.project or _slug(Path(args.target).name),
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
        return _vector_search(
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
        db = entity_graph.GraphDB(run_dir / "graph.db")
        try:
            node, err = entity_graph._resolve_single_node(db, args.neighbors)
            if err:
                payload["graph_error"] = err
            else:
                payload["node"] = node
                payload["neighbors"] = db.neighbors(node["node_id"], limit=args.limit)
        finally:
            db.close()
    return payload


def baseline_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run).resolve()
    manifest = _load_run_manifest(run_dir)
    facts = _read_jsonl(run_dir / "facts.jsonl")
    frontier = _read_jsonl(run_dir / "frontier.jsonl")
    as_of = _parse_iso_date(args.as_of)
    buckets = _bucket_facts(facts, as_of=as_of, limit=args.limit)
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
        "frontier_status_counts": _frontier_status_counts(frontier),
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
        _emit_json(out_path, payload)
        payload["artifacts"]["baseline"] = str(out_path)
    return payload


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
    # Default is empty string (not supplied); code treats empty as 'resolve from run manifest'.
    # Explicit choices are still validated when supplied; empty string bypasses validation intentionally.
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
