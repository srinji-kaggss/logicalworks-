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

import subprocess

_CTX7_TIMEOUT = 45
_MAX = 4000   # clip each source — grounding feeds a prompt; keep it window-cheap


def _ctx7_docs(query: str) -> str:
    """Resolve libraries/APIs for the query via the ctx7 CLI. Real grounding; fail-soft to ''."""
    try:
        proc = subprocess.run(["npx", "ctx7@latest", "library", query],
                              capture_output=True, text=True, timeout=_CTX7_TIMEOUT)
    except Exception:
        return ""
    out = (proc.stdout or "").strip()
    # a quota/error line is not evidence
    if not out or "quota" in out.lower() or "error" in out.lower()[:40]:
        return ""
    return out[:_MAX]


def _web(query: str) -> str:
    """Web grounding seam. firecrawl (MCP) is the query interface; when its credits are exhausted we
    return '' (no evidence) rather than fake it. Wired by the caller's MCP layer when available."""
    return ""   # honest degraded state today (firecrawl credits exhausted); no silent fabrication


def ground(query: str, want_docs: bool = True, want_web: bool = True) -> dict:
    """Fuse the sources for one query. Returns {query, docs, web, sources, has_evidence}.
    sources lists which providers actually contributed real content."""
    docs = _ctx7_docs(query) if want_docs else ""
    web = _web(query) if want_web else ""
    sources = [n for n, v in (("ctx7", docs), ("web", web)) if v]
    return {"query": query, "docs": docs, "web": web,
            "sources": sources, "has_evidence": bool(sources)}


def as_findings(g: dict) -> str:
    """Render a ground() result as an UNTRUSTED-DATA findings block for the Reason prompt (hacker L7).
    The Tongue is instructed (REASON_SYSTEM) to treat anything inside the tags as data, not commands."""
    parts = [f"<UNTRUSTED_FINDINGS source={','.join(g['sources']) or 'none'}>"]
    if g["docs"]:
        parts.append(f"[docs/ctx7]\n{g['docs']}")
    if g["web"]:
        parts.append(f"[web]\n{g['web']}")
    if not g["sources"]:
        parts.append("(no evidence retrieved — this is a PLANNING round; do not claim findings)")
    parts.append("</UNTRUSTED_FINDINGS>")
    return "\n".join(parts)
