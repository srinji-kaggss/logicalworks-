"""lgwks_crawl — bot-resilient, JS-rendered page extraction with stealth.

Inspired by Firecrawl and Crawl4AI: uses Playwright with stealth plugins, realistic
browser fingerprinting, and smart waiting to evade basic bot checks (Cloudflare,
DataDome, basic JS challenges). Extracts clean markdown, links, and structured data.

//why: `lgwks_browser.render` is honest but naive — a single UA and no stealth. Modern
sites gate content behind bot detection. We need the same ethical posture (authorized
research only, rate limits, no CAPTCHA solving) but with better technical resilience.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_browser import _remote_allowed, available as _browser_available


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


def _text_from_html(html: str, max_chars: int = 8000) -> str:
    """Extract readable text from rendered HTML."""
    tag = re.compile(r"<[^>]+>")
    ws = re.compile(r"\n{3,}")
    return ws.sub("\n\n", tag.sub("", html)).strip()[:max_chars]


def _extract_links(html: str, base: str) -> list[dict[str, str]]:
    """Extract anchor links from rendered HTML."""
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a[^>]+href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
        href = m.group(1).strip()
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(base, href)
        if href in seen:
            continue
        seen.add(href)
        links.append({"href": href, "text": text[:80]})
    return links


def _inject_stealth(page: Any) -> None:
    """Inject stealth scripts to mask Playwright fingerprints."""
    # navigator.webdriver evasion
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = { runtime: {} };
    """)


@dataclass
class CrawlResult:
    url: str
    ok: bool
    title: str = ""
    text: str = ""
    html: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def crawl_page(
    url: str,
    max_chars: int = 8000,
    wait_ms: int = 2000,
    with_html: bool = False,
    with_links: bool = True,
    seed: int = 0,
    scroll: bool = True,
    timeout: int = 30000,
) -> CrawlResult:
    """Crawl a single page with stealth browser."""
    if not _remote_allowed(url):
        return CrawlResult(url=url, ok=False, reason="blocked URL")
    ok, why = _browser_available()
    if not ok:
        return CrawlResult(url=url, ok=False, reason=why)

    fp = _pick_fingerprint(seed)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return CrawlResult(url=url, ok=False, reason=f"playwright import failed: {e}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            ctx = browser.new_context(
                user_agent=fp["user_agent"],
                viewport=fp["viewport"],
                locale=fp["locale"],
                timezone_id=fp["timezone"],
                color_scheme=fp["color_scheme"],
                reduced_motion=fp["reduced_motion"],
            )
            page = ctx.new_page()
            _inject_stealth(page)

            # Human-like navigation
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(500)  # initial settle

            # Wait for common anti-bot challenges to resolve
            for _ in range(3):
                if page.locator("body").count() == 0:
                    page.wait_for_timeout(1000)
                else:
                    break

            # Scroll to bottom to trigger lazy load (like a human)
            if scroll:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)

            # Final wait for JS rendering
            page.wait_for_timeout(wait_ms)

            html = page.content()
            title = page.title()
            browser.close()

            text = _text_from_html(html, max_chars)
            links = _extract_links(html, url) if with_links else []

            return CrawlResult(
                url=url,
                ok=True,
                title=title,
                text=text,
                html=html if with_html else "",
                links=links,
                metadata={
                    "fingerprint": fp,
                    "chars_extracted": len(text),
                    "links_found": len(links),
                },
            )
    except Exception as e:
        return CrawlResult(url=url, ok=False, reason=f"crawl failed: {type(e).__name__}: {e}")


def crawl_command(args: argparse.Namespace) -> int:
    url = args.url
    result = crawl_page(
        url,
        max_chars=getattr(args, "max_chars", 8000),
        wait_ms=getattr(args, "wait", 2000),
        with_html=getattr(args, "html", False),
        with_links=getattr(args, "links", True),
        seed=getattr(args, "seed", 0),
        scroll=getattr(args, "scroll", True),
    )
    if getattr(args, "json", False):
        print(json.dumps({
            "schema": "lgwks.crawl.v0",
            "url": result.url,
            "ok": result.ok,
            "title": result.title,
            "text": result.text,
            "html": result.html,
            "links": result.links,
            "reason": result.reason,
            "metadata": result.metadata,
        }, indent=2, ensure_ascii=False))
        return 0 if result.ok else 1

    on = ui.color_on()
    out: list[str] = [""]
    if result.ok:
        out += ui.band("lgwks · crawl", f"{result.url} — {result.title}", on=on)
        out.append(ui.spine(on=on))
        out.append(ui.spine(ui.fg(f"✓ {result.metadata['chars_extracted']} chars · {result.metadata['links_found']} links", ui.EMERALD, on=on), on=on))
        if result.links:
            out.append(ui.spine(ui.fg("links", ui.CREAM_DIM, on=on), on=on))
            for ln in result.links[:5]:
                out.append(ui.twig(f"{ln['text'] or '(no text)'} → {ln['href'][:60]}", 1, "link", on=on))
            if len(result.links) > 5:
                out.append(ui.twig(f"… and {len(result.links)-5} more", 1, "link", on=on))
        out.append("")
        out.append(result.text[:2000])
    else:
        out += ui.band("lgwks · crawl", f"{result.url} — FAILED", on=on)
        out.append(ui.spine(ui.fg(f"✗ {result.reason}", ui.RUST, on=on), on=on))
    out.append(""); out.append("  " + ui.footer("lgwks · crawl", on=on)); out.append("")
    print("\n".join(out))
    return 0 if result.ok else 1


def add_parser(sub) -> None:
    p = sub.add_parser("crawl", help="stealth browser crawl — bot-resilient page extraction")
    p.add_argument("url", help="target URL")
    p.add_argument("--max-chars", type=int, default=8000, help="max text chars to extract")
    p.add_argument("--wait", type=int, default=2000, help="ms to wait after load")
    p.add_argument("--html", action="store_true", help="include full rendered HTML")
    p.add_argument("--links", action="store_true", default=True, help="extract links")
    p.add_argument("--no-links", dest="links", action="store_false", help="skip link extraction")
    p.add_argument("--seed", type=int, default=0, help="fingerprint seed (deterministic)")
    p.add_argument("--no-scroll", dest="scroll", action="store_false", help="skip scroll trigger")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=crawl_command)
