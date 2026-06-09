"""
lgwks_multimodal — image extraction + multimodal embedding seam.

Extracts images from web pages (screenshots, <img> tags), PDF pages, and image files,
then embeds them into the SAME vector space as text using google/gemini-embedding-2
via OpenRouter. Also produces a deterministic 256-d image fingerprint for
context-finding / frontier search when the remote eye is unavailable.

Every image produces:
  - A text description (alt text, caption, surrounding context)
  - A 256-d deterministic perceptual fingerprint (for frontier/context finding)
  - A 4096-d semantic vector via gemini-embedding-2 (when available)

The image chunks live alongside text chunks in the substrate artifact tree,
so queries can match across modalities.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import lgwks_keyvault

# OpenRouter multimodal embedding config
_MM_MODEL = os.environ.get(
    "LGWKS_MM_MODEL",
    "google/gemini-embedding-exp-03-07",  # latest gemini embedding with image support
)
_MM_ENDPOINT = "https://openrouter.ai/api/v1/embeddings"
_MM_TIMEOUT = int(os.environ.get("LGWKS_MM_TIMEOUT", "60"))

# Maximum image dimension for resize-before-encode (to keep base64 small)
_MAX_IMG_DIM = 1024
_MAX_IMG_BYTES = 3_000_000  # ~3MB base64 cap

# File extensions we treat as images
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}


def _is_image(path: Path | str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXTS


def _b64size(b64: str) -> int:
    return len(b64) * 3 // 4


def _resize_and_encode(raw: bytes, *, max_dim: int = _MAX_IMG_DIM, fmt: str = "PNG") -> tuple[str, str]:
    """Resize image to max_dim on longest side and encode to base64. Returns (b64, mime_type)."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw))
        # Convert to RGB if needed (handles palette, RGBA, etc.)
        if img.mode in ("RGBA", "P", "LA", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        mime = f"image/{fmt.lower()}"
        return b64, mime
    except Exception:
        # Fallback: raw base64, attempt to sniff mime
        mime = _sniff_mime(raw)
        return base64.b64encode(raw).decode("ascii"), mime


def _sniff_mime(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"GIF"):
        return "image/gif"
    return "image/png"


# ── Deterministic image fingerprint (256-d) ───────────────────────────────────

def _perceptual_fingerprint(raw: bytes, dims: int = 256) -> list[float]:
    """Produce a deterministic 256-d vector from image bytes for frontier/context search.
    Falls back to hash-of-bytes if PIL unavailable."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw))
        # Convert to small grayscale thumbnail
        thumb = img.convert("L").resize((16, 16), Image.LANCZOS)
        pixels = list(thumb.getdata())
        # Build histogram-like features + spatial grid
        vec = [0.0] * dims
        # 1. Global statistics (first 16 dims)
        mean_val = sum(pixels) / len(pixels)
        vec[0] = mean_val / 255.0
        std_val = (sum((p - mean_val) ** 2 for p in pixels) / len(pixels)) ** 0.5
        vec[1] = std_val / 128.0
        # 2. 4x4 grid averages (16 blocks * 14 dims = 224 dims, but we have 256)
        block_size = 4
        idx = 2
        for by in range(4):
            for bx in range(4):
                block = []
                for y in range(by * block_size, (by + 1) * block_size):
                    for x in range(bx * block_size, (bx + 1) * block_size):
                        block.append(pixels[y * 16 + x])
                avg = sum(block) / len(block)
                vec[idx] = avg / 255.0
                idx += 1
                # Add gradient features
                if len(block) >= 2:
                    vec[idx] = (block[1] - block[0]) / 255.0
                    idx += 1
        # 3. DCT-like low-freq (hash-based fill for remaining dims)
        h = hashlib.blake2b(raw, digest_size=32).digest()
        for i in range(idx, dims):
            byte_val = h[i % 32]
            vec[i] = (byte_val / 127.5) - 1.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [round(v / norm, 6) for v in vec]
    except Exception:
        # Fallback: blake2b hash projected into 256-d
        h = hashlib.blake2b(raw, digest_size=64).digest()
        vec = [0.0] * dims
        for i in range(0, len(h), 2):
            idx = (h[i] | (h[i + 1] << 8)) % dims
            val = ((h[i] % 2) * 2 - 1) * (1.0 + (h[i + 1] % 16))
            vec[idx] += val
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [round(v / norm, 6) for v in vec]


# ── Multimodal embedding via OpenRouter ───────────────────────────────────────

def _mm_key() -> str | None:
    key, _ = lgwks_keyvault.get_secret("openrouter")
    return key


def embed_multimodal(
    text: str,
    image_b64: str = "",
    image_mime: str = "image/png",
    *,
    model: str = _MM_MODEL,
    timeout: int = _MM_TIMEOUT,
) -> dict[str, Any]:
    """Embed text + optional image via google/gemini-embedding-2 on OpenRouter.
    Always returns BOTH deterministic and semantic vectors.

    Returns:
        {
            "ok": bool,
            "det": {"vector": [...256], "provider": "perceptual-fingerprint", "dims": 256},
            "sem": {"vector": [...4096], "provider": "openrouter:...", "dims": 4096} | None,
            "error": str | None,
        }
    """
    # Deterministic fingerprint: if image present, hash image; else hash text
    det_text = text if text else ""
    det_raw = det_text.encode("utf-8")
    if image_b64:
        try:
            det_raw = base64.b64decode(image_b64)
        except Exception:
            pass
    det_vec = _perceptual_fingerprint(det_raw)
    out: dict[str, Any] = {
        "ok": True,
        "det": {"vector": det_vec, "provider": "perceptual-fingerprint", "dims": len(det_vec)},
        "sem": None,
        "error": None,
    }

    # Semantic: only if OpenRouter key available
    key = _mm_key()
    if not key:
        out["error"] = "openrouter key unavailable"
        return out

    # Build multimodal input
    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append({"type": "text", "text": text[:8000]})
    if image_b64:
        # Check size cap
        if _b64size(image_b64) > _MAX_IMG_BYTES:
            out["error"] = f"image too large: {_b64size(image_b64)} bytes base64 > {_MAX_IMG_BYTES}"
            return out
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_mime};base64,{image_b64}"},
        })

    if not parts:
        out["error"] = "no content to embed"
        return out

    body = json.dumps({
        "model": model,
        "input": parts,
        "encoding_format": "float",
    }).encode("utf-8")

    req = urllib.request.Request(
        _MM_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://logicalworks.ca",
            "X-OpenRouter-Title": "Logical Works - lgwks multimodal eye",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vec = [float(x) for x in data["data"][0]["embedding"]]
        out["sem"] = {"vector": vec, "provider": f"openrouter:{model}", "dims": len(vec)}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        out["error"] = f"openrouter multimodal error: {type(exc).__name__}: {exc}"
        out["ok"] = False

    return out


# ── Image extraction helpers ─────────────────────────────────────────────────

def screenshot_page(page, *, max_dim: int = _MAX_IMG_DIM) -> tuple[str, str] | None:
    """Take a screenshot of a Playwright page, resize, return (b64, mime). Returns None on failure."""
    try:
        raw = page.screenshot(type="png", full_page=False)
        if not raw:
            return None
        b64, mime = _resize_and_encode(raw, max_dim=max_dim, fmt="PNG")
        return b64, mime
    except Exception:
        return None


def extract_pdf_page_image(raw: bytes, page_num: int = 0, *, max_dim: int = _MAX_IMG_DIM) -> tuple[str, str] | None:
    """Render a PDF page to image. Returns (b64, mime) or None. Requires fitz (PyMuPDF)."""
    try:
        import fitz
        import io
        doc = fitz.open(stream=io.BytesIO(raw), filetype="pdf")
        if page_num >= len(doc):
            return None
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150)
        img_raw = pix.tobytes("png")
        b64, mime = _resize_and_encode(img_raw, max_dim=max_dim, fmt="PNG")
        return b64, mime
    except Exception:
        return None


def file_to_b64(path: Path | str, *, max_dim: int = _MAX_IMG_DIM) -> tuple[str, str] | None:
    """Read an image file, resize if needed, return (b64, mime)."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = p.read_bytes()
        b64, mime = _resize_and_encode(raw, max_dim=max_dim)
        return b64, mime
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 -m lgwks_multimodal <image_file> [text]")
        sys.exit(2)
    img_path = sys.argv[1]
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    b64_mime = file_to_b64(img_path)
    if not b64_mime:
        print(f"error: cannot read image: {img_path}")
        sys.exit(1)
    b64, mime = b64_mime
    result = embed_multimodal(text, b64, mime)
    print(json.dumps(result, indent=2, default=str))
