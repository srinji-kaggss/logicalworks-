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
import logging
import re
import ipaddress
import select
import socket
import sys
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

from lgwks_substrate_config import TAG_RE as _TAG, WS_COLLAPSE_RE as _WS  # one source of truth
# A real, current desktop Chrome fingerprint — present as a human browser, the honest way past JS walls.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SESSION_DIR = Path.home() / ".config" / "lgwks" / "sessions"
_INSTALL = "pipx install playwright && playwright install chromium webkit"
NO_ACCESS_RE = re.compile(
    r"\b(access forbidden|access denied|not authorized|not authorised|permission denied|"
    r"do not have access|don't have access|no access|read-protected|insufficient privileges)\b",
    re.I,
)


def _click_candidate_score(candidate: dict) -> int:
    """Rank click candidates from DOM structure, not site-specific labels."""
    area = int(float(candidate.get("area") or 0))
    text_len = int(candidate.get("text_len") or 0)
    score = 0

    if candidate.get("in_main"):
        score += 80
    if candidate.get("in_article"):
        score += 30
    if candidate.get("in_chrome"):
        score -= 90
    if candidate.get("in_dialog"):
        score -= 50

    if candidate.get("tag") == "button" or candidate.get("role") in {"button", "link"}:
        score += 20
    if candidate.get("cursor") == "pointer":
        score += 25
    if candidate.get("href"):
        score += 3

    # Tiles/cards are usually larger than chrome links; cap to avoid one huge
    # container dominating every real control.
    score += min(60, area // 2500)
    if 4 <= text_len <= 80:
        score += 12
    elif text_len > 140:
        score -= 20

    y = float(candidate.get("y") or 0)
    if y < 80:
        score -= 20
    if candidate.get("depth", 0) > 18:
        score -= 10
    if not str(candidate.get("text") or "").strip() and not str(candidate.get("href") or "").strip():
        score -= 100
    return score


def _classify_click_outcome(seed_url: str, seed_text: str, row: dict) -> dict[str, bool]:
    final_url = str(row.get("final_url") or seed_url)
    text = str(row.get("text") or "")
    status = str(row.get("status") or "error")
    return {
        "timeout": "TimeoutError" in str(row.get("reason") or ""),
        "same_url": final_url == seed_url,
        "same_text": bool(seed_text) and text == seed_text,
        "no_access": status == "no_access",
        "ok": status == "ok",
    }


def _should_stop_click_discovery(metrics: dict[str, int]) -> bool:
    attempts = int(metrics.get("attempts", 0))
    if attempts < 4:
        return False
    if int(metrics.get("timeouts", 0)) >= 3 and int(metrics.get("ok", 0)) == 0:
        return True
    if int(metrics.get("same_state", 0)) >= 4 and int(metrics.get("novel", 0)) == 0:
        return True
    if attempts >= 6 and (int(metrics.get("timeouts", 0)) + int(metrics.get("same_state", 0))) >= 5 and int(metrics.get("novel", 0)) == 0:
        return True
    return False


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
    if engine == "nodriver":
        try:
            import nodriver  # noqa: F401
            return True, "ok"
        except Exception:
            return False, "nodriver not installed — run: pip install nodriver"

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False, f"playwright not installed — {_INSTALL}"
    if _browser_path(engine) is None:
        return False, f"{engine} browser not installed — run: playwright install {engine}"
    return True, "ready"


def _text_from(html: str, max_chars: int) -> str:
    # Boilerplate-pruned clean markdown via the content-extract seam (was a crude
    # regex tag-strip). "wget but better": drop nav/chrome/ads to the content core.
    # Falls back to the regex strip if extraction yields nothing.
    try:
        import lgwks_content_extract
        text = lgwks_content_extract.extract_main_content(html, max_chars=max_chars)
        if text.strip():
            return text
    except Exception:
        pass
    return _WS.sub("\n\n", _TAG.sub("", html)).strip()[:max_chars]


def _remote_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
        return False
    if host.endswith((".xip.io", ".nip.io")):
        return False
    
    # Defense-in-depth: resolve the host to ensure it doesn't point to internal networks (DNS rebinding / xip.io)
    resolved_ips = []
    try:
        # Try to parse as direct IP first.
        ipaddress.ip_address(host)
        resolved_ips.append(host)
    except ValueError:
        # If it's a hostname, resolve it. Pass an explicit port because some
        # socket implementations reject getaddrinfo(host, None).
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            for info in socket.getaddrinfo(host, port):
                resolved_ips.append(info[4][0])
        except Exception:
            # Resolver outages should not make every public URL unusable. Literal
            # and localhost-style targets are already blocked above; when DNS is
            # unavailable, allow syntactically public hostnames and let the fetch
            # layer fail naturally if the name cannot be reached.
            return "." in host and not host.endswith((".local", ".internal", ".invalid"))

    if not resolved_ips:
        return False

    for ip_str in set(resolved_ips):
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        # IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1) must resolve to their IPv4 counterpart
        if hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast,
                ip.is_reserved, ip.is_unspecified)):
            return False
        # Specific cloud metadata endpoints that might bypass 'private' checks depending on IP version
        if str(ip) in {"169.254.169.254", "100.100.100.200"}:
            return False
            
    return True


def _headers(url: str) -> dict[str, str]:
    try:
        import lgwks_auth_runtime
        return lgwks_auth_runtime.headers_for_url(url)
    except Exception:
        return {}


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _remote_allowed(newurl):
            raise urllib.error.HTTPError(req.full_url, code, "blocked redirect target", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _raw_render_fallback(url: str, max_chars: int, *, with_html: bool, user_agent: str | None,
                         extra_headers: dict | None, reason: str) -> dict:
    """Guarded zero-JS fallback for public pages when Playwright navigation fails."""
    headers = {"User-Agent": user_agent or _UA}
    if extra_headers:
        headers.update(extra_headers)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.build_opener(_SafeRedirectHandler()).open(req, timeout=20) as resp:
            raw = resp.read(2_000_000)
        html = raw.decode("utf-8", "replace")
        out = {"ok": True, "text": _text_from(html, max_chars), "reason": f"raw-fallback after {reason}"}
        if with_html:
            out["html"] = html
        return out
    except Exception as exc:
        return {"ok": False, "text": "", "reason": f"{reason}; raw fallback failed: {type(exc).__name__}: {exc}"}


def _route_handler(lock_host: str, auth_headers: dict[str, str]):
    """Return a Playwright route handler that:
    1. Blocks SSRF targets on EVERY request (including redirects/subresources).
    2. Injects auth_headers ONLY when the request host matches the lock host.
    """
    def handler(route, request):
        url = request.url
        # SSRF validation on every single request made by the browser
        if not _remote_allowed(url):
            logger.warning("blocking SSRF attempt in browser: %s", url)
            route.abort("blockedbyclient")
            return

        req_host = urllib.parse.urlparse(url).hostname or ""
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
           wait_ms: int = 1500, with_html: bool = False, with_screenshot: bool = False,
           browser_engine: str = "webkit",
           user_agent: str | None = None, extra_headers: dict | None = None) -> dict:
    """Fetch a JS-rendered page with a real browser.

    browser_engine: "webkit" (default, Safari engine — best for macOS Safari sessions)
    or "chromium" (use for Chrome-cookie compatibility or --disable-blink-features
    anti-detection on heavily bot-walled sites).
    use_session loads the saved session for this host from ~/.config/lgwks/sessions/.
    with_html also returns the rendered DOM.
    with_screenshot returns a base64 PNG screenshot for multimodal embedding.
    user_agent overrides the default UA (e.g. Googlebot for paywall bypass).
    extra_headers are merged onto every request (e.g. {"Referer": "https://www.google.com"}).
    Returns {ok, text, reason[, html, screenshot_b64, screenshot_mime]}.
    """
    if not _remote_allowed(url):
        return {"ok": False, "text": "", "reason": "blocked URL"}
    ok, why = available(browser_engine)
    if not ok:
        return {"ok": False, "text": "", "reason": why}
    if browser_engine not in ("chromium", "webkit", "nodriver"):
        return {"ok": False, "text": "", "reason": f"unknown browser_engine: {browser_engine!r} — use 'chromium', 'webkit' or 'nodriver'"}

    if browser_engine == "nodriver":
        try:
            import asyncio
            import nodriver
            async def _nodriver_render():
                browser = await nodriver.start()
                page = await browser.get(url)
                await asyncio.sleep(wait_ms / 1000.0)
                html = await page.get_content()
                text = _text_from(html, max_chars)
                await browser.stop()
                return {"ok": True, "text": text, "html": html, "reason": "rendered:nodriver"}
            return asyncio.run(_nodriver_render())
        except Exception as e:
            return {"ok": False, "text": "", "reason": f"nodriver failed: {type(e).__name__}"}
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
            try:
                ctx_kwargs: dict = {
                    "user_agent": user_agent or _UA, "locale": "en-CA",
                    "timezone_id": "America/Toronto",
                    "viewport": {"width": 1366, "height": 900},
                    "storage_state": storage,                    # the user's session, iff present
                }
                if extra_headers:
                    ctx_kwargs["extra_http_headers"] = extra_headers
                ctx = browser.new_context(**ctx_kwargs)
                # Defense-in-depth: always route via handler to block SSRF subresources/redirects
                ctx.route("**/*", _route_handler(lock_host, auth_headers))

                page = ctx.new_page()

                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait_ms)                   # let client JS render
                html = page.content()
                out = {"ok": True, "text": _text_from(html, max_chars), "reason": f"rendered:{browser_engine}"}
                if with_html:
                    out["html"] = html                           # the DOM the browser saw — parse links here
                if with_screenshot:
                    try:
                        raw = page.screenshot(type="png", full_page=False)
                        if raw:
                            import lgwks_multimodal as mm
                            b64, mime = mm._resize_and_encode(raw, max_dim=mm._MAX_IMG_DIM, fmt="PNG")
                            out["screenshot_b64"] = b64
                            out["screenshot_mime"] = mime
                    except Exception:
                        out["screenshot_b64"] = None
                        out["screenshot_mime"] = None
                return out
            finally:
                browser.close()
    except Exception as e:
        reason = f"render failed: {type(e).__name__}: {e}"
        if not use_session and not auth_headers:
            return _raw_render_fallback(
                url,
                max_chars,
                with_html=with_html,
                user_agent=user_agent,
                extra_headers=extra_headers,
                reason=reason,
            )
        return {"ok": False, "text": "", "reason": reason}


def _click_candidates_js() -> str:
    return """
    () => {
      const nodes = Array.from(document.querySelectorAll(
        "a[href], button, [role='button'], [role='link'], [onclick], [data-url], [data-href], [aria-label], [tabindex], [class*='card' i], [class*='tile' i], [class*='app' i], [class*='service' i], [class*='item' i]"
      ));
      const chromeSelector = "header, footer, nav, aside, [role='navigation'], [role='banner'], [role='contentinfo'], [class*='nav' i], [class*='menu' i], [class*='footer' i], [class*='header' i]";
      const mainSelector = "main, [role='main'], article, section, [class*='content' i], [class*='card' i], [class*='tile' i], [class*='app' i]";
      const out = [];
      const seen = new Set();
      const depthOf = (el) => {
        let depth = 0;
        for (let p = el; p; p = p.parentElement) depth += 1;
        return depth;
      };
      for (const el of nodes) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        if (rect.width < 2 || rect.height < 2 || style.visibility === "hidden" || style.display === "none") continue;
        const text = (el.innerText || el.textContent || el.getAttribute("aria-label") || el.getAttribute("title") || "").trim().replace(/\\s+/g, " ");
        const href = el.href || el.getAttribute("href") || el.getAttribute("data-url") || el.getAttribute("data-href") || "";
        if (!text && !href) continue;
        if (!href && text.length > 180) continue;
        if (rect.width > window.innerWidth * 0.95 && rect.height > window.innerHeight * 0.45) continue;
        const key = `${text}|${href}|${el.tagName}|${el.getAttribute("role") || ""}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const id = out.length;
        el.setAttribute("data-lgwks-click-id", String(id));
        out.push({
          id,
          text: text.slice(0, 120),
          text_len: text.length,
          href,
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute("role") || "",
          area: Math.round(rect.width * rect.height),
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          depth: depthOf(el),
          in_main: Boolean(el.closest(mainSelector)),
          in_article: Boolean(el.closest("article")),
          in_chrome: Boolean(el.closest(chromeSelector)),
          in_dialog: Boolean(el.closest("dialog, [role='dialog'], [aria-modal='true'], [class*='modal' i]")),
          cursor: style.cursor || ""
        });
      }
      return out;
    }
    """


def discover_clicks(
    url: str,
    *,
    max_clicks: int = 20,
    wait_ms: int = 2500,
    browser_engine: str = "chromium",
) -> list[dict]:
    """Deterministically click visible same-page controls from an authorized browser session.

    Each candidate is clicked in a fresh page/context state so a dead branch does not poison
    the remaining exploration. This is discovery, not auth bypass: it only uses the user's
    saved session and records no-access outcomes explicitly.
    """
    if not _remote_allowed(url):
        return [{"ok": False, "status": "blocked", "url": url, "reason": "blocked URL"}]
    ok, why = available(browser_engine)
    if not ok:
        return [{"ok": False, "status": "error", "url": url, "reason": why}]
    if browser_engine not in ("chromium", "webkit"):
        return [{"ok": False, "status": "error", "url": url, "reason": f"unknown browser_engine: {browser_engine!r}"}]

    from playwright.sync_api import sync_playwright

    session_path = _session_for_url(url)
    storage = str(session_path) if session_path else None
    lock_host = urllib.parse.urlparse(url).hostname or ""
    auth_headers = _headers(url)
    rows: list[dict] = []
    try:
        with sync_playwright() as p:
            engine = p.webkit if browser_engine == "webkit" else p.chromium
            launch_kwargs: dict = {"headless": True}
            if browser_engine == "chromium":
                launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]
            browser = engine.launch(**launch_kwargs)
            try:
                ctx = browser.new_context(
                    user_agent=_UA, locale="en-CA", timezone_id="America/Toronto",
                    viewport={"width": 1366, "height": 900},
                    storage_state=storage,
                )
                if auth_headers:
                    ctx.route("**/*", _route_handler(lock_host, auth_headers))

                seed = ctx.new_page()
                seed.goto(url, wait_until="domcontentloaded", timeout=30000)
                seed.wait_for_timeout(wait_ms)
                seed_text = _text_from(seed.content(), 120_000)
                scored_candidates = [
                    (cand, _click_candidate_score(cand))
                    for cand in seed.evaluate(_click_candidates_js())
                ]
                candidates = [
                    cand
                    for cand, score in sorted(scored_candidates, key=lambda item: item[1], reverse=True)
                    if score > 0
                ][:max_clicks]
                seed.close()
                metrics = {"attempts": 0, "ok": 0, "novel": 0, "same_state": 0, "timeouts": 0}

                for cand in candidates:
                    page = None
                    target_page = None
                    try:
                        page = ctx.new_page()
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(wait_ms)
                        page.evaluate(_click_candidates_js())
                        # Hardening (#154 M5): our injected JS only ever assigns
                        # non-negative integer ids (out.length). Reject anything
                        # else so a malicious page cannot smuggle a CSS-selector
                        # fragment through cand['id'] to widen/redirect the click.
                        cand_id = str(cand.get("id", ""))
                        if not cand_id.isdigit():
                            rows.append({
                                "ok": False, "status": "error", "url": url, "final_url": "",
                                "reason": "rejected non-integer click id", "candidate": cand,
                            })
                            metrics["attempts"] += 1
                            continue
                        selector = f"[data-lgwks-click-id='{cand_id}']"
                        before = page.url
                        popup = None
                        def on_popup(p):
                            nonlocal popup
                            popup = p
                        page.on("popup", on_popup)
                        try:
                            page.locator(selector).click(timeout=5000)
                            page.wait_for_timeout(1000)
                            target_page = popup if popup else page
                            try:
                                target_page.wait_for_load_state("domcontentloaded", timeout=15000)
                            except Exception:
                                pass
                            target_page.wait_for_timeout(wait_ms)
                        finally:
                            page.remove_listener("popup", on_popup)
                        
                        html = target_page.content()
                        text = _text_from(html, 120_000)
                        status = "no_access" if NO_ACCESS_RE.search(text) else "ok"
                        rows.append({
                            "ok": status == "ok",
                            "status": status,
                            "url": before,
                            "final_url": target_page.url,
                            "text": text,
                            "html": html,
                            "html_len": len(html),
                            "candidate": cand,
                        })
                        metrics["attempts"] += 1
                        outcome = _classify_click_outcome(url, seed_text, rows[-1])
                        if outcome["ok"]: metrics["ok"] += 1
                        if outcome["timeout"]: metrics["timeouts"] += 1
                        if outcome["same_url"] and outcome["same_text"]:
                            metrics["same_state"] += 1
                        else:
                            metrics["novel"] += 1
                    except Exception as exc:
                        rows.append({
                            "ok": False, "status": "error", "url": url, "final_url": "",
                            "reason": f"click failed: {type(exc).__name__}", "candidate": cand,
                        })
                        metrics["attempts"] += 1
                        outcome = _classify_click_outcome(url, seed_text, rows[-1])
                        if outcome["timeout"]: metrics["timeouts"] += 1
                    finally:
                        if target_page and target_page is not page:
                            target_page.close()
                        if page:
                            page.close()
                    
                    if _should_stop_click_discovery(metrics):
                        break
            finally:
                browser.close()
    except Exception as exc:
        return [{"ok": False, "status": "error", "url": url, "reason": f"click discovery failed: {type(exc).__name__}"}]
    return rows


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

    # //why: if a session was previously saved for this host, preload it so the user
    # only needs to complete any remaining step (OTP/passkey), not re-authenticate from zero.
    existing_session = _session_for_url(login_url)
    preload_storage = str(existing_session) if existing_session else None

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
            ctx = browser.new_context(
                user_agent=_UA, locale="en-CA",
                storage_state=preload_storage,
            )
            page = ctx.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            if manual:
                if not preload_storage:
                    print(f"  No saved session for {host} — log in to create one.", flush=True)
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
