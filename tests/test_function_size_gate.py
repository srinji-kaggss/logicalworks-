"""Function-size ratchet gate (R6.4) — no new god-functions; existing ones only shrink.

The Pristine Program decomposes oversized functions "behind existing seams when
touched" (M6). This gate makes that durable: a source-scan that fails if any
`lgwks_*.py` function exceeds the line threshold and is NOT in the allow-list, OR
if an allow-listed function GROWS beyond its recorded ceiling. So new bloat fails
immediately, and a tracked god-function can only get smaller (you lower its ceiling
or remove it from the list) — never silently larger.

No silent self-allow-listing (R4.7): every allow-list entry carries its ceiling
(today's size) and is tracked for decomposition in #351. R6.1 already shrank
`build_run` 469→31, so it is intentionally NOT in the list — if it regrows past
the threshold the gate catches it.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
THRESHOLD = 200  # lines (inclusive def→end) above which a function needs a reason

# (module, function) -> ceiling. Ceiling = the function's size when listed; the
# gate fails if the live size exceeds it (growth) or if the entry is stale (the
# function shrank ≤ THRESHOLD or vanished). All tracked for decomposition in #351.
ALLOWED: dict[tuple[str, str], int] = {
    ("lgwks_jarvis.py", "crawl_command"): 418,        # Pristine R6.2 — jarvis brain-graph sink
    ("lgwks_research.py", "run_auto"): 213,           # R6.3 done — round body extracted (was 385); residual setup+report
    ("lgwks_research.py", "_run_round"): 212,         # R6.3 — extracted round body w/ explicit _RoundState; 7 cohesive step-seams remain
    ("lgwks_substrate_run.py", "_ingest_docs"): 278,  # R6.1 residue — per-doc ingest loop
    ("lgwks_substrate_crawl.py", "_crawl_site"): 321,
    ("lgwks_home.py", "_browser_entryway"): 282,
    ("lgwks_bot_stress.py", "run"): 253,
    ("lgwks_review.py", "review_command"): 241,
    ("lgwks_pipeline.py", "run_pipeline"): 237,
    ("lgwks_bot_optimizer.py", "run"): 230,
    ("lgwks_graph.py", "extract_from_repo"): 225,
}

SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "__pycache__", "archive"}


def _source_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO.glob("lgwks_*.py"):
        parts = p.relative_to(REPO).parts
        if any(seg.startswith(".") or seg in SKIP_DIRS for seg in parts):
            continue
        out.append(p)
    return sorted(out)


def _functions(path: Path) -> list[tuple[str, int]]:
    """(function_name, line_count) for every top-level-or-nested def in the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None)
            if end is not None:
                out.append((node.name, end - node.lineno + 1))
    return out


class TestFunctionSizeGate(unittest.TestCase):
    def _scan(self) -> dict[tuple[str, str], int]:
        """All functions over THRESHOLD: (file, func) -> live line count."""
        big: dict[tuple[str, str], int] = {}
        for path in _source_files():
            for name, length in _functions(path):
                if length > THRESHOLD:
                    # Last def of a given (file,name) wins; names are unique per file in practice.
                    big[(path.name, name)] = max(length, big.get((path.name, name), 0))
        return big

    def test_no_unlisted_or_grown_god_functions(self):
        big = self._scan()
        violations: list[str] = []
        for key, length in sorted(big.items()):
            ceiling = ALLOWED.get(key)
            if ceiling is None:
                violations.append(
                    f"{key[0]}:{key[1]} is {length} lines (> {THRESHOLD}) and not allow-listed "
                    f"— decompose it behind a seam, or add it to ALLOWED with a #351 reason"
                )
            elif length > ceiling:
                violations.append(
                    f"{key[0]}:{key[1]} grew to {length} lines (ceiling {ceiling}) "
                    f"— a tracked god-function must only shrink"
                )
        self.assertEqual(violations, [], "function-size ratchet broken:\n  " + "\n  ".join(violations))

    def test_allow_list_is_honest(self):
        """No stale allow-list entry: each must still exist and exceed THRESHOLD."""
        big = self._scan()
        problems: list[str] = []
        for key, ceiling in ALLOWED.items():
            if key not in big:
                problems.append(
                    f"{key[0]}:{key[1]} is allow-listed (ceiling {ceiling}) but is now "
                    f"≤ {THRESHOLD} lines or gone — remove it from ALLOWED (it was decomposed)"
                )
        self.assertEqual(problems, [], "stale allow-list entries:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    unittest.main()
