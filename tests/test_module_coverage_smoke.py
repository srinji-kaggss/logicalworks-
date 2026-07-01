"""Smoke-import tests for lgwks_redact and lgwks_proc.

These modules were previously in the EXCLUDED debt list in test_module_coverage.py.
Adding these smoke tests allows them to be removed from EXCLUDED.
"""

from __future__ import annotations

import unittest

import lgwks_proc
import lgwks_redact


class TestLgwksRedact(unittest.TestCase):
    def test_scrub_redacts_api_key(self):
        """scrub('api_key=abcdef12345678') contains [REDACTED] and does NOT contain abcdef12345678."""
        result = lgwks_redact.scrub("api_key=abcdef12345678")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("abcdef12345678", result)

    def test_SECRET_RE_is_compiled_regex(self):
        """SECRET_RE has a .sub attribute (compiled regex pattern)."""
        self.assertTrue(hasattr(lgwks_redact.SECRET_RE, "sub"))


class TestLgwksProc(unittest.TestCase):
    def test_is_git_repo_self(self):
        """is_git_repo('.') is True when run from repo root."""
        self.assertTrue(lgwks_proc.is_git_repo("."))

    def test_run_git_rev_parse(self):
        """run_git('.', 'rev-parse', '--is-inside-work-tree') returns (0, 'true')."""
        rc, out = lgwks_proc.run_git(".", "rev-parse", "--is-inside-work-tree")
        self.assertEqual((rc, out), (0, "true"))

    def test_run_git_nonexistent_path_returns_nonzero(self):
        """run_git on a nonexistent path returns a 2-tuple whose first element is not 0."""
        result = lgwks_proc.run_git("/definitely/not/a/real/path/xyz123", "status")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertNotEqual(result[0], 0)


if __name__ == "__main__":
    unittest.main()
