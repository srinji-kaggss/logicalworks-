"""#167 Phase 4 hardening + #277 capability-gated graph door.

Four hardening axes, each with its acceptance pinned:

  1. Cross-tenant leakage (§1-INV) THROUGH the capability-gated door — for graph
     reads now (the #277 gap), the same way vectors are already swept. A verified
     capability is required; the read is scoped to the VERIFIED principal, never a
     caller-supplied tier string; tenant A never sees tenant B's private rows.
  2. Crash replay — wipe a projection and rebuild it from the Causal Tape;
     deterministic (same tape → same projection); a corrupt/torn tape is REFUSED,
     not silently replayed (CausalTape.verify_chain).
  3. Re-tokenization lineage — a new tokenizer adds a lineage; the old projections
     are untouched and tokenization_id distinguishes the two.
  4. Performance smoke — a batch of artifacts ingests without pathology.

Findings documented in the PR body; true positives (tape had no integrity check)
fixed in the same change (verify_chain).
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import lgwks_access as access
import lgwks_capability as capability
import lgwks_storage


class _FakePort:
    """Non-HMAC CapabilityPort stand-in (mirrors test_lgwks_access) so the door is
    exercised without touching the Keychain. Proves the door gates via the
    CapabilityPort interface, not the concrete HMAC token."""

    def __init__(self, principal: str, scopes):
        self._principal = principal
        self._scopes = frozenset(scopes)

    def verify(self, handle, key):
        return access.VerifiedCap(principal=self._principal, cap_ref="fake",
                                  scopes=self._scopes, _internal_cap=handle)

    def require_scope(self, handle, scope, key):
        v = self.verify(handle, key)
        if scope not in v.scopes:
            raise capability.CapabilityError(f"fake-port: lacks {scope!r}")
        return v

    def resolve(self, principal): raise NotImplementedError
    def principal_of(self, verified): return verified.principal
    def cap_ref(self, verified): return verified.cap_ref
    def mint_promote(self, principal): raise NotImplementedError


def _gate(td: str) -> lgwks_storage.StorageGate:
    return lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="default")


class TestGraphDoorCrossTenant(unittest.TestCase):
    """#277 — graph reads through the capability-gated TenantStore door."""

    def _seed_graph(self, gate):
        # 3 private-A nodes, 2 private-B nodes, 1 world node — all tier-tagged.
        for i in range(3):
            gate.graph_fabric.upsert_node(f"a{i}", "doc", f"a{i}", artifact_cid=f"a{i}", tier="tenant-A")
        for i in range(2):
            gate.graph_fabric.upsert_node(f"b{i}", "doc", f"b{i}", artifact_cid=f"b{i}", tier="tenant-B")
        gate.graph_fabric.upsert_node("w0", "doc", "w0", artifact_cid="w0", tier="world")
        gate.graph_fabric.commit()

    def test_door_requires_capability_and_scopes_to_principal(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                self._seed_graph(gate)
                door_a = access.TenantStore.over_gate(
                    _FakePort("tenant-A", {capability.TENANT_RW, capability.WORLD_R}),
                    handle=None, key=b"", gate=gate)
                door_b = access.TenantStore.over_gate(
                    _FakePort("tenant-B", {capability.WORLD_R}),
                    handle=None, key=b"", gate=gate)

                # A resolves its own + world, never B's private node.
                self.assertIsNotNone(door_a.graph_resolve("a1")[0])
                self.assertIsNotNone(door_a.graph_resolve("w0")[0])
                self.assertIsNone(door_a.graph_resolve("b0")[0], "A read a B-private graph node — LEAK")

                # B resolves its own + world, never A's private node.
                self.assertIsNotNone(door_b.graph_resolve("b0")[0])
                self.assertIsNone(door_b.graph_resolve("a0")[0], "B read an A-private graph node — LEAK")

                # §1-INV via stats: A sees A⊕world node count, not B's.
                stats_a = door_a.graph_stats()
                self.assertEqual(stats_a["nodes"], 4)  # 3 A + 1 world

    def test_door_refuses_without_read_scope(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                self._seed_graph(gate)
                door = access.TenantStore.over_gate(
                    _FakePort("tenant-A", set()), handle=None, key=b"", gate=gate)
                with self.assertRaises(capability.CapabilityError):
                    door.graph_resolve("a0")
                with self.assertRaises(capability.CapabilityError):
                    door.graph_stats()


class TestCrashReplay(unittest.TestCase):
    def _seed_run(self, gate):
        gate.ingest_fact("chunk-a", "crm depends on identity", "rule",
                         capability="ingest_chunk", meta={"doc_id": "d1", "pos": 0}, run_id="run-A")
        gate.ingest_fact("chunk-b", "cdp controls events not records", "rule",
                         capability="ingest_chunk", meta={"doc_id": "d1", "pos": 1}, run_id="run-A")

    def test_rebuild_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                self._seed_run(gate)
                gate.replay_run("run-A")
                first = gate.relational._conn.execute(
                    "SELECT chunk_id, text, stem_text, fact_score, chunk_kind, tokenization_id, artifact_cid "
                    "FROM chunks ORDER BY chunk_id").fetchall()
                # wipe the projection entirely and rebuild from the tape.
                gate.relational._conn.executescript(
                    "DELETE FROM chunks; DELETE FROM facts; DELETE FROM chunk_fts; DELETE FROM fact_fts;")
                gate.relational._conn.commit()
                gate.replay_run("run-A")
                second = gate.relational._conn.execute(
                    "SELECT chunk_id, text, stem_text, fact_score, chunk_kind, tokenization_id, artifact_cid "
                    "FROM chunks ORDER BY chunk_id").fetchall()
                self.assertEqual(first, second, "replay is not deterministic")
                self.assertEqual(len(first), 2)

    def test_replay_refuses_tampered_tape(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                self._seed_run(gate)
                # tamper: rewrite an entry's fact_cid so its entry_hash no longer matches.
                gate.tape._conn.execute(
                    "UPDATE tape SET fact_cid = 'tampered' WHERE sequence = 1 AND tenant_id = 'default'")
                gate.tape._conn.commit()
                ok, err = gate.tape.verify_chain("default")
                self.assertFalse(ok)
                assert err is not None
                self.assertIn("tampered", err)
                with self.assertRaises(ValueError):
                    gate.replay_run("run-A")

    def test_verify_chain_detects_sequence_gap(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                self._seed_run(gate)
                # delete a middle/earlier entry → linkage + sequence break.
                gate.tape._conn.execute(
                    "DELETE FROM tape WHERE sequence = 1 AND tenant_id = 'default'")
                gate.tape._conn.commit()
                ok, err = gate.tape.verify_chain("default")
                self.assertFalse(ok)


class TestRetokenizationLineage(unittest.TestCase):
    def test_new_tokenizer_adds_lineage_without_touching_old(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                # index the same artifact under two tokenizer lineages.
                gate.token_index.index_tokens("word_regex:v1", "art-1", (1, 2, 3))
                gate.token_index.index_tokens("aetherius:v0", "art-1", (10, 20))
                postings = gate.token_index.query_artifact_tokens("art-1")
                lineages = {p[0] for p in postings}
                self.assertEqual(lineages, {"word_regex:v1", "aetherius:v0"})
                # old lineage still resolves exactly as before — untouched.
                self.assertEqual(gate.token_index.query_token("word_regex:v1", 1), ["art-1"])
                # the new lineage is independent.
                self.assertEqual(gate.token_index.query_token("aetherius:v0", 10), ["art-1"])


class TestPerfSmoke(unittest.TestCase):
    def test_batch_ingest_completes(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                t0 = time.perf_counter()
                rows = [{"fact_hash": f"f{i}", "fact_text": f"fact {i}", "provider": "det",
                         "dims": 4, "vector": [0.1, 0.2, 0.3, float(i % 7) + 0.1],
                         "tokenization_id": "word_regex:v1", "artifact_cid": f"f{i}"} for i in range(300)]
                inserted = gate.vector_fabric.ingest_fact_vectors(rows)
                elapsed = time.perf_counter() - t0
                self.assertEqual(inserted, 300)
                # generous ceiling — catches a pathological regression, not micro-jitter.
                self.assertLess(elapsed, 30.0, f"300-vector ingest took {elapsed:.1f}s")


if __name__ == "__main__":
    unittest.main()
