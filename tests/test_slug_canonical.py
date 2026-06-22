"""#223 family 5 — canonical filesystem slug.

The five fs-slug copies (`substrate_io._slug`, `project_artifacts._slug`,
`jarvis.slugify`, `workflows.slugify`, plus the now-renamed concept dedup key)
drifted on charset / run-collapse / strip / fallback / limit. They are now one
primitive, `lgwks_substrate_io.slug`.

These tests are the *evidence* that convergence changed no persisted-path bytes:
each identity generator is asserted byte-for-byte against an inline copy of its
PRE-convergence implementation (the oracle), over an adversarial input battery.
The one deliberate net change (workflows' partial `--` collapse) is pinned
separately, with its downstream re-slug invariance.
"""

from __future__ import annotations

import re
import unittest

import lgwks_substrate_io as io
import lgwks_jarvis as jarvis
import lgwks_project_artifacts as pa
import lgwks_workflows as wf
import lgwks_concept as concept
from lgwks_hashing import content_id


# --- adversarial input battery (covers every drift axis) ---------------------
INPUTS = [
    "",
    "   ",
    "Hello World",
    "https://Example.COM/Some/Path?q=1#frag",
    "http://a.b.c/d_e-f.g",
    "a -- b",            # adjacent separator + dash → the collapse-bug trigger
    "a---b",
    "a / / b",
    "...leading.dots...",
    "___under___scores___",
    "café_münchen",      # unicode (folded by ascii dialects, kept by \w)
    "UPPER_snake-Case.dot",
    "x" * 200,           # > every limit
    ("y-" * 60),         # long, ends on a separator after truncation
    "!!!",               # all-separators → fallback path
    "tab\tand\nnewline",
]


# --- oracles: verbatim copies of the PRE-convergence implementations ----------
def _old_substrate_io_slug(text: str, limit: int = 64) -> str:
    return (re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip(".-") or "substrate")[:limit]


def _old_project_artifacts_slug(value: str) -> str:
    safe = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip(".-") or "project"
    return f"{safe}-{content_id(value, 12)}"


def _old_jarvis_slugify(value: str, limit: int = 48) -> str:
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or "jarvis-crawl")[:limit].strip("-") or "jarvis-crawl"


class TestByteEquivalence(unittest.TestCase):
    """Identity/path generators: new == old, byte-for-byte, on every input."""

    def test_substrate_io_slug_unchanged(self):
        for s in INPUTS:
            self.assertEqual(io._slug(s), _old_substrate_io_slug(s), repr(s))
            for lim in (8, 16, 64):
                self.assertEqual(io._slug(s, lim), _old_substrate_io_slug(s, lim), (s, lim))

    def test_project_artifacts_slug_unchanged(self):
        for s in INPUTS:
            self.assertEqual(pa._slug(s), _old_project_artifacts_slug(s), repr(s))

    def test_jarvis_slugify_unchanged(self):
        for s in INPUTS:
            self.assertEqual(jarvis.slugify(s), _old_jarvis_slugify(s), repr(s))
            for lim in (8, 16, 48):
                self.assertEqual(jarvis.slugify(s, lim), _old_jarvis_slugify(s, lim), (s, lim))


class TestCanonicalSlug(unittest.TestCase):
    def test_collapses_runs_to_single_dash(self):
        self.assertEqual(io.slug("a   b___c", allow=""), "a-b-c")

    def test_strip_and_fallback(self):
        self.assertEqual(io.slug("!!!", fallback="x", allow=""), "x")
        self.assertEqual(io.slug("--mid--", allow=""), "mid")

    def test_dot_only_stripped_when_allowed(self):
        # '.' kept + stripped at ends when allowed
        self.assertEqual(io.slug(".a.b.", allow="._-"), "a.b")
        # '.' folded to '-' when not allowed
        self.assertEqual(io.slug("a.b", allow=""), "a-b")

    def test_scheme_strip(self):
        self.assertEqual(io.slug("https://x.io/y", allow="", strip_scheme=True), "x-io-y")
        self.assertEqual(io.slug("https://x.io/y", allow="", strip_scheme=False), "https-x-io-y")

    def test_restrip_after_truncate(self):
        # truncation lands on a separator → restrip removes the trailing dash
        self.assertEqual(io.slug("ab-cd", limit=3, allow="", restrip_after_truncate=True), "ab")
        self.assertEqual(io.slug("ab-cd", limit=3, allow="", restrip_after_truncate=False), "ab-")


class TestWorkflowsCharacterizedChange(unittest.TestCase):
    """workflows.slugify: the single deliberate net change is full run-collapse."""

    def test_full_collapse_fixes_partial_dash_bug(self):
        # old: re.sub(...).strip('-').replace('--','-') left '--' on 3+ runs.
        trigger = "a-- b"  # literal '-' adjacent to a separator → '---' before .replace
        old = re.sub(r"[^\w-]+", "-", trigger.lower()).strip("-").replace("--", "-")
        self.assertIn("--", old)                       # the bug, as it was ("a--b")
        self.assertNotIn("--", wf.slugify(trigger))    # now fully collapsed ("a-b")

    def test_downstream_reslug_invariance_for_ascii(self):
        # For inputs without the collapse trigger, the final persisted id (after
        # substrate_run re-slugs via io._slug) is unchanged by the fold.
        for s in ["My Project", "repo_name-v2", "café"]:
            self.assertEqual(io._slug(wf.slugify(s)), io._slug(io._slug(s)))


class TestConceptDedupKeyDistinct(unittest.TestCase):
    def test_keeps_spaces_unlike_fs_slug(self):
        self.assertEqual(concept._dedup_key("RRSP Transfer!"), "rrsp transfer")
        self.assertNotIn(" ", io.slug("RRSP Transfer!", allow=""))


if __name__ == "__main__":
    unittest.main()
