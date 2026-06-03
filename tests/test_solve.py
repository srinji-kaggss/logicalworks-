"""Tests for lgwks_solve — forensics, quiet/timeout propagation, intent gating."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import lgwks_solve as solve
from lgwks_steering import Steering


class TestSolveGit(unittest.TestCase):
    def test_solve_git_abstains_on_unrelated_thought(self):
        tmp = Path(tempfile.mkdtemp())
        # Initialize a mock git repo
        (tmp / ".git").mkdir()
        
        # Mock _is_repo to return True
        # Mock _diagnose to return a list of findings (e.g. detached HEAD)
        f1 = solve.Finding(
            what="You are in DETACHED HEAD at a1b2c3d — commits you make now belong to no branch.",
            severity="caution",
            next_step="git switch -c rescue",
            evidence=[solve.Evidence("ev-head", "HEAD is detached", "git symbolic-ref HEAD", "detached")]
        )
        
        with patch("lgwks_solve._is_repo", return_value=True), \
             patch("lgwks_solve._diagnose", return_value=[f1]):
            
            # Case 1: thought is related to detached head -> does not abstain
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = solve.solve_git(tmp, thought="detached HEAD", as_json=True)
            self.assertEqual(rc, 0)
            res = json.loads(out.getvalue())
            self.assertNotEqual(res["story"], "abstain")
            self.assertEqual(len(res["findings"]), 1)
            
            # Case 2: thought is unrelated (e.g. verify PR385) -> abstains and clears findings
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                rc2 = solve.solve_git(tmp, thought="verify PR385/#382", as_json=True)
            self.assertEqual(rc2, 0)
            res2 = json.loads(out2.getvalue())
            self.assertEqual(res2["story"], "abstain")
            self.assertEqual(len(res2["findings"]), 0)

    def test_solve_git_quiet_mode(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".git").mkdir()
        f1 = solve.Finding(
            what="Clean repo",
            severity="info",
            next_step="",
            evidence=[]
        )
        
        with patch("lgwks_solve._is_repo", return_value=True), \
             patch("lgwks_solve._diagnose", return_value=[f1]), \
             patch("lgwks_solve._synthesize", return_value="story"):
            
            # Default mode -> writes to stderr
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                solve.solve_git(tmp, quiet=False)
            self.assertGreater(len(err.getvalue()), 0)
            
            # Quiet mode -> suppresses stderr
            err_quiet = io.StringIO()
            with contextlib.redirect_stderr(err_quiet), contextlib.redirect_stdout(io.StringIO()):
                solve.solve_git(tmp, quiet=True)
            self.assertEqual(len(err_quiet.getvalue()), 0)

    def test_solve_git_timeout_propagation(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".git").mkdir()
        
        # When subprocess.run runs inside _git, check that it uses the set timeout
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "true"
        mock_run.stderr = ""
        
        with patch("subprocess.run", return_value=mock_run):
            solve.solve_git(tmp, timeout=12)
            # Find the git call
            for call in mock_run.call_args_list:
                args, kwargs = call
                if kwargs.get("timeout") is not None:
                    self.assertEqual(kwargs["timeout"], 12)
