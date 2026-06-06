"""
Conformance gate — the lead-architect drift-prevention mechanism.

Context (the catastrophic failure this prevents): issue #29 — "gates trust on a
broken model" — was caused by lgwks_intent_classifier._embed delegating to
np.random.randn. Random vectors meant cosine confidence was NOISE, yet that noise
was allowed to gate tool authority. The deeper failure was embedder DIVERGENCE:
several modules each carried their own embedding implementation, so one could rot
to RNG (or drift in dims/space) without any single test catching it.

//why a test, not a doctrine line: "don't put RNG in an embedding path" as prose
relies on every future agent reading and obeying it. Native enforcement > prose
(fleet doctrine T6): this scans the source on every CI run and FAILS THE BUILD if
the regression returns. The skeptic's question — "what stops this from happening a
third time?" — is answered by a machine, not a promise.

Two invariants:
  1. NO embedding-producing function in any non-test module may use a
     nondeterministic RNG. (The #29 root cause, made unrepresentable.)
  2. The intent classifier — the module that gates AUTHORITY — must embed through
     the single canonical seam lgwks_run.embed, not a private re-implementation.
     (The specific drift that re-occurred: re-pointing _embed at a feature-hash
     copy instead of the real Qwen Eye. A regression of that exact mistake fails
     here.)
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# //why this exact set: these are the nondeterministic generators that produce a
# different vector for the same text across calls — the property that turned
# "confidence" into noise in #29. random.seed-then-call is still nondeterministic
# across processes, so the call sites themselves are forbidden in embed paths.
FORBIDDEN_RNG = {
    ("numpy", "random"), ("np", "random"),
    ("random", "randn"), ("random", "rand"), ("random", "random"),
    ("random", "gauss"), ("random", "normalvariate"), ("random", "uniform"),
}

# //why name-pattern, not a hardcoded list: a NEW embedding function added next
# year is caught automatically. We match the function name, then scan only its
# body — RNG used legitimately elsewhere (jitter, sampling, layout) is untouched.
EMBED_NAMES = {"embed", "_embed", "embedding", "_embedding", "embed_one"}


def _core_modules() -> list[Path]:
    # //why skip any hidden dir (component starting with '.'): nested git worktrees
    # under .claude/worktrees hold OTHER agents' branches — possibly the pre-fix
    # stub. They are not THIS source tree; scanning them would fail the build on
    # code we do not own here. Also skip vendored/venv trees.
    SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "__pycache__"}
    out: list[Path] = []
    for p in REPO.rglob("*.py"):
        parts = p.relative_to(REPO).parts
        if any(seg.startswith(".") for seg in parts):
            continue
        if any(seg in SKIP_DIRS for seg in parts):
            continue
        name = parts[-1]
        if "tests" in parts or name.startswith("test_"):
            continue
        out.append(p)
    return out


def _embed_functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name in EMBED_NAMES]


class TestNoRngInEmbeddingPaths(unittest.TestCase):
    """Invariant 1: an embedding function is deterministic — no RNG, ever."""

    def test_no_nondeterministic_rng_in_any_embed_function(self):
        offenders: list[str] = []
        for path in _core_modules():
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for fn in _embed_functions(tree):
                # //why AST attribute access, NOT a source substring: a substring
                # scan flags the word "np.random" in an explanatory COMMENT (e.g.
                # "replaces the old np.random stub"). Only an actual attribute-access
                # node is a real call. This catches np.random.X and random.randn(...)
                # as real code while ignoring prose that names the banned pattern.
                for node in ast.walk(fn):
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                        if (node.value.id, node.attr) in FORBIDDEN_RNG:
                            offenders.append(
                                f"{path.relative_to(REPO)}:{getattr(node,'lineno','?')} "
                                f"{fn.name}() uses {node.value.id}.{node.attr}")
        self.assertEqual(
            offenders, [],
            "Embedding paths must be deterministic — RNG here is the #29 root cause:\n  "
            + "\n  ".join(offenders))


class TestAuthorityGateUsesCanonicalSeam(unittest.TestCase):
    """Invariant 2: the authority-gating classifier embeds through lgwks_run.embed."""

    def test_intent_classifier_embed_routes_through_lgwks_run(self):
        # //why source-level assertion: the drift that recurred was _embed being
        # re-pointed at a private feature-hash copy. The defense is to require the
        # canonical seam by name in the one module whose embeddings gate authority.
        src = (REPO / "lgwks_intent_classifier.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        embed_fns = [f for f in _embed_functions(tree) if f.name == "_embed"]
        self.assertTrue(embed_fns, "lgwks_intent_classifier must define _embed")
        body = ast.get_source_segment(src, embed_fns[0]) or ""
        self.assertIn(
            "lgwks_run.embed", body,
            "lgwks_intent_classifier._embed must route through the canonical seam "
            "lgwks_run.embed (the real Qwen Eye), not a private embedding copy. "
            "This is the exact drift that caused the catastrophic failure twice.")

    def test_classifier_defines_no_local_hash_embedder(self):
        # //why AST, not a source grep: the prior heuristic grepped the whole file
        # and false-positived on a COMMENT that names blake2b. The real invariant is
        # structural — the module must not DEFINE its own hashing embedder. We check
        # that no embed function in this module calls hashlib.* (the build-your-own
        # feature-hash signature). Routing stays through lgwks_run.embed.
        src = (REPO / "lgwks_intent_classifier.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for fn in _embed_functions(tree):
            for node in ast.walk(fn):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    self.assertNotEqual(
                        node.value.id, "hashlib",
                        f"{fn.name}() builds a local hash embedder via hashlib — "
                        "the authority gate must embed through lgwks_run.embed, not its own copy")


class TestCanonicalSeamIsHonestAboutSemantics(unittest.TestCase):
    """The seam must tell the truth about whether a vector is semantic."""

    def test_run_embed_marks_fallback_non_semantic(self):
        # //why this is the linchpin of the authority law: if the deterministic
        # fallback ever returned is_semantic=True, a lexical vector could reach the
        # full-authority bar. Force the offline path and assert it is honest.
        self.addCleanup(os.environ.pop, "LGWKS_NO_MODELS", None)  # always restore
        os.environ["LGWKS_NO_MODELS"] = "1"
        import importlib, sys
        sys.path.insert(0, str(REPO))
        import lgwks_run  # noqa: E402
        importlib.reload(lgwks_run)
        vec, provider, is_semantic = lgwks_run.embed("score this intent", embed_on=True)
        self.assertIsNotNone(vec)
        self.assertFalse(is_semantic, "the feature-hash fallback must NOT claim to be semantic")
        self.assertEqual(provider, "deterministic-feature-hash", "provider name must be honest")

    def test_run_embed_off_returns_none(self):
        import sys
        sys.path.insert(0, str(REPO))
        import lgwks_run
        vec, _provider, is_semantic = lgwks_run.embed("x", embed_on=False)
        self.assertIsNone(vec)
        self.assertFalse(is_semantic)


if __name__ == "__main__":
    unittest.main()
