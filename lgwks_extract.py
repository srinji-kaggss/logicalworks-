"""
lgwks_extract — ingest every file format → text. The "read anything" port.

OpenAI Deep Research reads the SOURCE, not just the search snippet — PDFs, filings, docs. Three runs
proved we hit a PDF (the Value Partners acquisition press release lives as a PDF on greatwestlifeco.com)
and couldn't read it. This turns any URL or local file — pdf · docx · xlsx · pptx · html · csv · txt —
into bounded markdown/text the Tongue can reason over, picking the best extractor present (resolver).

Degrade chain per type, LOUD on total failure (never silently drop a source):
  pdf   : pdftotext (poppler) → pymupdf(fitz) → ""
  office: markitdown → ""    (docx/xlsx/pptx)
  html  : crwl md-fit → curl+strip
  text  : read directly
"""

from __future__ import annotations

import re
import ipaddress
import os
import socket
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from curl_cffi import requests as _curl
except Exception:
    _curl = None

try:
    import lgwks_capabilities as _cap
except Exception:
    _cap = None

from lgwks_substrate_config import TAG_RE as _TAG, WS_COLLAPSE_RE as _WS  # one source of truth

# ── bot-wall detection ────────────────────────────────────────────────────────

_WALL_RE = re.compile(
    r"unauthorized request|bot-traffic@|access denied|are you a (?:human|robot)|"
    r"verify you are (?:a )?human|please enable cookies and|ddos protection|"
    r"cf-browser-verification|cf-challenge|captcha|rate.?limit(?:ed)?|"
    r"request blocked|temporarily blocked|too many requests|"
    r"enable JavaScript|doesn't work properly without|requires JavaScript|"
    r"Just a moment|Attention Required",
    re.I,
)
_PDF_EXT = {".pdf"}
_OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
_TEXT_EXT = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".toml", ".ini", ".cfg", ".xml",
             # source files — a coding AI reads code constantly; label it honestly as text, not html.
             ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt", ".swift", ".rb", ".php",
             ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".sh", ".bash", ".zsh", ".sql", ".lua", ".r"}


def _bin(name: str) -> str | None:
    return _cap.find_binary(name) if _cap else None


def _trim(s: str, max_chars: int) -> str:
    return _WS.sub("\n\n", s).strip()[:max_chars]


def _ext_of(target: str) -> str:
    path = urllib.parse.urlparse(target).path if "://" in target else target
    return Path(path).suffix.lower()


def _is_url(target: str) -> bool:
    return bool(urllib.parse.urlparse(target).scheme)


def _is_http_url(target: str) -> bool:
    return urllib.parse.urlparse(target).scheme in {"http", "https"}


def _host_is_blocked(target: str) -> bool:
    host = urllib.parse.urlparse(target).hostname
    if not host:
        return True
    low = host.lower().rstrip(".")
    if low in {"localhost", "metadata.google.internal"} or low.endswith(".localhost"):
        return True
    candidates = [low]
    try:
        candidates.extend(info[4][0] for info in socket.getaddrinfo(low, None))
    except Exception:
        pass
    for candidate in set(candidates):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast,
                ip.is_reserved, ip.is_unspecified)):
            return True
        if str(ip) == "169.254.169.254":
            return True
    return False


def _remote_allowed(target: str) -> bool:
    return _is_http_url(target) and not _host_is_blocked(target)


def _headers(url: str) -> dict[str, str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        import lgwks_auth_runtime
        headers.update(lgwks_auth_runtime.headers_for_url(url))
    except Exception:
        pass
    return headers


# ── Safe redirect handler: strip auth when host changes (issue #14) ──────────────────────────
class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows redirects only when safe: strips Authorization/Cookie on cross-host jumps
    and re-applies the remote-allowed gate to the redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        orig_host = urllib.parse.urlparse(req.full_url).hostname or ""
        new_host = urllib.parse.urlparse(newurl).hostname or ""
        # Re-apply host-blocking policy to the destination
        if not _remote_allowed(newurl):
            raise urllib.error.HTTPError(
                newurl, code, f"Redirect to blocked host: {new_host}", headers, fp
            )
        # If host changes, strip credential headers before following
        if orig_host.lower() != new_host.lower():
            safe_headers = {
                k: v for k, v in req.headers.items()
                if k.lower() not in ("authorization", "cookie")
            }
            return urllib.request.Request(
                newurl,
                data=req.data,
                headers=safe_headers,
                origin_req_host=req.origin_req_host,
                unverifiable=True,
            )
        return urllib.request.Request(
            newurl,
            data=req.data,
            headers=dict(req.headers),
            origin_req_host=req.origin_req_host,
            unverifiable=True,
        )


def _opener() -> urllib.request.OpenerDirector:
    """Build an opener with the safe redirect handler installed."""
    return urllib.request.build_opener(_SafeRedirectHandler())


def _pdf(raw: bytes, max_chars: int) -> str:
    """pdftotext (stdin→stdout) first; pymupdf as fallback. Both bounded."""
    exe = _bin("pdftotext")
    if exe:
        try:
            p = subprocess.run([exe, "-layout", "-", "-"], input=raw, capture_output=True, timeout=40)
            txt = (p.stdout or b"").decode("utf-8", "replace").strip()
            if txt:
                return _trim(txt, max_chars)
        except Exception:
            pass
    try:
        import fitz  # pymupdf
        import io
        doc = fitz.open(stream=io.BytesIO(raw), filetype="pdf")
        return _trim("\n".join(page.get_text() for page in doc), max_chars)
    except Exception:
        return ""


def _office(local_path: str, max_chars: int) -> str:
    """markitdown handles docx/xlsx/pptx → markdown. Requires a local file path."""
    try:
        from markitdown import MarkItDown
        return _trim(MarkItDown().convert(local_path).text_content, max_chars)
    except Exception:
        return ""


# SPA/bot-wall sentinels: when the cheap floor returns these, the page needs a real (JS) browser.
_JS_WALL = re.compile(r"enable JavaScript|doesn't work properly without|requires JavaScript|"
                      r"Just a moment|Attention Required|cf-browser-verification", re.I)


def _html(url: str, max_chars: int) -> str:
    """The strict escalation ladder: Deterministic -> Sensor -> Generative.
    
    //why: Handoffs to a higher tier are ONLY used when the limit of the 
    previous gate is hit, and never before. (Performance & Determinism mandate).
    """
    if not _remote_allowed(url):
        return ""

    best = ""

    # GATE 1: Deterministic (crwl / Rust-based DOM-to-MD)
    exe = _bin("crwl")
    if exe:
        try:
            p = subprocess.run([exe, url, "-o", "md-fit"], capture_output=True, text=True, timeout=40)
            best = (p.stdout or "").strip()
        except Exception:
            pass

    # Check Gate 1 Success
    if best and not _WALL_RE.search(best[:1500]) and len(best) > 200:
        return _trim(best, max_chars)

    # GATE 2: Sensor / ML (Lightweight Extraction / Impersonation)
    if _curl:
        try:
            r = _curl.get(url, impersonate="chrome124", timeout=25, headers=_headers(url))
            if r.status_code == 200:
                import lgwks_html
                best = lgwks_html.html_to_markdown(r.text)
        except Exception:
            pass

    # Check Gate 2 Success
    if best and not _WALL_RE.search(best[:1500]) and len(best) > 200:
        return _trim(best, max_chars)

    # GATE 3: Generative (Vision / Qwen3-VL)
    # ONLY escalate to heavy LLM visual grounding if the page is completely locked
    try:
        import lgwks_search_engine
        res = lgwks_search_engine._ground_visually(url, "Extract core text and facts")
        if res.get("ok") and "fact" in res:
            return _trim(res["fact"]["content"], max_chars)
    except Exception:
        pass

    # Final validation failure
    import lgwks_auth_runtime
    lgwks_auth_runtime.note_auth_failure(url, 403)
    return ""


def _download(url: str) -> bytes:
    if not _remote_allowed(url):
        return b""
    try:
        req = urllib.request.Request(url, headers=_headers(url))
        with _opener().open(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        try:
            import lgwks_auth_runtime
            lgwks_auth_runtime.note_auth_failure(url, exc.code)
        except Exception:
            pass
        return b""
    except Exception:
        return b""


def extract(target: str, max_chars: int = 8000) -> dict:
    """Any URL or local path → {text, kind, ok, source}. ok=False is honest failure (never silent ext)."""
    ext = _ext_of(target)
    is_url = _is_url(target)
    if is_url and not _remote_allowed(target):
        kind = "unsupported-url-scheme" if not _is_http_url(target) else "blocked-host"
        return {"source": target, "kind": kind, "ok": False, "text": ""}
    kind, text = "html", ""

    if ext in _PDF_EXT:
        kind = "pdf"
        raw = _download(target) if is_url else Path(target).read_bytes() if Path(target).exists() else b""
        text = _pdf(raw, max_chars) if raw else ""
    elif ext in _OFFICE_EXT:
        kind = "office"
        local = target
        staged_tmp: str | None = None
        if is_url:  # markitdown needs a file → stage it
            raw = _download(target)
            if raw:
                # Hardening (#154 M1): use a private, unpredictable temp file
                # (0600, random name) instead of a fixed /tmp/lgwks-extract path,
                # and remove it afterward — closes the symlink/predictable-path
                # race and the disk leak.
                fd, staged_tmp = tempfile.mkstemp(prefix="lgwks-extract-", suffix=ext)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(raw)
                local = staged_tmp
        try:
            text = _office(local, max_chars)
        finally:
            if staged_tmp:
                try:
                    os.unlink(staged_tmp)
                except OSError:
                    pass
    elif ext in _TEXT_EXT and not is_url:
        kind = "text"
        text = _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else ""
    else:
        kind = "html"
        text = _html(target, max_chars) if is_url else (
            _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else "")

    result = {"source": target, "kind": kind, "ok": bool(text), "text": text}
    # Site-aware enrichment for supported platforms (Twitter/X, Reddit, Scholar)
    if is_url and text:
        try:
            import lgwks_sites
            site_data = lgwks_sites.extract_for_site(target, text)
            if site_data:
                result["site_data"] = site_data
                # If site extraction succeeded, update the text with the structured body
                if site_data.get("ok") and site_data.get("body"):
                    result["text"] = site_data["body"]
        except Exception:
            pass  # degrade gracefully — generic text is still useful
    return result
