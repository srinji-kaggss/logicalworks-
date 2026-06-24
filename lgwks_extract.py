"""
lgwks_extract — ingest every file format → text. The "read anything" port.

OpenAI Deep Research reads the SOURCE, not just the search snippet — PDFs, filings, docs. Three runs
proved we hit a PDF (the Value Partners acquisition press release lives as a PDF on greatwestlifeco.com)
and couldn't read it. This turns any URL or local file — pdf · docx · xlsx · pptx · html · csv · txt —
into bounded markdown/text the Tongue can reason over, picking the best extractor present (resolver).

Degrade chain per type, LOUD on total failure (never silently drop a source):
  pdf   : pdftotext (poppler) → pymupdf(fitz) → render+OCR for image-only PDFs (poppler + Vision/tesseract)
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
# Image-only-PDF OCR tier: hard cap on pages rendered+OCR'd so a huge PDF can never
# run unbounded. The max_chars budget also early-stops once enough text is gathered.
_PDF_OCR_PAGE_CAP = 25
_PDF_OCR_DPI = 150
_OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
# Text-classification extensions via the canonical composition seam (#150 C-13):
# the shared set is the one source of truth (substrate_config.TEXT_EXT — includes
# .jsonl + all source exts); extract DECLARES ".log" as its local extra. Routing
# onto the canonical fixes the prior accidental drift where extract lacked ".jsonl":
# such a file is now classified kind="text" instead of kind="html" (the extracted
# text is identical — both branches read_text — only the label is corrected).
from lgwks_substrate_config import TEXT_EXT as _BASE_TEXT_EXT, with_extras, IMAGE_EXTS as _IMAGE_EXTS  # one source of truth
_TEXT_EXT = with_extras(_BASE_TEXT_EXT, ".log")


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


def _pdf_render_ocr(raw: bytes, max_chars: int, page_range: tuple[int, int] | None = None) -> str:
    """Image-only-PDF tier: render pages to images (poppler pdftoppm) and OCR each via
    the ONE canonical OCR port (lgwks_input._ocr_image_bytes: tesseract → macOS Vision).
    Local, zero-egress, zero new deps. Bounded by both _PDF_OCR_PAGE_CAP and max_chars
    (early-stops once the budget is reached). page_range=(first,last) (1-indexed) renders
    only that span — the resumability mechanism for truncated big-PDF extracts. Returns
    "" if poppler/OCR are unavailable or nothing is recognised."""
    pdftoppm = _bin("pdftoppm")
    if not pdftoppm:
        return ""
    try:
        import lgwks_input  # function-local: lgwks_input._try_pdf_text imports _pdf back → avoid import cycle
    except Exception:
        return ""
    if not lgwks_input._ocr_available():
        return ""
    first, last = page_range if page_range else (1, _PDF_OCR_PAGE_CAP)
    last = min(last, _PDF_OCR_PAGE_CAP)
    if last < first:
        return ""
    try:
        with tempfile.TemporaryDirectory() as td:
            fd, pdf_tmp = tempfile.mkstemp(suffix=".pdf", dir=td)
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
            prefix = os.path.join(td, "pg")
            r = subprocess.run(
                [pdftoppm, "-png", "-r", str(_PDF_OCR_DPI),
                 "-f", str(first), "-l", str(last), pdf_tmp, prefix],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                return ""
            chunks: list[str] = []
            total = 0
            for img in sorted(Path(td).glob("pg-*.png")):
                if total >= max_chars:
                    break
                text = lgwks_input._ocr_image_bytes(img.read_bytes(), timeout=60) or ""
                if text:
                    chunks.append(_dedup_chrome(text))
                    total += len(text)
            return _trim("\n\n".join(chunks), max_chars)
    except Exception:
        return ""


def _pdf_page_count(raw: bytes) -> int | None:
    """Cheap total-page probe via poppler pdfinfo (no rendering). None if unavailable.
    pdfinfo takes a FILE PATH (not stdin), so stage the bytes in a private temp file."""
    exe = _bin("pdfinfo")
    if not exe:
        return None
    pdf_tmp: str | None = None
    try:
        fd, pdf_tmp = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        p = subprocess.run([exe, pdf_tmp], capture_output=True, timeout=20)
        for line in (p.stdout or b"").decode("utf-8", "replace").splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    finally:
        if pdf_tmp:
            try:
                os.unlink(pdf_tmp)
            except OSError:
                pass
    return None


def _dedup_chrome(text: str) -> str:
    """Reclaim the char budget from repeated page chrome the OCR captures on every page
    (site nav, repeated table headers like 'Features'/'Minimum'). Conservative: only
    drops a line if it is identical to one already seen in THIS page AND it is short
    (<=48 chars) — the signature of repeated headers/labels, not prose. Legit repeated
    short values in a list are a tolerable, rare cost; the budget reclaimed for unique
    content is the win. Page-scoped (per OCR page), so cross-page prose is never touched."""
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s and len(s) <= 48 and s in seen:
            continue  # repeated short chrome — drop the duplicate
        if s and len(s) <= 48:
            seen.add(s)
        out.append(line)
    return "\n".join(out)


def _pdf(raw: bytes, max_chars: int, page_range: tuple[int, int] | None = None) -> str:
    """Degrade chain for PDF → text. Deterministic first, sensor last:
    pdftotext (text layer) → pymupdf (text layer) → render+OCR (image-only PDFs).
    All tiers bounded by max_chars; page_range (1-indexed) selects a span for
    resumability. Never egresses; never silently calls a cloud OCR."""
    exe = _bin("pdftotext")
    if exe:
        try:
            cmd = [exe, "-layout"]
            if page_range:
                cmd += ["-f", str(page_range[0]), "-l", str(page_range[1])]
            cmd += ["-", "-"]
            p = subprocess.run(cmd, input=raw, capture_output=True, timeout=40)
            txt = (p.stdout or b"").decode("utf-8", "replace").strip()
            if txt:
                return _trim(txt, max_chars)
        except Exception:
            pass
    try:
        import fitz  # pymupdf
        import io
        doc = fitz.open(stream=io.BytesIO(raw), filetype="pdf")
        if page_range:
            pages = doc[page_range[0] - 1:page_range[1]]
        else:
            pages = doc
        text = _trim("\n".join(page.get_text() for page in pages), max_chars)
        if text:
            return text
    except Exception:
        pass
    # Tier 3 — image-only PDF (no text layer): render pages and OCR locally.
    return _pdf_render_ocr(raw, max_chars, page_range=page_range)


def _strip_xml(xml: str) -> str:
    """XML/XHTML → readable text: turn block-level close tags into newlines, strip the
    rest, unescape entities. Stdlib only (re + html). Used by _zip_doc_text."""
    import html as _html
    xml = re.sub(r"</(?:p|div|tr|br|li|h[1-6]|table|sectPr)\s*>", "\n", xml, flags=re.I)
    text = _TAG.sub(" ", xml)
    text = _html.unescape(text)
    return text


_ZIP_DOC_EXT = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
                ".odt", ".odp", ".ods", ".epub"}


def _zip_doc_text(data: bytes, ext: str, max_chars: int) -> str:
    """Zero-dependency text extraction from ZIP-container documents
    (docx/xlsx/pptx/odt/ods/odp/epub) using only stdlib zipfile. This is the
    always-available tier behind markitdown in _office, and the primary path for
    .epub (markitdown does not read epubs). Never raises; bounded by max_chars.

    docx → word/document.xml (+ footnotes/endnotes)
    pptx → ppt/slides/slide*.xml
    xlsx → xl/sharedStrings.xml + xl/worksheets/sheet*.xml   (strings table + numbers)
    odt/odp/ods → content.xml
    epub  → OPS XHTML/HTML chapters"""
    import io as _io
    import zipfile
    try:
        zf = zipfile.ZipFile(_io.BytesIO(data))
        names = zf.namelist()
    except Exception:
        return ""
    ext = (ext or "").lower()
    # Normalize the hint to a routing subkind. Accept either a real extension
    # (.docx/...) or an already-classified subkind (docx/xlsx/pptx/odt/epub) from
    # the global URL content sniff, so URL-fetched zips with no extension route
    # correctly. Unknown hint → auto-detect from the namelist.
    if ext in {".docx", ".doc"}:
        ext = "docx"
    elif ext in {".pptx", ".ppt"}:
        ext = "pptx"
    elif ext in {".xlsx", ".xls"}:
        ext = "xlsx"
    elif ext in {".odt", ".odp", ".ods"}:
        ext = "odt"
    elif ext == ".epub":
        ext = "epub"
    if ext not in {"docx", "pptx", "xlsx", "odt", "epub"}:
        ext = _zip_subkind(data)  # auto-detect by peeking inside
    if ext == "docx":
        pick = [n for n in names if n in ("word/document.xml",
                                          "word/footnotes.xml", "word/endnotes.xml")]
    elif ext == "pptx":
        pick = [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
    elif ext == "xlsx":
        pick = [n for n in names if n == "xl/sharedStrings.xml"]
        pick += [n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    elif ext == "odt":
        pick = [n for n in names if n == "content.xml"]
    elif ext == "epub":
        pick = [n for n in names if n.endswith((".xhtml", ".html", ".htm"))
                and "nav" not in os.path.basename(n).lower()]
    else:
        pick = [n for n in names if n.endswith((".xml", ".xhtml", ".html", ".htm"))][:60]
    parts: list[str] = []
    try:
        for n in pick:
            parts.append(_strip_xml(zf.read(n).decode("utf-8", "replace")))
    except Exception:
        pass
    joined = "\n".join(p for p in parts if p and p.strip())
    return _trim(joined, max_chars)


def _office(local_path: str, max_chars: int) -> str:
    """docx/xlsx/pptx → markdown. Tier 1: markitdown (richest, when installed).
    Tier 2: stdlib zipfile extraction (always available, zero deps). Both bounded."""
    try:
        from markitdown import MarkItDown
        text = _trim(MarkItDown().convert(local_path).text_content, max_chars)
        if text:
            return text
    except Exception:
        pass
    try:
        return _zip_doc_text(Path(local_path).read_bytes(), Path(local_path).suffix, max_chars)
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


def _zip_subkind(raw: bytes) -> str:
    """Peek inside a ZIP container to classify it as a routing kind: epub / docx /
    xlsx / pptx / odt / office(generic). Used by the global content sniff for
    URL-fetched zips whose extension is unknown or misleading (e.g. a publisher
    serving an .xlsx at /export/123). Never raises."""
    import io as _io
    import zipfile
    try:
        zf = zipfile.ZipFile(_io.BytesIO(raw))
        names = zf.namelist()
    except Exception:
        return "office"
    if "mimetype" in names:
        try:
            mt = zf.read("mimetype").decode("utf-8", "replace").strip().lower()
        except Exception:
            mt = ""
        if "epub" in mt:
            return "epub"
        if "opendocument" in mt:
            return "odt"
    if any(n.startswith("word/") for n in names):
        return "docx"
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    if any(n.startswith("ppt/") for n in names):
        return "pptx"
    return "office"


def _sniff_url_kind(url: str) -> tuple[str, bytes]:
    """GLOBAL content detection for a URL: stream the leading bytes and classify by
    what they ARE (magic bytes), not by any URL pattern or substring. Returns
    (kind, body): body is the full fetched bytes for document kinds
    (pdf/epub/office/image) and b"" for html/unknown (the caller defers to the HTML
    ladder, which re-fetches with crwl/curl/VL quality). One connection for documents,
    a 1KB probe for pages. Definitive extensions are routed earlier as fast-paths; the
    sniff is the global truth for ambiguous URLs (arxiv /pdf/<id>, doi redirects,
    publisher /article/<doi>, scholar result links, shortened links) — it works for
    everything because it reads the bytes, not the URL."""
    if not _remote_allowed(url):
        return ("html", b"")
    try:
        from lgwks_input import _sniff_mime  # canonical magic sniffer — one source of truth
    except Exception:
        _sniff_mime = None  # type: ignore[assignment]
    try:
        req = urllib.request.Request(url, headers=_headers(url))
        with _opener().open(req, timeout=30) as resp:
            head = resp.read(1024)
            if not head:
                return ("html", b"")
            if head[:4] == b"%PDF":
                return ("pdf", head + resp.read())
            if head[:2] == b"PK":
                full = head + resp.read()
                return (_zip_subkind(full), full)
            if _sniff_mime and _sniff_mime(head).startswith("image/"):
                return ("image", head + resp.read())
            return ("html", b"")  # html/text/unknown → defer to the _html ladder
    except urllib.error.HTTPError as exc:
        try:
            import lgwks_auth_runtime
            lgwks_auth_runtime.note_auth_failure(url, exc.code)
        except Exception:
            pass
        return ("html", b"")
    except Exception:
        return ("html", b"")


def extract(target: str, max_chars: int = 8000, page_range: tuple[int, int] | None = None) -> dict:
    """Any URL or local path → text envelope. ok=False is honest failure (never silent ext).

    Envelope (additive over the original {source,kind,ok,text}; existing consumers unaffected):
      truncated   bool  — hit the max_chars cap; the source almost certainly has more.
                          Never let a consumer mistake a slice for the whole (experience fix).
      chars       int   — len(text), for quick budget reasoning without re-measuring.
      pages       str   — "a–b" pages actually read, when known (PDF).
      total_pages int|None — full document page count, when cheaply probeable (PDF via pdfinfo).
    page_range=(first,last) (1-indexed) selects a PDF span — the resumability mechanism:
    on truncation, re-run with --pages (last_read+1)–total_pages to continue."""
    ext = _ext_of(target)
    is_url = _is_url(target)
    if is_url and not _remote_allowed(target):
        kind = "unsupported-url-scheme" if not _is_http_url(target) else "blocked-host"
        return {"source": target, "kind": kind, "ok": False, "text": "", "truncated": False, "chars": 0}
    kind, text = "html", ""
    pages_read: tuple[int, int] | None = None
    total_pages: int | None = None

    if ext in _PDF_EXT:
        kind = "pdf"
        raw = _download(target) if is_url else Path(target).read_bytes() if Path(target).exists() else b""
        if raw:
            total_pages = _pdf_page_count(raw)
            text = _pdf(raw, max_chars, page_range=page_range)
            if page_range:
                pages_read = page_range  # explicit range — accurately reported
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
    elif ext in _IMAGE_EXTS:
        # Image file (png/jpg/...) → OCR via the SAME canonical port the PDF-render
        # tier uses (lgwks_input._ocr_image_bytes). Never returns raw image bytes as
        # "text" (which previously surfaced as binary garbage @ ok=True).
        kind = "image"
        raw = _download(target) if is_url else (Path(target).read_bytes() if Path(target).exists() else b"")
        if raw:
            try:
                import lgwks_input  # function-local: same OCR primitive, no second path
                text = lgwks_input._ocr_image_bytes(raw, timeout=60) or ""
            except Exception:
                text = ""
        else:
            text = ""
    elif ext == ".epub":
        # EPUB is a ZIP of XHTML chapters — extract the readable text, never the
        # raw container bytes (which previously surfaced as binary garbage @ ok=True).
        kind = "epub"
        raw = _download(target) if is_url else (Path(target).read_bytes() if Path(target).exists() else b"")
        text = _zip_doc_text(raw, ext, max_chars) if raw else ""
    elif ext in _TEXT_EXT and not is_url:
        kind = "text"
        text = _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else ""
    else:
        # AMBIGUOUS target — extension didn't match a definitive kind. Route by
        # CONTENT, not URL pattern (the global engine): for URLs, sniff the actual
        # bytes and dispatch to the matching extractor; anything that isn't a
        # document (html/text/unknown) defers to the _html escalation ladder.
        # This is what makes scholar result links, doi redirects, publisher
        # /article/<doi>, arxiv /pdf/<id>, and shortened links all work — they're
        # classified by what the bytes ARE, not by a brittle URL substring.
        if is_url:
            skind, sbytes = _sniff_url_kind(target)
            if skind == "pdf":
                kind, text = "pdf", _pdf(sbytes, max_chars, page_range=page_range)
                if sbytes:
                    total_pages = _pdf_page_count(sbytes)
                    if page_range:
                        pages_read = page_range  # explicit range — accurately reported
            elif skind in ("epub", "docx", "xlsx", "pptx", "odt", "office"):
                kind, text = ("epub" if skind == "epub" else "office"), _zip_doc_text(sbytes, skind, max_chars)
            elif skind == "image":
                kind = "image"
                try:
                    import lgwks_input
                    text = lgwks_input._ocr_image_bytes(sbytes, timeout=60) or ""
                except Exception:
                    text = ""
            else:  # html / unknown → the HTML escalation ladder (crwl → curl → VL)
                kind, text = "html", _html(target, max_chars)
        else:
            # local file with an unrecognized extension: read as text.
            kind = "html"
            text = _trim(Path(target).read_text(errors="replace"), max_chars) if Path(target).exists() else ""

    # Truncation signal (experience fix): if the output hit the char cap, the source
    # almost certainly has more — flag it so a consumer never mistakes a slice for the
    # whole. len(text) >= max_chars is a reliable cap-hit indicator for the bounded tiers.
    truncated = bool(text) and len(text) >= max_chars
    result = {"source": target, "kind": kind, "ok": bool(text), "text": text,
              "truncated": truncated, "chars": len(text)}
    if pages_read:
        result["pages"] = f"{pages_read[0]}\u2013{pages_read[1]}"
    if total_pages is not None:
        result["total_pages"] = total_pages
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
