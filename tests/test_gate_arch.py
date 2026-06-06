"""
Tests for the G1 Architecture gate (spec-00).

Verifies:
  • HARD forbidden-import rule violation → FAIL
  • ADVISORY rule violation → CANNOT_DECIDE (never FAIL)
  • conformant fixture → PASS
  • rule klass read from arch-rules.json, never decided at runtime
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lgwks_gate_arch import RuleVerifier, make_arch_verifiers
from lgwks_verify import Klass, Outcome


class TestArchGate(unittest.TestCase):
    def test_hard_forbidden_import(self):
        """A module violating a HARD forbidden-import rule → FAIL naming the edge."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("import urllib.request\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "data-boundary-no-network",
                "klass": "HARD",
                "kind": "forbidden-import",
                "from": [path.stem],
                "must_not_import": ["urllib.request", "urllib"],
                "diagnosis_hint": "found a network import in a data-boundary module",
            }
            v = RuleVerifier(rule)
            verdict = v.check(path, {})
            self.assertEqual(verdict.outcome, Outcome.FAIL)
            self.assertEqual(verdict.klass, Klass.HARD)
            self.assertIn("urllib.request", verdict.diagnosis or "")
        finally:
            os.unlink(path)

    def test_conformant_passes(self):
        """A conformant fixture → PASS."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("import json\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "data-boundary-no-network",
                "klass": "HARD",
                "kind": "forbidden-import",
                "from": [path.stem],
                "must_not_import": ["urllib.request"],
                "diagnosis_hint": "found a network import",
            }
            v = RuleVerifier(rule)
            verdict = v.check(path, {})
            self.assertEqual(verdict.outcome, Outcome.PASS)
        finally:
            os.unlink(path)

    def test_advisory_silent_except(self):
        """An ADVISORY rule violation → CANNOT_DECIDE score + note, never FAIL."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("try:\n    pass\nexcept Exception:\n    pass\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "typed-errors-no-silent-except",
                "klass": "ADVISORY",
                "kind": "ast-pattern",
                "forbid_pattern": "except handler whose body is only `pass`",
                "applies_to": [path.stem],
                "diagnosis_hint": "empty except swallows a typed error",
            }
            v = RuleVerifier(rule)
            verdict = v.check(path, {})
            self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
            self.assertEqual(verdict.klass, Klass.ADVISORY)
            self.assertIn("Pass", verdict.diagnosis or "")
        finally:
            os.unlink(path)

    def test_advisory_no_global_mutable(self):
        """Module-level mutable binding → ADVISORY CANNOT_DECIDE."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("counter = 0\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "no-module-level-mutable-global",
                "klass": "ADVISORY",
                "kind": "no-global-mutable-state",
                "applies_to": [path.stem],
                "allow": ["UPPER_CASE constants"],
                "diagnosis_hint": "module-level mutable binding detected",
            }
            v = RuleVerifier(rule)
            verdict = v.check(path, {})
            self.assertEqual(verdict.outcome, Outcome.CANNOT_DECIDE)
            self.assertEqual(verdict.klass, Klass.ADVISORY)
            self.assertIn("counter", verdict.diagnosis or "")
        finally:
            os.unlink(path)

    def test_klass_read_from_data(self):
        """Each rule's HARD|ADVISORY class is read from arch-rules.json, never decided at runtime."""
        verifiers = make_arch_verifiers()
        for v in verifiers:
            self.assertIn(v.klass, {Klass.HARD, Klass.ADVISORY})
            # The rule id must be from arch-rules.json
            self.assertTrue(v.gate_id)

    def test_dynamic_forbidden_import_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("import importlib\nmod = importlib.import_module('urllib.request')\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "data-boundary-no-network",
                "klass": "HARD",
                "kind": "forbidden-import",
                "from": [path.stem],
                "must_not_import": ["urllib.request"],
                "diagnosis_hint": "found a network import",
            }
            verdict = RuleVerifier(rule).check(path, {})
            self.assertEqual(verdict.outcome, Outcome.FAIL)
            self.assertIn("dynamic import", verdict.diagnosis or "")
        finally:
            os.unlink(path)

    def test_dynamic_allowed_import_does_not_fail(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
            fh.write("import importlib\nmod = importlib.import_module('json')\n")
            fh.flush()
            path = Path(fh.name)
        try:
            rule = {
                "id": "data-boundary-no-network",
                "klass": "HARD",
                "kind": "forbidden-import",
                "from": [path.stem],
                "must_not_import": ["urllib.request"],
                "diagnosis_hint": "found a network import",
            }
            verdict = RuleVerifier(rule).check(path, {})
            self.assertEqual(verdict.outcome, Outcome.PASS)
        finally:
            os.unlink(path)

    def test_malformed_rule_rejected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write(json.dumps({"rules": [{"id": "bad-rule", "klass": "HARD"}]}))
            fh.flush()
            path = Path(fh.name)
        try:
            with self.assertRaises(ValueError):
                make_arch_verifiers(rules_path=path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
