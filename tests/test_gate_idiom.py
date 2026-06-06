"""
Tests for the G2 Idiom gate (spec-00).

Verifies:
  • always ADVISORY (never FAIL, never blocks ship)
  • emits score 0..1 + idiom-diff report
  • embedder failure → CANNOT_DECIDE, NOT a 0 score
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_gate_idiom import IdiomVerifier
from lgwks_verify import Klass, Outcome


class TestIdiomGate(unittest.TestCase):
    def test_advisory_only_never_fail(self):
        """Always returns an ADVISORY verdict (never FAIL, never blocks ship)."""
        v = IdiomVerifier()
        self.assertEqual(v.klass, Klass.ADVISORY)

    def test_score_and_report(self):
        """Emits a score in 0..1 + an idiom-diff report."""
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            (corpus / "a.py").write_text("def hello(): pass\n")
            (corpus / "b.py").write_text("def world(): pass\n")
            v = IdiomVerifier(corpus_dir=corpus, max_files=10)
            candidate = "def foo(): pass\n"
            verdict = v.check(candidate, {})
            self.assertEqual(verdict.outcome, Outcome.PASS)
            self.assertEqual(verdict.klass, Klass.ADVISORY)
            self.assertIsNotNone(verdict.score)
            self.assertGreaterEqual(verdict.score, 0.0)
            self.assertLessEqual(verdict.score, 1.0)
            self.assertTrue(any("score" in e for e in verdict.evidence or []))
            self.assertTrue(any("exemplars" in e for e in verdict.evidence or []))
            self.assertTrue(any("deviations" in e for e in verdict.evidence or []))

    def test_embedder_failure_cannot_decide(self):
        """On embedder failure returns ADVISORY+CANNOT_DECIDE — NOT a 0 score."""
        v = IdiomVerifier()
        # monkeypatch _corpus_embeddings to simulate failure
        v._corpus_embeddings = lambda: None
        verdict = v.check("def foo(): pass\n", {})
        self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
        self.assertEqual(verdict.klass, Klass.ADVISORY)
        self.assertIsNone(verdict.score)

    def test_empty_corpus_cannot_decide(self):
        """Empty corpus → CANNOT_DECIDE."""
        with tempfile.TemporaryDirectory() as tmp:
            v = IdiomVerifier(corpus_dir=tmp, max_files=10)
            verdict = v.check("def foo(): pass\n", {})
            self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
            self.assertIsNone(verdict.score)

    def test_duplicate_content_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            (corpus / "a.py").write_text("def hello(): pass\n")
            (corpus / "b.py").write_text("def hello(): pass\n")
            v = IdiomVerifier(corpus_dir=corpus, max_files=10)
            verdict = v.check("def world(): pass\n", {})
            self.assertEqual(verdict.outcome, Outcome.PASS)
            self.assertTrue(any("duplicate" in e.lower() for e in verdict.evidence or []))

    def test_similarity_failure_cannot_decide(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            (corpus / "a.py").write_text("def hello(): pass\n")
            v = IdiomVerifier(corpus_dir=corpus, max_files=10)
            import lgwks_embed
            orig_cos = lgwks_embed._cos
            lgwks_embed._cos = lambda _a, _b: (_ for _ in ()).throw(RuntimeError("math domain error"))
            try:
                verdict = v.check("def foo(): pass\n", {})
                self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
                self.assertIn("similarity computation failed", verdict.diagnosis or "")
            finally:
                lgwks_embed._cos = orig_cos

    def test_score_bounds_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            (corpus / "a.py").write_text("def hello(): pass\n")
            v = IdiomVerifier(corpus_dir=corpus, max_files=10)
            import lgwks_embed
            orig_cos = lgwks_embed._cos
            lgwks_embed._cos = lambda _a, _b: 2.5
            try:
                with self.assertRaises(ValueError):
                    v.check("def foo(): pass\n", {})
            finally:
                lgwks_embed._cos = orig_cos


if __name__ == "__main__":
    unittest.main()
