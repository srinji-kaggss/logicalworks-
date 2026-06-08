from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_model_hub as mh


class TestModelHub(unittest.TestCase):
    def test_convert_to_coreml_skips_cleanly_when_python_too_new(self):
        with mock.patch.object(mh.sys, "version_info", (3, 14, 0)):
            result = mh.convert_to_coreml(Path("/tmp/nonexistent-model"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], "")
        self.assertIn("Python <=3.12", result["reason"])

    def test_train_text_classifier_rejects_tiny_or_single_label_sets(self):
        result = mh.train_text_classifier(["a", "b", "c"], ["x", "x", "x"])
        self.assertFalse(result["ok"])
        self.assertIn("at least 4 rows across 2 labels", result["reason"])

    def test_doctor_reports_catalog_and_summary(self):
        with tempfile.TemporaryDirectory() as td:
            model_root = Path(td)
            tiny = model_root / "tiny-bert"
            tiny.mkdir(parents=True)
            (tiny / "config.json").write_text("{}", encoding="utf-8")
            (tiny / "weights.safetensors").write_text("x", encoding="utf-8")
            with mock.patch.dict(os.environ, {"LGWKS_MODELS_DIR": td}, clear=False):
                report = mh.doctor()
        self.assertEqual(report["schema"], "lgwks.model_hub.doctor.v1")
        self.assertGreaterEqual(report["summary"]["catalog_models"], 4)
        self.assertEqual(report["summary"]["present_models"], 1)
        names = [row["name"] for row in report["catalog"]]
        self.assertIn("tiny-bert", names)
        self.assertIn("intent_classifier", json.dumps(report))
