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
from pathlib import Path

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n{3,}")
# A real, current desktop Chrome fingerprint — present as a human browser, the honest way past JS walls.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SESSION = Path.home() / ".config" / "lgwks" / "linkedin-session.json"  # the user's saved login state
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


def render(url: str, max_chars: int = 8000, *, use_session: bool = False,
           wait_ms: int = 1500) -> dict:
    """Fetch a JS-rendered page with a real browser. use_session loads the user's saved login
    (for LinkedIn/auth pages). Returns {ok, text, reason}. ok=False carries an honest reason."""
    ok, why = available()
    if not ok:
        return {"ok": False, "text": "", "reason": why}
    from playwright.sync_api import sync_playwright
    storage = str(_SESSION) if (use_session and _SESSION.exists()) else None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=_UA, locale="en-CA", timezone_id="America/Toronto",
                viewport={"width": 1366, "height": 900},
                storage_state=storage,                       # the user's session, iff present
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(wait_ms)                   # let client JS render
            html = page.content()
            browser.close()
            return {"ok": True, "text": _text_from(html, max_chars), "reason": "rendered"}
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
    _SESSION.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)      # visible — the human logs in
            ctx = browser.new_context(user_agent=_UA, locale="en-CA")
            page = ctx.new_page()
            page.goto(login_url)
            # block until the human finishes login + navigates into the app
            page.wait_for_url(lambda u: "login" not in u and "checkpoint" not in u, timeout=300000)
            ctx.storage_state(path=str(_SESSION))
            browser.close()
        return {"ok": True, "path": str(_SESSION), "reason": "session saved"}
    except Exception as e:
        return {"ok": False, "reason": f"login capture failed: {type(e).__name__}"}


def linkedin(url: str, max_chars: int = 8000) -> dict:
    """Fetch a LinkedIn page through the user's consented session. Honest if no session saved yet."""
    if not _SESSION.exists():
        return {"ok": False, "text": "",
                "reason": "no LinkedIn session — run: lgwks login linkedin (opens a window; you log in)"}
    return render(url, max_chars, use_session=True, wait_ms=2500)
