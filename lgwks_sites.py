"""lgwks_sites — site-aware extractors for high-value platforms.

Each extractor is a regex/HTML parser tuned to a specific domain (Twitter/X, Reddit,
Google Scholar). They degrade gracefully: if the site changes its markup, the extractor
returns partial data (never crashes) and the caller falls back to generic extraction.

All extractors return a dict with a common schema:
  {kind, title, body, author, date, metrics, url, extra, ok, fallback}
"""

from __future__ import annotations

import json
import re
import urllib.parse

# ── Common helpers ──────────────────────────────────────────────────────────

def _host(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or ""


def _first(rex: re.Pattern, text: str) -> str:
    m = rex.search(text)
    return m.group(1) if m else ""


def _unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')


# ── Twitter / X ─────────────────────────────────────────────────────────────
_TWITTER_HOSTS = {"twitter.com", "x.com", "mobile.twitter.com"}

# Meta-tag extraction (works on both server-rendered and some JS-rendered snapshots)
_TW_TITLE = re.compile(r'<meta[^>]*name="twitter:title"[^>]*content="([^"]*)"', re.I)
_TW_DESC = re.compile(r'<meta[^>]*name="twitter:description"[^>]*content="([^"]*)"', re.I)
_TW_AUTHOR = re.compile(r'<meta[^>]*name="twitter:creator"[^>]*content="([^"]*)"', re.I)
_TW_IMG_ALT = re.compile(r'<img[^>]*alt="([^"]*)"[^>]*data-testid="tweetPhoto"', re.I)

# JSON-LD or hydrated state (embedded in script tags)
_TW_DATA = re.compile(r'data-testid="tweet".*?>(.*?)</div>', re.S)
_TW_TEXT = re.compile(r'data-testid="tweetText">(.*?)</div>', re.S)
_TW_STAT = re.compile(r'(\d+)\s*(?:reposts?|retweets?)', re.I)
_TW_LIKE = re.compile(r'(\d+)\s*(?:likes?)', re.I)
_TW_REPLY = re.compile(r'(\d+)\s*(?:replies?)', re.I)


def extract_twitter(url: str, html: str) -> dict:
    """Extract tweet data from Twitter/X HTML. Returns partial data on any parse failure."""
    title = _unescape(_first(_TW_TITLE, html))
    desc = _unescape(_first(_TW_DESC, html))
    author = _unescape(_first(_TW_AUTHOR, html))
    # Prefer tweetText div over meta description when available
    text_match = _TW_TEXT.search(html)
    body = _unescape(text_match.group(1)) if text_match else (desc or title)
    # engagement heuristics from any text in the page
    metrics = {}
    for rex, key in ((_TW_STAT, "retweets"), (_TW_LIKE, "likes"), (_TW_REPLY, "replies")):
        m = rex.search(html)
        if m:
            metrics[key] = int(m.group(1))
    ok = bool(body and len(body) > 10)
    return {
        "kind": "twitter",
        "title": title or "",
        "body": body,
        "author": author or "",
        "date": "",
        "metrics": metrics,
        "url": url,
        "extra": {},
        "ok": ok,
        "fallback": not ok,
    }


# ── Reddit ──────────────────────────────────────────────────────────────────
_REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com"}

_RE_TITLE = re.compile(r'<title>(.*?)</title>', re.I | re.S)
_RE_POST = re.compile(r'<shreddit-post[^>]*title="([^"]*)"[^>]*>', re.I)
_RE_SCORE = re.compile(r'<faceplate-number[^>]*number="([^"]*)"[^>]*>', re.I)
_RE_COMMENT = re.compile(r'<shreddit-comment[^>]*>.*?<p[^>]*>(.*?)</p>', re.I | re.S)
_RE_BODY = re.compile(r'<div[^>]*class="[^"]*(?:text-neutral-content|md)[^"]*"[^>]*>(.*?)</div>', re.I | re.S)
_RE_OLD_POST = re.compile(r'<a[^>]*class="title"[^>]*>(.*?)</a>', re.I)
_RE_OLD_BODY = re.compile(r'<div[^>]*class="usertext-body"[^>]*>(.*?)</div>', re.I | re.S)


def extract_reddit(url: str, html: str) -> dict:
    """Extract Reddit post data. Handles both new (shreddit) and old Reddit markup."""
    # Prefer post-specific markup over generic <title> (which includes | r/subreddit)
    post = _unescape(_first(_RE_POST, html))
    old_post = _unescape(_first(_RE_OLD_POST, html))
    title = post or old_post or _unescape(_first(_RE_TITLE, html))
    # Try new Reddit body first, then old Reddit
    body_match = _RE_BODY.search(html)
    body = _unescape(body_match.group(1)) if body_match else ""
    if not body:
        old_body = _RE_OLD_BODY.search(html)
        body = _unescape(old_body.group(1)) if old_body else ""
    # engagement
    score_match = _RE_SCORE.search(html)
    metrics = {"upvotes": int(score_match.group(1))} if score_match else {}
    comments = [_unescape(m.group(1)) for m in _RE_COMMENT.finditer(html)]
    ok = bool(title or body)
    return {
        "kind": "reddit",
        "title": title or post,
        "body": body,
        "author": "",
        "date": "",
        "metrics": metrics,
        "url": url,
        "extra": {"comments": comments[:20]},  # cap comments to avoid token bloat
        "ok": ok,
        "fallback": not ok,
    }


# ── Google Scholar ──────────────────────────────────────────────────────────
_SCHOLAR_HOSTS = {"scholar.google.com"}

# Result-page extraction
_GS_TITLE = re.compile(r'class="gs_rt"[^>]*>.*?<a[^>]*>(.*?)</a>', re.I | re.S)
_GS_TITLE2 = re.compile(r'class="gs_rt"[^>]*><span[^>]*>.*?</span>\s*(.*?)</', re.I | re.S)
_GS_AUTHORS = re.compile(r'class="gs_a"[^>]*>(.*?)</div>', re.I | re.S)
_GS_CITED = re.compile(r'Cited by\s+(\d+)', re.I)
_GS_PDF = re.compile(r'<a[^>]*href="([^"]*\.pdf)"[^>]*>\s*\[PDF\]', re.I)
_GS_SNIPPET = re.compile(r'class="gs_rs"[^>]*>(.*?)</div>', re.I | re.S)

# Individual paper / citation view
_GS_BIB_TITLE = re.compile(r'<div[^>]*class="gsc_oci_title"[^>]*>(.*?)</div>', re.I | re.S)
_GS_BIB_ROW = re.compile(r'<div[^>]*class="gs_oci_field"[^>]*>([^<]*)</div>\s*<div[^>]*class="gs_oci_value"[^>]*>(.*?)</div>', re.I | re.S)


def extract_scholar(url: str, html: str) -> dict:
    """Extract paper metadata from Google Scholar result or citation page HTML."""
    title = _unescape(_first(_GS_TITLE, html))
    if not title:
        title = _unescape(_first(_GS_TITLE2, html))
    if not title:
        title = _unescape(_first(_GS_BIB_TITLE, html))
    authors_raw = _unescape(_first(_GS_AUTHORS, html))
    authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
    snippet = _unescape(_first(_GS_SNIPPET, html))
    cited_match = _GS_CITED.search(html)
    pdf_match = _GS_PDF.search(html)
    # bib rows (individual paper view)
    bib = {}
    for label, value in _GS_BIB_ROW.findall(html):
        bib[label.strip().rstrip(":").lower()] = _unescape(value.strip())
    year = bib.get("year", "")
    venue = bib.get("journal", bib.get("conference", bib.get("book", "")))
    metrics = {}
    if cited_match:
        metrics["citations"] = int(cited_match.group(1))
    ok = bool(title)
    return {
        "kind": "scholar",
        "title": title,
        "body": snippet,
        "author": ", ".join(authors) if authors else bib.get("authors", ""),
        "date": year,
        "metrics": metrics,
        "url": url,
        "extra": {
            "venue": venue,
            "pdf_url": pdf_match.group(1) if pdf_match else "",
            "bib": bib,
        },
        "ok": ok,
        "fallback": not ok,
    }


# ── Dispatch ────────────────────────────────────────────────────────────────

def extract_for_site(url: str, html: str) -> dict | None:
    """Dispatch to the correct site-aware extractor based on hostname.
    Returns None if no extractor matches (caller falls back to generic)."""
    host = _host(url).lower().lstrip("www.")
    if host in _TWITTER_HOSTS:
        return extract_twitter(url, html)
    if host in _REDDIT_HOSTS:
        return extract_reddit(url, html)
    if host in _SCHOLAR_HOSTS:
        return extract_scholar(url, html)
    return None


def supported_host(url: str) -> bool:
    host = _host(url).lower().lstrip("www.")
    return host in (_TWITTER_HOSTS | _REDDIT_HOSTS | _SCHOLAR_HOSTS)
