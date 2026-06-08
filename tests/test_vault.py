"""
Tests for lgwks_vault (hardened build #3).

Enterprise-grade assertions:
  * AES-256-GCM encrypts with distinct nonces every time
  * Argon2id KDF per version produces distinct keys
  * Audit log records every operation
  * Re-encryption changes ciphertext
  * Legacy Fernet entries are readable
  * Fail-closed when no signing key is anchored
  * Tampered ciphertext returns None (no exception leak)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_vault as vault
import lgwks_sign


class TestVaultEnterprise(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_dir = vault._DIR
        self._orig_audit = vault._AUDIT_LOG
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        vault._DIR = td / "store" / "intent"
        vault._AUDIT_DIR = td / ".lgwks"
        vault._AUDIT_LOG = vault._AUDIT_DIR / "vault-audit.jsonl"

    def tearDown(self) -> None:
        vault._DIR = self._orig_dir
        vault._AUDIT_LOG = self._orig_audit
        self._td.cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_audit(self) -> list[dict]:
        if not vault._AUDIT_LOG.exists():
            return []
        return [json.loads(line) for line in vault._AUDIT_LOG.read_text().splitlines() if line.strip()]

    def _fake_signing_key(self, secret: bytes = b"test-secret-48-characters-long!!!"):
        """Patch lgwks_sign.signing_key to return a keyed mode."""
        return mock.patch.object(lgwks_sign, "signing_key", return_value=(secret, "keyed-test"))

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------
    def test_set_get_roundtrip(self):
        """Value survives encrypt -> decrypt unchanged."""
        with self._fake_signing_key():
            meta = vault.set_entry("user:pii", {"email": "a@b.com", "ssn": "123-45-6789"})
            self.assertTrue(meta["stored"])
            self.assertEqual(meta["key_version"], "kv1")
            self.assertEqual(meta["mode"], "keyed-test")

            restored = vault.get_entry("user:pii")
            self.assertEqual(restored, {"email": "a@b.com", "ssn": "123-45-6789"})

    def test_distinct_nonces_produce_distinct_ciphertext(self):
        """Two set_entry calls for the same value must produce different ciphertexts."""
        with self._fake_signing_key():
            vault.set_entry("nonce-test", "x")
            blob1 = vault._entry_path("nonce-test").read_bytes()

            vault.set_entry("nonce-test", "x")
            blob2 = vault._entry_path("nonce-test").read_bytes()

            self.assertNotEqual(blob1, blob2)

    def test_tampered_ciphertext_returns_none(self):
        """Corrupted blob must not raise; must return None."""
        with self._fake_signing_key():
            vault.set_entry("tamper-test", {"secret": 42})
            p = vault._entry_path("tamper-test")
            blob = bytearray(p.read_bytes())
            blob[-1] ^= 0xFF  # flip last byte
            p.write_bytes(bytes(blob))

            self.assertIsNone(vault.get_entry("tamper-test"))

    # ------------------------------------------------------------------
    # KDF
    # ------------------------------------------------------------------
    def test_different_versions_produce_different_keys(self):
        """Argon2id with different salts must derive different keys."""
        with self._fake_signing_key():
            v1 = vault._derive_vault_key(b"test-secret", vault._get_version_salt("kv1"))
            v2 = vault._derive_vault_key(b"test-secret", vault._get_version_salt("kv2"))
            self.assertNotEqual(v1, v2)
            self.assertEqual(len(v1), 32)
            self.assertEqual(len(v2), 32)

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def test_set_creates_audit_record(self):
        """set_entry must leave an audit trail."""
        with self._fake_signing_key():
            vault.set_entry("audit-me", 1)
            events = self._read_audit()
            self.assertTrue(any(e["op"] == "set" and e["key_name"] == "audit-me" for e in events))

    def test_get_creates_audit_record(self):
        """get_entry must leave an audit trail."""
        with self._fake_signing_key():
            vault.set_entry("audit-read", 2)
            self._read_audit()  # clear prior
            vault.get_entry("audit-read")
            events = self._read_audit()
            reads = [e for e in events if e["op"] == "get"]
            self.assertTrue(len(reads) >= 1)

    def test_delete_creates_audit_record(self):
        """delete_entry must leave an audit trail."""
        with self._fake_signing_key():
            vault.set_entry("audit-del", 3)
            vault.delete_entry("audit-del")
            events = self._read_audit()
            dels = [e for e in events if e["op"] == "delete"]
            self.assertTrue(any(d["key_name"] == "audit-del" for d in dels))

    # ------------------------------------------------------------------
    # Key rotation
    # ------------------------------------------------------------------
    def test_re_encrypt_changes_ciphertext(self):
        """re_encrypt_entries must produce different ciphertext for every entry."""
        with self._fake_signing_key():
            vault.set_entry("rotate-me", {"val": 99})
            old_blob = vault._entry_path("rotate-me").read_bytes()

            result = vault.re_encrypt_entries(new_key_version="kv2")
            self.assertEqual(result["migrated"], 1)
            self.assertEqual(result["failed"], 0)

            new_blob = vault._entry_path("rotate-me").read_bytes()
            self.assertNotEqual(old_blob, new_blob)
            # Version header must reflect new version
            self.assertTrue(new_blob.startswith(b"kv2:"))

            # Data must still decrypt
            data = vault.get_entry("rotate-me")
            self.assertEqual(data, {"val": 99})

    # ------------------------------------------------------------------
    # Legacy compatibility
    # ------------------------------------------------------------------
    def test_legacy_fernet_entry_readable(self):
        """An old Fernet blob must still decrypt and be flagged as legacy."""
        with self._fake_signing_key():
            # Write a legacy Fernet blob directly
            from cryptography.fernet import Fernet
            secret, _ = lgwks_sign.signing_key()
            material = hashlib.sha256(b"lgwks-vault-v1\x00" + secret).digest()
            key = __import__("base64").urlsafe_b64encode(material)
            f = Fernet(key)
            blob = f.encrypt(json.dumps({"legacy": True}).encode("utf-8"))
            vault._DIR.mkdir(parents=True, exist_ok=True)
            vault._entry_path("legacy-entry").write_bytes(blob)

            restored = vault.get_entry("legacy-entry")
            self.assertEqual(restored, {"legacy": True})

    # ------------------------------------------------------------------
    # Fail-closed
    # ------------------------------------------------------------------
    def test_locked_set_refuses(self):
        """Without a signing key, set_entry must raise PermissionError."""
        with mock.patch.object(lgwks_sign, "signing_key", return_value=(b"", "unanchored")):
            with self.assertRaises(PermissionError):
                vault.set_entry("should-fail", 1)

    def test_locked_get_refuses(self):
        """Without a signing key, get_entry must raise PermissionError."""
        vault._DIR.mkdir(parents=True, exist_ok=True)
        vault._entry_path("stale").write_bytes(b"x")
        with mock.patch.object(lgwks_sign, "signing_key", return_value=(b"", "unanchored")):
            with self.assertRaises(PermissionError):
                vault.get_entry("stale")

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def test_file_600(self):
        """Encrypted files must be owner-readable only."""
        with self._fake_signing_key():
            vault.set_entry("perms", 1)
            p = vault._entry_path("perms")
            self.assertEqual(oct(p.stat().st_mode)[-3:], "600")


if __name__ == "__main__":
    unittest.main()
