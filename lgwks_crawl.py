"""lgwks_crawl — single-page fetch shim: delegates to lgwks_substrate.build_run(max_pages=1).

Legacy `crawl_page` and `CrawlResult` remain importable for backward compatibility but
delegate to `lgwks_browser.render` directly.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import lgwks_ui as ui


# ── backward compatibility ────────────────────────────────────────────────────

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
    """Extract readable text from rendered HTML."""
    from lgwks_html import html_to_markdown
    text, _, _ = html_to_markdown(html, base_url)
    return text[:max_chars]


def _extract_links(html: str, base: str) -> list[dict[str, str]]:
    """Extract anchor links from rendered HTML."""
    from lgwks_html import html_to_markdown
    _, _, links = html_to_markdown(html, base)
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
    """Delegate to lgwks_browser.render and return a CrawlResult for backward compat."""
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^\w-]+", "-", text.lower()).strip("-").replace("--", "-")[:64]


# ── CLI ───────────────────────────────────────────────────────────────────────

def crawl_command(args: argparse.Namespace) -> int:
    """Fetch a single page via substrate.build_run(max_pages=1, max_depth=0)."""
    url = args.url
    json_out = getattr(args, "json", False)
    machine = bool(getattr(args, "machine", False) or json_out)

    import lgwks_substrate as sub

    sub_args = argparse.Namespace(
        target=url,
        project=f"fetch-{_slug(url)[:48]}",
        source_type="auto",
        max_pages=1,
        max_depth=0,
        max_files=0,
        max_chars=getattr(args, "max_chars", 8000),
        chunk_words=450,
        chunk_overlap=70,
        fact_threshold=0.6,
        embed_provider="dual",
        embed_model="",
        login_if_needed=True,
        login_url="",
        success_selector=None,
        max_auto_bypass_attempts=3,
        max_auth_handoffs=3,
        browser_engine=getattr(args, "browser_engine", "chromium"),
        click_discovery=False,
        max_clicks_per_page=20,
        crawl_mode="link-only",
    )

    try:
        manifest = sub.build_run(sub_args)
    except Exception as exc:
        if machine:
            print(json.dumps({
                "schema": "lgwks.crawl.v0",
                "ok": False,
                "url": url,
                "reason": str(exc),
            }, indent=2, ensure_ascii=False))
            return 1
        on = ui.color_on()
        print("\n".join(ui.band("lgwks · fetch", f"{url} — FAILED", on=on)))
        print(ui.spine(ui.fg(f"✗ {exc}", ui.RUST, on=on), on=on))
        print("", ui.footer("lgwks · fetch", on=on), "")
        return 1

    run_dir = Path(manifest["artifacts"]["root"])
    counts = manifest.get("counts", {})
    docs = counts.get("documents", 0)
    chunks = counts.get("chunks", 0)

    if machine:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    on = ui.color_on()
    out: list[str] = [""]
    if docs > 0:
        out += ui.band("lgwks · fetch", f"{url} — substrate fetch", on=on)
        out.append(ui.spine(on=on))
        out.append(ui.spine(ui.fg(f"✓ {docs} doc  · {chunks} chunks", ui.EMERALD, on=on), on=on))
    else:
        out += ui.band("lgwks · fetch", f"{url} — no content", on=on)
    out.append("")
    out.append(f"  manifest: {run_dir / 'manifest.json'}")
    out.append(f"  run_dir:  {run_dir}")
    out.append("", ui.footer("lgwks · fetch", on=on), "")
    print("\n".join(out))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "fetch",
        aliases=["crawl"],
        help="single-page browser fetch/extract — routes through substrate.build_run(max_pages=1)",
    )
    p.add_argument("url", help="target URL")
    p.add_argument("--max-chars", type=int, default=8000, help="max text chars to extract")
    p.add_argument("--wait", type=int, default=2000, help="ms to wait after load (ignored; substrate manages)")
    p.add_argument("--html", action="store_true", help="ignored; substrate manages")
    p.add_argument("--links", action="store_true", default=True, help="ignored; extraction is automatic")
    p.add_argument("--no-links", dest="links", action="store_false", help="ignored")
    p.add_argument("--seed", type=int, default=0, help="ignored; substrate deterministic")
    p.add_argument("--no-scroll", dest="scroll", action="store_false", help="ignored")
    p.add_argument(
        "--webkit", dest="browser_engine", action="store_const", const="webkit",
        default="chromium",
        help="use WebKit engine instead of Chromium",
    )
    p.add_argument("--json", action="store_true", help="emit full substrate manifest JSON")
    p.set_defaults(func=crawl_command)
