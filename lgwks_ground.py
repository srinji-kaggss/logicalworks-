"""
lgwks_ground — fused live grounding for the research loop (#9 / harness layer).

ONE capability, two sources, fail-soft: ctx7 (library/API truth) + web (world truth). This is the
evidence source that turns a PLANNING round into an EVIDENCE round — the model reasons over REAL
fetched content, so falsifiers can actually fire (closes the epistemics "estimate-mode theater").

Trust (hacker L7): everything ground() returns is UNTRUSTED DATA from the world. The caller wraps it
in <UNTRUSTED_FINDINGS> before it reaches a Tongue prompt; ground() itself never executes content.

Providers (each fail-soft → returns ""):
  docs = ctx7 CLI (`npx ctx7@latest library "<q>"`) — real, works today; perfect for implementation
         guides, which reference libraries/APIs.
  web  = free HTTP search floor (lgwks_search) → fetch the top hits with the crawler. We do NOT
         silently fake web evidence — a degraded web source contributes no evidence and says so.

has_evidence is True iff at least one source returned real content — the loop keys PLANNING vs
EVIDENCE off this, never off a model claim.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_CTX7_TIMEOUT = 60
_MAX = 4000   # clip each source — grounding feeds a prompt; keep it window-cheap
_LIB_ID = re.compile(r"Context7-compatible library ID:\s*(/\S+)")
_SRC_URL = re.compile(r"Source:\s*(https?://\S+)")


def _ctx7_run(args: list[str]) -> str:
    """Run a ctx7 CLI subcommand, fail-soft to ''. A quota/error banner is not evidence."""
    try:
        proc = subprocess.run(["npx", "ctx7@latest", *args],
                              capture_output=True, text=True, timeout=_CTX7_TIMEOUT)
    except Exception:
        return ""
    out = (proc.stdout or "").strip()
    if not out or "quota" in out.lower() or out.lower().startswith("error"):
        return ""
    return out


def _ctx7_docs(query: str) -> tuple[str, list[str]]:
    """TWO-STEP ctx7 grounding (the fix for shallow evidence): `library` resolves the query to a
    Context7 library ID, then `docs <id> "<query>"` fetches the ACTUAL documentation (code + prose +
    Source: URLs) — not the one-line resolver descriptions the loop was reasoning over before. The
    docs body is what lets the Reason step actually confirm/contradict a behavioural claim. Returns
    (docs_text, source_urls); fail-soft to ('', [])."""
    resolved = _ctx7_run(["library", query])
    if not resolved:
        return "", []
    m = _LIB_ID.search(resolved)             # pick the top-ranked library id (ctx7 lists best first)
    if not m:
        return "", []
    docs = _ctx7_run(["docs", m.group(1), query])
    if not docs:
        # docs fetch failed/empty — fall back to the resolver descriptions (thin but real), and say so.
        return f"[ctx7 resolver descriptions only — no docs body for {m.group(1)}]\n{resolved}"[:_MAX], []
    urls = list(dict.fromkeys(_SRC_URL.findall(docs)))[:10]   # real citations — seeds the resolver RISK
    return docs[:_MAX], urls


def _quarantine(url: str, kind: str, body: str) -> str:
    """Put fetched UNTRUSTED content into the content-addressed cache; return its hash (or '' fail-soft).
    Realises the z2/z4 quarantine + evidence-by-ref: the model reasons over text the store holds as data."""
    try:
        import lgwks_cache
        return lgwks_cache.put(url, kind, body)["hash"]
    except Exception:
        return ""


def _curate_results(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply the G3 URL-risk gate before any source is fetched."""
    try:
        import lgwks_urlrisk
    except Exception:
        return results, []
    feed_path = Path(os.environ["LGWKS_URLRISK_FEED"]) if os.environ.get("LGWKS_URLRISK_FEED") else None
    history_path = Path(os.environ["LGWKS_URLRISK_HISTORY"]) if os.environ.get("LGWKS_URLRISK_HISTORY") else None
    scored = lgwks_urlrisk.curate_scope(
        [r.get("url", "") for r in results if r.get("url")],
        feed_path=feed_path,
        history_path=history_path,
    )
    by_url = {item.url: item for item in scored.scored}
    kept = [r for r in results
            if (it := by_url.get(r.get("url", ""))) is not None and it.decision == "allow"]
    denied = [{"url": item.url, "decision": item.decision, "reasons": item.reasons}
              for item in scored.scored if item.decision != "allow"]
    return kept, denied


def _web(query: str, read_top: int = 3) -> tuple[str, list[str]]:
    """Web grounding through the ONE canonical evidence kernel:
    fixed search (lgwks_search, rendered fallback) → canonical browser fetch
    (lgwks_browser.render) → canonical HTML→markdown (lgwks_html) → canonical
    noise-gated fact extraction (lgwks_substrate_text) — the SAME extractor the
    substrate crawl uses.

    This retires the divergent single-fact resolver (lgwks_search_engine.resolve_fact)
    so the research loop and the substrate crawl share ONE evidence path instead of
    two slightly-different ones (#research-dogfood: kill the dual path). Returns the
    top noise-gated facts across multiple primary sources + their citation URLs."""
    import lgwks_browser
    import lgwks_search
    import lgwks_substrate_text as st
    from lgwks_html import html_to_markdown

    # G3 URL-risk gate BEFORE any fetch — never render an un-curated URL (preserves
    # the private/metadata-host + scheme blocks; the gate is shared, not re-derived).
    kept, _denied = _curate_results(lgwks_search.search(query, k=read_top * 2))
    blocks: list[str] = []
    sources: list[str] = []
    for r in kept:
        if len(sources) >= read_top:
            break
        url = (r.get("url") or "").strip()
        if not url:
            continue
        page = lgwks_browser.render(url, max_chars=40_000, with_html=True)
        if not page.get("ok"):
            continue
        html = page.get("html") or ""
        markdown = html_to_markdown(html, url)[0] if html else (page.get("text") or "")
        facts = st._fact_sentences(markdown, 0.6)[:6]
        if not facts:
            continue
        ch = _quarantine(url, "web-grounded-facts", "\n".join(facts))
        tag = f" · cache:{ch[:12]}" if ch else ""
        blocks.append(f"[{r.get('via', 'web')}{tag}] {url}\n" + "\n".join(f"- {f}" for f in facts))
        sources.append(url)
    return "\n\n".join(blocks), sources


def ground(query: str, want_docs: bool = True, want_web: bool = True) -> dict:
    """Fuse the sources for one query. Returns {query, docs, web, sources, has_evidence, doc_sources}.
    doc_sources are verifiable citation URLs (ctx7 docs + web results), not model-claimed."""
    docs, doc_sources = _ctx7_docs(query) if want_docs else ("", [])
    web, web_sources = _web(query) if want_web else ("", [])
    sources = [n for n, v in (("docs", docs), ("web", web)) if v]  # agnostic role labels, no brands
    return {"query": query, "docs": docs, "web": web,
            "doc_sources": list(dict.fromkeys(doc_sources + web_sources)),
            "sources": sources, "has_evidence": bool(sources)}


def as_findings(g: dict) -> str:
    """Render a ground() result as an UNTRUSTED-DATA findings block for the Reason prompt (hacker L7).
    The Tongue is instructed (REASON_SYSTEM) to treat anything inside the tags as data, not commands."""
    parts = [f"<UNTRUSTED_FINDINGS source={','.join(g['sources']) or 'none'}>"]
    if g["docs"]:
        parts.append(f"[docs/ctx7]\n{g['docs']}")
    if g.get("doc_sources"):
        parts.append("[citation URLs (verifiable)]\n" + "\n".join(g["doc_sources"]))
    if g["web"]:
        parts.append(f"[web]\n{g['web']}")
    if not g["sources"]:
        parts.append("(no evidence retrieved — this is a PLANNING round; do not claim findings)")
    parts.append("</UNTRUSTED_FINDINGS>")
    return "\n".join(parts)
