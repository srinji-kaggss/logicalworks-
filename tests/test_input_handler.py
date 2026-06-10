"""Acceptance tests for lgwks.modality.item.v1 (I2).

Acceptance criteria from INGESTION-PLAN §I2:
  A1. known text extensions → modality="text", parsed_unit is non-empty str
  A2. PNG/JPEG/WEBP magic bytes → modality="image", raw_bytes preserved
  A3. MP4 magic bytes → modality="video", raw_bytes preserved
  A4. unknown binary → modality="quarantine"
  A5. audio bytes → modality="quarantine"
  A6. handle() NEVER raises — fuzz 50 random byte strings, no crash
  A7. handle() returns at least one ModalityItem in every case
  A8. schema field is always "lgwks.modality.item.v1"
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgwks_input import (
    SCHEMA,
    ModalityItem,
    handle,
    handle_path,
    _sniff_mime,
    _looks_text,
)

# ---------------------------------------------------------------------------
# Minimal synthetic bytes for each modality
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
_RANDOM_BIN  = bytes(range(256))  # clearly binary, not text


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
        self.assertTrue(items, "must return at least one item")
        return items[0]

    def test_py_file(self):
        code = b"def foo():\n    return 42\n"
        item = self._text_item(code, "foo.py")
        self.assertEqual(item.modality, "text")
        self.assertIsInstance(item.parsed_unit, str)
        self.assertIn("foo", item.parsed_unit)
        self.assertIsNone(item.raw_bytes)

    def test_txt_file(self):
        item = self._text_item(b"hello world\n", "readme.txt")
        self.assertEqual(item.modality, "text")

    def test_md_file(self):
        item = self._text_item(b"# Title\n\nBody text\n", "README.md")
        self.assertEqual(item.modality, "text")

    def test_json_file(self):
        item = self._text_item(b'{"key": "value"}', "data.json")
        self.assertEqual(item.modality, "text")

    def test_ts_file(self):
        item = self._text_item(b"const x: number = 1;", "app.ts")
        self.assertEqual(item.modality, "text")

    def test_rust_file(self):
        item = self._text_item(b"fn main() {}", "main.rs")
        self.assertEqual(item.modality, "text")

    def test_shell_script(self):
        item = self._text_item(b"#!/bin/bash\necho hi\n", "run.sh")
        self.assertEqual(item.modality, "text")

    def test_yaml_file(self):
        item = self._text_item(b"key: value\nlist:\n  - a\n", "config.yml")
        self.assertEqual(item.modality, "text")

    def test_looks_text_heuristic_for_unknown_ext(self):
        item = self._text_item(b"plaintext payload " * 100, "unknown.blob")
        self.assertEqual(item.modality, "text", "heuristic should catch printable binary")

    def test_text_item_schema(self):
        item = self._text_item(b"content", "file.py")
        self.assertEqual(item.schema, SCHEMA)


# ---------------------------------------------------------------------------
# A2 — image routing
# ---------------------------------------------------------------------------

class TestImageRouting(unittest.TestCase):
    def test_png_magic(self):
        items = handle(_PNG_MAGIC, "photo.png")
        self.assertEqual(items[0].modality, "image")
        self.assertEqual(items[0].raw_bytes, _PNG_MAGIC)
        self.assertIsNone(items[0].parsed_unit)

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
        # Plain bytes but .png extension — extension wins
        items = handle(b"fakepng", "logo.png", filename="logo.png")
        self.assertEqual(items[0].modality, "image")

    def test_raw_bytes_preserved(self):
        items = handle(_PNG_MAGIC, "img.png")
        self.assertEqual(items[0].raw_bytes, _PNG_MAGIC)


# ---------------------------------------------------------------------------
# A3 — video routing
# ---------------------------------------------------------------------------

class TestVideoRouting(unittest.TestCase):
    def test_mp4_magic(self):
        items = handle(_MP4_MAGIC, "clip.mp4")
        self.assertEqual(items[0].modality, "video")
        self.assertEqual(items[0].raw_bytes, _MP4_MAGIC)
        self.assertIsNone(items[0].parsed_unit)

    def test_mp4_extension(self):
        items = handle(b"\x00" * 32, "video.mp4", filename="video.mp4")
        self.assertEqual(items[0].modality, "video")

    def test_mov_extension(self):
        items = handle(b"\x00" * 32, "clip.mov", filename="clip.mov")
        self.assertEqual(items[0].modality, "video")


# ---------------------------------------------------------------------------
# A5 — audio → quarantine
# ---------------------------------------------------------------------------

class TestAudioQuarantine(unittest.TestCase):
    def test_mp3_quarantined(self):
        items = handle(_MP3_MAGIC, "song.mp3")
        self.assertEqual(items[0].modality, "quarantine")
        self.assertIn("audio", items[0].quarantine_reason.lower())

    def test_flac_quarantined(self):
        items = handle(_FLAC_MAGIC, "track.flac")
        self.assertEqual(items[0].modality, "quarantine")

    def test_wav_extension_quarantined(self):
        items = handle(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 10, "audio.wav", filename="audio.wav")
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
# A6 / A7 / A8 — handle() invariants
# ---------------------------------------------------------------------------

class TestInvariants(unittest.TestCase):
    def test_never_raises_on_50_random_inputs(self):
        rng = random.Random(42)
        for i in range(50):
            size = rng.randint(0, 32_768)
            data = bytes(rng.getrandbits(8) for _ in range(size))
            ext = rng.choice(["", ".bin", ".dat", ".xyz", ".py", ".png", ".mp4"])
            origin = f"fuzz_{i}{ext}"
            try:
                items = handle(data, origin, filename=origin)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"handle() raised on fuzz input {i}: {exc}")
            self.assertGreater(len(items), 0, f"empty result on fuzz {i}")
            self.assertEqual(items[0].schema, SCHEMA, f"wrong schema on fuzz {i}")

    def test_always_returns_list(self):
        for payload in [b"", b"hello", _RANDOM_BIN, _PNG_MAGIC]:
            result = handle(payload, "test")
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)

    def test_schema_always_lgwks_modality_item_v1(self):
        for payload, name in [
            (b"code", "file.py"),
            (_PNG_MAGIC, "img.png"),
            (_MP4_MAGIC, "vid.mp4"),
            (_RANDOM_BIN, "bin.dat"),
            (_MP3_MAGIC, "audio.mp3"),
        ]:
            items = handle(payload, name)
            for item in items:
                self.assertEqual(item.schema, SCHEMA)

    def test_text_item_has_no_raw_bytes(self):
        items = handle(b"print('hi')", "hello.py")
        self.assertIsNone(items[0].raw_bytes)

    def test_media_item_has_no_parsed_unit(self):
        for payload, name in [(_PNG_MAGIC, "img.png"), (_MP4_MAGIC, "vid.mp4")]:
            items = handle(payload, name)
            self.assertIsNone(items[0].parsed_unit)


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


if __name__ == "__main__":
    unittest.main()
