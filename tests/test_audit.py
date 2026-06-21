"""Tests for lgwks_audit — the canonical hardened audit-append primitive (#223 family 1).

Locks the guarantees that the 5 hand-rolled writers used to drift on: redaction
(sensitive-named keys + embedded secrets), owner-only file/dir permissions,
append semantics, and never-raises-on-failure.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_audit as audit


class AuditAppendTests(unittest.TestCase):
    def _read(self, path: Path) -> list[dict]:
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def test_appends_readable_jsonl(self):
        with TemporaryDirectory() as td:
            log = Path(td) / ".lgwks" / "x-audit.jsonl"
            self.assertTrue(audit.audit_append(log, {"op": "a", "n": 1}))
            self.assertTrue(audit.audit_append(log, {"op": "b", "n": 2}))
            recs = self._read(log)
            self.assertEqual([r["op"] for r in recs], ["a", "b"])  # append, not overwrite

    def test_redacts_credential_named_keys(self):
        with TemporaryDirectory() as td:
            log = Path(td) / "a.jsonl"
            audit.audit_append(log, {
                "token": "ghp_abcdefghijklmnop",
                "api_key": "sk-12345678",
                "password": "hunter2hunter2",
                "auth": "Bearer zzzzzzzz",
            })
            rec = self._read(log)[0]
            for k in ("token", "api_key", "password", "auth"):
                self.assertEqual(rec[k], "[REDACTED]", f"{k} not redacted")

    def test_does_not_redact_benign_keys(self):
        with TemporaryDirectory() as td:
            log = Path(td) / "a.jsonl"
            # 'author' contains 'auth', 'key_name' contains 'key' — must NOT be redacted.
            audit.audit_append(log, {"author": "alice", "key_name": "vault-key", "verb": "harden"})
            rec = self._read(log)[0]
            self.assertEqual(rec["author"], "alice")
            self.assertEqual(rec["key_name"], "vault-key")
            self.assertEqual(rec["verb"], "harden")

    def test_scrubs_secret_embedded_in_string_value(self):
        with TemporaryDirectory() as td:
            log = Path(td) / "a.jsonl"
            audit.audit_append(log, {"cmd": "deploy --api_key=supersecretvalue123 now"})
            rec = self._read(log)[0]
            self.assertIn("[REDACTED]", rec["cmd"])
            self.assertNotIn("supersecretvalue123", rec["cmd"])

    def test_nested_redaction(self):
        with TemporaryDirectory() as td:
            log = Path(td) / "a.jsonl"
            audit.audit_append(log, {"args": {"token": "ghp_aaaaaaaaaaaa", "repo": "acme/demo"}})
            rec = self._read(log)[0]
            self.assertEqual(rec["args"]["token"], "[REDACTED]")
            self.assertEqual(rec["args"]["repo"], "acme/demo")  # benign value preserved

    def test_owner_only_permissions(self):
        with TemporaryDirectory() as td:
            log = Path(td) / ".lgwks" / "a.jsonl"
            audit.audit_append(log, {"op": "x"})
            self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(log.parent.stat().st_mode), 0o700)

    def test_never_raises_returns_false_on_unwritable_path(self):
        with TemporaryDirectory() as td:
            blocker = Path(td) / "blocker"
            blocker.write_text("i am a file, not a dir", encoding="utf-8")
            # parent path traverses through a regular file → mkdir must fail
            log = blocker / "sub" / "a.jsonl"
            self.assertFalse(audit.audit_append(log, {"op": "x"}))  # no exception, returns False


if __name__ == "__main__":
    unittest.main()
