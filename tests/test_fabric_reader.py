"""Task #4 — the unified FabricReader read surface.

Populates a gate's State Fabric (tape, vectors, relational FTS, graph, tokens),
then proves every legacy-consumer need is served through the single reader:
lexical search, vector retrieval + space dim, graph neighbors/stats, token
streams, and tape replay in causal order.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_artifact_tokenized as artifact_mod
import lgwks_fabric_reader as reader_mod
import lgwks_storage
import lgwks_vector as vec_mod


def _seed(gate: lgwks_storage.StorageGate) -> artifact_mod.TokenizedArtifact:
    # Relational + FTS via the run projection.
    gate.relational.project_run(
        source_rows=[{"source_id": "src-1", "source": "http://x", "title": "X", "discovered_by": "seed", "depth": 0}],
        doc_rows=[{"document_id": "doc-1", "source_id": "src-1", "title": "X", "source": "http://x", "word_count": 3}],
        chunk_rows=[{"chunk_id": "chunk-1", "document_id": "doc-1", "source": "http://x", "url": "http://x",
                     "text": "alpha beta gamma", "stem_text": "alpha beta", "hash": "h1",
                     "fact_score": 0.5, "chunk_kind": "prose", "position": 0}],
        fact_rows=[{"fact_id": "fact-1", "chunk_id": "chunk-1", "document_id": "doc-1",
                    "fact_text": "alpha beta", "fact_score": 0.5, "chunk_kind": "prose"}],
        vector_rows=[],
        frontier=[],
    )
    # Graph.
    gate.graph_fabric.ingest_chunks([{"chunk_id": "chunk-1", "document_id": "doc-1", "url": "http://x",
                                      "text": "alpha beta gamma", "hash": "h1", "schema": "PROSE"}])
    # Tape + tokens + vector via the ingest endpoint.
    art = artifact_mod.build_artifact(
        tenant_id="t", source="ingest", modality="text",
        tokenization_id=gate.tokenizers.default_word_regex_id(),
        token_stream=[7, 8, 9], payload_cid="b2b256:" + "a" * 64,
        payload_meta={"title": "hi"}, capability_id="cap", timestamp=1.0,
    )
    vec = vec_mod.encode_record([0.1] * 8, modality="text", space_id="sp", tenant="t",
                                source_cid=art.payload_cid, artifact_cid=art.artifact_cid)
    gate.ingest_artifact(art, vector_record=vec)
    return art


class TestFabricReader(unittest.TestCase):
    def test_reader_serves_all_surfaces(self):
        with tempfile.TemporaryDirectory() as td:
            gate = lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t")
            try:
                art = _seed(gate)
                r = reader_mod.FabricReader(gate)

                # lexical search
                self.assertEqual([h["chunk_id"] for h in r.search_chunks("alpha")], ["chunk-1"])
                self.assertEqual([h["fact_id"] for h in r.search_facts("beta")], ["fact-1"])

                # vector retrieval + space dim
                self.assertEqual(len(r.vectors_by_source("b2b256:" + "a" * 64)), 1)
                self.assertEqual(r.vector_space_dims(), 8)

                # graph
                self.assertGreaterEqual(r.graph_stats()["chunks"], 1)

                # token streams (keyed on the content-addressed artifact_cid)
                toks = [t[1] for t in r.artifact_tokens(art.artifact_cid)]
                self.assertEqual(toks, [7, 8, 9])

                # tape replay in causal order (tape fact_cid == artifact_cid)
                entries = list(r.replay(tenant_id="t"))
                self.assertEqual([e["sequence"] for e in entries], [1])
                self.assertEqual(entries[0]["fact_cid"], art.artifact_cid)
            finally:
                gate.close()

    def test_replay_orders_multiple_appends(self):
        with tempfile.TemporaryDirectory() as td:
            gate = lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t")
            try:
                for i in range(3):
                    art = artifact_mod.build_artifact(
                        tenant_id="t", source="ingest", modality="text",
                        tokenization_id=gate.tokenizers.default_word_regex_id(),
                        token_stream=[], payload_cid=f"b2b256:{i:064d}",
                        payload_meta={}, capability_id="cap", timestamp=float(i),
                    )
                    gate.ingest_artifact(art)
                seqs = [e["sequence"] for e in reader_mod.FabricReader(gate).replay("t")]
                self.assertEqual(seqs, [1, 2, 3])
            finally:
                gate.close()


if __name__ == "__main__":
    unittest.main()
