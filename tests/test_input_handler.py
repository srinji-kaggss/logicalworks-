"""Acceptance tests for lgwks.modality.item.v1 (I2) — hardened two-phase design.

Acceptance criteria from INGESTION-PLAN §I2:
  A1. known text extensions → modality="text", parsed_unit is non-empty str
  A2. PNG/JPEG/WEBP magic bytes → modality="image", raw_bytes preserved
  A3. MP4 magic bytes → modality="video", extraction_strategy set
  A4. unknown binary → modality="quarantine"
  A5. audio bytes → modality="quarantine"
  A6. handle() NEVER raises — fuzz 50 random byte strings, no crash
  A7. handle() returns at least one ModalityItem in every case
  A8. schema field is always "lgwks.modality.item.v1"
  A9. extraction_strategy is always set (never empty string)
 A10. source_fingerprint is always set on non-empty payloads
 A11. text items: raw_bytes=None; media items: parsed_unit=None
 A12. extract() NEVER raises — fuzz 50 items, no crash
 A13. video → strategy VIDEO_FRAMES if ffmpeg available
 A14. image → strategy OCR_IMAGE or VISUAL_EMBED (never empty)
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgwks_input import (
    SCHEMA,
    STRATEGY_TEXT_DIRECT,
    STRATEGY_OCR_IMAGE,
    STRATEGY_VISUAL_EMBED,
    STRATEGY_VIDEO_FRAMES,
    STRATEGY_NONE,
    ModalityItem,
    extract,
    handle,
    handle_and_extract,
    handle_path,
    _sniff_mime,
    _looks_text,
    _fingerprint,
)

# ---------------------------------------------------------------------------
# Synthetic test bytes
# ---------------------------------------------------------------------------

_PNG_MAGIC   = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8
_JPEG_MAGIC  = b'\xff\xd8\xff\xe0' + b'\x00' * 16
_WEBP_MAGIC  = b'RIFF\x24\x00\x00\x00WEBP' + b'\x00' * 4
_GIF_MAGIC   = b'GIF89a' + b'\x00' * 10
_MP4_MAGIC   = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 8
_PDF_MAGIC   = b'%PDF-1.4 %\xe2\xe3\xcf\xd3\n'
_MP3_MAGIC   = b'ID3\x04\x00\x00' + b'\x00' * 10
_FLAC_MAGIC  = b'fLaC' + b'\x00' * 12
_RTF_MAGIC   = b'{\\rtf1\\ansi hello}'
_RANDOM_BIN  = bytes(range(256))


class TestMimeSniffer(unittest.TestCase):
    def test_png(self):
        self.assertEqual(_sniff_mime(_PNG_MAGIC), "image/png")

    def test_jpeg(self):
        self.assertEqual(_sniff_mime(_JPEG_MAGIC), "image/jpeg")

    def test_gif(self):
        self.assertEqual(_sniff_mime(_GIF_MAGIC), "image/gif")

    def test_webp(self):
        self.assertEqual(_sniff_mime(_WEBP_MAGIC), "image/webp")

    def test_pdf(self):
        self.assertEqual(_sniff_mime(_PDF_MAGIC), "application/pdf")

    def test_mp3(self):
        self.assertEqual(_sniff_mime(_MP3_MAGIC), "audio/mpeg")

    def test_flac(self):
        self.assertEqual(_sniff_mime(_FLAC_MAGIC), "audio/flac")

    def test_mp4(self):
        self.assertEqual(_sniff_mime(_MP4_MAGIC), "video/mp4")

    def test_rtf(self):
        self.assertEqual(_sniff_mime(_RTF_MAGIC), "application/rtf")

    def test_empty_returns_octet_stream(self):
        self.assertEqual(_sniff_mime(b""), "application/octet-stream")


class TestFingerprint(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(_fingerprint(b"hello"), _fingerprint(b"hello"))

    def test_different_inputs_differ(self):
        self.assertNotEqual(_fingerprint(b"hello"), _fingerprint(b"world"))

    def test_empty_returns_deterministic_hash(self):
        # blake2b of empty bytes is still a valid 16-char hex hash
        fp = _fingerprint(b"")
        self.assertRegex(fp, r'^[0-9a-f]{16}$')

    def test_hex_string(self):
        fp = _fingerprint(b"data")
        self.assertRegex(fp, r'^[0-9a-f]{16}$')


class TestLooksText(unittest.TestCase):
    def test_ascii_source_is_text(self):
        self.assertTrue(_looks_text(b"def hello():\n    pass\n" * 50))

    def test_binary_is_not_text(self):
        self.assertFalse(_looks_text(_RANDOM_BIN))

    def test_empty_is_not_text(self):
        self.assertFalse(_looks_text(b""))


# ---------------------------------------------------------------------------
# A1 — text routing
# ---------------------------------------------------------------------------

class TestTextRouting(unittest.TestCase):
    def _text_item(self, payload: bytes, filename: str) -> ModalityItem:
        items = handle(payload, filename, filename=filename)
        self.assertTrue(items)
        return items[0]

    def test_py_file(self):
        item = self._text_item(b"def foo():\n    return 42\n", "foo.py")
        self.assertEqual(item.modality, "text")
        self.assertIn("foo", item.parsed_unit)
        self.assertIsNone(item.raw_bytes)
        self.assertEqual(item.extraction_strategy, STRATEGY_TEXT_DIRECT)

    def test_ts_file_not_video(self):
        # .ts extension must NOT be routed as video/MP2T (mimetypes stdlib bug)
        item = self._text_item(b"const x: number = 1;", "app.ts")
        self.assertEqual(item.modality, "text")

    def test_txt_file(self):
        item = self._text_item(b"hello world\n", "readme.txt")
        self.assertEqual(item.modality, "text")

    def test_md_file(self):
        item = self._text_item(b"# Title\n\nBody text\n", "README.md")
        self.assertEqual(item.modality, "text")

    def test_json_file(self):
        item = self._text_item(b'{"key": "value"}', "data.json")
        self.assertEqual(item.modality, "text")

    def test_rust_file(self):
        item = self._text_item(b"fn main() {}", "main.rs")
        self.assertEqual(item.modality, "text")

    def test_shell_script(self):
        item = self._text_item(b"#!/bin/bash\necho hi\n", "run.sh")
        self.assertEqual(item.modality, "text")

    def test_yaml_file(self):
        item = self._text_item(b"key: value\n", "config.yml")
        self.assertEqual(item.modality, "text")

    def test_fingerprint_set_on_text(self):
        item = self._text_item(b"content " * 10, "file.py")
        self.assertTrue(item.source_fingerprint)
        self.assertRegex(item.source_fingerprint, r'^[0-9a-f]{16}$')

    def test_looks_text_heuristic_for_unknown_ext(self):
        item = self._text_item(b"plaintext payload " * 100, "unknown.blob")
        self.assertEqual(item.modality, "text")

    def test_strategy_is_text_direct(self):
        item = self._text_item(b"code", "file.py")
        self.assertEqual(item.extraction_strategy, STRATEGY_TEXT_DIRECT)

    def test_schema_always_correct(self):
        item = self._text_item(b"content", "file.py")
        self.assertEqual(item.schema, SCHEMA)


# ---------------------------------------------------------------------------
# A2 — image routing
# ---------------------------------------------------------------------------

class TestImageRouting(unittest.TestCase):
    def test_png_magic(self):
        items = handle(_PNG_MAGIC, "photo.png")
        item = items[0]
        self.assertEqual(item.modality, "image")
        self.assertEqual(item.raw_bytes, _PNG_MAGIC)
        self.assertIsNone(item.parsed_unit)
        self.assertIn(item.extraction_strategy, (STRATEGY_OCR_IMAGE, STRATEGY_VISUAL_EMBED))

    def test_jpeg_magic(self):
        items = handle(_JPEG_MAGIC, "photo.jpg")
        self.assertEqual(items[0].modality, "image")

    def test_webp_magic(self):
        items = handle(_WEBP_MAGIC, "photo.webp")
        self.assertEqual(items[0].modality, "image")

    def test_gif_magic(self):
        items = handle(_GIF_MAGIC, "anim.gif")
        self.assertEqual(items[0].modality, "image")

    def test_image_extension_routes_even_without_magic(self):
        items = handle(b"fakepng", "logo.png", filename="logo.png")
        self.assertEqual(items[0].modality, "image")

    def test_raw_bytes_preserved(self):
        items = handle(_PNG_MAGIC, "img.png")
        self.assertEqual(items[0].raw_bytes, _PNG_MAGIC)

    def test_fingerprint_set(self):
        items = handle(_PNG_MAGIC, "img.png")
        self.assertTrue(items[0].source_fingerprint)

    def test_strategy_never_empty(self):
        items = handle(_PNG_MAGIC, "img.png")
        self.assertNotEqual(items[0].extraction_strategy, "")


# ---------------------------------------------------------------------------
# A3 — video routing
# ---------------------------------------------------------------------------

class TestVideoRouting(unittest.TestCase):
    def test_mp4_magic(self):
        items = handle(_MP4_MAGIC, "clip.mp4")
        item = items[0]
        self.assertEqual(item.modality, "video")
        self.assertIsNone(item.parsed_unit)

    def test_mp4_strategy_set(self):
        items = handle(_MP4_MAGIC, "clip.mp4")
        item = items[0]
        # strategy is VIDEO_FRAMES if ffmpeg available, else NONE
        self.assertIn(item.extraction_strategy, (STRATEGY_VIDEO_FRAMES, STRATEGY_NONE))

    def test_mp4_extension(self):
        items = handle(b"\x00" * 32, "video.mp4", filename="video.mp4")
        self.assertEqual(items[0].modality, "video")

    def test_mov_extension(self):
        items = handle(b"\x00" * 32, "clip.mov", filename="clip.mov")
        self.assertEqual(items[0].modality, "video")

    def test_video_fingerprint_set(self):
        items = handle(_MP4_MAGIC, "vid.mp4")
        self.assertTrue(items[0].source_fingerprint)


# ---------------------------------------------------------------------------
# A5 — audio → quarantine
# ---------------------------------------------------------------------------

class TestAudioQuarantine(unittest.TestCase):
    def test_mp3_quarantined(self):
        items = handle(_MP3_MAGIC, "song.mp3")
        self.assertEqual(items[0].modality, "quarantine")
        self.assertIn("audio", items[0].quarantine_reason.lower())
        self.assertEqual(items[0].extraction_strategy, STRATEGY_NONE)

    def test_flac_quarantined(self):
        items = handle(_FLAC_MAGIC, "track.flac")
        self.assertEqual(items[0].modality, "quarantine")

    def test_wav_extension_quarantined(self):
        wav = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 10
        items = handle(wav, "audio.wav", filename="audio.wav")
        self.assertEqual(items[0].modality, "quarantine")


# ---------------------------------------------------------------------------
# A4 — unknown binary → quarantine
# ---------------------------------------------------------------------------

class TestUnknownBinaryQuarantine(unittest.TestCase):
    def test_random_binary_quarantined(self):
        items = handle(_RANDOM_BIN, "mystery.bin")
        self.assertEqual(items[0].modality, "quarantine")

    def test_empty_quarantined(self):
        items = handle(b"", "empty.dat")
        self.assertEqual(items[0].modality, "quarantine")
        self.assertIn("empty", items[0].quarantine_reason)


# ---------------------------------------------------------------------------
# A9 / A10 / A11 — structural invariants on all items
# ---------------------------------------------------------------------------

class TestModalityItemInvariants(unittest.TestCase):
    _CASES = [
        (_PNG_MAGIC, "img.png"),
        (_MP4_MAGIC, "vid.mp4"),
        (_RANDOM_BIN, "bin.dat"),
        (_MP3_MAGIC, "audio.mp3"),
        (b"def foo(): pass\n", "foo.py"),
        (b"", "empty.dat"),
    ]

    def test_strategy_always_set(self):
        for data, name in self._CASES:
            items = handle(data, name)
            for item in items:
                self.assertNotEqual(item.extraction_strategy, "",
                                    f"empty strategy on {name}")

    def test_text_items_have_no_raw_bytes(self):
        items = handle(b"print('hi')", "hello.py")
        self.assertIsNone(items[0].raw_bytes)

    def test_media_items_have_no_parsed_unit(self):
        for payload, name in [(_PNG_MAGIC, "img.png"), (_MP4_MAGIC, "vid.mp4")]:
            items = handle(payload, name)
            self.assertIsNone(items[0].parsed_unit, f"parsed_unit should be None for {name}")

    def test_fingerprint_set_on_nonempty(self):
        for data, name in self._CASES:
            if not data:
                continue
            items = handle(data, name)
            for item in items:
                self.assertTrue(item.source_fingerprint, f"no fingerprint on {name}")

    def test_schema_always_correct(self):
        for data, name in self._CASES:
            items = handle(data, name)
            for item in items:
                self.assertEqual(item.schema, SCHEMA)


# ---------------------------------------------------------------------------
# A6 / A7 — fuzz: handle() never raises
# ---------------------------------------------------------------------------

class TestHandleFuzz(unittest.TestCase):
    def test_never_raises_on_50_random_inputs(self):
        rng = random.Random(42)
        for i in range(50):
            size = rng.randint(0, 32_768)
            data = bytes(rng.getrandbits(8) for _ in range(size))
            ext = rng.choice(["", ".bin", ".dat", ".xyz", ".py", ".png", ".mp4", ".ts", ".wav"])
            origin = f"fuzz_{i}{ext}"
            try:
                items = handle(data, origin, filename=origin)
            except Exception as exc:
                self.fail(f"handle() raised on fuzz input {i}: {exc}")
            self.assertGreater(len(items), 0, f"empty result on fuzz {i}")
            self.assertEqual(items[0].schema, SCHEMA)


# ---------------------------------------------------------------------------
# A12 — fuzz: extract() never raises
# ---------------------------------------------------------------------------

class TestExtractFuzz(unittest.TestCase):
    def _make_item(self, modality: str, strategy: str,
                   data: bytes, origin: str) -> ModalityItem:
        return ModalityItem(
            schema=SCHEMA, modality=modality,
            parsed_unit=None, raw_bytes=data,
            mime="application/octet-stream", origin=origin,
            extraction_strategy=strategy,
        )

    def test_never_raises_on_text_direct(self):
        item = ModalityItem(
            schema=SCHEMA, modality="text",
            parsed_unit="hello", raw_bytes=None,
            mime="text/plain", origin="test",
            extraction_strategy=STRATEGY_TEXT_DIRECT,
        )
        result = extract(item)
        self.assertEqual(result[0].parsed_unit, "hello")

    def test_never_raises_on_quarantine(self):
        item = self._make_item("quarantine", STRATEGY_NONE, _RANDOM_BIN, "q.bin")
        try:
            result = extract(item)
        except Exception as exc:
            self.fail(f"extract() raised: {exc}")
        self.assertGreater(len(result), 0)

    def test_never_raises_on_visual_embed(self):
        item = self._make_item("image", STRATEGY_VISUAL_EMBED, _PNG_MAGIC, "img.png")
        try:
            result = extract(item)
        except Exception as exc:
            self.fail(f"extract() raised: {exc}")
        self.assertGreater(len(result), 0)

    def test_never_raises_on_50_random_items(self):
        rng = random.Random(99)
        strategies = [STRATEGY_TEXT_DIRECT, STRATEGY_OCR_IMAGE,
                      STRATEGY_VISUAL_EMBED, STRATEGY_NONE]
        for i in range(50):
            data = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 1024)))
            strategy = rng.choice(strategies)
            modality = "text" if strategy == STRATEGY_TEXT_DIRECT else "image"
            parsed = "text" if strategy == STRATEGY_TEXT_DIRECT else None
            item = ModalityItem(
                schema=SCHEMA, modality=modality,
                parsed_unit=parsed, raw_bytes=data if parsed is None else None,
                mime="application/octet-stream", origin=f"fuzz_{i}",
                extraction_strategy=strategy,
            )
            try:
                result = extract(item)
            except Exception as exc:
                self.fail(f"extract() raised on fuzz item {i}: {exc}")
            self.assertGreater(len(result), 0)


# ---------------------------------------------------------------------------
# A13 — video strategy set correctly based on ffmpeg availability
# ---------------------------------------------------------------------------

class TestVideoStrategy(unittest.TestCase):
    def test_strategy_video_frames_when_ffmpeg_available(self):
        with patch("lgwks_input._ffmpeg_available", return_value=True):
            items = handle(_MP4_MAGIC, "vid.mp4")
        self.assertEqual(items[0].extraction_strategy, STRATEGY_VIDEO_FRAMES)

    def test_strategy_none_when_ffmpeg_unavailable(self):
        with patch("lgwks_input._ffmpeg_available", return_value=False):
            items = handle(_MP4_MAGIC, "vid.mp4")
        self.assertEqual(items[0].extraction_strategy, STRATEGY_NONE)

    def test_extract_video_frames_produces_items_when_ffmpeg_available(self):
        # Only run if real ffmpeg is present (integration test)
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        # Create a minimal valid mp4-like item; if ffmpeg can't decode it,
        # extract() must still return quarantine, not raise.
        item = ModalityItem(
            schema=SCHEMA, modality="video",
            parsed_unit=None, raw_bytes=b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32,
            mime="video/mp4", origin="test.mp4",
            extraction_strategy=STRATEGY_VIDEO_FRAMES,
        )
        try:
            result = extract(item)
        except Exception as exc:
            self.fail(f"extract() raised: {exc}")
        self.assertGreater(len(result), 0)
        # Result is either frame items or a quarantine — both are valid
        self.assertTrue(all(r.schema == SCHEMA for r in result))


# ---------------------------------------------------------------------------
# A14 — image strategy: OCR_IMAGE if tesseract, else VISUAL_EMBED
# ---------------------------------------------------------------------------

class TestImageStrategy(unittest.TestCase):
    def test_ocr_strategy_when_tesseract_available(self):
        with patch("lgwks_input._tesseract_available", return_value=True):
            items = handle(_PNG_MAGIC, "img.png")
        self.assertEqual(items[0].extraction_strategy, STRATEGY_OCR_IMAGE)

    def test_visual_embed_when_tesseract_unavailable(self):
        with patch("lgwks_input._tesseract_available", return_value=False):
            items = handle(_PNG_MAGIC, "img.png")
        self.assertEqual(items[0].extraction_strategy, STRATEGY_VISUAL_EMBED)

    def test_extract_ocr_returns_text_when_tesseract_works(self):
        with patch("lgwks_input._ocr_image_bytes", return_value="OCR OUTPUT TEXT"):
            item = ModalityItem(
                schema=SCHEMA, modality="image",
                parsed_unit=None, raw_bytes=_PNG_MAGIC,
                mime="image/png", origin="img.png",
                extraction_strategy=STRATEGY_OCR_IMAGE,
                source_fingerprint="abc",
            )
            result = extract(item)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].modality, "text")
        self.assertEqual(result[0].parsed_unit, "OCR OUTPUT TEXT")
        self.assertEqual(result[0].extraction_strategy, STRATEGY_TEXT_DIRECT)

    def test_extract_ocr_falls_back_to_visual_embed_on_failure(self):
        with patch("lgwks_input._ocr_image_bytes", return_value=None):
            item = ModalityItem(
                schema=SCHEMA, modality="image",
                parsed_unit=None, raw_bytes=_PNG_MAGIC,
                mime="image/png", origin="img.png",
                extraction_strategy=STRATEGY_OCR_IMAGE,
                source_fingerprint="abc",
            )
            result = extract(item)
        self.assertEqual(result[0].extraction_strategy, STRATEGY_VISUAL_EMBED)


# ---------------------------------------------------------------------------
# handle_path convenience wrapper
# ---------------------------------------------------------------------------

class TestHandlePath(unittest.TestCase):
    def test_reads_real_file(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x = 1\n")
            tmp = Path(f.name)
        try:
            items = handle_path(tmp)
            self.assertEqual(items[0].modality, "text")
            self.assertEqual(items[0].extraction_strategy, STRATEGY_TEXT_DIRECT)
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_file_returns_quarantine(self):
        items = handle_path(Path("/nonexistent/file.py"))
        self.assertEqual(items[0].modality, "quarantine")
        self.assertIn("read error", items[0].quarantine_reason)

    def test_origin_defaults_to_path(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"content")
            tmp = Path(f.name)
        try:
            items = handle_path(tmp)
            self.assertEqual(items[0].origin, str(tmp))
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# needs_extraction() helper
# ---------------------------------------------------------------------------

class TestNeedsExtraction(unittest.TestCase):
    def test_text_direct_does_not_need_extraction(self):
        item = ModalityItem(
            schema=SCHEMA, modality="text", parsed_unit="hi",
            raw_bytes=None, mime="text/plain", origin="f.py",
            extraction_strategy=STRATEGY_TEXT_DIRECT,
        )
        self.assertFalse(item.needs_extraction())

    def test_ocr_image_needs_extraction(self):
        item = ModalityItem(
            schema=SCHEMA, modality="image", parsed_unit=None,
            raw_bytes=_PNG_MAGIC, mime="image/png", origin="f.png",
            extraction_strategy=STRATEGY_OCR_IMAGE,
        )
        self.assertTrue(item.needs_extraction())

    def test_video_frames_needs_extraction(self):
        item = ModalityItem(
            schema=SCHEMA, modality="video", parsed_unit=None,
            raw_bytes=_MP4_MAGIC, mime="video/mp4", origin="f.mp4",
            extraction_strategy=STRATEGY_VIDEO_FRAMES,
        )
        self.assertTrue(item.needs_extraction())

    def test_none_does_not_need_extraction(self):
        item = ModalityItem(
            schema=SCHEMA, modality="quarantine", parsed_unit=None,
            raw_bytes=_RANDOM_BIN, mime="application/octet-stream", origin="f.bin",
            extraction_strategy=STRATEGY_NONE,
        )
        self.assertFalse(item.needs_extraction())


if __name__ == "__main__":
    unittest.main()
