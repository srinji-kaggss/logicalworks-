"""
lgwks_capabilities — the resolver that fixes "the tool isn't where it should be."

The googler incident is the general disease: code assumed a binary on PATH, it wasn't installed
anywhere, and the CLI SILENTLY no-op'd (lgwks:569 fallback) — three research runs found nothing and
never said why. The cure is a capability resolver that (1) probes WIDELY — PATH plus the real install
locations Homebrew/pipx/npm/~/.local scatter binaries into — (2) picks the BEST present provider per
capability via an explicit degrade chain, and (3) degrades LOUDLY: when nothing is present it tells you
the exact install command, never a silent empty result.

This is the engine model (SPEC §2) made operational: each capability is a port; providers are ranked;
the resolver reports what's wired and what's missing so `lgwks doctor` is the one-look truth.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Where Homebrew (arm+intel), pipx, npm-global, mise, and user installs actually drop binaries — the
# "right place" is many places. PATH is necessary, not sufficient (the googler lesson).
_EXTRA_DIRS = [
    "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
    str(Path.home() / ".local/bin"),
    str(Path.home() / ".local/pipx/venvs"),  # pipx app shims live under bin/ per venv
    "/opt/homebrew/opt",
]


def find_binary(name: str) -> str | None:
    """which() FIRST (honours the live PATH), then the scatter dirs. Returns abs path or None.
    This is the fix for 'installed but not on PATH' — we look where installers actually put things."""
    hit = shutil.which(name)
    if hit:
        return hit
    for d in _EXTRA_DIRS:
        p = Path(d) / name
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
        # pipx: <venvs>/<name>/bin/<name>
        pv = Path(d) / name / "bin" / name
        if pv.exists() and os.access(pv, os.X_OK):
            return str(pv)
    return None


# Each capability = an ordered provider chain (best first) + the install hint if NONE are present.
# VENDOR-AGNOSTIC: providers carry an architectural `id` (role/mechanism, what callers see) and an
# internal `bin`/`mod` (the actual tool to invoke — never surfaced). Strip brands from the surface;
# keep only the capability. Order encodes "use the best present tool." (Director: strip vendor names.)
_CAPABILITIES: dict[str, dict] = {
    "search": {
        "why": "find live-world facts (news, acquisitions, entities) — the eyes",
        "providers": [
            {"id": "keyed", "kind": "bin", "bin": "firecrawl", "note": "keyed API; richest, metered"},
            {"id": "rendered", "kind": "pymod", "mod": "playwright",
             "note": "results via real browser — survives blocks (the around-the-block path)"},
            {"id": "cli", "kind": "any-bin", "bins": ["ddgr", "googler"], "note": "search CLI if present"},
            {"id": "open", "kind": "builtin", "note": "open HTML endpoint via http — zero-dep floor"},
        ],
        "install": "(none needed — 'open' floor always works; 'rendered' uses the browser capability)",
    },
    "fetch": {
        "why": "turn a URL into clean text",
        "providers": [
            {"id": "crawler", "kind": "bin", "bin": "crwl", "note": "markdown-fit extraction"},
            {"id": "raw", "kind": "builtin", "note": "http + strip — raw floor"},
        ],
        "install": "pipx install crawl4ai",
    },
    "browser": {
        "why": "bot-resilient, JS-rendering fetch of SPA/auth-gated pages",
        "providers": [
            {"id": "headless", "kind": "pymod", "mod": "playwright", "note": "real browser engine"},
        ],
        "install": "pipx install playwright && playwright install chromium",
    },
    "extract": {
        "why": "ingest every file format (pdf, docx, xlsx, pptx) → text",
        "providers": [
            {"id": "pdf", "kind": "bin", "bin": "pdftotext", "note": "fast pdf→text"},
            {"id": "pdf-layout", "kind": "pymod", "mod": "fitz", "note": "layout-aware pdf"},
            {"id": "any-format", "kind": "pymod", "mod": "markitdown", "note": "office → markdown"},
        ],
        "install": "brew install poppler && pipx install markitdown",
    },
}


def _present(p: dict) -> str | None:
    """Resolve a provider to its internal location (never surfaced) or None. Probes at call time."""
    kind = p["kind"]
    if kind == "builtin":
        return p["id"]
    if kind == "bin":
        return find_binary(p["bin"])
    if kind == "any-bin":
        for b in p.get("bins", []):
            hit = find_binary(b)
            if hit:
                return hit
        return None
    if kind == "pymod":
        try:
            __import__(p["mod"])
            return f"mod:{p['mod']}"
        except Exception:
            return None
    return None


def resolve(capability: str) -> dict:
    """Pick the best present provider. Returns {capability, chosen(=agnostic id), path, chain, missing,
    install}. chosen=None means LOUD failure — install hint included, never a silent empty. The `path`
    (internal tool location) is kept for invocation but the surfaced identity is the agnostic id."""
    spec = _CAPABILITIES.get(capability)
    if not spec:
        return {"capability": capability, "chosen": None, "error": "unknown capability"}
    chain = []
    chosen = None
    where = None
    for p in spec["providers"]:
        loc = _present(p)
        chain.append({"id": p["id"], "present": bool(loc), "note": p["note"]})  # id, not brand
        if loc and not chosen:
            chosen, where = p["id"], loc
    return {"capability": capability, "why": spec["why"], "chosen": chosen, "path": where,
            "chain": chain, "missing": chosen is None, "install": spec["install"]}


def doctor() -> list[dict]:
    """Resolve every capability — the one-look truth of what's wired and what to install."""
    return [resolve(c) for c in _CAPABILITIES]


def best(capability: str) -> str | None:
    """Convenience: just the chosen provider name (or None). Callers branch on this, loudly."""
    return resolve(capability)["chosen"]
