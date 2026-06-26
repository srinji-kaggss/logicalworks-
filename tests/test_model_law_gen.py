"""Tests for the generated model law (kill the hand-transcription bug class).

`lgwks_model_mesh.MESH_LAW` is GENERATED from `spec/second-harness/model-law.json`
by `scripts/gen_model_law.py`. These tests are the in-suite mirror of the
`model.law` Keel lane:

  1. the committed MESH_LAW block matches a fresh regeneration (no hand-edit drift);
  2. the canonical source conforms to the mesh vocabulary;
  3. the Aetherius §3 prose table still matches the source's recorded `prose_table`
     (a future hallucinated id in the spec prose FAILS this);
  4. a tampered law block is rejected by --verify (the gate actually bites).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "gen_model_law", ROOT / "scripts" / "gen_model_law.py")
gen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gen)


class TestGeneratedLaw(unittest.TestCase):
    def setUp(self):
        self.gen = gen
        self.law = gen.load_law()

    def test_block_is_fresh(self):
        """The committed MESH_LAW block equals a fresh regeneration from source."""
        text = self.gen.TARGET.read_text(encoding="utf-8")
        self.assertEqual(
            self.gen.current_block(text), self.gen.emit_block(self.law),
            "MESH_LAW block is stale/hand-edited — run scripts/gen_model_law.py --write")

    def test_source_conforms_to_mesh_vocab(self):
        self.assertEqual(self.gen.validate_vocab(self.law), [])

    def test_prose_table_reconciles(self):
        self.assertEqual(self.gen.reconcile_prose(self.law), [])

    def test_verify_gate_passes(self):
        self.assertEqual(self.gen.cmd_verify(), 0)

    def test_source_matches_in_code_law(self):
        """Source entries round-trip to exactly today's MESH_LAW (no inventory change)."""
        import lgwks_model_mesh as mesh
        built = [mesh._entry(**e) for e in self.gen.law_entries(self.law)]
        self.assertEqual(built, mesh.MESH_LAW)


class TestGateBites(unittest.TestCase):
    """The gate must bite on prose drift AND catalog parity violations."""

    def test_prose_drift_is_caught(self):
        law = gen.load_law()
        # Simulate someone re-introducing a hallucinated id into the spec prose
        # without updating the canonical source: the recorded table no longer matches.
        law["prose_table"][4]["model"] = "Qwen-9.9-VL-Hallucinated"
        problems = gen.reconcile_prose(law)
        self.assertTrue(problems, "prose drift went undetected — the gate does not bite")
        self.assertIn("row 5", problems[0])

    def test_catalog_parity_is_caught(self):
        """A law entry added without a matching catalog entry must trip the gate."""
        import copy
        law = copy.deepcopy(gen.load_law())
        # Inject a phantom current_law mlx entry that isn't in _MODEL_CATALOG.
        law["entries"].append({
            "entry": {
                "name": "mlx-community/phantom-model-not-in-catalog",
                "runtime": "mlx",
                "locality": "local",
                "role": "proposal",
                "trust_class": "generative",
                "status": "current_law",
                "notes": "phantom — must fail parity",
            }
        })
        problems = gen.check_catalog_parity(law)
        self.assertTrue(problems, "catalog parity mismatch went undetected — the gate does not bite")
        self.assertTrue(
            any("phantom-model-not-in-catalog" in p for p in problems),
            f"expected phantom name in parity error; got: {problems}"
        )


if __name__ == "__main__":
    unittest.main()
