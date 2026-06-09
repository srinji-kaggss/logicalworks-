"""Tests for lgwks_concept — deterministic concept extraction + activation steering."""
from __future__ import annotations

import unittest

import lgwks_concept as cx
from lgwks_concept import ConceptExtractor, concept_vector, extract_from_chunks


class TestConceptExtractor(unittest.TestCase):
    def test_definition_extraction(self):
        ce = ConceptExtractor()
        ce.ingest(
            "Amazon EC2 (Elastic Compute Cloud) is a web service that provides "
            "resizable compute capacity in the cloud.",
            chunk_id="c1",
            doc_id="d1",
        )
        concepts, rels = ce.finalize()
        self.assertTrue(concepts)
        # Must extract "Amazon EC2"
        slugs = {c.slug for c in concepts}
        self.assertTrue(
            any("amazon ec2" == s for s in slugs),
            f"Expected 'amazon ec2' in {slugs}",
        )

    def test_ec2_meaning(self):
        """When I say EC2, the model must know what EC2 actually means."""
        ce = ConceptExtractor()
        ce.ingest(
            "Amazon EC2 (Elastic Compute Cloud) is a web service that provides "
            "resizable compute capacity in the cloud. "
            "AWS Lambda is a serverless compute service that lets you run code "
            "without provisioning or managing servers. "
            "EC2 instances can be launched in multiple Availability Zones.",
            chunk_id="c1",
            doc_id="d1",
        )
        concepts, rels = ce.finalize()
        cg = cx.ConceptGraph(concepts, rels)
        info = cg.what_is("EC2")
        self.assertIsNotNone(info, "EC2 must resolve to a concept")
        # "Elastic Compute Cloud" is extracted as alias/definition from parenthetical
        all_meaning = f"{info['definition']} {' '.join(info['aliases'])}".lower()
        self.assertIn("elastic compute cloud", all_meaning)
        self.assertIn("amazon ec2", info["label"].lower())

    def test_activation_steering_lambda_to_ec2(self):
        """Saying 'serverless' activates Lambda, and Lambda activates EC2 awareness."""
        ce = ConceptExtractor()
        ce.ingest(
            "AWS Lambda is a serverless compute service. "
            "Amazon EC2 is a virtual server service. "
            "Lambda functions can trigger EC2 instances.",
            chunk_id="c1",
            doc_id="d1",
        )
        concepts, rels = ce.finalize()
        cg = cx.ConceptGraph(concepts, rels)
        # Lambda should activate EC2 (downstream)
        activated = cg.activates("lambda")
        self.assertTrue(activated, "Lambda must activate related concepts")
        # At least one activated concept should contain EC2
        self.assertTrue(
            any("ec2" in a.lower() for a in activated),
            f"Lambda activates should include EC2: {activated}",
        )

    def test_concept_vector_determinism(self):
        ce = ConceptExtractor()
        ce.ingest(
            "Amazon EC2 is a web service.",
            chunk_id="c1",
            doc_id="d1",
        )
        concepts, _ = ce.finalize()
        vec_a = concept_vector(concepts[0])
        vec_b = concept_vector(concepts[0])
        self.assertEqual(vec_a, vec_b, "Concept vector must be deterministic")
        self.assertEqual(len(vec_a), 256)

    def test_extract_from_chunks(self):
        chunks = [
            {"chunk_id": "c1", "document_id": "d1", "text": "Amazon EC2 is a web service."},
            {"chunk_id": "c2", "document_id": "d1", "text": "AWS Lambda is serverless."},
        ]
        cg = extract_from_chunks(chunks)
        ec2 = cg.what_is("EC2")
        self.assertIsNotNone(ec2)
        self.assertIn("web service", ec2["definition"])


if __name__ == "__main__":
    unittest.main()
