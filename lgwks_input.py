"""lgwks_input — universal input handler (lgwks.modality.item.v1).

I2 of the INGESTION-PLAN: two-phase design.

Phase 1  handle()   — classifies bytes → ModalityItem with extraction_strategy.
                       Fast, never raises, suitable for real-time hook path.

Phase 2  extract()  — performs the actual extraction work declared by the strategy.
                       May be slow (OCR, frame sampling); run async / off-path.

Routing table
-------------
text/code extensions + UTF-8 decodable  → text,      strategy=text_direct
PDF                                      → text,      strategy=text_direct (inline extraction)
DOCX/PPTX/XLSX/RTF                       → text,      strategy=text_direct (if markitdown)
                                         → quarantine if markitdown unavailable
PNG/JPEG/GIF/WEBP/BMP/TIFF              → image,     strategy=ocr_image  (tesseract if avail)
                                         → image,     strategy=visual_embed if no OCR
MP4/MOV/AVI/MKV/WEBM                    → video,     strategy=video_frames (ffmpeg required)
audio (MP3/WAV/FLAC/AAC/OGG)            → quarantine strategy=none
anything else                            → quarantine strategy=none

Extraction strategies (resolved by extract())
  text_direct   — parsed_unit already populated, no-op
  ocr_image     — run tesseract on raw_bytes → new text ModalityItem
  visual_embed  — no OCR available; embed as image, same schema, no text
  video_frames  — ffmpeg frame-sample → per-frame text ModalityItems (OCR or fingerprint)
  none          — quarantined; no extraction possible

handle() NEVER raises — all errors → quarantine item.
extract() NEVER raises — extraction failures produce a quarantine item.

Video frame extraction design (first principles)
-------------------------------------------------
A 1B-class vision model treats video as: sample N frames → per-frame text description
→ embed descriptions with the SAME text embedder → same vector space as code.
This means video and code queries can retrieve each other — cross-modal retrieval
at zero extra embedding cost. For a screen recording of a bug, the extracted text
("frame 4: terminal output ERROR null pointer lgwks_cognition.py:145") hits the
same ANN index as a code search.

Anti-hallucination extraction rules
-------------------------------------
1. For text: parsed_unit is ALWAYS the raw decoded source — never an LLM summary
   (summaries live in the intelligence layer upstream, not here)
2. For images: OCR is deterministic (tesseract) — no model generation
3. For video frames: OCR + perceptual hash fingerprint — deterministic pipeline
4. Extraction strategy is a CONTRACT: downstream can audit what happened

Authority: spec/second-harness/INGESTION-PLAN.md §I2
Schema id: lgwks.modality.item.v1
"""

from __future__ import annotations

import hashlib
import mimetypes
import struct
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

STRATEGY_TEXT_DIRECT  = "text_direct"   # parsed_unit already populated
STRATEGY_OCR_IMAGE    = "ocr_image"     # run tesseract on raw_bytes
STRATEGY_VISUAL_EMBED = "visual_embed"  # no OCR; embed image vector directly
STRATEGY_VIDEO_FRAMES = "video_frames"  # ffmpeg sample → per-frame text items
STRATEGY_NONE         = "none"          # quarantine — no extraction possible

# ---------------------------------------------------------------------------
# Extension routing tables
# (aligned with lgwks_embed.TEXT_EXT and lgwks_multimodal._IMAGE_EXTS)
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

    modality            : "text" | "image" | "video" | "quarantine"
    parsed_unit         : extracted text string (text items, text_direct strategy)
                          None for image/video/quarantine until extract() is called
    raw_bytes           : original bytes (image / video / quarantine items)
                          None for text_direct items (already extracted)
    mime                : detected MIME type string
    origin              : caller-supplied label (filepath, URL, logical handle)
    extraction_strategy : what extract() should do with this item
    frame_index         : for video frame items produced by extract(), the frame number
    source_fingerprint  : perceptual hash of raw_bytes (for dedup in video frames)
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
        return self.extraction_strategy not in (STRATEGY_TEXT_DIRECT, STRATEGY_NONE)

    def word_count(self) -> int:
        if self.parsed_unit:
            return len(self.parsed_unit.split())
        return 0


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
# Perceptual fingerprint (deterministic, no model needed)
# ---------------------------------------------------------------------------

def _fingerprint(data: bytes) -> str:
    """blake2b-8 of the first 64KB — fast dedup signal for media items."""
    return hashlib.blake2b(data[:65536], digest_size=8).hexdigest()


# ---------------------------------------------------------------------------
# Text extraction helpers (inline — no LLM; raw source only)
# ---------------------------------------------------------------------------

def _try_pdf_text(data: bytes, max_chars: int = 100_000) -> Optional[str]:
    try:
        from lgwks_extract import _pdf  # type: ignore[import-untyped]
        text = _pdf(data, max_chars)
        return text if text and text.strip() else None
    except ImportError:
        pass
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
    ext = Path(filename).suffix.lower()
    try:
        import io as _io
        from markitdown import MarkItDown  # type: ignore[import-untyped]
        md = MarkItDown()
        result = md.convert_stream(_io.BytesIO(data), file_extension=ext or ".bin")
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
    try:
        return data[:max_chars].decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data[:max_chars].decode("latin-1")
    except Exception:
        return None


def _looks_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    printable = sum(1 for b in sample if 0x09 <= b <= 0x0D or 0x20 <= b <= 0x7E)
    return printable / len(sample) >= 0.85


# ---------------------------------------------------------------------------
# OCR helper (deterministic, no model)
# ---------------------------------------------------------------------------

def _tesseract_available() -> bool:
    try:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=3)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _ocr_image_bytes(data: bytes, timeout: int = 30) -> Optional[str]:
    """Run tesseract OCR on image bytes. Returns None if unavailable or fails."""
    if not _tesseract_available():
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = Path(f.name)
            f.write(data)
        result = subprocess.run(
            ["tesseract", str(img_path), "stdout", "--psm", "3"],
            capture_output=True, timeout=timeout
        )
        img_path.unlink(missing_ok=True)
        if result.returncode == 0:
            text = result.stdout.decode("utf-8", errors="replace").strip()
            return text if text else None
    except (subprocess.TimeoutExpired, OSError, Exception):
        try:
            img_path.unlink(missing_ok=True)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Video frame extraction
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _extract_video_frames(
    data: bytes,
    origin: str,
    *,
    fps: float = 1.0,
    max_frames: int = 30,
    ocr: bool = True,
) -> list[ModalityItem]:
    """Frame-sample a video and produce one ModalityItem per frame.

    For each frame:
      - If tesseract available: OCR → text ModalityItem with parsed_unit
      - Always: perceptual fingerprint stored in source_fingerprint
      - Frame index stored in frame_index

    The text items live in the SAME vector space as code (they are just text).
    A screen recording of a bug therefore hits the same ANN index as code search.

    Returns list of items. Never raises — returns quarantine item on failure.
    """
    if not _ffmpeg_available():
        return [_quarantine(data, origin, "video_frames: ffmpeg not available")]

    has_ocr = ocr and _tesseract_available()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        vid_path = tmp_path / "input.mp4"
        vid_path.write_bytes(data)

        frame_dir = tmp_path / "frames"
        frame_dir.mkdir()

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-i", str(vid_path),
                    "-vf", f"fps={fps},scale=1280:-1",
                    "-frames:v", str(max_frames),
                    "-q:v", "3",
                    str(frame_dir / "frame_%04d.png"),
                ],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0 and not list(frame_dir.glob("*.png")):
                return [_quarantine(data, origin,
                                   f"ffmpeg failed: {result.stderr[:200].decode('utf-8','replace')}")]
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [_quarantine(data, origin, f"video_frames error: {exc}")]

        items: list[ModalityItem] = []
        for i, frame_path in enumerate(sorted(frame_dir.glob("*.png"))):
            frame_bytes = frame_path.read_bytes()
            fp = _fingerprint(frame_bytes)

            if has_ocr:
                ocr_text = _ocr_image_bytes(frame_bytes)
                if ocr_text:
                    items.append(ModalityItem(
                        schema=SCHEMA,
                        modality="text",
                        parsed_unit=f"[video:{origin} frame:{i+1}] {ocr_text}",
                        raw_bytes=None,
                        mime="text/plain",
                        origin=f"{origin}#frame{i+1}",
                        extraction_strategy=STRATEGY_TEXT_DIRECT,
                        frame_index=i + 1,
                        source_fingerprint=fp,
                    ))
                    continue

            # No OCR available: emit image item with source_fingerprint for dedup
            items.append(ModalityItem(
                schema=SCHEMA,
                modality="image",
                parsed_unit=None,
                raw_bytes=frame_bytes,
                mime="image/png",
                origin=f"{origin}#frame{i+1}",
                extraction_strategy=STRATEGY_VISUAL_EMBED,
                frame_index=i + 1,
                source_fingerprint=fp,
            ))

        if not items:
            return [_quarantine(data, origin, "video_frames: no frames extracted")]
        return items


# ---------------------------------------------------------------------------
# Quarantine helper
# ---------------------------------------------------------------------------

def _quarantine(data: bytes, origin: str, reason: str) -> ModalityItem:
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
        extraction_strategy=STRATEGY_NONE,
        source_fingerprint=_fingerprint(data) if data else "",
        quarantine_reason=reason,
    )


# ---------------------------------------------------------------------------
# Phase 1 — handle() : classify and annotate (fast, never raises)
# ---------------------------------------------------------------------------

def handle(data: bytes, origin: str, *, filename: str = "") -> list[ModalityItem]:
    """Phase 1: classify raw bytes → ModalityItem(s) with extraction_strategy.

    Fast path — suitable for real-time hook. No OCR, no ffmpeg, no LLM.
    Call extract() on items whose needs_extraction() is True for the full pipeline.

    Returns at least one ModalityItem. Never raises.
    """
    if not data:
        return [_quarantine(data, origin, "empty payload")]

    fname = filename or Path(origin).name
    ext = Path(fname).suffix.lower()
    mime = _detect_mime(data, fname)

    try:
        # ── text extensions take priority — prevents .ts → video/MP2T etc. ──
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

        # ── image ──────────────────────────────────────────────────────────
        if mime.startswith("image/") or ext in _IMAGE_EXTS:
            fp = _fingerprint(data)
            strategy = STRATEGY_OCR_IMAGE if _tesseract_available() else STRATEGY_VISUAL_EMBED
            return [ModalityItem(
                schema=SCHEMA, modality="image",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
                extraction_strategy=strategy,
                source_fingerprint=fp,
            )]

        # ── video ──────────────────────────────────────────────────────────
        if mime.startswith("video/") or ext in _VIDEO_EXTS:
            if not _ffmpeg_available():
                return [ModalityItem(
                    schema=SCHEMA, modality="video",
                    parsed_unit=None, raw_bytes=data,
                    mime=mime, origin=origin,
                    extraction_strategy=STRATEGY_NONE,
                    source_fingerprint=_fingerprint(data),
                    quarantine_reason="ffmpeg unavailable",
                )]
            return [ModalityItem(
                schema=SCHEMA, modality="video",
                parsed_unit=None, raw_bytes=data,
                mime=mime, origin=origin,
                extraction_strategy=STRATEGY_VIDEO_FRAMES,
                source_fingerprint=_fingerprint(data),
            )]

        # ── audio → quarantine ─────────────────────────────────────────────
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
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
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
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]
            return [_quarantine(data, origin, f"office extraction unavailable for {ext}")]

        # ── ZIP (unknown office) ───────────────────────────────────────────
        if mime == "application/zip":
            text = _try_doc_text(data, mime, fname)
            if text:
                return [ModalityItem(
                    schema=SCHEMA, modality="text",
                    parsed_unit=text, raw_bytes=None,
                    mime=mime, origin=origin,
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
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
                    extraction_strategy=STRATEGY_TEXT_DIRECT,
                    source_fingerprint=_fingerprint(data),
                )]

        # ── heuristic: mostly-printable ────────────────────────────────────
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
# Phase 2 — extract() : run the extraction strategy (slow, async-friendly)
# ---------------------------------------------------------------------------

def extract(item: ModalityItem, *, fps: float = 1.0, max_frames: int = 30) -> list[ModalityItem]:
    """Phase 2: perform the extraction declared by item.extraction_strategy.

    text_direct  → [item]  (no-op, already extracted)
    ocr_image    → OCR via tesseract → [text item]  or [quarantine if fails]
    visual_embed → [item]  (no text possible; embed visually downstream)
    video_frames → ffmpeg frame sample → [text or image items, one per frame]
    none         → [item]  (quarantine, leave as-is)

    Never raises.
    """
    try:
        if item.extraction_strategy == STRATEGY_TEXT_DIRECT:
            return [item]

        if item.extraction_strategy == STRATEGY_NONE:
            return [item]

        if item.extraction_strategy == STRATEGY_VISUAL_EMBED:
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
            # OCR failed — keep as visual_embed (still useful)
            return [ModalityItem(
                schema=item.schema, modality=item.modality,
                parsed_unit=item.parsed_unit, raw_bytes=item.raw_bytes,
                mime=item.mime, origin=item.origin,
                extraction_strategy=STRATEGY_VISUAL_EMBED,
                source_fingerprint=item.source_fingerprint,
                quarantine_reason="ocr_image: tesseract returned no text",
            )]

        if item.extraction_strategy == STRATEGY_VIDEO_FRAMES:
            if item.raw_bytes is None:
                return [_quarantine(b"", item.origin, "video_frames: no raw_bytes")]
            return _extract_video_frames(
                item.raw_bytes, item.origin,
                fps=fps, max_frames=max_frames
            )

        return [_quarantine(item.raw_bytes or b"", item.origin,
                            f"unknown strategy: {item.extraction_strategy!r}")]

    except Exception as exc:  # noqa: BLE001
        return [_quarantine(item.raw_bytes or b"", item.origin,
                            f"extract() exception: {exc}")]


# ---------------------------------------------------------------------------
# Convenience: classify + extract in one call
# ---------------------------------------------------------------------------

def handle_and_extract(
    data: bytes,
    origin: str,
    *,
    filename: str = "",
    fps: float = 1.0,
    max_frames: int = 30,
) -> list[ModalityItem]:
    """Classify and immediately extract. Suitable for batch / background ingestion."""
    classified = handle(data, origin, filename=filename)
    result: list[ModalityItem] = []
    for item in classified:
        result.extend(extract(item, fps=fps, max_frames=max_frames))
    return result


def handle_path(path: Path, *, origin: str = "") -> list[ModalityItem]:
    """Classify a file from disk (phase 1 only — no extraction)."""
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
