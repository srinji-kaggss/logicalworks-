"""Tests for hooks/subconscious_inbound.py — U7 inbound hook.

Exercises the hook exactly as the UserPromptSubmit harness does: JSON on stdin,
JSON (or nothing) on stdout, always exit 0. Maps 1:1 to issue #81 acceptance.

H1  real prompt: exit 0, valid JSON, additionalContext has C/G/P + top verbs
H2  non-generative (INV-3): only scores/labels/paths — no prose sentences
H3  fail-silent (INV-6): empty prompt -> exit 0, no output
H4  malformed stdin -> exit 0, no output (never block the prompt)
H5  latency (INV-7): real <1s
H6  shape: hookSpecificOutput.hookEventName == UserPromptSubmit
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

_HOOK = Path(__file__).resolve().parent.parent / "hooks" / "subconscious_inbound.py"


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestInboundHook(unittest.TestCase):
    def test_h1_real_prompt(self):
        r = _run(json.dumps({"prompt": "refactor the auth module"}))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("C=", ctx)
        self.assertIn("G=", ctx)
        self.assertIn("P=", ctx)
        self.assertIn("[subconscious · §6]", ctx)

    def test_h2_non_generative(self):
        r = _run(json.dumps({"prompt": "find all files changed in the last commit"}))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        # No generated prose — every line is a labelled score/path/header.
        for line in ctx.splitlines():
            self.assertTrue(
                line.startswith(("[subconscious", "C=", "top verbs:", "pathways:",
                                 "graph (", "(deterministic")),
                f"unexpected prose line: {line!r}",
            )

    def test_h3_empty_prompt_silent(self):
        r = _run(json.dumps({"prompt": ""}))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_h3_missing_prompt_silent(self):
        r = _run(json.dumps({}))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_h4_malformed_stdin_silent(self):
        r = _run("not json at all {{{")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_h5_latency(self):
        t0 = time.time()
        _run(json.dumps({"prompt": "score relations and graph query the corpus"}))
        self.assertLess(time.time() - t0, 1.0)

    def test_h6_hook_shape(self):
        r = _run(json.dumps({"prompt": "embed a PDF"}))
        out = json.loads(r.stdout)
        self.assertEqual(
            out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )


if __name__ == "__main__":
    unittest.main()
