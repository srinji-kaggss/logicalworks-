"""Tests for lgwks.artifact.tokenized.v1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_artifact_tokenized as art


class TestBuildArtifact(unittest.TestCase):
    def test_minimal_artifact(self):
        a = art.build_artifact(
            tenant_id="t1",
            source="ingest",
            modality="text",
            tokenization_id="word_regex:v1",
            token_stream=[1, 2, 3],
            payload_cid="b2b256:" + "a" * 64,
            capability_id="cap:test",
            timestamp=1234567890.0,
        )
        self.assertEqual(a.schema, art.SCHEMA)
        self.assertEqual(a.tenant_id, "t1")
        self.assertEqual(a.source, "ingest")
        self.assertEqual(a.modality, "text")
        self.assertEqual(a.token_stream, (1, 2, 3))
        self.assertTrue(a.artifact_cid)

    def test_artifact_cid_is_deterministic(self):
        kwargs = dict(
            tenant_id="t1",
            source="ingest",
            modality="text",
            tokenization_id="word_regex:v1",
            token_stream=[1, 2, 3],
            payload_cid="b2b256:" + "a" * 64,
            capability_id="cap:test",
            timestamp=1234567890.0,
        )
        a1 = art.build_artifact(**kwargs)
        a2 = art.build_artifact(**kwargs)
        self.assertEqual(a1.artifact_cid, a2.artifact_cid)

    def test_payload_meta_affects_cid(self):
        base = dict(
            tenant_id="t1",
            source="ingest",
            modality="text",
            tokenization_id="word_regex:v1",
            token_stream=[1, 2, 3],
            payload_cid="b2b256:" + "a" * 64,
            capability_id="cap:test",
            timestamp=1234567890.0,
        )
        a1 = art.build_artifact(payload_meta={"title": "a"}, **base)
        a2 = art.build_artifact(payload_meta={"title": "b"}, **base)
        self.assertNotEqual(a1.artifact_cid, a2.artifact_cid)

    def test_invalid_source_raises(self):
        with self.assertRaises(art.ArtifactError):
            art.build_artifact(
                tenant_id="t1",
                source="not_a_source",
                modality="text",
                tokenization_id="word_regex:v1",
                token_stream=[],
                payload_cid="cid",
                capability_id="cap",
                timestamp=1.0,
            )

    def test_invalid_modality_raises(self):
        with self.assertRaises(art.ArtifactError):
            art.build_artifact(
                tenant_id="t1",
                source="ingest",
                modality="pdf",
                tokenization_id="word_regex:v1",
                token_stream=[],
                payload_cid="cid",
                capability_id="cap",
                timestamp=1.0,
            )

    def test_roundtrip_dict(self):
        a = art.build_artifact(
            tenant_id="t1",
            source="research",
            run_id="run-1",
            session_id="sess-1",
            modality="reasoning",
            tokenization_id="aetherius:v0",
            token_stream=[256, 512, 65, 66],
            payload_cid="b2b256:" + "b" * 64,
            payload_meta={"title": "reasoning trace"},
            capability_id="cap:research",
            timestamp=1234567890.0,
            prev_hash="genesis",
        )
        d = a.to_dict()
        self.assertEqual(d["schema"], art.SCHEMA)
        a2 = art.validate_artifact_dict(d)
        self.assertEqual(a.artifact_cid, a2.artifact_cid)
        self.assertEqual(a.token_stream, a2.token_stream)


if __name__ == "__main__":
    unittest.main()
