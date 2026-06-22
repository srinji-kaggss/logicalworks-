"""#166 Phase 3 — unified query surface + fabric introspection over the State Fabric.

Pins:
  - StorageGate.status()        — tape depth + per-projection counts + tokenizers
  - tokenizer listing           — the registered analyzers
  - FabricReader.query()        — ONE query, ONE result set spanning lexical (relational
                                  FTS), token-index, graph, and vector projections; every
                                  lexical/vector hit carries tokenization_id + artifact_cid
  - VectorFabric.search_similar — cosine ranking within a space
  - StorageGate.replay_run()    — rebuild the relational projection for a run by replaying
                                  the Causal Tape (projections are disposable; tape is truth)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lgwks_storage
import lgwks_vector as vec_mod
from lgwks_fabric_reader import FabricReader


def _gate(td: str) -> lgwks_storage.StorageGate:
    return lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t")


def _project_two_chunks(gate: lgwks_storage.StorageGate) -> None:
    gate.relational.project_run(
        source_rows=[{"source_id": "s1", "source": "u", "title": "T", "discovered_by": "seed", "depth": 0}],
        doc_rows=[{"document_id": "d1", "source_id": "s1", "title": "T", "source": "u", "word_count": 5}],
        chunk_rows=[
            {"chunk_id": "chunk-crm", "document_id": "d1", "source": "u", "url": "u",
             "text": "crm depends on identity and contact storage", "stem_text": "crm depend ident",
             "hash": "h1", "fact_score": 0.9, "chunk_kind": "rule", "position": 0,
             "tokenization_id": "word_regex:v1", "artifact_cid": "chunk-crm"},
            {"chunk_id": "chunk-cdp", "document_id": "d1", "source": "u", "url": "u",
             "text": "cdp controls events not records", "stem_text": "cdp control event",
             "hash": "h2", "fact_score": 0.8, "chunk_kind": "rule", "position": 1,
             "tokenization_id": "word_regex:v1", "artifact_cid": "chunk-cdp"},
        ],
        fact_rows=[], vector_rows=[], frontier=[],
    )


class TestStatusAndTokenizers(unittest.TestCase):
    def test_status_structure_and_counts(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                gate.ingest_fact("chunk-1", "crm depends on identity", "rule", capability="c", run_id="run-A")
                st = gate.status()
                self.assertEqual(st["tenant_id"], "t")
                self.assertEqual(st["tape"]["entries"], 1)
                self.assertEqual(st["tape"]["last_sequence"], 1)
                self.assertIn("vector", st["projections"])
                self.assertIn("relational", st["projections"])
                self.assertIn("word_regex:v1", st["tokenizers"])

    def test_tokenizers_listed(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                ids = {t.tokenizer_id for t in gate.tokenizers.list_tokenizers()}
                self.assertIn("word_regex:v1", ids)


class TestUnifiedQuery(unittest.TestCase):
    def test_query_spans_projections_with_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                _project_two_chunks(gate)
                # graph arm: a resolvable node.
                gate.graph_fabric.upsert_node("crm", "concept", "crm", artifact_cid="chunk-crm", tier="t")
                gate.graph_fabric.commit()
                # vector arm: two records in one space; the crm one should rank first
                # for a crm-leaning query vector.
                for cid, vec in (("chunk-crm", [1.0, 0.0, 0.0, 0.0]), ("chunk-cdp", [0.0, 1.0, 0.0, 0.0])):
                    gate.vector_fabric.ingest_fact_vectors([{
                        "fact_hash": cid, "fact_text": "", "provider": "det", "dims": 4,
                        "vector": vec, "tokenization_id": "word_regex:v1", "artifact_cid": cid,
                    }])

                result = FabricReader(gate).query("crm identity", limit=5)

                # one result set, all arms present
                self.assertEqual(set(result), {"query", "lexical", "tokens", "graph", "vector"})
                # lexical hit carries provenance
                chunks = result["lexical"]["chunks"]
                self.assertTrue(chunks)
                self.assertEqual(chunks[0]["artifact_cid"], "chunk-crm")
                self.assertEqual(chunks[0]["tokenization_id"], "word_regex:v1")
                # graph arm resolved the node
                self.assertIsNotNone(result["graph"]["node"])

    def test_search_similar_ranks_within_space(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                for cid, vec in (("a", [1.0, 0.0]), ("b", [0.0, 1.0])):
                    gate.vector_fabric.ingest_fact_vectors([{
                        "fact_hash": cid, "fact_text": "", "provider": "det", "dims": 2,
                        "vector": vec, "tokenization_id": "word_regex:v1", "artifact_cid": cid,
                    }])
                q = vec_mod.encode_record([0.9, 0.1], modality="text", space_id="det:d2",
                                          tenant=vec_mod.WORLD_TENANT, source_cid="q")
                ranked = gate.vector_fabric.search_similar(q, limit=2)
                self.assertEqual(ranked[0][1].artifact_cid, "a")
                self.assertGreater(ranked[0][0], ranked[1][0])


class TestReplay(unittest.TestCase):
    def test_replay_rebuilds_relational_from_tape(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                # ingest two chunks (tape entries) for run-A, tagged with run_id.
                gate.ingest_fact("chunk-a", "crm depends on identity", "rule",
                                 capability="ingest_chunk", meta={"doc_id": "d1", "pos": 0}, run_id="run-A")
                gate.ingest_fact("chunk-b", "cdp controls events", "rule",
                                 capability="ingest_chunk", meta={"doc_id": "d1", "pos": 1}, run_id="run-A")
                # simulate a lost projection: wipe the relational chunks table.
                gate.relational._conn.execute("DELETE FROM chunks")
                gate.relational._conn.commit()
                self.assertEqual(
                    gate.relational._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 0)

                # replay the tape for the run → relational rows are reconstructed.
                report = gate.replay_run("run-A")
                self.assertEqual(report["chunks"], 2)
                rows = gate.relational._conn.execute(
                    "SELECT chunk_id, tokenization_id, artifact_cid FROM chunks ORDER BY chunk_id").fetchall()
                self.assertEqual([r[0] for r in rows], ["chunk-a", "chunk-b"])
                self.assertTrue(all(r[1] == "word_regex:v1" for r in rows))
                self.assertEqual({r[2] for r in rows}, {"chunk-a", "chunk-b"})

    def test_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            with _gate(td) as gate:
                gate.ingest_fact("chunk-a", "crm depends on identity", "rule",
                                 capability="ingest_chunk", meta={"doc_id": "d1", "pos": 0}, run_id="run-A")
                gate.replay_run("run-A")
                gate.replay_run("run-A")  # second replay must not duplicate
                n = gate.relational._conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE chunk_id = 'chunk-a'").fetchone()[0]
                self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
