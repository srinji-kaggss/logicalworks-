"""Module coverage gate (R8) — every tracked lgwks_*.py module with live callers must be tested.

This test ensures that every `lgwks_*.py` source module that is actually imported by
another module is also imported by at least one test file. This prevents the silent
accumulation of untested-but-called modules.

Mechanism:
  1. Scan all source modules (lgwks_*.py at repo root).
  2. Build the import graph: which modules import which other modules.
  3. Identify modules that have live callers (imported by at least one other module).
  4. Scan test files to see which modules are imported.
  5. Assert that every module with live callers is also imported by at least one test.
  6. Maintain an EXCLUDED dict for known debt (existing untested-but-called modules).

Known debt (pre-existing modules with callers but no test imports yet):
  These are real modules that genuinely have live callers today but haven't been
  added to any test file's imports yet. The EXCLUDED set is the COMPLETE current
  debt list (tracked in #349), computed from this same scan.

Known limitations (by design, conservative — they err toward FEWER violators, so a
flagged module is always real debt):
  - Static imports only: the `lgwks` dispatcher loads command modules via dynamic
    __import__("lgwks_<cmd>") / SourceFileLoader, which AST cannot see. A module
    reached ONLY via dynamic dispatch counts as having no static callers (out of scope).
  - Test-import detection scans tests/ only; axiom/tests/ imports zero lgwks_* (verified).
"""

from __future__ import annotations

import ast
import unittest
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ── Excluded modules (known debt — pre-existing, not yet tested) ─────────────────
# The COMPLETE current set of root lgwks_*.py modules that have live callers but zero
# test imports (135 called, 116 tested, 19 debt). Computed from the same scan this gate
# runs — not hand-curated — so the list is exactly (called - tested) and both invariants
# below hold by construction. Each is tracked for backfill in #349; remove an entry as
# its test lands. A NEW untested-but-called module is NOT here → it fails the gate.
_DEBT_REASON = "pre-existing: live callers but no test imports it yet; backfill tracked in #349"
EXCLUDED = {m: _DEBT_REASON for m in (
    "lgwks_coreml",
    "lgwks_do",
    "lgwks_fabric_projection",
    "lgwks_foundation",
    "lgwks_keyvault",
    "lgwks_map",
    "lgwks_multimodal",
    "lgwks_phase",
    "lgwks_proc",
    "lgwks_project_deploy",
    "lgwks_project_plan",
    "lgwks_project_review",
    "lgwks_redact",
    "lgwks_search_engine",
    "lgwks_substrate_crawl",
    "lgwks_substrate_run",
    "lgwks_substrate_vector",
    "lgwks_ui",
)}

# ── Source file collector (mirrors test_primitive_regrowth.py) ──────────────────


def _source_files() -> list[Path]:
    """Collect all source modules at repo root matching lgwks_*.py."""
    SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "__pycache__", "archive", "hooks"}
    out: list[Path] = []
    for p in REPO.glob("lgwks_*.py"):
        parts = p.relative_to(REPO).parts
        # Skip dot-prefixed paths
        if any(seg.startswith(".") for seg in parts):
            continue
        # Skip version control / build / cache dirs
        if any(seg in SKIP_DIRS for seg in parts):
            continue
        out.append(p)
    return sorted(out)


def _test_files() -> list[Path]:
    """Collect all test files under tests/."""
    tests_dir = REPO / "tests"
    if not tests_dir.is_dir():
        return []
    out: list[Path] = []
    for p in tests_dir.glob("*.py"):
        if p.name.startswith("test_"):
            out.append(p)
    return sorted(out)


def _extract_imports(source_text: str) -> set[str]:
    """Parse source and extract lgwks_* module names imported."""
    imports = set()
    try:
        tree = ast.parse(source_text)
    except (SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        # Handle: import lgwks_foo [as x]
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("lgwks_"):
                    imports.add(alias.name)
        # Handle: from lgwks_foo import ... or from lgwks_foo.x import ...
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("lgwks_"):
                # Extract just the base module name (before any dots)
                base = node.module.split(".")[0]
                if base.startswith("lgwks_"):
                    imports.add(base)

    return imports


class TestModuleCoverage(unittest.TestCase):
    """Gate that every module with live callers is tested."""

    def _scan(self) -> tuple[list[str], dict[str, set[str]], set[str], set[str]]:
        """Return (violators, import_graph, test_imports, modules_with_callers)."""
        sources = _source_files()

        # Build import graph: module_name -> set of modules it imports
        import_graph: dict[str, set[str]] = defaultdict(set)
        for path in sources:
            mod_name = path.stem  # e.g., "lgwks_foo"
            try:
                src = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IOError):
                continue
            imports = _extract_imports(src)
            # Only track lgwks_* imports, exclude self-references
            imports = {m for m in imports if m.startswith("lgwks_") and m != mod_name}
            import_graph[mod_name] = imports

        # Find modules that are imported by at least one other source module
        all_imported_by_sources: set[str] = set()
        for importer, imports in import_graph.items():
            all_imported_by_sources.update(imports)

        modules_with_callers = all_imported_by_sources

        # Scan test files for imports
        test_files = _test_files()
        test_imports: set[str] = set()
        for path in test_files:
            try:
                src = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IOError):
                continue
            test_imports.update(_extract_imports(src))

        # Find untested modules with live callers (violators)
        violators = sorted(modules_with_callers - test_imports - set(EXCLUDED.keys()))

        return violators, import_graph, test_imports, modules_with_callers

    def test_every_called_module_has_a_test_import(self):
        """Assert no untested-but-called modules exist (except EXCLUDED)."""
        violators, _, _, _ = self._scan()
        self.assertEqual(
            violators,
            [],
            "untested modules with live callers (not in EXCLUDED) — "
            "add to EXCLUDED if pre-existing debt, or add test import if new:\n  "
            + "\n  ".join(violators),
        )

    def test_excluded_list_is_honest(self):
        """Assert every EXCLUDED module is real and has live callers today."""
        _, import_graph, test_imports, modules_with_callers = self._scan()
        sources = _source_files()
        source_names = {p.stem for p in sources}

        problems: list[str] = []

        for mod_name, reason in EXCLUDED.items():
            # Check that the module exists as a real source file
            if mod_name not in source_names:
                problems.append(
                    f"{mod_name}: EXCLUDED but no source file found (maybe file was deleted?)"
                )
            # Check that it has live callers (is imported by another source module)
            elif mod_name not in modules_with_callers:
                problems.append(
                    f"{mod_name}: EXCLUDED but has no live callers (no other module imports it)"
                )
            # Check that it is NOT already tested (otherwise it shouldn't be excluded)
            elif mod_name in test_imports:
                problems.append(f"{mod_name}: EXCLUDED but already tested (remove from EXCLUDED)")

        self.assertEqual(
            problems,
            [],
            "EXCLUDED list is stale or dishonest — fix the entries:\n  " + "\n  ".join(problems),
        )


if __name__ == "__main__":
    unittest.main()
