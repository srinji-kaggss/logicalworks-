"""
lgwks_gate_framework — G3 Framework-Reality gate (spec-00).

Verifies that external symbols referenced in candidate code exist in the *installed*
dependency surface, catching version-skew hallucinations. Ground truth = cargo metadata +
rustdoc JSON. Missing rustdoc JSON → CANNOT_DECIDE (never silently PASS).

Bare symbol-existence on compiled Rust is G0's job (rustc errors E0433/E0425) —
G3 only adds version-skew and pre-generation grounding.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from lgwks_verify import Klass, Outcome, Verdict

# false-PASS surface: regex-based Rust path extraction misses macro-generated paths,
# dynamically constructed strings used as paths, and type-inference-driven resolution.
# //why: declared explicitly per spec-01 soundness obligation. If rustdoc JSON is present,
# the symbol set is complete for the compiled surface; the extraction gap is in the
# candidate parser, which cannot be bounded complete → we state it here.
_FALSE_PASS_SURFACE = (
    "regex-based candidate parser misses macro-generated paths, "
    "dynamic string paths, and inferred-qualified paths"
)


class G3Verifier:
    gate_id = "framework-reality"
    klass = Klass.HARD

    def __init__(self, crate_dir: str | Path | None = None) -> None:
        self.crate_dir = Path(crate_dir) if crate_dir else None

    def _cargo_metadata(self) -> dict[str, Any] | None:
        """Run cargo metadata to discover the crate and its dependencies."""
        if not self.crate_dir:
            return None
        try:
            p = subprocess.run(
                ["cargo", "metadata", "--format-version", "1", "--no-deps"],
                cwd=self.crate_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if p.returncode == 0:
                return json.loads(p.stdout)
        except Exception:
            pass
        return None

    def _find_rustdoc_json(self) -> Path | None:
        """Search for existing rustdoc JSON in target/doc."""
        if not self.crate_dir:
            return None
        candidates = list(self.crate_dir.glob("target/doc/*.json"))
        # prefer the crate's own rustdoc JSON
        for c in candidates:
            return c
        return None

    def _generate_rustdoc_json(self) -> Path | None:
        """Try to generate rustdoc JSON (requires nightly). Returns path if produced."""
        if not self.crate_dir:
            return None
        try:
            p = subprocess.run(
                [
                    "cargo", "rustdoc", "--",
                    "-Zunstable-options", "--output-format", "json",
                ],
                cwd=self.crate_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if p.returncode == 0:
                found = self._find_rustdoc_json()
                if found:
                    return found
        except Exception:
            pass
        return None

    def _installed_symbols(self) -> tuple[set[str], list[str]] | None:
        """
        Build the installed-symbol set from rustdoc JSON.
        Returns (symbols, dependencies) or None if rustdoc JSON is unavailable.
        """
        rustdoc = self._find_rustdoc_json() or self._generate_rustdoc_json()
        if rustdoc is None or not rustdoc.exists():
            return None
        symbols: set[str] = set()
        try:
            with open(rustdoc, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return None
        # rustdoc JSON v2 shape: index[id].name + paths[id] gives the full path
        index = data.get("index", {})
        paths = data.get("paths", {})
        for idx, item in index.items():
            name = item.get("name", "")
            path_parts = paths.get(idx, [])
            if name and path_parts:
                # record both the full path and the leaf name
                full_path = "::".join(str(p) for p in path_parts)
                symbols.add(full_path)
                symbols.add(f"{full_path}::{name}")
                symbols.add(name)
        return symbols, []

    def _extract_references(self, code: str) -> set[str]:
        """
        Extract external crate references from candidate Rust code.
        //why: regex-based — see _FALSE_PASS_SURFACE above.
        """
        refs: set[str] = set()
        # use some_crate::path::Item;
        for m in re.finditer(r"\buse\s+([a-zA-Z_][a-zA-Z0-9_]*(?:::[a-zA-Z_][a-zA-Z0-9_]*)*)\s*;", code):
            refs.add(m.group(1))
        # use some_crate::path::{Item1, Item2};
        for m in re.finditer(r"\buse\s+([a-zA-Z_][a-zA-Z0-9_]*(?:::[a-zA-Z_][a-zA-Z0-9_]*)*)::\{([^}]+)\}", code):
            prefix = m.group(1)
            for item in m.group(2).split(","):
                refs.add(f"{prefix}::{item.strip()}")
        # Qualified paths in expressions: some_crate::path::item(...)
        for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:::[a-zA-Z_][a-zA-Z0-9_]*)+)\s*[(<]", code):
            refs.add(m.group(1))
        # Also catch bare path references: some_crate::path::Item
        for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:::[a-zA-Z_][a-zA-Z0-9_]*)+)\b", code):
            path = m.group(1)
            if "::" in path:
                refs.add(path)
        return refs

    def _grounding_context(self, symbols: set[str]) -> list[str]:
        """Pre-generation grounding: emit the installed symbol surface."""
        return sorted(symbols)[:500]  # cap for token economy

    def check(self, subject: object, context: object) -> Verdict:
        """
        subject: candidate Rust code (str)
        context: dict with optional 'crate_dir' (str|Path); if absent and self.crate_dir unset → CANNOT_DECIDE
        """
        code = subject if isinstance(subject, str) else str(subject)
        ctx = context if isinstance(context, dict) else {}
        crate_dir = ctx.get("crate_dir")
        if crate_dir:
            self.crate_dir = Path(crate_dir)

        if not self.crate_dir or not self.crate_dir.exists():
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis="no --crate-dir provided; cohere abstains with CANNOT_DECIDE, never guesses",
            )

        result = self._installed_symbols()
        if result is None:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis="rustdoc JSON not available; install nightly toolchain or run `cargo rustdoc -- -Zunstable-options --output-format json`",
            )

        symbols, _deps = result
        refs = self._extract_references(code)
        # Filter to external references (first segment is not std/core/crate)
        # Heuristic: if the first segment matches a known dependency or is not 'std'/'core'/'alloc'
        external = {r for r in refs if not r.startswith(("std::", "core::", "alloc::", "crate::"))}
        missing = []
        for r in external:
            # check exact match or prefix match (module path)
            if r not in symbols:
                # try prefix match for module-level items
                parts = r.split("::")
                found_prefix = False
                for i in range(len(parts), 0, -1):
                    prefix = "::".join(parts[:i])
                    if prefix in symbols:
                        found_prefix = True
                        break
                if not found_prefix:
                    missing.append(r)

        if missing:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"version-skew: referenced symbols not in installed surface: {missing}. false-PASS surface: {_FALSE_PASS_SURFACE}",
            )

        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.PASS,
            klass=self.klass,
            evidence=self._grounding_context(symbols),
        )
