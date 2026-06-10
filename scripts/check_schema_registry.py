#!/usr/bin/env python3
"""Registry conformance gate (governance/README.md + docs/schemas/REGISTRY.md rule 4).

Every `lgwks.<domain>.<name>.v<N>` literal in the codebase must have a row in
docs/schemas/REGISTRY.md. Minting without registration is a defect.

Exit 0 = conformant. Exit 1 = unregistered ids (listed). Pure stdlib.
"""
from __future__ import annotations

import re
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "schemas" / "REGISTRY.md"
ID_RE = re.compile(r"lgwks\.[a-z0-9_]+(?:\.[a-z0-9_]+)*\.v[0-9]+")
BRACE_RE = re.compile(r"lgwks\.[a-z0-9_.{},]*\{[a-z0-9_,]+\}[a-z0-9_.{},]*\.v[0-9]+")
# tests/ excluded: fixture ids are not contracts; minting happens in src.
# .claude/ excluded: agent worktrees carry duplicate copies of the tree.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "store", "target", ".lgwks", ".claude", "tests"}
CODE_SUFFIXES = {".py", ".rs", ".sh"}


def expand_braces(pattern: str) -> list[str]:
    groups = re.findall(r"\{([a-z0-9_,]+)\}", pattern)
    template = re.sub(r"\{[a-z0-9_,]+\}", "{}", pattern)
    return [template.format(*combo) for combo in product(*(g.split(",") for g in groups))]


def registry_ids() -> set[str]:
    text = REGISTRY.read_text(encoding="utf-8")
    ids = set(ID_RE.findall(text))
    for braced in BRACE_RE.findall(text):
        ids.update(expand_braces(braced))
    return ids


def code_ids() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in ROOT.rglob("*"):
        if path.suffix not in CODE_SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for schema_id in ID_RE.findall(text):
            found.setdefault(schema_id, []).append(str(path.relative_to(ROOT)))
    return found


def main() -> int:
    registered = registry_ids()
    used = code_ids()
    missing = {sid: files for sid, files in sorted(used.items()) if sid not in registered}
    if not missing:
        print(f"registry conformant: {len(used)} ids in code, all registered ({len(registered)} rows known)")
        return 0
    print(f"UNREGISTERED schema ids ({len(missing)}) — add a row to docs/schemas/REGISTRY.md or fix the literal:")
    for sid, files in missing.items():
        print(f"  {sid}  ← {', '.join(sorted(set(files))[:3])}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
