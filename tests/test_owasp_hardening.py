"""OWASP hardening regression tests — SSRF, Path Traversal (LFI), SQLi.

These vectors were originally captured as ad-hoc print-scripts at the repo root
(ssrf_test.py, lfi_test.py, sqli_test.py, ssrf_redirect_test.py) during the U5
OWASP hardening pass. They are folded here as real assertions so the coverage is
enforced by the suite instead of relying on a human eyeballing stdout.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import lgwks_browser as browser
from lgwks_storage import StorageGate
from lgwks_substrate_io import _iter_text_files


class TestSSRFGuard(unittest.TestCase):
    """_remote_allowed must reject loopback, link-local, metadata, and the
    classic IP-obfuscation / DNS-rebinding bypasses — not just literal 127.0.0.1."""

    BLOCKED = [
        "http://127.0.0.1",
        "http://localhost",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (cred theft)
        "http://metadata.google.internal",
        "file:///etc/passwd",                          # non-http scheme
        "gopher://127.0.0.1:6379",                     # gopher → redis SSRF
        "http://2130706433",                           # decimal-encoded 127.0.0.1
        "http://0x7f000001",                           # hex-encoded 127.0.0.1
        "http://127.0.0.1.xip.io",                     # wildcard-DNS rebinding
        "http://127.0.0.1.nip.io/foo",                 # wildcard-DNS rebinding
    ]

    def test_all_bypass_vectors_blocked(self):
        for url in self.BLOCKED:
            with self.subTest(url=url):
                self.assertFalse(
                    browser._remote_allowed(url),
                    f"SSRF guard must block {url!r}",
                )


class TestPathTraversalGuard(unittest.TestCase):
    """_iter_text_files must not follow a symlink that escapes the scan root —
    an attacker dropping a symlink to /etc/passwd must not get it ingested."""

    def test_out_of_tree_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "scan_root"
            root.mkdir()
            (root / "legit.txt").write_text("legit content")

            secret = Path(td) / "secret.txt"
            secret.write_text("SUPER_SECRET_DATA")
            evil = root / "evil.txt"
            os.symlink(secret, evil)

            discovered = {Path(f).name for f in _iter_text_files(root, 100)}
            self.assertIn("legit.txt", discovered)
            self.assertNotIn(
                "evil.txt",
                discovered,
                "out-of-tree symlink must not be traversed (LFI)",
            )


class TestSQLInjectionGuard(unittest.TestCase):
    """Storage queries are parameterized: a SQL-control-character CID must be
    stored/queried as an opaque literal, never interpreted as SQL."""

    MALICIOUS_CID = "' OR 1=1; --"

    def test_malicious_cid_stored_as_literal(self):
        with tempfile.TemporaryDirectory() as td:
            gate = StorageGate(Path(td), tenant_id="tenant1")
            gate.ingest_fact(self.MALICIOUS_CID, "test content", "text", "test_cap")

            row = gate.fact_list.lookup(self.MALICIOUS_CID)
            self.assertIsNotNone(row, "literal CID must round-trip via parameterized query")
            self.assertEqual(row["fact_hash"], self.MALICIOUS_CID)
            self.assertEqual(row["fact_text"], "test content")

    def test_injection_does_not_corrupt_table(self):
        with tempfile.TemporaryDirectory() as td:
            gate = StorageGate(Path(td), tenant_id="tenant1")
            gate.ingest_fact("benign-cid", "kept", "text", "cap")
            gate.ingest_fact(self.MALICIOUS_CID, "evil", "text", "cap")

            # The benign row must survive; the injection string is inert data.
            self.assertEqual(gate.fact_list.lookup("benign-cid")["fact_text"], "kept")


if __name__ == "__main__":
    unittest.main()
