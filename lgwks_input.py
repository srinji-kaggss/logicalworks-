"""lgwks_input — universal input handler (lgwks.modality.item.v1).

I2 of the INGESTION-PLAN: two-phase design.

Phase 1  handle()   — classifies bytes → ModalityItem with extraction_strategy.
                       Fast, never raises, suitable for real-time hook path.

Phase 2  extract()  — performs extraction declared by the strategy (OCR only).
                       May be slow; run async / off-path.

Routing table
-------------
text/code extensions + UTF-8 decodable  → text,      strategy=text_direct
PDF                                      → text,      strategy=text_direct
DOCX/PPTX/XLSX/RTF                       → text,      strategy=text_direct (if markitdown)
                                         → quarantine if markitdown unavailable
PNG/JPEG/GIF/WEBP/BMP/TIFF              → image,     strategy=ocr_image (tesseract if avail)
                                         → image,     strategy=visual_embed if no OCR
MP4/MOV/AVI/MKV/WEBM                    → video,     strategy=video_embed (I4 native VL)
audio (MP3/WAV/FLAC/AAC/OGG)            → quarantine strategy=none
anything else                            → quarantine strategy=none

Extraction strategies
---------------------
  text_direct   — parsed_unit already populated; no-op in extract()
  ocr_image     — tesseract OCR on raw_bytes → new text ModalityItem
  visual_embed  — no OCR available; I4 embeds image natively via Qwen3-VL
  video_embed   — I4 embeds video natively via Qwen3-VL-Embedding-8B video API
                  (raw_bytes passed directly; no frame extraction here)
  none          — quarantined; nothing to do

Video design
------------
Qwen3-VL-Embedding-8B accepts video natively. I4 calls the VL video path:
    processor(text=instruction, videos=[video_bytes_or_path])
producing one 4096-d vector in the SAME space as text and image embeddings.
I2 does NOT extract frames — that is the model's job. We just classify and
keep the raw bytes intact.

Anti-hallucination rules
------------------------
parsed_unit is ALWAYS raw decoded source — never an LLM summary.
Summaries live in the intelligence layer (Liquid Nano, I3 upstream), not here.
OCR (tesseract) is deterministic. extraction_strategy is a CONTRACT.

Authority: spec/second-harness/INGESTION-PLAN.md §I2
Schema id: lgwks.modality.item.v1
"""

from __future__ import annotations

import hashlib
import mimetypes
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCHEMA = "lgwks.modality.item.v1"

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Extraction strategy constants
# ---------------------------------------------------------------------------

STRATEGY_TEXT_DIRECT  = "text_direct"   # parsed_unit populated; no-op
STRATEGY_OCR_IMAGE    = "ocr_image"     # tesseract OCR → text ModalityItem
STRATEGY_VISUAL_EMBED = "visual_embed"  # I4 embeds image via Qwen3-VL
STRATEGY_VIDEO_EMBED  = "video_embed"   # I4 embeds video via Qwen3-VL native video API
STRATEGY_NONE         = "none"          # quarantine; nothing to do

# ---------------------------------------------------------------------------
# Extension routing tables
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
_AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"})

QUARANTINE_DIR = _REPO_ROOT / "store" / "untrusted"


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModalityItem:
    """Single lgwks.modality.item.v1 instance.

    modality            : "text" | "image" | "video" | "quarantine"
    parsed_unit         : raw decoded text (text items only); None for media/quarantine
    raw_bytes           : original bytes for image/video/quarantine; None for text
    mime                : detected MIME type
    origin              : caller label (filepath, URL, logical handle)
    extraction_strategy : contract for what extract() / I4 should do
    frame_index         : -1 unless this item is a video frame (from a future VL split)
    source_fingerprint  : blake2b-8 hex of raw content — dedup signal
    quarantine_reason   : non-empty only when modality == "quarantine"
    """
    schema: str
    modality: str
    parsed_unit: Optional[str]
    raw_bytes: Optional[bytes]
    mime: str
    origin: str
    extraction_strategy: str = field(default=STRATEGY_NONE)
    frame_index: int = field(default=-1)
    source_fingerprint: str = field(default="")
    quarantine_reason: str = field(default="")

    def is_quarantined(self) -> bool:
        return self.modality == "quarantine"

    def needs_extraction(self) -> bool:
        """True only for strategies that extract() can do work on (OCR).
        VIDEO_EMBED and VISUAL_EMBED are I4's domain — not extract()'s."""
        return self.extraction_strategy == STRATEGY_OCR_IMAGE

    def word_count(self) -> int:
        return len(self.parsed_unit.split()) if self.parsed_unit else 0


# ---------------------------------------------------------------------------
# Magic-byte MIME sniffer
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
    if h[:4] == b'PK\x03\x04':                            return "application/zip"
    if data[:6] == b'{\\rtf1':                             return "application/rtf"
    if len(data) > 8 and data[4:8] == b'ftyp':            return "video/mp4"
    if h[:4] in (b'\x00\x00\x00\x14', b'\x00\x00\x00\x18',
                 b'\x00\x00\x00\x1c', b'\x00\x00\x00\x20'):
        if len(data) > 8 and data[4:8] == b'ftyp':        return "video/mp4"
    if h[:4] == b'\x1a\x45\xdf\xa3':                      return "video/webm"
    if h[:3] == b'ID3' or h[:2] == b'\xff\xfb':           return "audio/mpeg"
    if h[:4] == b'fLaC':                                   return "audio/flac"
    if h[:4] == b'OggS':                                   return "audio/ogg"
    if h[:4] == b'RIFF' and h[8:12] == b'WAVE':           return "audio/wav"

    return "application/octet-stream"


def _detect_mime(data: bytes, filename: str) -> str:
    """Magic bytes first; extension fallback via mimetypes stdlib."""
    magic = _sniff_mime(data)
    if magic != "application/octet-stream":
        return magic
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

def _fingerprint(data: bytes) -> str:
    """blake2b-8 of the first 64KB — dedup signal, not a cid."""
    return hashlib.blake2b(data[:65536], digest_size=8).hexdigest()


# ---------------------------------------------------------------------------
# Text extraction (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _try_pdf_text(data: bytes, max_chars: int = 100_000) -> Optional[str]:
    try:
        from lgwks_extract import _pdf  # type: ignore[import-untyped]
        text = _pdf(data, max_chars)
        return text if text and text.strip() else None
    except ImportError:
        pass
    try:
        r = subprocess.run(["pdftotext", "-", "-"], input=data,
                           capture_output=True, timeout=30)
        if r.returncode == 0:
            text = r.stdout.decode("utf-8", errors="replace")
            return text[:max_chars] if text.strip() else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    try:
        import io as _io
        import fitz  # type: ignore[import-untyped]
        doc = fitz.open(stream=_io.BytesIO(data), filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
        doc.close()
        return text[:max_chars] if text.strip() else None
    except (ImportError, Exception):
        return None


def _try_doc_text(data: bytes, filename: str, max_chars: int = 100_000) -> Optional[str]:
    ext = Path(filename).suffix.lower()
    try:
        import io as _io
        from markitdown import MarkItDown  # type: ignore[import-untyped]
        result = MarkItDown().convert_stream(_io.BytesIO(data), file_extension=ext or ".bin")
        text = result.text_content if hasattr(result, "text_content") else str(result)
        return text[:max_chars] if text and text.strip() else None
    except (ImportError, Exception):
        pass
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
    for enc in ("utf-8", "latin-1"):
        try:
            return data[:max_chars].decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _looks_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    printable = sum(1 for b in sample if 0x09 <= b <= 0x0D or 0x20 <= b <= 0x7E)
    return printable / len(sample) >= 0.85


# ---------------------------------------------------------------------------
# Image OCR (optional, deterministic)
# ---------------------------------------------------------------------------

def _tesseract_available() -> bool:
    try:
        return subprocess.run(["tesseract", "--version"],
                              capture_output=True, timeout=3).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _ocr_image_bytes(data: bytes, timeout: int = 30) -> Optional[str]:
    """Run tesseract on image bytes. Returns None if unavailable or produces no text."""
    if not _tesseract_available():
        return None
    img_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = Path(f.name)
            f.write(data)
        r = subprocess.run(["tesseract", str(img_path), "stdout", "--psm", "3"],
                           capture_output=True, timeout=timeout)
        img_path.unlink(missing_ok=True)
        if r.returncode == 0:
            text = r.stdout.decode("utf-8", errors="replace").strip()
            return text or None
    except Exception:
        if img_path:
            img_path.unlink(missing_ok=True)
    return None


# ---------------------------------------------------------------------------
# Quarantine helper
# ---------------------------------------------------------------------------

def _quarantine(data: bytes, origin: str, reason: str) -> ModalityItem:
    try:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return ModalityItem(
        schema=SCHEMA, modality="quarantine",
        parsed_unit=None, raw_bytes=data,
        mime=_sniff_mime(data), origin=origin,
        extraction_strategy=STRATEGY_NONE,
        source_fingerprint=_fingerprint(data),
        quarantine_reason=reason,
    )


# ---------------------------------------------------------------------------
# Phase 1 — handle() : classify + annotate (fast, never raises)
# ---------------------------------------------------------------------------

def handle(data: bytes, origin: str, *, filename: str = "") -> list[ModalityItem]:
    """Classify raw bytes into a ModalityItem. Fast; no model calls; never raises.

    Video items carry raw_bytes intact and strategy=video_embed — I4 passes them
    directly to Qwen3-VL's native video embedding API. No frame extraction here.
    """
    if not data:
        return [_quarantine(data, origin, "empty payload")]

    fname = filename or Path(origin).name
    ext = Path(fname).suffix.lower()
    mime = _detect_mime(data, fname)

    try:
        # text extensions first — prevents stdlib mimetypes misroutes (.ts → video)
        if ext in _TEXT_EXTS:
            text = _decode_text(data)
            if text is not None:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime or "text/plain", origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]
            return [_quarantine(data, origin, f"text extension {ext} but not decodable")]

        # image
        if mime.startswith("image/") or ext in _IMAGE_EXTS:
            strategy = STRATEGY_OCR_IMAGE if _tesseract_available() else STRATEGY_VISUAL_EMBED
            return [ModalityItem(
                schema=SCHEMA, modality="image",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
                extraction_strategy=strategy,
                source_fingerprint=_fingerprint(data),
            )]

        # video — raw bytes passed to I4; Qwen3-VL embeds natively
        if mime.startswith("video/") or ext in _VIDEO_EXTS:
            return [ModalityItem(
                schema=SCHEMA, modality="video",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
                extraction_strategy=STRATEGY_VIDEO_EMBED,
                source_fingerprint=_fingerprint(data),
            )]

        # audio → quarantine (no audio embedder)
        if mime.startswith("audio/") or ext in _AUDIO_EXTS:
            return [_quarantine(data, origin, "audio not yet supported")]

        # PDF
        if mime == "application/pdf" or ext == ".pdf":
            text = _try_pdf_text(data)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]
            return [_quarantine(data, origin, "pdf extraction failed")]

        # Office / RTF
        if ext in {".docx", ".pptx", ".xlsx", ".doc", ".rtf", ".odt"}:
            text = _try_doc_text(data, fname)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]
            return [_quarantine(data, origin, f"office extraction unavailable for {ext}")]

        # ZIP (unknown office type)
        if mime == "application/zip":
            text = _try_doc_text(data, fname)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]
            return [_quarantine(data, origin, "zip: office extraction unavailable")]

        # MIME-based text
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
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]

        # heuristic: mostly-printable bytes
        if _looks_text(data):
            text = _decode_text(data)
            if text is not None:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime="text/plain", origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]

        return [_quarantine(data, origin, f"unroutable mime={mime} ext={ext or 'none'}")]

    except Exception as exc:  # noqa: BLE001
        return [_quarantine(data, origin, f"handler exception: {exc}")]


# ---------------------------------------------------------------------------
# Phase 2 — extract() : run OCR (slow, async-friendly)
# Only OCR_IMAGE needs work here. VIDEO_EMBED is handled entirely by I4.
# ---------------------------------------------------------------------------

def extract(item: ModalityItem) -> list[ModalityItem]:
    """Run the extraction strategy declared on item.

    text_direct   → [item]  no-op
    ocr_image     → tesseract OCR → [text item]; fallback → [visual_embed item]
    visual_embed  → [item]  no-op; I4 embeds via Qwen3-VL image path
    video_embed   → [item]  no-op; I4 embeds via Qwen3-VL native video path
    none          → [item]  no-op; quarantine

    Never raises.
    """
    try:
        if item.extraction_strategy in (
            STRATEGY_TEXT_DIRECT, STRATEGY_VISUAL_EMBED,
            STRATEGY_VIDEO_EMBED, STRATEGY_NONE,
        ):
            return [item]

        if item.extraction_strategy == STRATEGY_OCR_IMAGE:
            if item.raw_bytes is None:
                return [_quarantine(b"", item.origin, "ocr_image: no raw_bytes")]
            text = _ocr_image_bytes(item.raw_bytes)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime="text/plain", origin=item.origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=item.source_fingerprint,
                )]
            # OCR ran but returned no text — fall back to visual embed
            return [ModalityItem(
                schema=item.schema, modality=item.modality,
                parsed_unit=None, raw_bytes=item.raw_bytes,
                mime=item.mime, origin=item.origin,
                extraction_strategy=STRATEGY_VISUAL_EMBED,
                source_fingerprint=item.source_fingerprint,
                quarantine_reason="ocr_image: tesseract returned no text",
            )]

        return [_quarantine(item.raw_bytes or b"", item.origin,
                            f"unknown strategy: {item.extraction_strategy!r}")]

    except Exception as exc:  # noqa: BLE001
        return [_quarantine(item.raw_bytes or b"", item.origin,
                            f"extract() exception: {exc}")]


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def handle_and_extract(data: bytes, origin: str, *, filename: str = "") -> list[ModalityItem]:
    """Classify + OCR extraction in one call. Video items pass through unchanged."""
    result: list[ModalityItem] = []
    for item in handle(data, origin, filename=filename):
        result.extend(extract(item))
    return result


def handle_path(path: Path, *, origin: str = "") -> list[ModalityItem]:
    """Classify a file from disk (phase 1 only)."""
    label = origin or str(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [_quarantine(b"", label, f"read error: {exc}")]
    return handle(data, label, filename=path.name)


def handle_path_and_extract(path: Path, *, origin: str = "") -> list[ModalityItem]:
    """Classify + extract a file from disk."""
    label = origin or str(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [_quarantine(b"", label, f"read error: {exc}")]
    return handle_and_extract(data, label, filename=path.name)
