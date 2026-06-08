"""lgwks_substrate_crawl — web crawl engine, auth-gate detection, and frontier management.

Defense-in-Depth:
- Layer 1 (entry): URL canonicalization strips fragments and normalizes ports.
- Layer 2 (business): auth-gate detection uses tiered signals (URL, title, body).
- Layer 3 (environment): browser engine fallback (chromium for manual auth on macOS).
- Layer 4 (debug): frontier records every URL attempt with status, depth, reason, telemetry.
"""

from __future__ import annotations

import urllib.parse
from collections import Counter, deque
from pathlib import Path
from typing import Any

import lgwks_browser
from lgwks_substrate_config import (
    AUTH_GATE_RE,
    STRONG_AUTH_GATE_RE,
    FrontierList,
)
from lgwks_substrate_io import _sha


def _html_to_markdown(html: str, url: str) -> tuple[str, str, list[dict[str, str]]]:
    """Late-binding wrapper so test patches on lgwks_substrate.html_to_markdown propagate here."""
    import sys
    facade = sys.modules.get("lgwks_substrate")
    if facade is not None:
        return getattr(facade, "html_to_markdown")(html, url)
    from lgwks_html import html_to_markdown as _htm
    return _htm(html, url)


def _canonicalize_crawl_url(url: str) -> str:
    """Strip fragments, normalize scheme/host case, drop default ports."""
    raw = urllib.parse.urldefrag((url or "").strip())[0]
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    if not host:
        return raw
    port = parsed.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def _looks_like_login_gate(title: str, text: str, url: str) -> bool:
    """Tiered auth-gate detection: URL → title → body → weak heuristic."""
    low_url = url.lower()
    if any(term in low_url for term in ("/login", "/signin", "signin", "authenticate", "sso")):
        return True
    title_sample = title.strip()
    if title_sample and AUTH_GATE_RE.search(title_sample):
        return True
    sample = text[:2500].strip()
    if STRONG_AUTH_GATE_RE.search(sample):
        return True
    weak_hits = __import__("re").findall(r"\blogins?\b", sample, flags=__import__("re").I)
    return len(weak_hits) >= 2 and bool(__import__("re").search(r"\b(username|user id|password|submit|remote logins?)\b", sample, __import__("re").I))


def _should_discover_clicks(page_url: str, links: list[dict[str, str]]) -> bool:
    """Click discovery is expensive; enable only when href frontier is thin."""
    page_host = urllib.parse.urlparse(page_url).hostname or ""
    same_host_links = {
        _canonicalize_crawl_url(link.get("href", ""))
        for link in links
        if (urllib.parse.urlparse(link.get("href", "")).hostname or "") == page_host
    }
    same_host_links.discard(_canonicalize_crawl_url(page_url))
    return len(same_host_links) <= 2


def _crawl_site(
    base_url: str,
    *,
    max_pages: int,
    max_depth: int,
    browser_engine: str,
    login_if_needed: bool,
    login_url: str,
    success_selector: str | None,
    max_auto_bypass_attempts: int,
    max_auth_handoffs: int,
    click_discovery: bool,
    max_clicks_per_page: int,
    crawl_mode: str = "link-then-click",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Breadth-first crawl with auth-gate detection, click discovery, and frontier logging."""
    parsed = urllib.parse.urlparse(base_url)
    base_host = parsed.hostname or ""
    seen: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque([(_canonicalize_crawl_url(base_url), 0, "seed")])
    docs: list[dict[str, Any]] = []
    frontier = FrontierList()
    click_telemetry_by_page: dict[str, dict[str, Any]] = {}
    doc_fingerprints: set[tuple[str, str]] = set()
    blocker_retries_used = 0
    url_attempts: Counter[str] = Counter()
    auth_handoffs = 0

    def append_doc(*, source: str, title: str, text: str, html_len: int, depth: int, discovered_by: str) -> bool:
        clean_source = _canonicalize_crawl_url(source) or source
        fingerprint = (clean_source, _sha(text or ""))
        if fingerprint in doc_fingerprints:
            return False
        doc_fingerprints.add(fingerprint)
        docs.append({
            "source": clean_source,
            "title": title or clean_source,
            "text": text,
            "html_len": html_len,
            "depth": depth,
            "discovered_by": discovered_by,
        })
        return True

    while queue and len(docs) < max_pages:
        url, depth, discovered_by = queue.popleft()
        clean = _canonicalize_crawl_url(url)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        url_attempts[clean] += 1
        attempt = url_attempts[clean]
        if not lgwks_browser._remote_allowed(clean):
            frontier.append({"url": clean, "depth": depth, "status": "blocked", "discovered_by": discovered_by})
            continue
        rendered = lgwks_browser.render(
            clean,
            max_chars=120_000,
            use_session=True,
            wait_ms=min(9000, 2500 + ((attempt - 1) * 2500)),
            with_html=True,
            browser_engine=browser_engine,
        )
        if not rendered.get("ok") or not rendered.get("html"):
            if blocker_retries_used < max_auto_bypass_attempts:
                blocker_retries_used += 1
                seen.discard(clean)
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "retrying_blocker",
                    "reason": rendered.get("reason", ""),
                    "attempt": attempt,
                    "discovered_by": discovered_by,
                })
                queue.appendleft((clean, depth, discovered_by))
                continue
            frontier.append({
                "url": clean, "depth": depth, "status": "error", "reason": rendered.get("reason", ""),
                "discovered_by": discovered_by,
            })
            continue
        markdown, title, links = _html_to_markdown(rendered["html"], clean)
        if login_if_needed and _looks_like_login_gate(title or "", markdown or rendered.get("text", ""), clean):
            if blocker_retries_used < max_auto_bypass_attempts:
                blocker_retries_used += 1
                seen.discard(clean)
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "retrying_gate",
                    "reason": "advanced bypass retry before human handoff",
                    "attempt": attempt,
                    "discovered_by": discovered_by,
                })
                queue.appendleft((clean, depth, discovered_by))
                continue
            if auth_handoffs >= max_auth_handoffs:
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "auth_exhausted",
                    "reason": "auth handoff limit reached",
                    "discovered_by": discovered_by,
                })
                continue
            auth_target = login_url or clean
            manual_engine = "chromium"
            login_result = lgwks_browser.save_session(
                auth_target,
                success_selector=success_selector,
                browser_engine=manual_engine,
                manual=True,
            )
            auth_handoffs += 1
            if not login_result.get("ok"):
                frontier.append({
                    "url": clean,
                    "depth": depth,
                    "status": "auth_failed",
                    "reason": login_result.get("reason", ""),
                    "discovered_by": discovered_by,
                })
                continue
            verify = lgwks_browser.render(
                clean,
                max_chars=120_000,
                use_session=True,
                wait_ms=5000,
                with_html=True,
                browser_engine=browser_engine,
            )
            if verify.get("ok") and verify.get("html"):
                v_md, v_title, _ = _html_to_markdown(verify["html"], clean)
                if not _looks_like_login_gate(v_title or "", v_md or verify.get("text", ""), clean):
                    seen.discard(clean)
                    queue.appendleft((clean, depth, discovered_by))
                    frontier.append({
                        "url": clean,
                        "depth": depth,
                        "status": "auth_verified",
                        "reason": login_result.get("reason", ""),
                        "discovered_by": discovered_by,
                    })
                    continue
            frontier.append({
                "url": clean,
                "depth": depth,
                "status": "auth_saved_but_failed",
                "reason": (
                    "session saved but headless render still shows a login gate; "
                    "site may block headless browsers or auth was incomplete — "
                    "try omitting --webkit, or capture the session in a normal browser and copy cookies"
                ),
                "discovered_by": discovered_by,
            })
            continue
        append_doc(
            source=clean,
            title=title or clean,
            text=markdown or rendered.get("text", ""),
            html_len=len(rendered["html"]),
            depth=depth,
            discovered_by=discovered_by,
        )
        frontier.append({
            "url": clean, "depth": depth, "status": "ok", "links_found": len(links),
            "discovered_by": discovered_by,
        })
        if depth >= max_depth:
            continue
        if crawl_mode == "link-only":
            click_allowed = False
        elif crawl_mode == "click-heavy":
            click_allowed = click_discovery
        else:
            click_allowed = click_discovery and _should_discover_clicks(clean, links)

        if click_discovery and not click_allowed:
            if crawl_mode == "link-only":
                reason = "crawl mode is link-only"
            elif crawl_mode == "link-then-click":
                reason = f"href frontier already productive ({len(links)} extracted links)"
            else:
                reason = "click discovery disabled or skipped"
            frontier.append({
                "url": clean,
                "depth": depth,
                "status": "click_skipped",
                "reason": reason,
                "discovered_by": clean,
                "links_found": len(links),
            })
        if click_allowed:
            click_rows = lgwks_browser.discover_clicks(
                clean,
                max_clicks=max_clicks_per_page,
                wait_ms=2500,
                browser_engine=browser_engine,
            )
            page_attempts = 0
            page_ok = 0
            page_timeouts = 0
            page_url_changes = 0
            page_content_only_changes = 0
            page_same_state = 0

            for row in click_rows:
                cand = row.get("candidate") or {}
                label = cand.get("text") or cand.get("href") or "click"
                final_url = _canonicalize_crawl_url(row.get("final_url") or clean)
                status = row.get("status", "error")
                text = row.get("text", "")
                reason = row.get("reason", "")

                page_attempts += 1
                is_timeout = "TimeoutError" in str(reason)
                if is_timeout:
                    page_timeouts += 1

                is_url_change = False
                is_content = False
                is_same_state = False

                if status == "ok":
                    page_ok += 1
                    if final_url != clean:
                        page_url_changes += 1
                        is_url_change = True
                    else:
                        seed_text = rendered.get("text", "")
                        if text != seed_text:
                            page_content_only_changes += 1
                            is_content = True
                        else:
                            page_same_state += 1
                            is_same_state = True

                frontier.append({
                    "url": final_url or clean,
                    "depth": depth + 1,
                    "status": f"click_{status}",
                    "reason": row.get("reason", label),
                    "discovered_by": clean,
                    "links_found": 0,
                    "click_telemetry": {
                        "is_url_change": is_url_change,
                        "is_content_only_change": is_content,
                        "is_same_state": is_same_state,
                        "is_timeout": is_timeout,
                        "target_info": {
                            "text": cand.get("text"),
                            "href": cand.get("href"),
                            "tag": cand.get("tag"),
                            "selector": f"[data-lgwks-click-id='{cand.get('id') if cand.get('id') is not None else ''}']"
                        }
                    }
                })
                if status != "ok" or not row.get("html"):
                    continue
                c_md, c_title, c_links = _html_to_markdown(row["html"], final_url or clean)
                if login_if_needed and _looks_like_login_gate(c_title or "", c_md or row.get("text", ""), final_url or clean):
                    frontier.append({
                        "url": final_url or clean,
                        "depth": depth + 1,
                        "status": "click_gate",
                        "reason": label,
                        "discovered_by": clean,
                        "links_found": len(c_links),
                    })
                    continue
                append_doc(
                    source=final_url or clean,
                    title=c_title or label,
                    text=c_md or row.get("text", ""),
                    html_len=row.get("html_len", 0),
                    depth=depth + 1,
                    discovered_by=clean,
                )
                final_host = urllib.parse.urlparse(final_url).hostname or ""
                if final_url and final_host == base_host and final_url not in seen:
                    queue.append((final_url, depth + 1, clean))
                if len(docs) >= max_pages:
                    break

            if page_attempts > 0:
                novelty_yield = round((page_url_changes + page_content_only_changes) / page_attempts, 4)
            else:
                novelty_yield = 0.0

            click_telemetry_by_page[clean] = {
                "attempts": page_attempts,
                "ok": page_ok,
                "timeouts": page_timeouts,
                "url_changes": page_url_changes,
                "content_only_changes": page_content_only_changes,
                "same_state": page_same_state,
                "novelty_yield": novelty_yield,
            }
        for link in links:
            href = _canonicalize_crawl_url(link.get("href", ""))
            host = urllib.parse.urlparse(href).hostname or ""
            if href and host == base_host and href not in seen:
                queue.append((href, depth + 1, clean))
    frontier.click_telemetry = click_telemetry_by_page
    return docs, frontier


def _crawl_map(frontier: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive a directed graph from the frontier: nodes = URLs, edges = parent-child."""
    url_state: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    for row in frontier:
        url = row.get("url", "")
        if url:
            url_state[url] = {
                "url": url,
                "depth": row.get("depth", 0),
                "status": row.get("status", ""),
                "links_found": row.get("links_found", 0),
            }
        parent = row.get("discovered_by", "")
        if parent and parent not in {"seed", "filesystem"} and url:
            key = (parent, url)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"from": parent, "to": url})
    return {"schema": "lgwks.substrate.crawl_map.v0", "nodes": list(url_state.values()), "edges": edges}


def _frontier_status_counts(frontier: list[dict[str, Any]]) -> dict[str, int]:
    """Count frontier entries by status."""
    counts: Counter[str] = Counter()
    for row in frontier:
        status = str(row.get("status", "") or "unknown")
        counts[status] += 1
    return dict(counts)
