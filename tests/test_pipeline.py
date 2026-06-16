from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_pipeline as pipeline
from lgwks_pipeline import PipelineChunk, EmbedResult, RankedChunk


class TestPipeline(unittest.TestCase):
    def test_math_utilities(self):
        # Test l2_norm
        v = [3.0, 4.0]
        normed = pipeline._l2_norm(v)
        self.assertAlmostEqual(normed[0], 0.6)
        self.assertAlmostEqual(normed[1], 0.8)

        # Test vec_mean
        vecs = [[1.0, 2.0], [3.0, 4.0]]
        mean = pipeline._vec_mean(vecs)
        self.assertEqual(mean, [2.0, 3.0])

    def test_first_principal_component(self):
        # PCA power iteration on simple 2D vectors
        vecs = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        pc = pipeline._first_principal_component(vecs)
        self.assertEqual(len(pc), 2)
        # For perfectly correlated data, first PC should have components close in magnitude (absolute value)
        self.assertAlmostEqual(abs(pc[0]), abs(pc[1]), places=5)

    def test_tokenize(self):
        text = "Hello, world! This is a test."
        tokens = pipeline._tokenize(text)
        self.assertEqual(tokens, ["hello", "world", "test."])

    def test_bm25_score(self):
        # Check scoring
        q_tokens = ["hello", "world"]
        doc_tokens = ["hello", "there", "world"]
        avg_len = 3.0
        score = pipeline.bm25_score(q_tokens, doc_tokens, avg_doc_len=avg_len)
        self.assertTrue(score > 0)

        # Document without query tokens should score 0
        doc_tokens_no_match = ["java", "python"]
        score_no_match = pipeline.bm25_score(q_tokens, doc_tokens_no_match, avg_doc_len=avg_len)
        self.assertEqual(score_no_match, 0.0)

    def test_compute_fact_density(self):
        text1 = "Wait, let's verify if the test passes. In 2026, 42 percent of runs failed."
        fd1 = pipeline.compute_fact_density(text1)
        # Contains numbers: 2026, 42
        self.assertTrue(fd1 > 0.0)

        text2 = "No numbers here, just letters."
        fd2 = pipeline.compute_fact_density(text2)
        self.assertEqual(fd2, 0.0)

    def test_compute_noise_score(self):
        c = PipelineChunk(
            chunk_id="c1",
            source_id="s1",
            source_type="file",
            text="Lorem ipsum dolor sit amet. FACT: 100% true.",
            fact_score=0.9,
        )
        score = pipeline.compute_noise_score(c)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_entity_overlap_score(self):
        q_entities = ["A", "B", "C"]
        doc_entities = ["B", "C", "D"]
        overlap = pipeline.entity_overlap_score(q_entities, doc_entities)
        # Jaccard = intersection / union = 2 / 4 = 0.5
        self.assertAlmostEqual(overlap, 0.5)

    def test_parameter_snapshot(self):
        snapshot = pipeline._parameter_snapshot()
        self.assertIn("RECALL_K", snapshot)
        self.assertIn("FAST_RANK_K", snapshot)
        self.assertEqual(snapshot["RECALL_K"], pipeline.RECALL_K)


if __name__ == "__main__":
    unittest.main()
