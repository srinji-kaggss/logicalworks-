"""
lgwks_search — the missing primitive: a zero-key, free web + news search provider.

Three runs proved the instrument could reason and refuse-to-fabricate but could NOT find live-world
events (a recent acquisition) — because the web arm was a stub returning "" and ctx7 only serves
library docs, not news/entities. This wires the eyes:

  search(query)        → ranked [{title,url,snippet}] via DuckDuckGo HTML (no API key, free).
  sweep(query)         → MULTI-MODAL: blind parallel arms (general · news · filings) merged + deduped,
                         each arm blind to the others so each surfaces what the others miss.
  fetch(url)           → page → markdown via the crwl crawler (the acquisition page itself).
  source_validity      → reject CAPTCHA / bot-challenge / login-wall before ingest (gate #29 fix).

Degrade chain is honest: a free HTTP search floor (curl) is primary; if curl/crwl are absent or
blocked we return [] and say so — never fabricate a result. Provider seam: any keyed backend plugs
in behind the same contract without changing callers (the engine model, SPEC §2). This codebase
ships no external/metered search dependency.

EMPTY-RESULT CONTRACT: [] means no usable results from attempted providers. [] does NOT mean the
web/codebase contains no evidence. Every empty result carries a provider_attempt_trace — see
last_search_trace() for search(), or the "provider_attempt_trace" key for sweep()/research_queue().
"""

from __future__ import annotations

import concurrent.futures
import html
import os
import re
import subprocess
import threading
import time
import urllib.parse

try:
    import lgwks_capabilities as _cap
except Exception:
    _cap = None  # resolver optional; without it CLI providers are skipped, DDG floor still works

# Rotating UA pool — deterministic per-call selection based on attempt index.
_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _pick_ua(seed: int) -> str:
    return _UA_POOL[seed % len(_UA_POOL)]
_DDG_HTML = "https://html.duckduckgo.com/html/"
_DDG_LITE = "https://lite.duckduckgo.com/lite/"   # lighter HTML; different host → independent rate-limit
_MOJEEK = "https://www.mojeek.com/search"
_SCHOLAR = "https://scholar.google.com/scholar"          # independent index (GET ?q=) — endpoint diversity
# DDG wraps result links as /l/?uddg=<percent-encoded-real-url> — we decode back to the true target.
_RESULT_A = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
# Generic anchor parser — robust across lite endpoints AND a browser-rendered DOM (the around-the-block).
_ANY_A = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_MOJEEK_A = re.compile(r'<a[^>]*class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)  # mojeek result only
_NAV_HOSTS = ("duckduckgo.com", "mojeek.com")       # self/nav links, never a result
from lgwks_substrate_config import TAG_RE as _TAG  # one source of truth
_YEAR = re.compile(r"\b(20\d{2})\b")
_YEAR_SPAN = re.compile(r"\b(20\d{2})\s*[-–]\s*(20\d{2})\b")


# Per-host politeness: the multi-arm sweep fires several requests concurrently. Without
# spacing they burst the SAME host (e.g. the one live search endpoint), which rate-limits
# the burst and returns empty for every arm — a self-inflicted denial of service that read
# as "no evidence". We reserve staggered per-host slots so same-host requests space out by
# _HOST_MIN_INTERVAL while different hosts still proceed in parallel.
_HOST_LOCK = threading.Lock()
_HOST_NEXT: dict[str, float] = {}
_HOST_MIN_INTERVAL = 1.2


def _polite_wait(url: str) -> None:
    host = urllib.parse.urlsplit(url).netloc
    if not host:
        return
    with _HOST_LOCK:
        slot = max(time.monotonic(), _HOST_NEXT.get(host, 0.0))
        _HOST_NEXT[host] = slot + _HOST_MIN_INTERVAL
    delay = slot - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def _curl(url: str, data: str | None = None, timeout: int = 20, ua: str = "") -> str:
    """One read-only HTTP GET/POST via curl. Returns body or '' (honest empty, never raises upward).
    Accepts an optional UA override; defaults to the first pool entry."""
    _polite_wait(url)
    cmd = ["curl", "-s", "-L", "--max-time", str(timeout), "-A", ua or _UA_POOL[0]]
    if data is not None:
        cmd += ["--data", data]
    cmd.append(url)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return p.stdout or ""
    except Exception:
        return ""


def _clean(s: str) -> str:
    return html.unescape(_TAG.sub("", s)).strip()


def _unwrap(href: str) -> str:
    """Decode a DDG redirect (//duckduckgo.com/l/?uddg=…) back to the real destination URL."""
    if "uddg=" in href:
        q = urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query
        u = urllib.parse.parse_qs(q).get("uddg")
        if u:
            return urllib.parse.unquote(u[0])
    return href if href.startswith("http") else "https:" + href


def _parse_ddg(body: str, k: int, via: str) -> list[dict]:
    """Parse an open-endpoint HTML results page into [{title,url,snippet,via}]. Shared by the http
    floor and the rendered (browser) path so both surface identical, vendor-neutral result shapes."""
    out: list[dict] = []
    snippets = _SNIPPET.findall(body)
    for i, (href, title) in enumerate(_RESULT_A.findall(body)):
        url = _unwrap(href)
        if not url.startswith("http"):
            continue
        out.append({"title": _clean(title), "url": url, "via": via,
                    "snippet": _clean(snippets[i]) if i < len(snippets) else ""})
        if len(out) >= k:
            break
    return out


def _parse_links(body: str, k: int, via: str) -> list[dict]:
    """Generic anchor parser: pull real result links out of ANY results HTML — a lite endpoint or a
    browser-rendered DOM. Skips self/nav hosts. This is what makes 'rendered' a TRUE around-the-block:
    we parse the DOM the browser actually saw, never re-GET a blocked endpoint."""
    out, seen = [], set()
    for href, title in _ANY_A.findall(body):
        url = _unwrap(href)
        host = urllib.parse.urlparse(url).netloc.lower()
        if not url.startswith("http") or "." not in host:   # reject relative/self links (e.g. '/lite/')
            continue
        if any(nav in host for nav in _NAV_HOSTS):
            continue
        t = _clean(title)
        key = url.split("?")[0].rstrip("/")
        if len(t) < 3 or key in seen:
            continue
        seen.add(key)
        out.append({"title": t, "url": url, "via": via, "snippet": ""})
        if len(out) >= k:
            break
    return out


def _parse_mojeek(body: str, k: int, via: str) -> list[dict]:
    """Mojeek-targeted: only `<a class="title">` anchors are real results — skips Mojeek's own promo/nav
    links the generic parser would conflate (the binning trap). Independent index → independent block."""
    out, seen = [], set()
    for href, title in _MOJEEK_A.findall(body):
        if not href.startswith("http"):
            continue
        key = href.split("?")[0].rstrip("/")
        t = _clean(title)
        if len(t) < 3 or key in seen:
            continue
        seen.add(key)
        out.append({"title": t, "url": href, "via": via, "snippet": ""})
        if len(out) >= k:
            break
    return out


def _backoff(attempt: int) -> float:
    """Deterministic exponential backoff with small jitter: 0.4·2^n capped at 2s, plus
    a deterministic perturbation (0–150 ms) so parallel requests don't stampede."""
    base = min(2.0, 0.4 * (2 ** attempt))
    jitter = (attempt * 0.071) % 0.15   # deterministic pseudo-random; avoids thundering herd
    return base + jitter


# Floor endpoints, rotated in order: independent hosts → an independent rate-limit each. One 429 no
# longer blinds the instrument (the live failure: a single DDG limit zeroed every arm).
# Order = liveness, not preference. The DDG HTML/lite endpoints currently bot-wall
# scrapers: they accept the connection then return an empty body, burning the FULL
# socket timeout (~20s) on every try. Tried first (as they were), they buried the one
# live endpoint behind ~80s of dead waits — and under the concurrent sweep that read as
# "no evidence". Live endpoint first + a tight per-endpoint floor timeout so a dead
# endpoint fast-fails (~_FLOOR_TIMEOUT s) instead of stalling the whole floor.
_FLOOR_TIMEOUT = 8
_FLOOR_ENDPOINTS = [
    ("mojeek", _MOJEEK, "get", _parse_mojeek),
    # ddg-html / ddg-lite are RETIRED from the rotation: both currently accept the
    # connection then return an empty body, burning the full socket timeout on every
    # try and never yielding a result. A dead endpoint in the floor is pure latency
    # (and, under the concurrent sweep, a self-DoS). Restore here behind a working
    # access path (the AI-First browser engine handles the around-the-block case via
    # the `rendered` provider). Parsers (_parse_ddg/_parse_links) kept for that revival.
]


# Minimum body length for a plausible results page (shorter = bot-wall or rate-limit)
_MIN_BODY = 200


def _open(query: str, k: int, *, sleep=time.sleep) -> list[dict]:
    """Open HTML floor with endpoint ROTATION + retry + jitter + UA rotation.
    Tries each independent endpoint up to 2×; on empty/blocked it backs off with jitter,
    then rotates. Returns [] only if ALL endpoints are dry after retries."""
    qs = urllib.parse.urlencode({"q": query})
    for ep_idx, (_name, base, method, parser) in enumerate(_FLOOR_ENDPOINTS):
        for retry in range(2):
            attempt = ep_idx * 2 + retry
            ua = _pick_ua(attempt)
            body = (_curl(base, data=qs, ua=ua, timeout=_FLOOR_TIMEOUT) if method == "post"
                    else _curl(base + "?" + qs, ua=ua, timeout=_FLOOR_TIMEOUT))
            if body and len(body) > _MIN_BODY:
                rows = parser(body, k, via="open")
                if rows:
                    return rows
            sleep(_backoff(attempt))
    return []


def _rendered(query: str, k: int) -> list[dict]:
    """The TRUE around-the-block: render the results page in a REAL browser (looks human, survives the
    blocks that 429 a scraper) and parse links from the DOM the browser saw — no re-GET of the blocked
    endpoint (the bug that made this hollow). Lite page is lighter to render."""
    try:
        import lgwks_browser
    except Exception:
        return []
    if not lgwks_browser.available()[0]:
        return []
    url = _DDG_LITE + "?" + urllib.parse.urlencode({"q": query})
    r = lgwks_browser.render(url, max_chars=40000, with_html=True)
    if not r.get("ok") or not r.get("html"):
        return []
    return _parse_links(r["html"], k, via="rendered")


def _cli(query: str, k: int) -> list[dict]:
    """A search CLI if one is present (probed at call time, vendor-agnostic). JSON mode → results."""
    exe = (_cap.find_binary("ddgr") or _cap.find_binary("googler")) if _cap else None
    if not exe:
        return []
    try:
        import json
        p = subprocess.run([exe, "--json", "-n", str(k), query],
                           capture_output=True, text=True, timeout=25)
        rows = json.loads(p.stdout or "[]")
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("abstract", ""), "via": "cli"} for r in rows if r.get("url")]
    except Exception:
        return []


# Provider chain, best-first, vendor-agnostic ids. Each returns [] on absence/empty → fall through
# (liveness, not mere presence). 'open' is the floor; 'rendered' is the around-the-block via browser.
# `rendered` is the LAST arm: it only runs when cli+open return empty (the fallthrough in search()),
# which is exactly the case now that the HTTP floor (mojeek/ddg) reliably 403s a scraper. With the
# floor blocked, gating rendered OFF made search() always return [] — the "categorical failure" that
# made research look broken. render() is bounded (goto timeout=30s + raw fallback) so a single-query
# fallthrough cannot stall indefinitely. Set LGWKS_SEARCH_NO_RENDERED=1 to disable it under the
# concurrent multi-arm sweep, where many slow renders could otherwise compound.
_PROVIDERS = [("cli", _cli), ("open", _open)]
if os.environ.get("LGWKS_SEARCH_NO_RENDERED") != "1":
    _PROVIDERS.append(("rendered", _rendered))


# search() returning [] is ambiguous on its own — see the module docstring's empty-result contract.
# _SEARCH_TRACE is a side-channel (NOT part of the list return, so it can never break a caller that
# does len()/indexing/iteration on search()'s result): a record of which providers were attempted
# and why each yielded nothing, refreshed on every search() call. THREAD-LOCAL because sweep() runs
# several search() calls concurrently (one per arm) — a single shared list would let one arm's
# trace clobber another's between the search() return and the trace read (a real race, not
# hypothetical: sweep()'s ThreadPoolExecutor fires _ARMS in parallel). last_search_trace() is the
# read accessor for the calling thread's most recent search() call.
_SEARCH_TRACE = threading.local()


def last_search_trace() -> list[dict]:
    """[{provider, attempted, error_or_reason}] for the most recent search() call made by the
    CURRENT thread. Populated even when search() found a result on the first provider
    (attempted=True, error_or_reason="") so the trace is never silently stale; always non-empty
    when search() returned []."""
    return list(getattr(_SEARCH_TRACE, "entries", []))


def active_provider() -> str:
    """The provider tried FIRST given what's present — the HONEST label (liveness still decided at call
    time: an empty result falls through open→rendered). Not the capability resolver's presence guess,
    which may name a keyed provider that is not wired into this module."""
    if _cap and (_cap.find_binary("ddgr") or _cap.find_binary("googler")):
        return "cli"
    return "open"


def _score(r: dict, terms: list[str]) -> int:
    """Relevance hygiene: how many query terms appear in title+snippet+url. Kills off-topic noise
    (e.g. an unrelated API doc) by ranking, not silent dropping — the Tongue still sees the tail."""
    hay = (r.get("title", "") + " " + r.get("snippet", "") + " " + r.get("url", "")).lower()
    return sum(1 for t in terms if t in hay)


def temporal_queries(query: str) -> list[str]:
    """Expand an explicit year-bounded query into newest→oldest subqueries.
    Example: 'Canada Life annual reports and MD&A (2022-2024)' → 2024, 2023, 2022.
    Empty list means no explicit temporal steering was requested."""
    m = _YEAR_SPAN.search(query)
    if not m:
        return []
    start, end = int(m.group(1)), int(m.group(2))
    lo, hi = min(start, end), max(start, end)
    if hi - lo > 25:
        return []
    stem = _YEAR_SPAN.sub("", query).replace("()", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" ,-")
    return [f"{stem} {year}" for year in range(hi, lo - 1, -1)]


def _result_year(result: dict) -> int:
    bag = " ".join(str(result.get(k, "")) for k in ("title", "snippet", "url", "query"))
    years = [int(y) for y in _YEAR.findall(bag)]
    return max(years) if years else 0


def order_results(query: str, results: list[dict]) -> list[dict]:
    """Deterministic newest→oldest ordering when the query declares a time window.
    Falls back to the existing relevance score when no explicit clock is present."""
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    has_clock = bool(temporal_queries(query))
    if has_clock:
        return sorted(
            results,
            key=lambda r: (
                int(r.get("query_year", 0) or 0),
                _result_year(r),
                _score(r, terms),
            ),
            reverse=True,
        )
    return sorted(results, key=lambda r: (_score(r, terms), _result_year(r)), reverse=True)


# ── Google Scholar support ───────────────────────────────────────────────────

def _parse_scholar(body: str, k: int, via: str) -> list[dict]:
    """Parse Google Scholar results HTML into [{title,url,snippet,via}].
    Each result is a <div class="gs_r"> block with title, authors, and snippet."""
    out: list[dict] = []
    # Scholar splits results into <div class="gs_r ..."> containers
    blocks = re.split(r'<div class="gs_r[^"]*"[^>]*>', body)[1:]
    for block in blocks[:k]:
        # title + URL from the first anchor inside h3.gs_rt
        tm = re.search(r'<h3 class="gs_rt"[^>]*>.*?<a href="([^"]+)"[^>]*>(.*?)</a>.*?</h3>', block, re.S | re.I)
        if not tm:
            continue
        url = tm.group(1)
        title = _clean(tm.group(2))
        # authors / venue / year
        am = re.search(r'<div class="gs_a"[^>]*>(.*?)</div>', block, re.S | re.I)
        authors = _clean(am.group(1)) if am else ""
        # snippet
        sm = re.search(r'<div class="gs_rs"[^>]*>(.*?)</div>', block, re.S | re.I)
        snippet = _clean(sm.group(1)) if sm else ""
        out.append({
            "title": title,
            "url": url,
            "via": via,
            "snippet": f"{authors} — {snippet}" if (authors and snippet) else (authors or snippet),
        })
    return out


def scholar(query: str, k: int = 6) -> list[dict]:
    """Search Google Scholar for academic papers. Returns [{title,url,snippet,via}].
    Uses the same UA rotation and retry logic as the open floor."""
    qs = urllib.parse.urlencode({"q": query, "hl": "en"})
    for attempt in range(3):
        ua = _pick_ua(attempt + 100)  # offset from web-search UA cycle
        body = _curl(_SCHOLAR + "?" + qs, ua=ua)
        if body and len(body) > _MIN_BODY and "gs_r" in body:
            rows = _parse_scholar(body, k, via="scholar")
            if rows:
                return rows
    return []


def search(query: str, k: int = 6) -> list[dict]:
    """Best present provider, FALLING THROUGH on empty (robust to broken/absent providers), then
    deduped-by-URL and relevance-ranked against the query. Reports which provider (`via`) won.

    NOTE on []: an empty return means no usable results from the providers attempted THIS call —
    it is not a claim that no evidence exists anywhere. Call last_search_trace() right after for
    the per-provider attempt record (which providers ran, and why each yielded nothing)."""
    raw: list[dict] = []
    trace: list[dict] = []
    for _id, fn in _PROVIDERS:
        try:
            raw = fn(query, k)
        except Exception as exc:  # a provider must never silently vanish from the trace
            trace.append({"provider": _id, "attempted": True, "error_or_reason": f"raised {exc!r}"})
            raw = []
            continue
        if raw:
            trace.append({"provider": _id, "attempted": True, "error_or_reason": ""})
            break
        trace.append({"provider": _id, "attempted": True, "error_or_reason": "returned no results"})
    _SEARCH_TRACE.entries = trace
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    seen, deduped = set(), []
    for r in raw:
        key = r.get("url", "").split("?")[0].rstrip("/")
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    deduped.sort(key=lambda r: _score(r, terms), reverse=True)  # most on-topic first
    return deduped[:k]


# Multi-modal arms: each is a query TRANSFORM, blind to the others (the sweep pattern). News + filings
# arms bias toward live events (acquisitions, leadership, regulatory) the bare site never surfaces.
_ARMS = {
    "general": lambda q: q,
    "news": lambda q: f"{q} news 2025 OR 2026 acquisition OR merger OR announcement",
    "filings": lambda q: f"{q} (SEDAR OR EDGAR OR press release OR investor relations)",
    "people": lambda q: f"{q} site:linkedin.com/company OR leadership OR executive",
}

# Scholar arm uses a dedicated academic endpoint, not the general web search providers.
_SCHOLAR_ARMS = {
    "academic": lambda q: q,
}


def sweep(query: str, k_per_arm: int = 4) -> dict:
    """Blind multi-modal sweep → merged, deduped-by-URL results + which arms found each. The completeness
    surface: every arm runs, and we report which arms returned nothing (no silent coverage gap).

    NOTE on has_evidence=False / results=[]: that means no usable results from the arms attempted
    THIS call, not that no evidence exists. provider_attempt_trace below names every arm tried and,
    for empty arms, the per-provider reason (sourced from search()'s last_search_trace())."""
    def run(name: str) -> tuple[str, list[dict]]:
        rows = search(_ARMS[name](query), k=k_per_arm)
        return name, rows, list(last_search_trace())

    def run_scholar(name: str) -> tuple[str, list[dict]]:
        rows = scholar(_SCHOLAR_ARMS[name](query), k=k_per_arm)
        reason = "" if rows else "returned no results"
        return name, rows, [{"provider": "scholar", "attempted": True, "error_or_reason": reason}]

    found: dict[str, dict] = {}
    arms_hit: dict[str, int] = {}
    arm_traces: dict[str, list[dict]] = {}
    all_runs = [(n, run) for n in _ARMS] + [(n, run_scholar) for n in _SCHOLAR_ARMS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_runs)) as ex:
        for name, results, provider_trace in ex.map(lambda item: item[1](item[0]), all_runs):
            arms_hit[name] = len(results)
            arm_traces[name] = provider_trace
            for r in results:
                key = r["url"].split("?")[0].rstrip("/")
                if key in found:
                    found[key]["arms"].append(name)
                else:
                    found[key] = {**r, "arms": [name]}
    empty = [n for n, c in arms_hit.items() if c == 0]
    provider_attempt_trace = [
        {"arm": arm, **entry} for arm in empty for entry in (arm_traces.get(arm) or
            [{"provider": "unknown", "attempted": True, "error_or_reason": "no trace recorded"}])
    ]
    return {"query": query, "results": list(found.values()),
            "arms_hit": arms_hit, "arms_empty": empty,
            "has_evidence": bool(found),
            "provider_attempt_trace": provider_attempt_trace}


def research_queue(query: str, k_per_arm: int = 4) -> dict:
    """A dogfood-oriented evidence queue: if the query declares a year window, search each year
    newest→oldest and preserve that order in the merged queue. Otherwise fall back to one sweep."""
    subqueries = temporal_queries(query)
    if not subqueries:
        pack = sweep(query, k_per_arm=k_per_arm)
        pack["results"] = order_results(query, pack.get("results", []))
        return pack

    found: dict[str, dict] = {}
    arms_hit: dict[str, int] = {}
    arms_empty: set[str] = set()
    provider_attempt_trace: list[dict] = []
    for subq in subqueries:
        year_match = _YEAR.search(subq)
        qyear = int(year_match.group(1)) if year_match else 0
        pack = sweep(subq, k_per_arm=k_per_arm)
        for arm, count in (pack.get("arms_hit") or {}).items():
            arms_hit[arm] = arms_hit.get(arm, 0) + int(count)
        arms_empty.update(pack.get("arms_empty") or [])
        for entry in pack.get("provider_attempt_trace") or []:
            provider_attempt_trace.append({"subquery": subq, **entry})
        for r in pack.get("results", []):
            key = r["url"].split("?")[0].rstrip("/")
            enriched = {**r, "query": subq, "query_year": qyear}
            if key in found:
                found[key]["arms"] = sorted(set(found[key].get("arms", []) + enriched.get("arms", [])))
                if qyear > int(found[key].get("query_year", 0) or 0):
                    found[key]["query"] = subq
                    found[key]["query_year"] = qyear
            else:
                found[key] = enriched
    ordered = order_results(query, list(found.values()))
    return {
        "query": query,
        "results": ordered,
        "arms_hit": arms_hit,
        "arms_empty": sorted(arms_empty),
        "has_evidence": bool(ordered),
        "subqueries": subqueries,
        "provider_attempt_trace": provider_attempt_trace,
    }


# ── source-validity verifier (gate-honesty #29) ──────────────────────────────────────────────

_CAPTCHA_MARKERS = [
    "captcha", "recaptcha", "are you human", "i'm not a robot", "verify you are human",
    "bot detection", "bot challenge", "cloudflare", "cf-turnstile", "hcaptcha",
]
_LOGIN_WALL_MARKERS = [
    "sign in", "log in", "login", "password", "forgot password", "create account",
    "register to view", "members only", "subscription required", "paywall",
]
_ACCESS_DENIED_MARKERS = [
    "access denied", "403 forbidden", "blocked", "rate limit exceeded",
]
_URL_CHALLENGE_FRAGMENTS = {
    "captcha",
    "bot-check",
    "botcheck",
    "areyouhuman",
    "security-check",
    "verify-human",
    "human-verification",
}


def source_validity(text: str, url: str = "") -> tuple[bool, str | None]:
    """
    Reject CAPTCHA / bot-challenge / empty-result / login-wall pages before ingest.
    Returns (ok, diagnosis). ok=False means CANNOT_DECIDE — do not map into concepts.

    DiD layers (independent; any one triggers rejection):
      1. Body-size floor       — near-empty is likely a failed fetch or bot wall.
      2. Content-marker scan   — literal strings for known challenge systems.
      3. URL-pattern scan      — known challenge URL fragments (independent of body).
      4. Structural heuristic  — password input fields, script-to-content ratio.
    """
    low = text.lower()

    # Layer 1: body-size floor
    stripped = re.sub(r"\s+", "", low)
    if len(stripped) < 20:
        return (False, "empty or near-empty body — likely bot-wall or failed fetch")

    # Layer 2: content-marker scan
    for marker in _CAPTCHA_MARKERS:
        if marker in low:
            return (False, f"CAPTCHA/bot-challenge marker detected: '{marker}'")
    for marker in _LOGIN_WALL_MARKERS:
        if marker in low:
            return (False, f"login-wall marker detected: '{marker}'")
    for marker in _ACCESS_DENIED_MARKERS:
        if marker in low:
            return (False, f"access-denied marker detected: '{marker}'")

    # Layer 3: URL-pattern scan. Tokenised matching avoids false positives like
    # `/coding-challenge-results` while still catching challenge endpoints.
    parsed = urllib.parse.urlparse(url or "")
    url_bag = "/".join(filter(None, [parsed.netloc.lower(), parsed.path.lower(), parsed.query.lower()]))
    url_tokens = {tok for tok in re.split(r"[^a-z0-9]+", url_bag) if tok}
    for frag in sorted(_URL_CHALLENGE_FRAGMENTS):
        frag_tokens = set(frag.split("-"))
        if frag in url_bag or frag_tokens.issubset(url_tokens):
            return (False, f"URL challenge fragment detected: '{frag}'")

    # Layer 4a: password input field is a login wall
    if re.search(r"<input[^>>]*type=[\"']?password[\"']?", low):
        return (False, "password input field detected — login wall")
    # Layer 4b: extreme script-to-content ratio often indicates JS-only challenge pages.
    script_tags = len(re.findall(r"<script\b", low))
    visible_text = len(re.sub(r"<[^>]+>", "", text).strip())
    if script_tags > 3 and visible_text < 200:
        return (False, "high script-to-content ratio — likely JS challenge page")

    return (True, None)


def fetch(url: str, max_chars: int = 6000) -> str:
    """Page → text, bounded. Delegates to the extract port (crwl → curl → real-browser escalation on a
    JS/bot wall), so a SPA or bot-walled page is no longer a silent empty. Falls back to crwl if extract
    is unavailable. The Tongue reads facts, not a whole page."""
    import lgwks_extract
    if not lgwks_extract._remote_allowed(url):
        return f"[refused: SSRF block] {url}"

    try:
        doc = lgwks_extract.extract(url, max_chars=max_chars)
        if doc.get("ok"):
            text = doc["text"]
            ok, diag = source_validity(text, url)
            if not ok:
                return f"[source-validity: CANNOT_DECIDE] {diag}"
            return text
    except Exception:
        pass
    try:
        p = subprocess.run(["crwl", url, "-o", "md-fit"], capture_output=True, text=True, timeout=40)
        text = (p.stdout or "").strip()[:max_chars]
        ok, diag = source_validity(text, url)
        if not ok:
            return f"[source-validity: CANNOT_DECIDE] {diag}"
        return text
    except Exception:
        return ""
