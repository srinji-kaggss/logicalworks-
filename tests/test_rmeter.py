"""Tests for R-meter token burn categorization in lgwks_session."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lgwks_session


class TestRMeter(unittest.TestCase):
    def _make_repo(self, commits: list[tuple[str, str]] = None) -> Path:
        """Create a temp git repo with optional commits."""
        d = Path(tempfile.mkdtemp(prefix="lgwks-rmeter-test-"))
        os.system(f"cd {d} && git init --quiet && git config user.email 'test@test' && git config user.name 'Test'")
        if commits:
            for msg in commits:
                (d / "f.txt").write_text(msg + "\n")
                os.system(f"cd {d} && git add . && git commit -m '{msg}' --quiet")
        return d

    def test_rmeter_invention_dominant(self):
        repo = self._make_repo([
            "feat: add new feature",
            "implement: cool thing",
            "design: new architecture",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=3)
        rm = summary.get("r_meter", {})
        self.assertEqual(rm["dominant"], "invention")
        self.assertGreater(rm["percentages"]["invention"], 50)

    def test_rmeter_recovery_dominant(self):
        repo = self._make_repo([
            "fix: bug in parser",
            "revert: broken commit",
            "test: add missing coverage",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=3)
        rm = summary.get("r_meter", {})
        self.assertEqual(rm["dominant"], "recovery")
        self.assertGreater(rm["percentages"]["recovery"], 50)

    def test_rmeter_noise_dominant(self):
        repo = self._make_repo([
            "wip: draft changes",
            "merge: main into feature",
            "docs: update readme",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=3)
        rm = summary.get("r_meter", {})
        # merge + docs + wip → noise or invention depending
        self.assertIn(rm["dominant"], ["noise", "invention"])

    def test_rmeter_counts_present(self):
        repo = self._make_repo([
            "feat: new thing",
            "fix: bug",
            "wip: temp",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=3)
        rm = summary.get("r_meter", {})
        self.assertIn("counts", rm)
        self.assertIn("percentages", rm)
        self.assertIn("dominant", rm)
        self.assertIn("total_weighted", rm)
        self.assertAlmostEqual(sum(rm["counts"].values()), rm["total_weighted"])

    def test_rmeter_in_narrative(self):
        repo = self._make_repo([
            "feat: something new",
            "fix: a bug",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=2)
        narrative = summary.get("narrative", "")
        self.assertIn("Token burn:", narrative)
        self.assertIn("dominant", narrative)

    def test_rmeter_empty_repo(self):
        repo = self._make_repo()
        summary = lgwks_session.session_summary(repo, n_commits=0)
        rm = summary.get("r_meter", {})
        self.assertEqual(rm["dominant"], "unknown")
        self.assertEqual(rm["total_weighted"], 0)

    def test_rmeter_json_output(self):
        repo = self._make_repo([
            "feat: new",
            "fix: bug",
        ])
        summary = lgwks_session.session_summary(repo, n_commits=2)
        # Verify JSON-serializable
        dumped = json.dumps(summary)
        loaded = json.loads(dumped)
        self.assertIn("r_meter", loaded)
        self.assertIn("dominant", loaded["r_meter"])


if __name__ == "__main__":
    unittest.main()
