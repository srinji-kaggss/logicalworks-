"""
Tests for the data trust boundary (build #2): untrusted-cache · cognition-log · intent-vault.
Each store is redirected to a temp dir so tests never touch real data. Verifies the T0 invariants:
content-addressing + integrity, append-only chain tamper-evidence, vault fail-closed + encrypt-at-rest,
and store SEPARATION (a write to one never lands in another).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_cache as cache
import lgwks_cognition as cognition
import lgwks_vault as vault
import lgwks_sign as sign


class TestUntrustedCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cache._DIR = Path(self.tmp) / "untrusted"
        cache._INDEX = cache._DIR / "index.jsonl"

    def test_content_addressed_dedup_and_integrity(self):
        e1 = cache.put("https://x.com/a", "html", "hello world")
        e2 = cache.put("https://x.com/a", "html", "hello world")
        self.assertEqual(e1["hash"], e2["hash"], "same content → same hash (dedup)")
        self.assertEqual(len(cache.entries()), 1, "identical content stored once")
        self.assertEqual(cache.get_text(e1["hash"]), "hello world")

    def test_tamper_on_read_returns_none(self):
        e = cache.put("u", "html", "trusted-bytes")
        Path(e["path"]).write_text("ALTERED")          # someone edits the cached file
        self.assertIsNone(cache.get_bytes(e["hash"]), "hash mismatch ⇒ treated as absent (tamper-evident)")

    def test_cached_file_is_not_executable(self):
        e = cache.put("u", "html", "x")
        self.assertFalse(os.access(e["path"], os.X_OK), "untrusted data is never executable")


class TestCognitionLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cognition._DIR = Path(self.tmp) / "cognition"

    def test_chain_verifies_and_persists_across_instances(self):
        log = cognition.CognitionLog("t", key=b"k")
        log.append("intent_commit", {"prompt": "Canada Life", "gap": "no timeframe", "why": "investment"})
        log.append("thought", {"note": "needs crawl-2"})
        # a fresh instance continues the same chain and still verifies
        log2 = cognition.CognitionLog("t", key=b"k")
        self.assertTrue(log2.verify())
        self.assertEqual(len(log2.corpus("intent_commit")), 1, "corpus reads back the training data")

    def test_tampering_breaks_the_chain(self):
        log = cognition.CognitionLog("t2", key=b"k")
        log.append("note", {"a": 1})
        log.append("note", {"a": 2})
        p = cognition._log_path("t2")
        lines = p.read_text().splitlines()
        lines[0] = lines[0].replace('"a":1', '"a":999') if '"a":1' in lines[0] else lines[0].replace('"a": 1', '"a": 999')
        p.write_text("\n".join(lines) + "\n")
        self.assertFalse(cognition.CognitionLog("t2", key=b"k").verify(), "rewriting a past entry breaks the chain")

    def test_unknown_kind_rejected(self):
        log = cognition.CognitionLog("t3", key=b"k")
        with self.assertRaises(ValueError):
            log.append("freeform-anything", {})


class TestIntentVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        vault._DIR = Path(self.tmp) / "intent"
        self._orig = sign.signing_key

    def tearDown(self):
        sign.signing_key = self._orig

    def test_locked_when_unanchored_refuses_to_store(self):
        sign.signing_key = lambda: (b"", "unanchored")     # no real key
        self.assertFalse(vault.is_unlocked())
        with self.assertRaises(PermissionError):
            vault.set_entry("ssn", "123-45-6789")          # fail-closed: never plaintext PII

    def test_encrypted_roundtrip_when_keyed(self):
        sign.signing_key = lambda: (b"a-real-anchored-secret", "keyed-env")
        vault.set_entry("intent", {"goal": "invest", "horizon": "3yr"})
        self.assertEqual(vault.get_entry("intent"), {"goal": "invest", "horizon": "3yr"})
        # the on-disk blob is ciphertext — the plaintext value must NOT appear
        blob = next(vault._DIR.glob("*.enc")).read_bytes()
        self.assertNotIn(b"invest", blob, "value is encrypted at rest, never plaintext")
        self.assertEqual(vault.keys(), ["intent"], "keys() lists names only")

    def test_foreign_blob_reads_as_absent(self):
        sign.signing_key = lambda: (b"keyA", "keyed-env")
        vault.set_entry("k", "v")
        sign.signing_key = lambda: (b"keyB-different", "keyed-env")   # wrong key
        self.assertIsNone(vault.get_entry("k"), "undecryptable under a different key ⇒ absent, never surfaced")


if __name__ == "__main__":
    unittest.main()
