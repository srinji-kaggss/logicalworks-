"""lgwks_ingest — the advanced web-crawler workflow, as ONE function an AI agent runs.

    ingest(url) -> a reproducible artifact tree

The whole pipeline, top to bottom, no hidden orchestration:

    URL
     └─ fetch  (bypass ladder — auth is the LAST resort, not the first)
     │     1. Googlebot UA + Referer: google.com   (paywalls serve full text to crawlers for SEO)
     │     2. stealth chromium                       (--disable-blink-features=AutomationControlled)
     │     3. human auth handoff + save session      (ONLY when every automated path fails)
     └─ harvest  (wget-style: every <img>/<video>/<source>/file link on the page)
     └─ classify each resource by Content-Type  ->  text | image | video | other
     └─ embed
     │     text   -> fact chunks -> det 256-d hash (always) + Qwen 4096 sliced to 3072 (local ollama, free)
     │     image  -> Gemini media seam (3072) + perceptual fingerprint (always)
     │     video  -> Gemini media seam (3072) + perceptual fingerprint (always)
     └─ artifact tree:  documents.jsonl · chunks.jsonl · facts.jsonl · vectors.jsonl ·
                        resources.jsonl · manifest.json

//why the routing: text embeds free and local via Qwen (ollama); only image/video ever
hit the paid Gemini media model. Qwen is sliced 4096->3072 so text and media share ONE
dimension. (Same dim != same semantic space — different models; the future self-hosted
Qwen3-VL swap, via lgwks_multimodal's LGWKS_EMBED_MEDIA_* env seam, unifies the space.)
This module COMPOSES proven primitives (lgwks_browser, lgwks_run, lgwks_multimodal,
lgwks_substrate_text) — it does not re-implement them.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import lgwks_browser
import lgwks_multimodal as mm
import lgwks_run
import lgwks_substrate_text as text
from lgwks_substrate_io import _sha

# Target embedding width. Gemini-embedding-2 emits 3072; we slice Qwen (native 4096)
# down to match so every vector in the run shares one dimension. //why: Director spec.
TARGET_DIMS = 3072

# Googlebot identity — the cheapest, highest-yield bypass. Many paywalls/soft gates
# serve full content to search crawlers for SEO; we present as one.
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
GOOGLE_REFERER = {"Referer": "https://www.google.com/"}

_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg",
               ".mp4", ".webm", ".mov", ".m4v", ".pdf"}
_MAX_RESOURCES = 40            # bound the harvest so a run is predictable + cheap
_MAX_MEDIA_BYTES = 8_000_000   # skip resources larger than this (don't embed huge blobs)


class _ResourceHarvester(HTMLParser):
    """Deterministic resource extractor — collects every embeddable/linked asset URL.
    No LLM, no heuristics beyond tag/attr inspection (extraction stays deterministic)."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base = base_url
        self.urls: list[str] = []

    def _add(self, raw: str | None) -> None:
        if not raw:
            return
        absolute = urllib.parse.urljoin(self.base, raw.strip())
        if absolute.startswith(("http://", "https://")) and absolute not in self.urls:
            self.urls.append(absolute)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in ("img", "source", "video", "audio"):
            self._add(a.get("src"))
            self._add(a.get("data-src"))     # lazy-loaded
            self._add(a.get("poster"))
        elif tag == "a":
            href = a.get("href") or ""
            if Path(urllib.parse.urlparse(href).path).suffix.lower() in _MEDIA_EXTS:
                self._add(href)


def _classify(content_type: str, url: str) -> str:
    """text | image | video | other — Content-Type header first, extension as fallback."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    if ct in ("text/html", "text/plain", "application/pdf") or ct.startswith("text/"):
        return "text"
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg"):
        return "image"
    if ext in (".mp4", ".webm", ".mov", ".m4v"):
        return "video"
    return "other"


def _fetch_page(url: str) -> dict[str, Any]:
    """Bypass ladder, cheapest-honest first; auth is the LAST resort.

    //why this order (learned the hard way): faking Googlebot from a non-Google IP
    gets BLOCKED by sites that verify the crawler via reverse-DNS (Wikipedia,
    Cloudflare). So lead with honest stealth — it works on the common case — and
    only fall to the Googlebot identity when a soft paywall/gate actually blocks us
    (news sites serve crawlers full text for SEO). Human auth fires only when both
    automated rungs hit a wall.
    """
    # Rung 1: honest stealth (real UA, anti-automation flag, real viewport).
    r = lgwks_browser.render(url, max_chars=120_000, with_html=True, with_screenshot=True,
                             browser_engine="chromium", wait_ms=3500)
    if r.get("ok") and r.get("html") and not _is_wall(r):
        r["bypass"] = "stealth-chromium"
        return r
    # Rung 2: Googlebot identity + Google referer — the paywall lever, used only
    # after honest stealth was walled.
    r2 = lgwks_browser.render(url, max_chars=120_000, with_html=True, with_screenshot=True,
                              browser_engine="chromium", user_agent=GOOGLEBOT_UA,
                              extra_headers=GOOGLE_REFERER, wait_ms=2500)
    if r2.get("ok") and r2.get("html") and not _is_wall(r2):
        r2["bypass"] = "googlebot-ua"
        return r2
    # Rung 3 (LAST resort): human auth handoff, then reuse the saved session.
    handoff = lgwks_browser.save_session(url, browser_engine="chromium", manual=True)
    if handoff.get("ok"):
        r3 = lgwks_browser.render(url, max_chars=120_000, with_html=True, with_screenshot=True,
                                  browser_engine="chromium", use_session=True, wait_ms=3500)
        r3["bypass"] = "human-auth"
        return r3
    failed = r if r.get("ok") is False else r2
    failed["bypass"] = "exhausted"
    return failed


# Bot-block / anti-scrape signals — distinct from a login gate. If we see these,
# the rung FAILED even though render returned 200 + HTML (the block page). Without
# this, a "you are blocked" page passes as success and the ladder never advances.
_BLOCK_RE = re.compile(
    r"unauthorized request|bot-traffic@|access denied|are you a (?:human|robot)|"
    r"verify you are (?:a )?human|please enable cookies and|ddos protection|"
    r"cf-browser-verification|cf-challenge|captcha|rate.?limit(?:ed)?|"
    r"request blocked|temporarily blocked|too many requests",
    re.I,
)


def _is_wall(r: dict[str, Any]) -> bool:
    """True if the rendered page is a login gate OR a bot-block/anti-scrape page.
    Either means this rung did not really get the content — advance the ladder."""
    from lgwks_substrate_crawl import _looks_like_login_gate
    html = r.get("html") or ""
    body = r.get("text", "") or html[:3000]
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    # //why length-gate: a genuine block/challenge page is SHORT (an error stub).
    # A real article that happens to DISCUSS captchas/rate-limits/blocking (e.g. the
    # Wikipedia "Web scraping" page) is long — scanning its body for block words is a
    # false positive that wrongly escalates the ladder. So only treat block signals
    # in the title (always) or in a short body as a real wall.
    if _BLOCK_RE.search(title):
        return True
    if len(body.strip()) < 1500 and _BLOCK_RE.search(body):
        return True
    return _looks_like_login_gate(title, body, "")


def _embed_text(body: str) -> dict[str, Any]:
    """det 256-d hash (always) + Qwen semantic (DEFERRED: ignore model feedback for now)."""
    dual = lgwks_run.embed_dual(body, embed_on=True)
    sem = dual.get("sem")
    if sem and sem.get("vector"):
        import lgwks_ollama
        sem = {**sem, "vector": lgwks_ollama.slice_mrl(sem["vector"], TARGET_DIMS),
               "dims": min(TARGET_DIMS, sem["dims"])}
    return {"det": dual.get("det"), "sem": sem}


def ingest(url: str, *, project: str = "", run_root: str = "store/ingest",
           max_resources: int = _MAX_RESOURCES, embed_media: bool = True) -> dict[str, Any]:
    """Run the full URL -> artifact-tree pipeline. Returns the manifest dict."""
    import httpx

    t0 = time.time()
    slug = re.sub(r"[^a-z0-9]+", "-", (project or urllib.parse.urlparse(url).netloc or "ingest").lower()).strip("-")
    run_dir = Path(run_root) / f"{slug}-{int(t0)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Fetch (bypass ladder) ────────────────────────────────────────────────
    page = _fetch_page(url)
    if not page.get("ok"):
        manifest = {"ok": False, "url": url, "reason": page.get("reason", "fetch failed"),
                    "bypass": page.get("bypass", "exhausted"), "run_dir": str(run_dir)}
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest

    from lgwks_html import html_to_markdown
    html = page.get("html", "")
    markdown, title, _links, _ = html_to_markdown(html, url)
    # //why: lgwks_html.html_to_markdown returns empty on some large/complex pages
    # (e.g. a 374KB Wikipedia article -> md_len 0). render()'s _text_from already
    # extracted clean text, so fall back to it — same guard substrate uses
    # (lgwks_substrate_crawl.py:241: `markdown or rendered.get("text")`).
    body = markdown.strip() or page.get("text", "")
    if not title:
        tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else url
    doc_id = f"doc-{_sha(url)[:16]}"

    documents = [{"document_id": doc_id, "url": url, "title": title or url,
                  "bypass": page.get("bypass"), "word_count": len(re.findall(r"\S+", body))}]
    chunk_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    counts = {"text_chunks": 0, "facts": 0, "images": 0, "videos": 0, "skipped": 0, "semantic": 0}

    # ── 2. TEXT: chunk -> fact -> det hash + Qwen(3072) ──────────────────────────
    for pos, piece in enumerate(text._chunk_text(body, size=450, overlap=70)):
        score = text._fact_score(piece)
        stem = text._stem_text(piece, 0.6)
        chunk_id = f"chunk-{_sha(doc_id + str(pos) + piece)[:16]}"
        chunk_rows.append({"chunk_id": chunk_id, "document_id": doc_id, "text": piece,
                           "fact_score": score, "chunk_kind": text._chunk_kind(piece, score), "position": pos})
        counts["text_chunks"] += 1
        emb = _embed_text(stem or piece)
        vector_rows.extend(_vrows(chunk_id, doc_id, emb, "text", piece[:2000], counts))
        for sentence in text._fact_sentences(stem, 0.6):
            fid = f"fact-{_sha(chunk_id + sentence)[:16]}"
            fact_rows.append({"fact_id": fid, "chunk_id": chunk_id, "fact_text": sentence})
            counts["facts"] += 1

    # ── 3. Page screenshot as an image chunk (visual modality of the page itself) ─
    if embed_media and page.get("screenshot_b64"):
        resource_rows.append({"url": url + "#screenshot", "kind": "image", "via": "page-screenshot"})
        _embed_media_resource(url + "#screenshot", page["screenshot_b64"],
                              page.get("screenshot_mime", "image/png"), title or url,
                              doc_id, vector_rows, fact_rows, counts)

    # ── 4. HARVEST resources (wget-style) -> classify -> route ───────────────────
    harvester = _ResourceHarvester(url)
    harvester.feed(page.get("html", ""))
    headers = {"User-Agent": GOOGLEBOT_UA, "Referer": "https://www.google.com/"}
    with httpx.Client(follow_redirects=True, timeout=30, headers=headers) as client:
        for res_url in harvester.urls[:max_resources]:
            row: dict[str, Any] = {"url": res_url}
            try:
                resp = client.get(res_url)
                kind = _classify(resp.headers.get("content-type", ""), res_url)
                row["kind"] = kind
                row["bytes"] = len(resp.content)
                if kind in ("image", "video"):
                    if len(resp.content) > _MAX_MEDIA_BYTES:
                        row["status"] = "skipped:too-large"; counts["skipped"] += 1
                    elif embed_media:
                        b64 = base64.b64encode(resp.content).decode("ascii")
                        mime = resp.headers.get("content-type", "").split(";")[0] or f"{kind}/*"
                        _embed_media_resource(res_url, b64, mime, title or url, doc_id,
                                              vector_rows, fact_rows, counts,
                                              video=(kind == "video"))
                        row["status"] = "embedded"
                    else:
                        row["status"] = "skipped:media-off"; counts["skipped"] += 1
                else:
                    row["status"] = "catalogued"  # text/other resources: recorded, not re-embedded
            except Exception as exc:
                row["status"] = f"error:{type(exc).__name__}"; counts["skipped"] += 1
            resource_rows.append(row)

    # ── 5. Emit the artifact tree ────────────────────────────────────────────────
    _emit(run_dir / "documents.jsonl", documents)
    _emit(run_dir / "chunks.jsonl", chunk_rows)
    _emit(run_dir / "facts.jsonl", fact_rows)
    _emit(run_dir / "vectors.jsonl", vector_rows)
    _emit(run_dir / "resources.jsonl", resource_rows)
    manifest = {
        "ok": True, "schema": "lgwks.ingest.v1", "url": url, "title": title or url,
        "bypass": page.get("bypass"), "run_dir": str(run_dir), "target_dims": TARGET_DIMS,
        "providers": {"text": "ollama:qwen3-embedding:8b->3072 + det-256", "media": mm._MM_MODEL},
        "counts": counts, "resources_seen": len(harvester.urls),
        "duration_sec": round(time.time() - t0, 2),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _embed_media_resource(res_url: str, b64: str, mime: str, caption: str, doc_id: str,
                          vector_rows: list, fact_rows: list, counts: dict, *, video: bool = False) -> None:
    chunk_id = f"chunk-{_sha(doc_id + res_url)[:16]}"
    if video:
        res = mm.embed_media(video_b64=b64, video_mime=mime, caption=caption)
        counts["videos"] += 1
    else:
        res = mm.embed_media(image_b64=b64, image_mime=mime, caption=caption)
        counts["images"] += 1
    
    # Emit triples for media evidence
    rel = "video" if video else "image"
    fact_rows.append({
        "fact_id": f"fact-{_sha(doc_id + chunk_id + rel)[:16]}",
        "i_cid": doc_id, "k": rel, "j_cid": chunk_id,
        "confidence_score": 1.0, "schema": "lgwks.score.record.v1"
    })
    
    vector_rows.extend(_vrows(chunk_id, doc_id, res, rel, res_url, counts))


def _vrows(chunk_id: str, doc_id: str, emb: dict, kind: str, vtext: str, counts: dict) -> list[dict]:
    """Build det (always) + sem (when present) vector rows in the shared row format."""
    rows: list[dict] = []
    det = emb.get("det")
    if det and det.get("vector"):
        rows.append({"vector_id": f"vec-{_sha(chunk_id + det['provider'])[:16]}", "chunk_id": chunk_id,
                     "document_id": doc_id, "provider": det["provider"], "is_semantic": False,
                     "dims": det["dims"], "vector_text": vtext, "vector": det["vector"], "chunk_kind": kind})
    sem = emb.get("sem")
    if sem and sem.get("vector"):
        counts["semantic"] += 1
        rows.append({"vector_id": f"vec-{_sha(chunk_id + sem['provider'])[:16]}", "chunk_id": chunk_id,
                     "document_id": doc_id, "provider": sem["provider"], "is_semantic": True,
                     "dims": sem["dims"], "vector_text": vtext, "vector": sem["vector"], "chunk_kind": kind})
    return rows


def _emit(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 lgwks_ingest.py <url> [--no-media]")
        raise SystemExit(2)
    target = sys.argv[1]
    no_media = "--no-media" in sys.argv[2:]
    result = ingest(target, embed_media=not no_media)
    print(json.dumps(result, indent=2))
