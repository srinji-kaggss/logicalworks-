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
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import lgwks_capabilities as _cap
except Exception:
    _cap = None

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n{3,}")
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
    """crwl md-fit → curl floor → escalate to a real browser (playwright) on a JS/bot wall.
    The escalation is the fix for SPAs like canadalife.com that return 'enable JavaScript'."""
    best = ""
    exe = _bin("crwl")
    if exe:
        try:
            p = subprocess.run([exe, url, "-o", "md-fit"], capture_output=True, text=True, timeout=40)
            best = (p.stdout or "").strip()
        except Exception:
            pass
    if not best:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            best = _TAG.sub("", urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace"))
        except Exception:
            best = ""
    # escalate to the real browser if we got nothing or hit a JS/bot wall.
    if not best or _JS_WALL.search(best[:1500]):
        try:
            import lgwks_browser
            r = lgwks_browser.render(url, max_chars=max_chars)
            if r["ok"] and r["text"]:
                return _trim(r["text"], max_chars)
        except Exception:
            pass
    return _trim(best, max_chars)


def _download(url: str) -> bytes:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        return b""


def extract(target: str, max_chars: int = 8000) -> dict:
    """Any URL or local path → {text, kind, ok, source}. ok=False is honest failure (never silent ext)."""
    ext = _ext_of(target)
    is_url = "://" in target
    kind, text = "html", ""

    if ext in _PDF_EXT:
        kind = "pdf"
        raw = _download(target) if is_url else Path(target).read_bytes() if Path(target).exists() else b""
        text = _pdf(raw, max_chars) if raw else ""
    elif ext in _OFFICE_EXT:
        kind = "office"
        local = target
        if is_url:  # markitdown needs a file → stage it
            raw = _download(target)
            if raw:
                tmp = Path(f"/tmp/lgwks-extract{ext}")
                tmp.write_bytes(raw)
                local = str(tmp)
        text = _office(local, max_chars)
    elif ext in _TEXT_EXT and not is_url:
        kind = "text"
        text = _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else ""
    else:
        kind = "html"
        text = _html(target, max_chars) if is_url else (
            _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else "")

    return {"source": target, "kind": kind, "ok": bool(text), "text": text}
