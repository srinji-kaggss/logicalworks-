"""Regrowth guard (R4.7) — the canonical-primitive drift-prevention gate.

This test is the machine-checkable complement of the Pristine Program R4 routing
pass: route manual cosine/dot, bare hashlib.sha*, and datetime.now( to their canonical
primitives (lgwks_vecmath, lgwks_hashing, lgwks_clock). A future straggler — a
new file that re-derives one of these inline — fails this test, not just a code review.

Three invariants:
  1. No manual sum-zip dot product outside canonical vecmath + documented allow-list.
  2. No bare hashlib.sha* call outside canonical hashing + documented allow-list.
  3. No datetime.now( call outside canonical clock + documented allow-list.

Legit forks in each allow-list are documented with a one-line reason.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ── allow-lists (canonical + legit forks) ─────────────────────────────────────

# hashlib.sha* — keyed/crypto hashing uses sha for HMAC or KDF, not CIDs.
# sha256 as a PRNG seed in __main__ CLI stubs (not stored IDs) is also allowed.
HASH_ALLOWED = {
    "lgwks_hashing.py",         # canonical — defines content_id / digest_bytes
    "lgwks_capability.py",      # HMAC signatures (keyed hash, not content-id)
    "lgwks_sign.py",            # HMAC signatures
    "lgwks_vault.py",           # KDF — PBKDF2/sha256 for key derivation
    "lgwks_score.py",           # sha256 as PRNG seed in __main__ CLI stub only
    "lgwks_viz_project.py",     # sha256 as PRNG seed in __main__ CLI stub only
}

# datetime.now( — elapsed-duration math (subtracting two datetimes) is NOT a stamp.
CLOCK_ALLOWED = {
    "lgwks_clock.py",           # canonical — defines now_iso / now_aware
    "lgwks_models_dev.py",      # elapsed duration: (datetime.now - fetched).total_seconds()
}

# sum(x*y for x,y in zip()) — legit non-similarity uses of a dot-product loop.
DOT_ALLOWED = {
    "lgwks_vecmath.py",         # canonical — defines dot / cosine / l2_norm
    "lgwks_score.py",           # I5 tensor contraction (antisymmetric scoring math, not cosine)
    "lgwks_algorithms.py",      # logistic regression predictor: sum(w*xi for w,xi in zip(weights,x))
    "lgwks_vector.py",          # domain-specific dot with same-space check + f32→f64 clamp
}


# ── source-file collector (mirrors test_one_embedder.py) ──────────────────────

def _source_files() -> list[Path]:
    SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "__pycache__", "archive"}
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
        # skip nested vision/ overlays — separate tree
        if "vision" in parts:
            continue
        out.append(p)
    return out


def _is_dot_generator(node: ast.AST) -> bool:
    """True if node is a generator/listcomp whose elt is x*y and iter is zip(...)."""
    if not isinstance(node, (ast.GeneratorExp, ast.ListComp)):
        return False
    if not isinstance(node.elt, ast.BinOp) or not isinstance(node.elt.op, ast.Mult):
        return False
    if len(node.generators) != 1:
        return False
    gen = node.generators[0]
    if not isinstance(gen.iter, ast.Call):
        return False
    func = gen.iter.func
    return (
        (isinstance(func, ast.Name) and func.id == "zip")
        or (isinstance(func, ast.Attribute) and func.attr == "zip")
    )


class TestNoPrimitiveRegrowth(unittest.TestCase):
    """Canonical-primitive routing must not regrow after R4."""

    def _scan(self) -> tuple[list[str], list[str], list[str]]:
        hash_hits: list[str] = []
        clock_hits: list[str] = []
        dot_hits: list[str] = []
        for path in _source_files():
            name = path.name
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(REPO))
            for node in ast.walk(tree):
                # hashlib.sha* — attribute access on `hashlib` object
                if (
                    name not in HASH_ALLOWED
                    and isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "hashlib"
                    and node.attr.startswith("sha")
                ):
                    hash_hits.append(f"{rel}:{getattr(node, 'lineno', '?')}")
                # datetime.now( — Call whose func is datetime.now attribute
                if (
                    name not in CLOCK_ALLOWED
                    and isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "now"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "datetime"
                ):
                    clock_hits.append(f"{rel}:{getattr(node, 'lineno', '?')}")
                # manual sum-zip dot product
                if (
                    name not in DOT_ALLOWED
                    and isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "sum"
                    and node.args
                    and _is_dot_generator(node.args[0])
                ):
                    dot_hits.append(f"{rel}:{getattr(node, 'lineno', '?')}")
        return hash_hits, clock_hits, dot_hits

    def test_no_bare_hashlib_sha(self):
        hits, _, _ = self._scan()
        self.assertEqual(
            hits, [],
            "bare hashlib.sha* outside canonical lgwks_hashing + allow-list — "
            "route to lgwks_hashing.content_id / digest_bytes / digest:\n  "
            + "\n  ".join(hits),
        )

    def test_no_bare_datetime_now(self):
        _, hits, _ = self._scan()
        self.assertEqual(
            hits, [],
            "bare datetime.now( outside canonical lgwks_clock + allow-list — "
            "route to lgwks_clock.now_iso() / now_aware():\n  "
            + "\n  ".join(hits),
        )

    def test_no_manual_sum_zip_dot(self):
        _, _, hits = self._scan()
        self.assertEqual(
            hits, [],
            "manual sum(x*y for x,y in zip()) outside canonical lgwks_vecmath + allow-list — "
            "route to lgwks_vecmath.dot():\n  "
            + "\n  ".join(hits),
        )


if __name__ == "__main__":
    unittest.main()
