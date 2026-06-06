from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_jepa as jepa


class TestJepa(unittest.TestCase):
    def _repo_fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "lgwks_capture.py").write_text("def capture():\n    return 'capture'\n", encoding="utf-8")
        (root / "lgwks_portal.py").write_text("def portal():\n    return 'portal'\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        return root

    def test_build_package_without_capture_creates_machine_and_human_views(self):
        repo = self._repo_fixture()
        with tempfile.TemporaryDirectory() as td:
            v1 = Path(td) / "v1.txt"
            v2 = Path(td) / "v2.txt"
            v1.write_text("capture portal substrate graph packet", encoding="utf-8")
            v2.write_text("portal packet graph capture runtime", encoding="utf-8")
            args = type("Args", (), {
                "intent": "",
                "view_file": [str(v1), str(v2)],
                "context_file": [],
                "stdin_text": "",
                "repo": str(repo),
                "project": "",
                "embed_provider": "deterministic",
                "embed_model": "",
                "max_pages": 25,
                "max_depth": 2,
                "max_files": 250,
                "max_chars": 120000,
                "chunk_words": 320,
                "chunk_overlap": 48,
                "fact_threshold": 0.6,
                "refresh_graph": True,
                "no_capture": True,
            })()
            with mock.patch.object(jepa, "JEPA_ROOT", Path(td) / "jepa"):
                packet = jepa.build_package(args)
        self.assertEqual(packet["schema"], jepa.JEPA_SCHEMA)
        self.assertTrue(packet["key"].startswith("jepa:"))
        self.assertTrue(packet["machine"]["portal_key"].startswith("portal:"))
        self.assertIn("summary", packet["human"])
        self.assertTrue(packet["latent"]["anchors"])

    def test_doctor_reports_current_gap_honestly(self):
        report = jepa.doctor()
        self.assertEqual(report["schema"], "lgwks.jepa.doctor.v1")
        self.assertTrue(report["runtime"]["multiview_package_builder"])
        self.assertIn("No trained JEPA predictor exists yet.", report["gaps"])

    def test_show_roundtrip_reads_saved_packet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            packet = {"schema": jepa.JEPA_SCHEMA, "key": "jepa:abc"}
            out = root / "jepa_abc.json"
            out.write_text(json.dumps(packet), encoding="utf-8")
            with mock.patch.object(jepa, "JEPA_ROOT", root):
                class Args:
                    key = "jepa:abc"
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = jepa.show_command(Args())
        self.assertEqual(rc, 0)
        self.assertIn("jepa:abc", buf.getvalue())
