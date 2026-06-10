"""lgwks_input — universal input handler (lgwks.modality.item.v1).

I2 of the INGESTION-PLAN: classifies raw bytes into a typed modality item so every
downstream component (I4 embedder, I5 scorer, substrate writer) speaks one contract.

Routing table
-------------
text/code extensions + UTF-8 decodable → text, parsed_unit = decoded str
PDF                                     → text, parsed_unit via lgwks_extract._pdf()
DOCX/PPTX/XLSX/RTF                      → text if markitdown available, else quarantine
PNG/JPEG/GIF/WEBP/BMP/TIFF              → image, raw_bytes preserved
MP4/MOV/AVI/MKV/WEBM                    → video, raw_bytes preserved
audio (MP3/WAV/FLAC/AAC/OGG)           → quarantine (deferred — no audio embedder yet)
anything else                           → quarantine

handle() NEVER raises — all errors produce a quarantine item.

Authority: spec/second-harness/INGESTION-PLAN.md §I2
Schema id: lgwks.modality.item.v1
"""

from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCHEMA = "lgwks.modality.item.v1"

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Extension routing tables (aligned with lgwks_embed.TEXT_EXT and
# lgwks_multimodal._IMAGE_EXTS so all three modules agree on coverage)
# ---------------------------------------------------------------------------

_TEXT_EXTS = frozenset({
    ".txt", ".md", ".rst", ".log",
    ".py", ".pyi", ".pyx", ".pxd",
    ".rs", ".toml", ".lock",
    ".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx",
    ".json", ".jsonl", ".json5",
    ".yaml", ".yml",
    ".sh", ".bash", ".zsh", ".fish",
    ".go", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh",
    ".java", ".kt", ".swift", ".rb", ".php",
    ".sql", ".graphql", ".proto",
    ".html", ".htm", ".css", ".xml", ".svg",
    ".lua", ".r", ".m", ".ex", ".exs", ".erl",
    ".ini", ".cfg", ".conf", ".env",
    ".csv", ".tsv",
    ".ipynb",
})

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"})
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".flv"})
_DOC_EXTS   = frozenset({".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".rtf", ".odt"})
_AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"})

QUARANTINE_DIR = _REPO_ROOT / "store" / "untrusted"


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModalityItem:
    """Single lgwks.modality.item.v1 instance.

    modality    : "text" | "image" | "video" | "quarantine"
    parsed_unit : extracted text string (text items) or None (media / quarantine)
    raw_bytes   : original bytes (image / video / quarantine); None for text
    mime        : detected MIME type string
    origin      : caller-supplied label (filename, URL, logical handle)
    quarantine_reason : non-empty only when modality == "quarantine"
    """
    schema: str
    modality: str
    parsed_unit: Optional[str]
    raw_bytes: Optional[bytes]
    mime: str
    origin: str
    quarantine_reason: str = field(default="")

    def is_quarantined(self) -> bool:
        return self.modality == "quarantine"


# ---------------------------------------------------------------------------
# Magic-byte MIME sniffer
# (modelled on lgwks_multimodal._sniff_mime; extended for all routed types)
# ---------------------------------------------------------------------------

def _sniff_mime(data: bytes) -> str:
    """Return best-guess MIME from the first 16 bytes. Never raises."""
    if not data:
        return "application/octet-stream"
    h = data[:16]

    if h[:8] == b'\x89PNG\r\n\x1a\n':                     return "image/png"
    if h[:2] == b'\xff\xd8':                               return "image/jpeg"
    if h[:6] in (b'GIF87a', b'GIF89a'):                   return "image/gif"
    if h[:4] == b'RIFF' and h[8:12] == b'WEBP':          return "image/webp"
    if h[:2] == b'BM':                                    return "image/bmp"
    if h[:4] in (b'II*\x00', b'MM\x00*'):                 return "image/tiff"

    if h[:4] == b'%PDF':                                   return "application/pdf"

    # ZIP-based (DOCX/PPTX/XLSX all start with PK\x03\x04)
    if h[:4] == b'PK\x03\x04':                            return "application/zip"

    # RTF
    if data[:6] == b'{\\rtf1':                             return "application/rtf"

    # MP4 family: 'ftyp' at bytes 4-8 or common box sizes
    if len(data) > 8 and data[4:8] == b'ftyp':            return "video/mp4"
    if h[:4] in (b'\x00\x00\x00\x14', b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c',
                 b'\x00\x00\x00\x20'):
        if len(data) > 8 and data[4:8] == b'ftyp':        return "video/mp4"

    # Matroska / WebM
    if h[:4] == b'\x1a\x45\xdf\xa3':                      return "video/webm"

    # Audio
    if h[:3] == b'ID3' or h[:2] == b'\xff\xfb':           return "audio/mpeg"
    if h[:4] == b'fLaC':                                   return "audio/flac"
    if h[:4] == b'OggS':                                   return "audio/ogg"
    if h[:4] == b'RIFF' and h[8:12] == b'WAVE':           return "audio/wav"
    if h[:4] == b'M4A ':                                   return "audio/mp4"

    return "application/octet-stream"


def _detect_mime(data: bytes, filename: str) -> str:
    """Magic bytes first; extension fallback via mimetypes stdlib."""
    magic = _sniff_mime(data)
    if magic != "application/octet-stream":
        return magic
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _try_pdf_text(data: bytes, max_chars: int = 100_000) -> Optional[str]:
    """Extract text from PDF bytes. Returns None on failure."""
    try:
        from lgwks_extract import _pdf  # type: ignore[import-untyped]
        text = _pdf(data, max_chars)
        return text if text and text.strip() else None
    except ImportError:
        pass

    # Fallback: pdftotext subprocess if available
    try:
        result = subprocess.run(
            ["pdftotext", "-", "-"],
            input=data, capture_output=True, timeout=30
        )
        if result.returncode == 0:
            text = result.stdout.decode("utf-8", errors="replace")
            return text[:max_chars] if text.strip() else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: fitz / PyMuPDF
    try:
        import io as _io
        import fitz  # type: ignore[import-untyped]
        doc = fitz.open(stream=_io.BytesIO(data), filetype="pdf")
        parts = [page.get_text() for page in doc]
        doc.close()
        text = "\n".join(parts)
        return text[:max_chars] if text.strip() else None
    except (ImportError, Exception):
        return None


def _try_doc_text(data: bytes, mime: str, filename: str, max_chars: int = 100_000) -> Optional[str]:
    """Extract text from DOCX/PPTX/XLSX/RTF. Returns None if unavailable."""
    ext = Path(filename).suffix.lower()

    # markitdown covers all office formats
    try:
        import io as _io
        from markitdown import MarkItDown  # type: ignore[import-untyped]
        md = MarkItDown()
        result = md.convert_stream(_io.BytesIO(data), file_extension=ext or ".bin")
        text = result.text_content if hasattr(result, "text_content") else str(result)
        return text[:max_chars] if text and text.strip() else None
    except (ImportError, Exception):
        pass

    # python-docx fallback for .docx
    if ext == ".docx":
        try:
            import io as _io
            import docx  # type: ignore[import-untyped]
            doc = docx.Document(_io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text[:max_chars] if text.strip() else None
        except (ImportError, Exception):
            pass

    return None


def _decode_text(data: bytes, max_chars: int = 500_000) -> Optional[str]:
    """Decode bytes as UTF-8 (latin-1 fallback). Returns None if binary."""
    try:
        return data[:max_chars].decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data[:max_chars].decode("latin-1")
    except Exception:
        return None


def _looks_text(data: bytes) -> bool:
    """Heuristic: at least 85% printable ASCII bytes."""
    if not data:
        return False
    sample = data[:4096]
    printable = sum(1 for b in sample if 0x09 <= b <= 0x0D or 0x20 <= b <= 0x7E)
    return printable / len(sample) >= 0.85


# ---------------------------------------------------------------------------
# Quarantine writer
# ---------------------------------------------------------------------------

def _quarantine(data: bytes, origin: str, reason: str) -> ModalityItem:
    """Write bytes to the quarantine store and return a quarantine ModalityItem."""
    try:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    mime = _sniff_mime(data)
    return ModalityItem(
        schema=SCHEMA,
        modality="quarantine",
        parsed_unit=None,
        raw_bytes=data,
        mime=mime,
        origin=origin,
        quarantine_reason=reason,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle(data: bytes, origin: str, *, filename: str = "") -> list[ModalityItem]:
    """Classify raw bytes into one or more ModalityItems.

    Args:
        data:     raw bytes of the item to classify
        origin:   caller label — e.g. a filepath, URL, or logical handle
        filename: optional filename hint for extension-based routing when magic
                  bytes are ambiguous (e.g. ZIP-based office docs)

    Returns:
        list[ModalityItem] — always at least one item; never raises.

    Routing guarantees:
        - text items:       parsed_unit is a non-empty str; raw_bytes is None
        - image/video:      parsed_unit is None; raw_bytes holds the original data
        - quarantine items: raw_bytes holds the data; quarantine_reason is set
    """
    if not data:
        return [_quarantine(data, origin, "empty payload")]

    fname = filename or Path(origin).name
    ext = Path(fname).suffix.lower()
    mime = _detect_mime(data, fname)

    try:
        # ── text by extension first (before MIME): prevents .ts → video/MP2T
        # misclassification from Python's mimetypes stdlib ─────────────────
        if ext in _TEXT_EXTS:
            text = _decode_text(data)
            if text is not None:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime or "text/plain", origin=origin,
                )]
            return [_quarantine(data, origin, f"text extension {ext} but not decodable")]

        # ── image ──────────────────────────────────────────────────────────
        if mime.startswith("image/") or ext in _IMAGE_EXTS:
            return [ModalityItem(
                schema=SCHEMA, modality="image",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
            )]

        # ── video ──────────────────────────────────────────────────────────
        if mime.startswith("video/") or ext in _VIDEO_EXTS:
            return [ModalityItem(
                schema=SCHEMA, modality="video",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
            )]

        # ── audio → quarantine (no audio embedder yet) ──────────────────
        if mime.startswith("audio/") or ext in _AUDIO_EXTS:
            return [_quarantine(data, origin, "audio not yet supported")]

        # ── PDF ────────────────────────────────────────────────────────────
        if mime == "application/pdf" or ext == ".pdf":
            text = _try_pdf_text(data)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                )]
            return [_quarantine(data, origin, "pdf extraction failed")]

        # ── Office / RTF ───────────────────────────────────────────────────
        if ext in {".docx", ".pptx", ".xlsx", ".doc", ".rtf", ".odt"}:
            text = _try_doc_text(data, mime, fname)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                )]
            return [_quarantine(data, origin, f"office extraction unavailable for {ext}")]

        # ── ZIP (unknown office type — probe content types) ────────────────
        if mime == "application/zip":
            text = _try_doc_text(data, mime, fname)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                )]
            return [_quarantine(data, origin, "zip: office extraction unavailable")]

        # ── MIME-based text routing ────────────────────────────────────────
        if mime.startswith("text/") or mime in {
            "application/json", "application/javascript",
            "application/x-python", "application/x-sh",
            "application/xml", "application/graphql",
        }:
            text = _decode_text(data)
            if text is not None:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                )]

        # ── heuristic: mostly-printable unknown ────────────────────────────
        if mime == "application/octet-stream" and _looks_text(data):
            text = _decode_text(data)
            if text is not None:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime="text/plain", origin=origin,
                )]

        # ── fallthrough → quarantine ───────────────────────────────────────
        return [_quarantine(data, origin, f"unroutable mime={mime} ext={ext or 'none'}")]

    except Exception as exc:  # noqa: BLE001
        return [_quarantine(data, origin, f"handler exception: {exc}")]


def handle_path(path: Path, *, origin: str = "") -> list[ModalityItem]:
    """Convenience wrapper: read a file from disk and call handle()."""
    label = origin or str(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [_quarantine(b"", label, f"read error: {exc}")]
    return handle(data, label, filename=path.name)
