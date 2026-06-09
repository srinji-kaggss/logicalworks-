"""Tests for lgwks_intent_router — deterministic intent routing."""

import json
import sys
import unittest

import lgwks_intent_router as router


class TestIntentRouter(unittest.TestCase):
    def test_classify_research(self):
        result = router.classify("find papers on transformer architecture")
        self.assertEqual(result["category"], "research")
        self.assertEqual(result["method"], "heuristic")
        self.assertGreater(result["confidence"], 0.5)
        self.assertIn("latency_ms", result)
        self.assertIn("input_hash", result)

    def test_classify_code(self):
        result = router.classify("debug failing test in lgwks_session")
        self.assertEqual(result["category"], "code")
        self.assertEqual(result["method"], "heuristic")

    def test_classify_system(self):
        result = router.classify("check system health and run doctor")
        self.assertEqual(result["category"], "system")

    def test_classify_github(self):
        result = router.classify("list open pull requests")
        self.assertEqual(result["category"], "github")
        self.assertGreater(result["confidence"], 0.7)

    def test_classify_devops(self):
        result = router.classify("deploy the fleet of agents")
        self.assertEqual(result["category"], "devops")

    def test_classify_multiply(self):
        result = router.classify("run git {status,log,diff}")
        self.assertEqual(result["category"], "multiply")
        self.assertGreater(result["confidence"], 0.8)

    def test_classify_unknown(self):
        result = router.classify("")
        self.assertEqual(result["category"], "unknown")

    def test_route_returns_verb(self):
        result = router.route("find papers on AI safety")
        self.assertIn("verb", result)
        self.assertIn("args", result)
        self.assertIn("note", result)
        self.assertEqual(result["category"], "research")

    def test_route_code(self):
        result = router.route("review my code for bugs")
        self.assertEqual(result["category"], "code")
        self.assertEqual(result["verb"], "repo status")

    def test_route_github(self):
        result = router.route("what issues are open")
        self.assertEqual(result["category"], "github")
        self.assertEqual(result["verb"], "gh issues")

    def test_route_unknown(self):
        result = router.route("blah blah nonsense")
        self.assertEqual(result["category"], "unknown")
        self.assertEqual(result["verb"], "refine")

    def test_input_hash_consistent(self):
        r1 = router.classify("test input")
        r2 = router.classify("test input")
        self.assertEqual(r1["input_hash"], r2["input_hash"])

    def test_cli_json(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = router._route_command(type("Args", (), {"text": "find papers", "json": True, "model": "auto"})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertEqual(data["category"], "research")
            self.assertIn("verb", data)
        finally:
            sys.stdout = old_stdout

    def test_cli_tty(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = router._route_command(type("Args", (), {"text": "debug my code", "json": False, "model": "auto"})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            self.assertIn("category:", output)
            self.assertIn("confidence:", output)
        finally:
            sys.stdout = old_stdout

    def test_cli_empty(self):
        import io
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            rc = router._route_command(type("Args", (), {"text": "", "json": False, "model": "auto"})())
            self.assertEqual(rc, 2)
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
