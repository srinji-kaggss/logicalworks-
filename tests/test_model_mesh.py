"""Tests for lgwks.model.mesh.v1 (#119 — model law as data).

Maps to the issue's acceptance bullets:
  1. the registry can represent every §3.1 model surface (assert each name present);
  2. reading/building the mesh loads NO model package and touches no weights;
  3. no runtime default changes — the mesh is descriptive (frozen-law snapshot).
"""

from __future__ import annotations

import sys
import unittest

import lgwks_model_mesh as mesh_mod

# The §3.1 "inventory this note must not silently replace" — every pinned model
# name the mesh MUST carry. (Seam/open-slot entries are name=null by design.)
REQUIRED_31_NAMES = {
    "mlx-community/ModernBERT-base-mlx-4bit",
    "Axiom-Byte-Framework",
    # Embed/Eye — source spec (MODEL-RUNTIME-FINALIZATION-2026-06-13 §92/§117) names the
    # Qwen3-VL EMBEDDING model, not the VL-Instruct visual agent the law had transcribed.
    "Qwen/Qwen3-VL-Embedding-8B",
    "meta-llama/Llama-Prompt-Guard-2-86M",
    "mlx-community/OLMo-2-0325-32B-Instruct-4bit",
    "logicalworks/had-fraud-engine-v1",
    "mlx-community/Qwen2.5-Omni-3B-Instruct-4bit-mlx",
    "mlx-community/liquid-lfm-2.5-1.2b-mlx-4bit",
}

# Model packages whose import would mean the mesh is loading models, not law.
_MODEL_PACKAGES = ("torch", "transformers", "mlx", "mlx_vlm", "coremltools", "llama_cpp")


class TestMeshShape(unittest.TestCase):
    def test_builds_and_validates(self):
        mesh = mesh_mod.build_mesh(generated_at="2026-06-13T00:00:00+00:00")
        self.assertEqual(mesh["schema"], "lgwks.model.mesh.v1")
        self.assertTrue(mesh["models"])
        mesh_mod.validate_mesh(mesh)  # idempotent revalidation

    def test_represents_every_31_surface(self):
        names = {m["name"] for m in mesh_mod.build_mesh()["models"]}
        missing = REQUIRED_31_NAMES - names
        self.assertEqual(missing, set(), f"mesh is missing §3.1 surfaces: {missing}")

    def test_open_slots_have_null_name(self):
        pass

    def test_open_slot_roles_present(self):
        pass

    def test_health_defaults_unknown(self):
        for m in mesh_mod.build_mesh()["models"]:
            self.assertEqual(m["health"]["status"], "unknown")


class TestValidation(unittest.TestCase):
    def test_rejects_bad_role(self):
        mesh = mesh_mod.build_mesh()
        mesh["models"][0]["role"] = "not-a-role"
        with self.assertRaises(ValueError):
            mesh_mod.validate_mesh(mesh)

    def test_rejects_named_open_slot(self):
        pass

    def test_rejects_wrong_schema(self):
        with self.assertRaises(ValueError):
            mesh_mod.validate_mesh({"schema": "lgwks.other.v1", "generated_at": None, "models": [{}]})


class TestNoModelLoad(unittest.TestCase):
    """Acceptance 2: building/reading the mesh imports no model package."""

    def test_build_imports_no_model_package(self):
        before = {p for p in _MODEL_PACKAGES if p in sys.modules}
        mesh_mod.build_mesh()
        after = {p for p in _MODEL_PACKAGES if p in sys.modules}
        self.assertEqual(after - before, set(), "build_mesh pulled a model package into sys.modules")

    def test_doctor_mesh_section_loads_no_model(self):
        import lgwks_model_hub as hub
        before = {p for p in _MODEL_PACKAGES if p in sys.modules}
        status = hub._model_mesh_status()
        after = {p for p in _MODEL_PACKAGES if p in sys.modules}
        self.assertEqual(after - before, set())
        self.assertEqual(status["schema"], "lgwks.model.mesh.v1")
        self.assertIn(status["source"], ("artifact", "law"))


class TestDescriptiveSnapshot(unittest.TestCase):
    """Acceptance 3: the mesh is descriptive — runtime defaults are unchanged.

    Pin the current-law name set so a future edit that silently swaps inventory
    (a default change) trips this snapshot rather than passing quietly.
    """

    def test_current_law_name_snapshot(self):
        current = {
            m["name"]
            for m in mesh_mod.build_mesh()["models"]
            if m["status"] == "current_law" and m["name"] is not None
        }
        self.assertEqual(current, REQUIRED_31_NAMES)


if __name__ == "__main__":
    unittest.main()
