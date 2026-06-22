"""Conformance gate — scan-policy single-source enforcement (#150 C-13).

Context (the bug this prevents): the same scan-exclusion sets (SKIP_DIRS, TEXT_EXT)
were copy-pasted across modules and drifted silently — `codebase` skipped a larger
tree than `embed`, and `extract` classified a different set of extensions as text
than the canonical. Different scanners saw different files. The divergence was
invisible because it lived in near-identical literals nobody diffed.

The fix is structural: ONE canonical base in `lgwks_substrate_config`, and any module
needing a scoped variant composes it via `with_extras(BASE, *extra)` — never restates
the base. This gate is the Director's "trust = easy fixes, not the pretense of no
mistakes": it does not stop you editing the policy, it stops the policy from
fragmenting. The easy path (compose) is made the only path, by failing the build if a
core module re-states a canonical set instead of deriving from it.

//why a test, not a doctrine line: prose relies on every future agent reading and
obeying it. This scans the source on every CI run, so the drift cannot return
unnoticed (the same native-enforcement pattern as test_one_embedder.py).

Two invariants:
  1. The canonical SKIP_DIRS / TEXT_EXT set-literals are defined exactly ONCE,
     in lgwks_substrate_config.
  2. No other core (root) module may assign a policy-named variable to a bare set
     literal that re-states the canonical base — it must compose via with_extras
     (a Call), a `base | {...}` BinOp, or a plain import alias.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import lgwks_substrate_config as sc

REPO = Path(__file__).resolve().parent.parent
CANON_MODULE = "lgwks_substrate_config.py"

# Names that denote a scan-policy set in any module (canonical or scoped variant).
POLICY_NAMES = {"SKIP_DIRS", "_SKIP_DIRS", "TEXT_EXT", "_TEXT_EXT", "_BASE_TEXT_EXT", "_BASE_SKIP_DIRS"}

# A literal sharing at least this many members with the canonical union is a COPY,
# not a coincidentally-overlapping small set.
COPY_THRESHOLD = 3
CANON_MEMBERS = frozenset(sc.SKIP_DIRS) | frozenset(sc.TEXT_EXT)


def _core_modules() -> list[Path]:
    # Core surface = root-level lgwks_*.py. Scripts (scripts/), the research subtree
    # (vision/), archived modules (archive/) and tests are out of scope by design —
    # a CI script's scan scope (e.g. scripts/check_schema_registry.py) is purpose-
    # specific, not the ingestion corpus, and is allowed its own set.
    return sorted(p for p in REPO.glob("lgwks_*.py"))


def _set_literal_members(node: ast.AST) -> set[str] | None:
    """If node is a set literal of string constants, return its members, else None."""
    if not isinstance(node, ast.Set):
        return None
    members: set[str] = set()
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            members.add(elt.value)
    return members


class TestScanPolicySingleSource(unittest.TestCase):
    def test_canonical_defined_only_in_substrate_config(self):
        # Invariant 1: the canonical literals live in exactly one module.
        offenders = []
        for path in _core_modules():
            if path.name == CANON_MODULE:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                names = {t.id for t in node.targets if isinstance(t, ast.Name)}
                if not (names & POLICY_NAMES):
                    continue
                members = _set_literal_members(node.value)
                if members is None:
                    continue  # composed (Call / BinOp / alias) — the sanctioned path
                overlap = members & CANON_MEMBERS
                if len(overlap) >= COPY_THRESHOLD:
                    offenders.append(
                        f"{path.name}:{node.lineno} — {sorted(names)} re-states "
                        f"{len(overlap)} canonical members {sorted(overlap)[:5]}…; "
                        f"compose via lgwks_substrate_config.with_extras(BASE, *extra) instead"
                    )
        self.assertEqual(offenders, [], "scan-policy set restated instead of composed:\n" + "\n".join(offenders))

    def test_with_extras_composes_base_and_declared_extras(self):
        self.assertEqual(sc.with_extras({"a", "b"}, "c", "d"), frozenset({"a", "b", "c", "d"}))

    def test_with_extras_does_not_mutate_base(self):
        base = {"a", "b"}
        sc.with_extras(base, "c")
        self.assertEqual(base, {"a", "b"})

    def test_with_extras_returns_immutable(self):
        self.assertIsInstance(sc.with_extras({"a"}, "b"), frozenset)


if __name__ == "__main__":
    unittest.main()
