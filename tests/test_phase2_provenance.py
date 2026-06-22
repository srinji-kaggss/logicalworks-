"""#165 Phase 2 — vectors written by the substrate paths carry tape provenance.

Acceptance #2 of #165: "Vectors written by those paths include tokenization_id
and artifact_cid." substrate_run now stamps every chunk/fact/vector row with
tokenization_id (which analyzer named the source) + artifact_cid (the tape fact
cid it derives from). These tests pin that the two projection write paths
substrate_run uses — VectorFabric.ingest_fact_vectors (world-tier fact
embeddings) and RelationalProjection.project_run (the relational vectors table)
— persist that provenance, so a reader can trace any vector back to its tape entry.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lgwks_storage


class TestVectorFabricProvenance(unittest.TestCase):
    def test_ingest_fact_vectors_persists_tokenization_and_artifact_cid(self):
        with tempfile.TemporaryDirectory() as td:
            with lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t") as gate:
                rows = [
                    {
                        "fact_hash": "fact-cid-abc",
                        "fact_text": "crm depends on identity",
                        "provider": "det",
                        "dims": 4,
                        "vector": [0.1, 0.2, 0.3, 0.4],
                        "fact_score": 0.9,
                        "chunk_kind": "rule",
                        "tokenization_id": "word_regex:v1",
                    }
                ]
                inserted = gate.vector_fabric.ingest_fact_vectors(rows)
                self.assertEqual(inserted, 1)
                # world-tier accumulation: the embedding is content-addressed back to
                # the fact's tape cid (== fact_hash) and tagged with its tokenizer.
                recs = gate.vector_fabric.query_by_artifact("fact-cid-abc")
                self.assertEqual(len(recs), 1, "embedding not retrievable by its artifact_cid")
                self.assertEqual(recs[0].artifact_cid, "fact-cid-abc")
                self.assertEqual(recs[0].tokenization_id, "word_regex:v1")

    def test_artifact_cid_defaults_to_fact_hash_when_unstamped(self):
        # Back-compat: a row with no explicit artifact_cid still gets one (== fact_hash),
        # so legacy callers don't write NULL-provenance vectors.
        with tempfile.TemporaryDirectory() as td:
            with lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t") as gate:
                rows = [{
                    "fact_hash": "lonely-cid",
                    "fact_text": "x",
                    "provider": "det",
                    "dims": 4,
                    "vector": [0.5, 0.5, 0.5, 0.5],
                }]
                gate.vector_fabric.ingest_fact_vectors(rows)
                recs = gate.vector_fabric.query_by_artifact("lonely-cid")
                self.assertEqual(len(recs), 1)
                self.assertEqual(recs[0].artifact_cid, "lonely-cid")


class TestRelationalProvenance(unittest.TestCase):
    def test_project_run_persists_vector_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            with lgwks_storage.StorageGate(Path(td) / "fabric", tenant_id="t") as gate:
                gate.relational.project_run(
                    source_rows=[{"source_id": "s1", "source": "u", "title": "T", "discovered_by": "seed", "depth": 0}],
                    doc_rows=[{"document_id": "d1", "source_id": "s1", "title": "T", "source": "u", "word_count": 3}],
                    chunk_rows=[{
                        "chunk_id": "chunk-1", "document_id": "d1", "source": "u", "url": "u",
                        "text": "crm depends on identity", "stem_text": "crm depend ident", "hash": "h",
                        "fact_score": 0.9, "chunk_kind": "rule", "position": 0,
                        "tokenization_id": "word_regex:v1", "artifact_cid": "chunk-1",
                    }],
                    fact_rows=[{
                        "fact_id": "fact-1", "chunk_id": "chunk-1", "document_id": "d1",
                        "fact_text": "crm depend ident", "fact_score": 0.9, "chunk_kind": "rule",
                        "tokenization_id": "word_regex:v1", "artifact_cid": "chunk-1",
                    }],
                    vector_rows=[{
                        "vector_id": "vec-1", "chunk_id": "chunk-1", "document_id": "d1",
                        "provider": "det", "is_semantic": False, "dims": 4,
                        "vector_text": "crm depends on identity", "vector": [0.1, 0.2, 0.3, 0.4],
                        "fact_score": 0.9, "chunk_kind": "rule",
                        "tokenization_id": "word_regex:v1", "artifact_cid": "chunk-1",
                    }],
                    frontier=[],
                )
                row = gate.relational._conn.execute(
                    "SELECT tokenization_id, artifact_cid FROM vectors WHERE vector_id = ?", ("vec-1",)
                ).fetchone()
                self.assertEqual(row[0], "word_regex:v1")
                self.assertEqual(row[1], "chunk-1")
                crow = gate.relational._conn.execute(
                    "SELECT tokenization_id, artifact_cid FROM chunks WHERE chunk_id = ?", ("chunk-1",)
                ).fetchone()
                self.assertEqual(crow, ("word_regex:v1", "chunk-1"))


class TestRunResearchEmission(unittest.TestCase):
    """#165 items 3+4 — run/research outputs land on the tape, keyed on a STABLE
    gate (no per-run islands), best-effort. We redirect RUN_ROOT to a tempdir so
    the shared corpus gate writes are isolated from the repo store."""

    def _modalities_on_tape(self, project: str, tenant: str = "default") -> list[str]:
        import lgwks_storage
        gate = lgwks_storage.get_gate(project, tenant_id=tenant)
        try:
            return [e["meta"].get("modality") for e in gate.tape.replay(tenant_id=tenant)]
        finally:
            gate.close()

    def test_research_report_lands_as_reasoning_artifact(self):
        import lgwks_substrate_config as cfg_mod
        import lgwks_research as research
        with tempfile.TemporaryDirectory() as td:
            orig = cfg_mod.RUN_ROOT
            cfg_mod.RUN_ROOT = Path(td) / "substrate"
            try:
                report = Path(td) / "REPORT.md"
                report.write_text("# Research Report — demo\n\nfindings.", encoding="utf-8")
                cfg = research.AutoConfig(objective="demo", purpose="p", start="demo", project="proj-x")
                research._emit_reasoning_artifact(cfg, "run-123", report)
                self.assertIn("reasoning", self._modalities_on_tape("proj-x"))
            finally:
                cfg_mod.RUN_ROOT = orig

    def test_run_artifacts_land_vectors_and_prevector(self):
        import lgwks_substrate_config as cfg_mod
        import lgwks_run as run
        with tempfile.TemporaryDirectory() as td:
            orig = cfg_mod.RUN_ROOT
            cfg_mod.RUN_ROOT = Path(td) / "substrate"
            try:
                prevector = Path(td) / "prevector.graph.json"
                prevector.write_text('{"$schema":"graph-schema/2","nodes":[],"edges":[]}', encoding="utf-8")
                embeddings = [{"id": "doc-1-c0", "doc": "doc-1", "dim": 4,
                               "provider": "deterministic", "semantic": False,
                               "vector": [0.1, 0.2, 0.3, 0.4]}]
                run._emit_run_artifacts("run-xyz", prevector, embeddings)
                import lgwks_storage
                gate = lgwks_storage.get_gate("run")
                try:
                    recs = gate.vector_fabric.query_by_artifact("doc-1-c0")
                    self.assertEqual(len(recs), 1)
                    self.assertEqual(recs[0].artifact_cid, "doc-1-c0")
                    self.assertTrue(recs[0].tokenization_id)
                    mods = [e["meta"].get("modality") for e in gate.tape.replay(tenant_id="default")]
                    self.assertIn("reasoning", mods)
                finally:
                    gate.close()
            finally:
                cfg_mod.RUN_ROOT = orig


if __name__ == "__main__":
    unittest.main()
