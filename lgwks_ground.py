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
  web  = firecrawl (MCP) when credits exist, else degraded. We do NOT silently fake web evidence —
         a degraded web source contributes no evidence and says so.

has_evidence is True iff at least one source returned real content — the loop keys PLANNING vs
EVIDENCE off this, never off a model claim.
"""

from __future__ import annotations

import re
import subprocess

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


def _web(query: str) -> str:
    """Web grounding seam. firecrawl (MCP) is the query interface; when its credits are exhausted we
    return '' (no evidence) rather than fake it. Wired by the caller's MCP layer when available."""
    return ""   # honest degraded state today (firecrawl credits exhausted); no silent fabrication


def ground(query: str, want_docs: bool = True, want_web: bool = True) -> dict:
    """Fuse the sources for one query. Returns {query, docs, web, sources, has_evidence, doc_sources}.
    sources lists which providers actually contributed real content; doc_sources are the real
    citation URLs ctx7 attached to the docs body (verifiable, not model-claimed)."""
    docs, doc_sources = _ctx7_docs(query) if want_docs else ("", [])
    web = _web(query) if want_web else ""
    sources = [n for n, v in (("ctx7", docs), ("web", web)) if v]
    return {"query": query, "docs": docs, "web": web, "doc_sources": doc_sources,
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
