"""
lgwks_browser — bot-resilient, JS-rendering fetch via a real browser (playwright). The eyes for pages
the curl/crwl floor can't see: SPAs (canadalife.com returned "enable JavaScript"), bot-walled sites,
and auth-gated pages (LinkedIn — through YOUR session, not a scraper botnet).

"Advanced bot detection" here = looking like a real human browser, not evading abusively: a genuine
Chromium with realistic UA/viewport/locale/timezone, human-scale waits, and — for auth sites — the
user's OWN logged-in session (storage_state). Boundaries (T0): authorized research only; respects
rate limits; LinkedIn runs through the user's consented session and its ToS restricts scraping, so it
is gated, throttled, and single-session — never a fleet. No CAPTCHA-solving, no credential theft.

Degrades honestly: if playwright or its Chromium isn't installed, returns ('', reason) with the exact
install command — never a silent empty (the googler lesson).
"""

from __future__ import annotations

import json
import re
import ipaddress
import select
import socket
import sys
import urllib.parse
from pathlib import Path

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n{3,}")
# A real, current desktop Chrome fingerprint — present as a human browser, the honest way past JS walls.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SESSION_DIR = Path.home() / ".config" / "lgwks" / "sessions"
_SESSION = Path.home() / ".config" / "lgwks" / "linkedin-session.json"  # legacy location
_INSTALL = "pipx install playwright && playwright install chromium webkit"


def _browser_path(engine: str) -> Path | None:
    """Return the expected browser executable path, or None if not found."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_type = p.webkit if engine == "webkit" else p.chromium
            executable = browser_type.executable_path
            if executable and Path(executable).exists():
                return Path(executable)
    except Exception:
        pass
    return None


def available(engine: str = "webkit") -> tuple[bool, str]:
    """Is a real browser usable? (pymod + installed browser binary).
    Returns (ok, reason-or-install-hint)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False, f"playwright not installed — {_INSTALL}"
    if _browser_path(engine) is None:
        return False, f"{engine} browser not installed — run: playwright install {engine}"
    return True, "ready"


def _text_from(html: str, max_chars: int) -> str:
    return _WS.sub("\n\n", _TAG.sub("", html)).strip()[:max_chars]


def _remote_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
        return False
    candidates = [host]
    try:
        candidates.extend(info[4][0] for info in socket.getaddrinfo(host, None))
    except Exception:
        pass
    for candidate in set(candidates):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        # //why: IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1) must resolve to their IPv4 counterpart
        if hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast,
                ip.is_reserved, ip.is_unspecified)):
            return False
        if str(ip) == "169.254.169.254":
            return False
    return True


def _headers(url: str) -> dict[str, str]:
    try:
        import lgwks_auth_runtime
        return lgwks_auth_runtime.headers_for_url(url)
    except Exception:
        return {}


def _route_handler(lock_host: str, auth_headers: dict[str, str]):
    """Return a Playwright route handler that injects auth_headers ONLY when the request host
    matches the lock host. Cross-origin subresources and redirects to other domains get no creds."""
    def handler(route, request):
        req_host = urllib.parse.urlparse(request.url).hostname or ""
        if lock_host.lower() == req_host.lower():
            merged = dict(request.headers)
            merged.update(auth_headers)
            route.continue_(headers=merged)
        else:
            route.continue_()
    return handler


def _session_for_url(url: str) -> Path | None:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return None
    safe = re.sub(r"[^a-z0-9._-]+", "-", host.lower()).strip("-")
    scoped = _SESSION_DIR / f"{safe}.json"
    if scoped.exists():
        return scoped
    if host.lower().endswith("linkedin.com") and _SESSION.exists():
        return _SESSION
    # Cross-domain adaptive: if auth happened on a different subdomain (e.g. auth.example.com)
    # but cookies are scoped to .example.com, find the session that covers this host.
    try:
        for path in _SESSION_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for cookie in data.get("cookies", []):
                domain = (cookie.get("domain") or "").lstrip(".").lower()
                if domain and (host.lower() == domain or host.lower().endswith("." + domain)):
                    return path
    except Exception:
        pass
    return None


def render(url: str, max_chars: int = 8000, *, use_session: bool = False,
           wait_ms: int = 1500, with_html: bool = False,
           browser_engine: str = "webkit") -> dict:
    """Fetch a JS-rendered page with a real browser.

    browser_engine: "webkit" (default, Safari engine — best for macOS Safari sessions)
    or "chromium" (use for Chrome-cookie compatibility or --disable-blink-features
    anti-detection on heavily bot-walled sites).
    use_session loads the saved session for this host from ~/.config/lgwks/sessions/.
    with_html also returns the rendered DOM. Returns {ok, text, reason[, html]}.
    """
    if not _remote_allowed(url):
        return {"ok": False, "text": "", "reason": "blocked URL"}
    ok, why = available(browser_engine)
    if not ok:
        return {"ok": False, "text": "", "reason": why}
    if browser_engine not in ("chromium", "webkit"):
        return {"ok": False, "text": "", "reason": f"unknown browser_engine: {browser_engine!r} — use 'chromium' or 'webkit'"}
    from playwright.sync_api import sync_playwright
    session_path = _session_for_url(url)
    storage = str(session_path) if (use_session or session_path) and session_path else None
    lock_host = urllib.parse.urlparse(url).hostname or ""
    auth_headers = _headers(url)
    try:
        with sync_playwright() as p:
            engine = p.webkit if browser_engine == "webkit" else p.chromium
            # //why: webkit launch takes no chromium-specific flags; keep args clean per engine
            launch_kwargs: dict = {"headless": True}
            if browser_engine == "chromium":
                launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
            browser = engine.launch(**launch_kwargs)
            ctx = browser.new_context(
                user_agent=_UA, locale="en-CA", timezone_id="America/Toronto",
                viewport={"width": 1366, "height": 900},
                storage_state=storage,                       # the user's session, iff present
            )
            if auth_headers:
                ctx.route("**/*", _route_handler(lock_host, auth_headers))
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(wait_ms)                   # let client JS render
            html = page.content()
            browser.close()
            out = {"ok": True, "text": _text_from(html, max_chars), "reason": f"rendered:{browser_engine}"}
            if with_html:
                out["html"] = html                           # the DOM the browser saw — parse links here
            return out
    except Exception as e:
        return {"ok": False, "text": "", "reason": f"render failed: {type(e).__name__}"}


def save_session(
    login_url: str = "https://www.linkedin.com/login",
    *,
    success_selector: str | None = None,
    browser_engine: str = "webkit",
    manual: bool = False,
) -> dict:
    """One-time: open a real browser so the USER logs in themselves, then persist their session.
    We never handle credentials — the human types them; we only save the resulting cookie/state.

    For SPAs (Angular, React, Vue) the URL may not change after login — use success_selector
    to wait for a post-auth DOM element. If omitted, auto-detects common patterns.

    Returns {ok, path, reason}. Requires a headed run (a visible window).

    manual=True skips DOM/URL success detection and lets the user complete OTP/passkey/magic-link
    flows in the visible browser, then press Enter in the terminal to persist the session."""
    ok, why = available(browser_engine)
    if not ok:
        return {"ok": False, "reason": why}
    if browser_engine not in ("chromium", "webkit"):
        return {"ok": False, "reason": f"unknown browser_engine: {browser_engine!r}"}
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    parsed = urllib.parse.urlparse(login_url)
    host = parsed.hostname or "session"
    safe = re.sub(r"[^a-z0-9._-]+", "-", host.lower()).strip("-")
    session_path = _SESSION_DIR / f"{safe}.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)

    # Auto-detect selectors if none provided
    # //why: these selectors must be UNLIKELY on a pre-auth page.
    # Generic tags like "main" or "article" or "#app" appear on login pages too,
    # so they are excluded from auto-detect; use only specific post-auth signals.
    _AUTO_SELECTORS = [
        # Angular / React / Vue dashboards
        "app-dashboard", "[data-testid='dashboard']", ".dashboard", "#dashboard",
        # User menus / profiles (signals auth success)
        ".user-menu", "[data-testid='user-menu']", "#userMenu",
        "[aria-label*='account' i]", "[aria-label*='profile' i]",
    ]

    try:
        with sync_playwright() as p:
            engine = p.webkit if browser_engine == "webkit" else p.chromium
            launch_kwargs: dict = {"headless": False}  # visible — the human logs in
            if browser_engine == "chromium":
                launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
            print(f"\n  Opening {browser_engine} browser for {login_url}", flush=True)
            print("  Complete login in that window, then return here and press Enter to continue...\n", flush=True)
            browser = engine.launch(**launch_kwargs)
            ctx = browser.new_context(user_agent=_UA, locale="en-CA")
            page = ctx.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            if manual:
                print("  Complete auth in the browser window, then press Enter here to continue...", flush=True)
                print("  (auto-close in 5 minutes if no input)", flush=True)
                ready, _, _ = select.select([sys.stdin], [], [], 300)
                if not ready:
                    browser.close()
                    return {"ok": False, "reason": "timeout: no input within 5 minutes — session not saved"}
                sys.stdin.readline()
                ctx.storage_state(path=str(session_path))
                browser.close()
                return {"ok": True, "path": str(session_path), "reason": "session saved (manual)"}

            # SPA-aware auth detection: wait for a post-auth DOM signal
            selector = success_selector
            if not selector:
                # Try each auto-selector with a short timeout; first match wins
                for sel in _AUTO_SELECTORS:
                    try:
                        el = page.wait_for_selector(sel, timeout=5000, state="visible")
                        if el:
                            selector = sel
                            break
                    except PWTimeout:
                        continue

            if selector:
                try:
                    page.wait_for_selector(selector, timeout=300000, state="visible")
                except PWTimeout:
                    browser.close()
                    return {"ok": False, "reason": f"timeout waiting for post-auth selector: {selector}"}
            else:
                # Fallback for traditional MPAs: URL no longer contains login
                try:
                    page.wait_for_url(lambda u: "login" not in u and "checkpoint" not in u, timeout=300000)
                except PWTimeout:
                    browser.close()
                    return {"ok": False, "reason": "timeout waiting for URL to leave login page"}

            ctx.storage_state(path=str(session_path))
            browser.close()
        return {"ok": True, "path": str(session_path), "reason": "session saved"}
    except Exception as e:
        return {"ok": False, "reason": f"login capture failed: {type(e).__name__}: {e}"}


def linkedin(url: str, max_chars: int = 8000) -> dict:
    """Fetch a LinkedIn page through the user's consented session. Honest if no session saved yet."""
    if not _session_for_url(url):
        return {"ok": False, "text": "",
                "reason": "no LinkedIn session — run: lgwks login linkedin (opens a window; you log in)"}
    return render(url, max_chars, use_session=True, wait_ms=2500)
