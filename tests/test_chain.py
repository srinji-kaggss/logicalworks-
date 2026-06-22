"""Tests for lgwks_chain (the canonical JSONL hash-chain primitive, #298).

Two things must hold for the lgwks_memory migration to be safe:
  1. BYTE-EXACT: the bytes lgwks_memory writes through the primitive are identical
     to what the pre-#298 inline logic wrote — proven against an independent oracle.
  2. LEGACY COMPAT: a memory.jsonl written in the old format still verifies and can
     be extended (no data migration).

Plus direct coverage of the primitive's link discipline (verify, refuse-broken).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_chain
import lgwks_memory as memory
import lgwks_sign


_FIXED_TS = 1_234_567_890.0


def _memory_oracle_line(seq, project, kind, data, prev, key):
    """Independent reconstruction of a pre-#298 lgwks_memory record + its bytes."""
    core = {"seq": seq, "ts": _FIXED_TS, "project": project, "kind": kind, "data": data, "prev": prev}
    core_str = json.dumps(core, sort_keys=True, separators=(",", ":"))
    h = lgwks_sign.mac(core_str + prev, key)
    rec = {**core, "hash": h}
    return json.dumps(rec, sort_keys=True, ensure_ascii=False)


class TestMemoryByteExact(unittest.TestCase):
    def setUp(self):
        self._orig_dir = memory._DIR
        self._orig_time = memory.time.time
        self._td = tempfile.TemporaryDirectory()
        memory._DIR = Path(self._td.name) / "store" / "projects"
        memory.time.time = lambda: _FIXED_TS  # deterministic ts for byte comparison

    def tearDown(self):
        memory._DIR = self._orig_dir
        memory.time.time = self._orig_time
        self._td.cleanup()

    def test_appended_bytes_match_oracle(self):
        project = "byte-exact"
        key = lgwks_sign.signing_key()[0]
        # unicode + nested payload exercises ensure_ascii=False + sort_keys
        payloads = [
            ("project_scope", {"site": "exämple.com", "goal": "café ☕"}),
            ("note", {"text": "naïve", "n": 3, "nested": {"b": 2, "a": 1}}),
            ("conversation", {"source": "user", "z": [3, 2, 1]}),
        ]
        prev = lgwks_chain.GENESIS
        lines_oracle = []
        for seq, (kind, data) in enumerate(payloads, start=1):
            rec = memory.append(project, kind, data, key=key)
            lines_oracle.append(_memory_oracle_line(seq, project, kind, data, prev, key))
            prev = rec["hash"]

        on_disk = memory._path(project).read_text(encoding="utf-8").splitlines()
        self.assertEqual(on_disk, lines_oracle, "memory bytes diverged from the pre-#298 oracle")
        self.assertTrue(memory.verify(project))


class TestLegacyChainCompat(unittest.TestCase):
    def setUp(self):
        self._orig_dir = memory._DIR
        self._td = tempfile.TemporaryDirectory()
        memory._DIR = Path(self._td.name) / "store" / "projects"

    def tearDown(self):
        memory._DIR = self._orig_dir
        self._td.cleanup()

    def test_legacy_jsonl_verifies_and_extends(self):
        project = "legacy"
        key = lgwks_sign.signing_key()[0]
        # Hand-write a 2-record chain exactly as the old code would have.
        p = memory._path(project)
        p.parent.mkdir(parents=True, exist_ok=True)
        prev = lgwks_chain.GENESIS
        out = []
        for seq, (kind, data) in enumerate([("note", {"a": 1}), ("note", {"b": 2})], start=1):
            out.append(_memory_oracle_line(seq, project, kind, data, prev, key))
            prev = json.loads(out[-1])["hash"]
        p.write_text("\n".join(out) + "\n", encoding="utf-8")

        self.assertTrue(memory.verify(project, key), "legacy-format chain must still verify")
        rec = memory.append(project, "note", {"c": 3}, key=key)  # extends without migration
        self.assertEqual(rec["seq"], 3)
        self.assertEqual(rec["prev"], prev)
        self.assertTrue(memory.verify(project, key))


class TestPrimitiveDiscipline(unittest.TestCase):
    def _log(self, path, key):
        return lgwks_chain.HashChainLog(
            path,
            key=key,
            build_core=lambda n, prev, kind, data: {"seq": n, "kind": kind, "data": data, "prev": prev},
            hash_core=lambda core, prev, k: lgwks_sign.mac(
                json.dumps(core, sort_keys=True, separators=(",", ":")) + prev, k
            ),
            serialize=lambda rec: json.dumps(rec, sort_keys=True),
        )

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._path = Path(self._td.name) / "chain.jsonl"
        self._key = lgwks_sign.signing_key()[0]

    def tearDown(self):
        self._td.cleanup()

    def test_append_verify_roundtrip(self):
        log = self._log(self._path, self._key)
        log.append("k", {"i": 1})
        log.append("k", {"i": 2})
        self.assertTrue(log.verify())
        rows = log.read()
        self.assertEqual([r["data"]["i"] for r in rows], [1, 2])
        self.assertEqual(rows[1]["prev"], rows[0]["hash"])

    def test_refuse_broken_chain(self):
        log = self._log(self._path, self._key)
        log.append("k", {"i": 1})
        # Tamper with the persisted hash.
        line = json.loads(self._path.read_text().strip())
        line["hash"] = line["hash"][:-1] + ("0" if line["hash"][-1] != "0" else "1")
        self._path.write_text(json.dumps(line, sort_keys=True) + "\n", encoding="utf-8")
        self.assertFalse(log.verify())
        with self.assertRaises(lgwks_chain.BrokenChainError):
            log.append("k", {"i": 2})

    def test_empty_chain_verifies(self):
        self.assertTrue(self._log(self._path, self._key).verify())


if __name__ == "__main__":
    unittest.main()
