"""lgwks_crawl — unified crawler dispatcher.
Merges fetch, crawl, and legacy jarvis into one canonical verb.

The crawl engine itself (substrate auth-aware bridge + deterministic Jarvis
crawler) lives in lgwks_jarvis. This module is the canonical `crawl` verb: it
owns the user-facing flag surface (including the #34 auth/embed/engine flags)
and maps them onto the engine — one crawl surface, no duplicated bridge logic.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import lgwks_substrate_io as _io  # canonical filesystem slug (one source of truth)


# ── backward-compatibility shims ──────────────────────────────────────────────
# Lightweight single-page helpers used by callers/tests that predate the
# substrate crawl runtime. They delegate to the canonical html/browser modules
# so there is exactly one extraction implementation behind them.

_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

_VIEWPORT_POOL = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

_LOCALE_POOL = ["en-US", "en-GB", "en-CA", "fr-FR", "de-DE"]
_TIMEZONE_POOL = ["America/New_York", "Europe/London", "America/Toronto", "Europe/Berlin", "Asia/Tokyo"]


def _pick_fingerprint(seed: int = 0) -> dict[str, Any]:
    """Deterministically pick a realistic browser fingerprint from the pool."""
    idx = seed % len(_UA_POOL)
    return {
        "user_agent": _UA_POOL[idx],
        "viewport": _VIEWPORT_POOL[idx % len(_VIEWPORT_POOL)],
        "locale": _LOCALE_POOL[idx % len(_LOCALE_POOL)],
        "timezone": _TIMEZONE_POOL[idx % len(_TIMEZONE_POOL)],
        "color_scheme": "light",
        "reduced_motion": "no-preference",
    }


def _text_from_html(html: str, max_chars: int = 8000, base_url: str = "") -> str:
    """Extract readable markdown text from rendered HTML.

    Routes through the content-extract seam (boilerplate pruning → canonical
    markdown). "wget but better": strip nav/chrome/ads to the content core
    before conversion. See lgwks_content_extract for the parser/heuristic."""
    import lgwks_content_extract
    return lgwks_content_extract.extract_main_content(html, base_url, max_chars=max_chars)


def _extract_links(html: str, base: str) -> list[dict[str, str]]:
    """Extract anchor links from rendered HTML, deduped, javascript: skipped."""
    from lgwks_html import html_to_markdown
    _, _, links, _ = html_to_markdown(html, base)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for ln in links:
        href = ln.get("href", "")
        if href.startswith("javascript:"):
            continue
        key = f"{ln.get('text', '')}|{href}"
        if key not in seen:
            seen.add(key)
            out.append(ln)
    return out


class CrawlResult:
    """Compatibility shim wrapping the dict returned by lgwks_browser.render."""
    def __init__(self, url: str = "", ok: bool = False, **kwargs: Any):
        self.url = url
        self.ok = ok
        for k, v in kwargs.items():
            setattr(self, k, v)


def crawl_page(url: str, **kwargs: Any) -> CrawlResult:
    """Delegate to lgwks_browser.render (SSRF-guarded) and wrap as CrawlResult."""
    import lgwks_browser
    res = lgwks_browser.render(url, **kwargs)
    return CrawlResult(
        url=url,
        ok=res.get("ok", False),
        title=res.get("title", ""),
        text=res.get("text", ""),
        html=res.get("html", ""),
        links=res.get("links", []),
        reason=res.get("reason", ""),
        metadata=res.get("metadata", {}),
    )


def crawl_command(args: argparse.Namespace) -> int:
    """Unified crawl command: maps the canonical flag surface onto lgwks_jarvis."""
    import lgwks_jarvis as jarvis

    # remap-db: absorbed surface of the former `jarvis remap-db` verb.
    remap_dir = getattr(args, "remap_db", None)
    if remap_dir:
        return jarvis.remap_db_command(argparse.Namespace(run_dir=remap_dir))

    target = args.target
    if not target:
        print("crawl: a target URL/keyword seed is required (or use --remap-db RUN_DIR)",
              file=sys.stderr)
        return 2
    is_url = target.startswith(("http://", "https://"))

    # User-facing --engine: substrate (default, URL→auth-aware) or jarvis/legacy
    # (deterministic crawler). The engine module treats anything != "legacy" as
    # a substrate candidate, so normalise the legacy aliases to "legacy".
    engine = getattr(args, "engine", "substrate")
    if engine in ("jarvis", "legacy"):
        engine = "legacy"

    # Substrate is the canonical ingest path for any concrete source (URL or local
    # file); only the legacy deterministic crawler treats a bare term as a keyword
    # seed. So under the substrate engine the target IS the source (build_run
    # auto-detects url vs file); under legacy a non-URL target is a keyword.
    use_as_source = is_url or engine == "substrate"
    jarvis_args = argparse.Namespace(
        source=target if use_as_source else None,
        keyword_terms=[] if use_as_source else [target],
        keywords=getattr(args, "keywords", None),
        prompt=getattr(args, "prompt", "map the machine-state understanding"),
        name=getattr(args, "name", None) or (f"crawl-{_io._slug(target)[:32]}" if target else None),
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        workers=getattr(args, "workers", 2),
        include_external=getattr(args, "include_external", False),
        search_expansion=getattr(args, "search_expansion", False),
        chunk_words=getattr(args, "chunk_words", 320),
        chunk_overlap=getattr(args, "chunk_overlap", 48),
        max_terms=getattr(args, "max_terms", 120),
        compress_limit=getattr(args, "compress_limit", 96),
        similarity_threshold=getattr(args, "similarity_threshold", 0.72),
        estimate_only=getattr(args, "estimate_only", False),
        engine=engine,
        # #34 substrate auth-aware bridge flags
        login_if_needed=getattr(args, "login_if_needed", True),
        login_url=getattr(args, "login_url", ""),
        auth_selector=getattr(args, "auth_selector", None),
        chromium=getattr(args, "chromium", False),
        embed_provider=getattr(args, "embed_provider", "deterministic"),
        embed_model=getattr(args, "embed_model", ""),
        click_discovery=getattr(args, "click_discovery", False),
        max_clicks_per_page=getattr(args, "max_clicks_per_page", 20),
        crawl_mode=getattr(args, "crawl_mode", "link-then-click"),
    )
    return jarvis.crawl_command(jarvis_args)


def add_parser(sub) -> None:
    crawl = sub.add_parser(
        "crawl",
        help="unified URL/keyword crawler (substrate auth-aware bridge + legacy jarvis)",
    )
    crawl.add_argument("target", nargs="?", help="URL to crawl or keyword seed")
    crawl.add_argument(
        "--engine", choices=["substrate", "jarvis", "legacy"], default="substrate",
        help="crawl engine: 'substrate' (auth-aware, default for URLs) or 'jarvis'/'legacy' (deterministic)",
    )

    crawl.add_argument("--max-pages", type=int, default=12)
    crawl.add_argument("--max-depth", type=int, default=1)
    crawl.add_argument("--max-chars", type=int, default=120_000)
    crawl.add_argument("--name", help="project/run name")
    crawl.add_argument("--chunk-words", type=int, default=320)
    crawl.add_argument("--chunk-overlap", type=int, default=48)
    crawl.add_argument("--estimate-only", action="store_true", help="print a compute estimate and exit")
    crawl.add_argument("--json", action="store_true", help="output JSON manifest")

    # legacy-engine pass-through (the former top-level `jarvis crawl` surface,
    # consumed by crawl_command via getattr; #218 consolidation finished — the
    # top-level `jarvis` verb was removed in favour of `crawl --engine legacy`).
    crawl.add_argument("--workers", type=int, default=2, help="(legacy) parallel fetch workers")
    crawl.add_argument("--include-external", action="store_true", help="(legacy) follow off-site links")
    crawl.add_argument("--keywords", help="(legacy) newline/comma/semicolon-delimited keywords")
    crawl.add_argument("--prompt", default="map the machine-state understanding", help="research intent")
    crawl.add_argument("--max-terms", type=int, default=120, help="(legacy) max concept terms")
    crawl.add_argument("--compress-limit", type=int, default=96, help="(legacy) term compression limit")
    crawl.add_argument("--similarity-threshold", type=float, default=0.72, help="(legacy) dedup threshold")
    # remap-db: the only unique surface of the former `jarvis remap-db` verb,
    # absorbed here as a flag (no positional target needed).
    crawl.add_argument("--remap-db", dest="remap_db", metavar="RUN_DIR",
                       help="upgrade an existing run database to the current schema, then exit")

    # #34 substrate auth-aware bridge flags
    crawl.add_argument("--login-if-needed", dest="login_if_needed", action="store_true", default=True,
                       help="(substrate) attempt session login when a gate is detected")
    crawl.add_argument("--no-login", dest="login_if_needed", action="store_false",
                       help="(substrate) never attempt login")
    crawl.add_argument("--login-url", default="", help="(substrate) explicit login page URL")
    crawl.add_argument("--auth-selector", default=None,
                       help="(substrate) CSS selector that confirms a successful login")
    crawl.add_argument("--chromium", action="store_true", help="(substrate) use chromium instead of webkit")
    crawl.add_argument("--embed-provider", default="deterministic", help="(substrate) embedding provider")
    crawl.add_argument("--embed-model", default="", help="(substrate) embedding model")

    # engine-specific pass-through
    crawl.add_argument("--click-discovery", action="store_true", help="(substrate) interactive discovery")
    crawl.add_argument("--search-expansion", action="store_true", help="(jarvis) use googler")

    crawl.set_defaults(func=crawl_command)
