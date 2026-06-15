"""Tests for lgwks.tokenizer.registry.v1."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_tokenizer_registry as reg


class TestTokenizerRegistry(unittest.TestCase):
    def test_defaults_seeded(self):
        with tempfile.TemporaryDirectory() as td:
            r = reg.TokenizerRegistry(Path(td))
            self.assertTrue(r.has(reg.DEFAULT_WORD_REGEX_ID))
            self.assertTrue(r.has(reg.DEFAULT_AETHERIUS_ID))
            ids = {rec.tokenizer_id for rec in r.list_tokenizers()}
            self.assertIn(reg.DEFAULT_WORD_REGEX_ID, ids)
            self.assertIn(reg.DEFAULT_AETHERIUS_ID, ids)

    def test_register_and_get(self):
        with tempfile.TemporaryDirectory() as td:
            r = reg.TokenizerRegistry(Path(td))
            rec = r.register(
                tokenizer_id="custom:porter:v1",
                kind="porter",
                version="v1",
                config='{"stemmer": "porter"}',
                vocab_cid="",
                modality_anchors=(),
            )
            self.assertEqual(rec.tokenizer_id, "custom:porter:v1")
            self.assertEqual(r.get("custom:porter:v1").kind, "porter")

    def test_register_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            r = reg.TokenizerRegistry(Path(td))
            r.register(
                tokenizer_id="custom:porter:v1",
                kind="porter",
                version="v1",
                config='{"stemmer": "porter"}',
                vocab_cid="",
                modality_anchors=(),
            )
            r2 = r.register(
                tokenizer_id="custom:porter:v1",
                kind="other",
                version="v2",
                config='{"stemmer": "other"}',
                vocab_cid="changed",
                modality_anchors=(),
            )
            # First definition wins.
            self.assertEqual(r2.kind, "porter")
            self.assertEqual(r.get("custom:porter:v1").kind, "porter")

    def test_registry_persists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r1 = reg.TokenizerRegistry(root)
            r1.register(
                tokenizer_id="custom:porter:v1",
                kind="porter",
                version="v1",
                config='{"stemmer": "porter"}',
                vocab_cid="",
                modality_anchors=(),
            )
            r2 = reg.TokenizerRegistry(root)
            self.assertTrue(r2.has("custom:porter:v1"))

    def test_aetherius_anchors(self):
        with tempfile.TemporaryDirectory() as td:
            r = reg.TokenizerRegistry(Path(td))
            rec = r.get(reg.DEFAULT_AETHERIUS_ID)
            self.assertIn("[IMG]", rec.modality_anchors)
            self.assertIn("[TTY]", rec.modality_anchors)


if __name__ == "__main__":
    unittest.main()
