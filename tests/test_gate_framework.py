"""
Tests for the G3 Framework-Reality gate (spec-00).

Verifies three L4 invariants:
  • candidate using only real symbols → PASS
  • candidate referencing a hallucinated symbol → FAIL (version-skew diagnosis)
  • missing rustdoc JSON → CANNOT_DECIDE, never silently PASS
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_gate_framework import G3Verifier
from lgwks_verify import Outcome


class TestG3Gate(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_dir = Path(__file__).resolve().parent / "fixtures" / "crate"
        self.verifier = G3Verifier(crate_dir=self.fixture_dir)

    def test_missing_crate_dir_cannot_decide(self):
        """Missing --crate-dir → CANNOT_DECIDE."""
        v = G3Verifier(crate_dir=None)
        verdict = v.check("use foo::Bar;", {})
        self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
        self.assertIn("no --crate-dir", verdict.diagnosis or "")

    def test_missing_rustdoc_cannot_decide(self):
        """Missing rustdoc JSON → CANNOT_DECIDE, never silently PASS."""
        # ensure no rustdoc JSON exists
        v = G3Verifier(crate_dir=self.fixture_dir)
        # _installed_symbols will look for rustdoc JSON; on stable it won't exist
        verdict = v.check("use fixture_crate::hello;", {})
        self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
        self.assertIn("rustdoc JSON not available", verdict.diagnosis or "")

    def test_valid_reference_passes(self):
        """Candidate using only real symbols → PASS."""
        v = G3Verifier(crate_dir=self.fixture_dir)
        # monkeypatch installed symbols to a known set
        v._installed_symbols = lambda: ({"fixture_crate::hello", "fixture_crate::Widget"}, [])
        verdict = v.check("use fixture_crate::hello;\nfn main() { hello(); }", {})
        self.assertEqual(verdict.outcome, Outcome.PASS)
        self.assertTrue(len(verdict.evidence or []) > 0)

    def test_hallucinated_symbol_fails(self):
        """Candidate referencing a symbol that does not exist in installed surface → FAIL."""
        v = G3Verifier(crate_dir=self.fixture_dir)
        v._installed_symbols = lambda: ({"fixture_crate::hello", "fixture_crate::Widget"}, [])
        verdict = v.check("use fixture_crate::nonexistent;\nfn main() { nonexistent(); }", {})
        self.assertEqual(verdict.outcome, Outcome.FAIL)
        self.assertIn("version-skew", verdict.diagnosis or "")
        self.assertIn("nonexistent", verdict.diagnosis or "")

    def test_grounding_context_emitted(self):
        """Pre-generation: PASS includes the installed symbol surface as evidence."""
        v = G3Verifier(crate_dir=self.fixture_dir)
        v._installed_symbols = lambda: ({"fixture_crate::hello", "fixture_crate::Widget"}, [])
        verdict = v.check("use fixture_crate::hello;", {})
        self.assertEqual(verdict.outcome, Outcome.PASS)
        self.assertTrue("fixture_crate::hello" in (verdict.evidence or []))

    def test_token_based_layer_catches_macro_paths(self):
        """DiD layer 2: token-based collector catches paths inside macro invocations
        that the regex-based extractor misses."""
        v = G3Verifier(crate_dir=self.fixture_dir)
        v._installed_symbols = lambda: ({"fixture_crate::hello", "fixture_crate::Widget"}, [])
        # The path appears inside a macro invocation with spaces — regex misses,
        # but token-based collector should catch it.
        code = 'macro_call! { fixture_crate :: hello }'
        refs = v._extract_references(code)
        self.assertIn("fixture_crate::hello", refs)

    def test_false_pass_surface_declared(self):
        """The verifier declares its false-PASS surface so consumers know the trust boundary."""
        from lgwks_gate_framework import _FALSE_PASS_SURFACE
        self.assertIn("regex-based", _FALSE_PASS_SURFACE)


if __name__ == "__main__":
    unittest.main()
