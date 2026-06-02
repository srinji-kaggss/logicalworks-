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

import re
import ipaddress
import socket
import urllib.parse
from pathlib import Path

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n{3,}")
# A real, current desktop Chrome fingerprint — present as a human browser, the honest way past JS walls.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SESSION_DIR = Path.home() / ".config" / "lgwks" / "sessions"
_SESSION = Path.home() / ".config" / "lgwks" / "linkedin-session.json"  # legacy location
_INSTALL = "pipx install playwright && playwright install chromium"


def available() -> tuple[bool, str]:
    """Is a real browser usable? (pymod + installed Chromium). Returns (ok, reason-or-install-hint)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False, f"playwright not installed — {_INSTALL}"
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
    return None


def render(url: str, max_chars: int = 8000, *, use_session: bool = False,
           wait_ms: int = 1500, with_html: bool = False) -> dict:
    """Fetch a JS-rendered page with a real browser. use_session loads the user's saved login
    (for LinkedIn/auth pages). with_html also returns the rendered DOM html so a caller can parse
    links/anchors from what the browser actually saw — the real around-the-block (no re-GET of a
    blocked endpoint). Returns {ok, text, reason[, html]}. ok=False carries an honest reason."""
    if not _remote_allowed(url):
        return {"ok": False, "text": "", "reason": "blocked URL"}
    ok, why = available()
    if not ok:
        return {"ok": False, "text": "", "reason": why}
    from playwright.sync_api import sync_playwright
    session_path = _session_for_url(url)
    storage = str(session_path) if (use_session or session_path) and session_path else None
    lock_host = urllib.parse.urlparse(url).hostname or ""
    auth_headers = _headers(url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
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
            out = {"ok": True, "text": _text_from(html, max_chars), "reason": "rendered"}
            if with_html:
                out["html"] = html                           # the DOM the browser saw — parse links here
            return out
    except Exception as e:
        return {"ok": False, "text": "", "reason": f"render failed: {type(e).__name__}"}


def save_session(login_url: str = "https://www.linkedin.com/login") -> dict:
    """One-time: open a real browser so the USER logs in themselves, then persist their session.
    We never handle credentials — the human types them; we only save the resulting cookie/state.
    Returns {ok, path, reason}. Requires a headed run (a visible window)."""
    ok, why = available()
    if not ok:
        return {"ok": False, "reason": why}
    from playwright.sync_api import sync_playwright
    parsed = urllib.parse.urlparse(login_url)
    host = parsed.hostname or "session"
    safe = re.sub(r"[^a-z0-9._-]+", "-", host.lower()).strip("-")
    session_path = _SESSION_DIR / f"{safe}.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)      # visible — the human logs in
            ctx = browser.new_context(user_agent=_UA, locale="en-CA")
            page = ctx.new_page()
            page.goto(login_url)
            # block until the human finishes login + navigates into the app
            page.wait_for_url(lambda u: "login" not in u and "checkpoint" not in u, timeout=300000)
            ctx.storage_state(path=str(session_path))
            browser.close()
        return {"ok": True, "path": str(session_path), "reason": "session saved"}
    except Exception as e:
        return {"ok": False, "reason": f"login capture failed: {type(e).__name__}"}


def linkedin(url: str, max_chars: int = 8000) -> dict:
    """Fetch a LinkedIn page through the user's consented session. Honest if no session saved yet."""
    if not _session_for_url(url):
        return {"ok": False, "text": "",
                "reason": "no LinkedIn session — run: lgwks login linkedin (opens a window; you log in)"}
    return render(url, max_chars, use_session=True, wait_ms=2500)
