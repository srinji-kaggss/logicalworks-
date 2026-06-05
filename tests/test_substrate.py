from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_substrate as substrate


class TestSubstrateScoring(unittest.TestCase):
    def test_fact_score_prefers_numeric_rules(self):
        a = substrate._fact_score("RRSP minimum amount is $5,000 and form T2033 is required.")
        b = substrate._fact_score("I think RRSP is a great account and people love it.")
        self.assertGreater(a, b)

    def test_stem_text_filters_narrative(self):
        text = "I think this is great. Minimum amount is $5,000. Use form T2033."
        out = substrate._stem_text(text, 0.6)
        self.assertIn("Minimum amount is $5,000.", out)
        self.assertIn("Use form T2033.", out)
        self.assertNotIn("I think this is great.", out)

    def test_looks_like_login_gate(self):
        self.assertTrue(substrate._looks_like_login_gate("Sign in", "Use Touch ID to continue", "https://portal.example.com/login"))
        self.assertTrue(substrate._looks_like_login_gate("Just a moment...", "Checking your browser before accessing the portal", "https://portal.example.com/"))
        self.assertFalse(substrate._looks_like_login_gate("Overview", "Transfer threshold is 500 dollars.", "https://portal.example.com/docs"))


class TestSubstrateBuild(unittest.TestCase):
    def test_build_from_local_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            (root / "a.md").write_text(
                "RRSP minimum amount is $5,000. Use form T2033. I think this is great.",
                encoding="utf-8",
            )
            (root / "b.txt").write_text(
                "Transfer route TR01 to TR02. Settlement is T+1. Marketing story goes here.",
                encoding="utf-8",
            )

            args = type("Args", (), {
                "target": str(root),
                "project": "fundserv-test",
                "source_type": "folder",
                "max_pages": 10,
                "max_depth": 1,
                "max_files": 10,
                "max_chars": 10000,
                "chunk_words": 80,
                "chunk_overlap": 10,
                "fact_threshold": 0.6,
                "embed_provider": "auto",
                "embed_model": "",
                "login_if_needed": True,
                "login_url": "",
                "success_selector": None,
                "max_auto_bypass_attempts": 3,
                "max_auth_handoffs": 3,
                "browser_engine": "chromium",
            })()

            with mock.patch.object(substrate.lgwks_run, "embed", return_value=([0.1, 0.2, 0.3], "ollama:qwen3-embedding:8b", True)):
                with mock.patch.object(substrate, "GLOBAL_FACT_DB", Path(td) / "global-facts.db"):
                    manifest = substrate.build_run(args)

            run_dir = Path(manifest["artifacts"]["root"])
            self.assertTrue((run_dir / "facts.jsonl").exists())
            facts = [json.loads(line) for line in (run_dir / "facts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any("T2033" in row["fact_text"] for row in facts))
            vectors = [json.loads(line) for line in (run_dir / "vectors.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(row["provider"] == "ollama:qwen3-embedding:8b" for row in vectors))
            self.assertGreaterEqual(manifest["embedding"]["semantic_vectors"], len(vectors))
            self.assertGreater(manifest["embedding"]["global_fact_vectors_written"], 0)
            self.assertTrue(Path(manifest["global_artifacts"]["fact_vector_db"]).exists())

    def test_crawl_site_prompts_auth_then_retries(self):
        state = {"saved": False}

        def fake_render(url, **_kwargs):
            if not state["saved"]:
                return {"ok": True, "html": "<html>Sign in with passkey</html>", "text": "Sign in with passkey"}
            return {"ok": True, "html": "<html>Transfer threshold is $500.</html>", "text": "Transfer threshold is $500."}

        def fake_html_to_markdown(html, url):
            if "Sign in" in html:
                return "Sign in with passkey", "Sign in", []
            return "Transfer threshold is $500.", "Overview", []

        def fake_save_session(_url, **_kwargs):
            state["saved"] = True
            return {"ok": True, "path": "/tmp/session.json", "reason": "session saved (manual)"}

        with mock.patch.object(substrate.lgwks_browser, "_remote_allowed", return_value=True):
            with mock.patch.object(substrate.lgwks_browser, "render", side_effect=fake_render):
                with mock.patch.object(substrate.lgwks_browser, "save_session", side_effect=fake_save_session):
                    with mock.patch.object(substrate, "html_to_markdown", side_effect=fake_html_to_markdown):
                        docs, frontier = substrate._crawl_site(
                            "https://portal.example.com",
                            max_pages=1,
                            max_depth=0,
                            browser_engine="webkit",
                            login_if_needed=True,
                            login_url="",
                            success_selector=None,
                            max_auto_bypass_attempts=1,
                            max_auth_handoffs=2,
                        )
        self.assertEqual(len(docs), 1)
        self.assertIn("$500", docs[0]["text"])
        self.assertTrue(any(row["status"] == "retrying_gate" for row in frontier))
        self.assertTrue(any(row["status"] == "auth_prompted" for row in frontier))


if __name__ == "__main__":
    unittest.main()
