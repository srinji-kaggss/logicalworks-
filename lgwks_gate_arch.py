"""
lgwks_gate_arch — G1 Architecture gate (spec-00).

Reads declarative rules from arch-rules.json and applies them as checks over Python
source files. Each rule's klass (HARD|ADVISORY) is declared in data — never decided at
runtime. This closes the gate-weakening backdoor.

HARD rules (forbidden-import) block ship. ADVISORY rules (global mutable state, silent
except) score and report without blocking.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from lgwks_verify import Klass, Outcome, Verdict


class RuleVerifier:
    """One verifier per rule in arch-rules.json — klass is read from data, not chosen."""
    def __init__(self, rule: dict[str, Any]) -> None:
        self.rule = rule
        self.gate_id = rule["id"]
        self.klass = Klass.HARD if rule.get("klass") == "HARD" else Klass.ADVISORY

    def check(self, subject: object, context: object) -> Verdict:
        kind = self.rule.get("kind", "")
        if kind == "forbidden-import":
            verdict = self._check_forbidden_import(subject, context)
        elif kind == "no-global-mutable-state":
            verdict = self._check_no_global_mutable(subject, context)
        elif kind == "ast-pattern":
            verdict = self._check_ast_pattern(subject, context)
        else:
            verdict = Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"unknown rule kind: {kind}",
            )
        return verdict

    def _check_forbidden_import(self, subject: object, context: object) -> Verdict:
        """AST scan: detect forbidden import edges.

        DiD layers:
          1. Static import statements (Import / ImportFrom).
          2. Dynamic imports with literal targets that resolve to a forbidden edge.
        """
        module_path = Path(subject) if isinstance(subject, (str, Path)) else None
        if module_path is None or not module_path.exists():
            ctx = context if isinstance(context, dict) else {}
            fallback = ctx.get("file_path")
            if fallback:
                module_path = Path(fallback)
            else:
                return Verdict(
                    gate_id=self.gate_id,
                    outcome=Outcome.CANNOT_DECIDE,
                    klass=self.klass,
                    diagnosis="subject is not a file path (no file_path in context)",
                )
        module_name = module_path.stem
        from_patterns = self.rule.get("from", [])
        if not any(module_name == f or module_path.name == f or str(module_path).endswith(f"/{f}.py") for f in from_patterns):
            # rule does not apply to this module
            return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)
        forbidden = self.rule.get("must_not_import", [])
        try:
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        except SyntaxError as exc:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"syntax error parsing {module_path}: {exc}",
            )
        violations: list[str] = []

        # Layer 1: static import statements.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for f in forbidden:
                        if alias.name == f or alias.name.startswith(f + "."):
                            violations.append(f"import {alias.name} in {module_path}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for f in forbidden:
                    if mod == f or mod.startswith(f + "."):
                        names = ", ".join(a.name for a in node.names)
                        violations.append(f"from {mod} import {names} in {module_path}")

        # Layer 2: dynamic imports with statically knowable targets only.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            call_name = ""
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "importlib" and func.attr == "import_module":
                    call_name = "importlib.import_module"
                elif func.value.id == "builtins" and func.attr == "__import__":
                    call_name = "builtins.__import__"
            elif isinstance(func, ast.Name) and func.id == "__import__":
                call_name = "__import__"
            if not call_name or not node.args:
                continue
            target = self._literal_import_target(node.args[0])
            if not target:
                continue
            for f in forbidden:
                if target == f or target.startswith(f + "."):
                    violations.append(
                        f"dynamic import via {call_name}('{target}') at line {node.lineno} in {module_path}"
                    )
        if violations:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=self.rule.get("diagnosis_hint", "forbidden import") + "; " + "; ".join(violations),
            )
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)

    @staticmethod
    def _literal_import_target(node: ast.AST) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return ""

    def _check_no_global_mutable(self, subject: object, context: object) -> Verdict:
        """AST scan: detect module-level mutable bindings (ADVISORY)."""
        module_path = Path(subject) if isinstance(subject, (str, Path)) else None
        if module_path is None or not module_path.exists():
            ctx = context if isinstance(context, dict) else {}
            fallback = ctx.get("file_path")
            if fallback:
                module_path = Path(fallback)
            else:
                return Verdict(
                    gate_id=self.gate_id,
                    outcome=Outcome.CANNOT_DECIDE,
                    klass=self.klass,
                    diagnosis="subject is not a file path (no file_path in context)",
                )
        module_name = module_path.stem
        applies = self.rule.get("applies_to", [])
        if not any(module_name == m or module_path.name == m for m in applies):
            return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)
        try:
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        except SyntaxError as exc:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"syntax error parsing {module_path}: {exc}",
            )
        violations: list[str] = []
        allow = set(self.rule.get("allow", []))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        # allow UPPER_CASE constants
                        if name.isupper():
                            continue
                        # skip typing/enum declarations (heuristic: RHS is Call/Name/Attribute)
                        if isinstance(node.value, (ast.Call, ast.Name, ast.Attribute)):
                            # still flag it — ADVISORY means review, not block
                            pass
                        violations.append(f"module-level mutable binding '{name}' at line {node.lineno}")
        if violations:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,  # ADVISORY rule → CANNOT_DECIDE or PASS only
                klass=self.klass,
                diagnosis=self.rule.get("diagnosis_hint", "global mutable state") + "; " + "; ".join(violations),
            )
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)

    def _check_ast_pattern(self, subject: object, context: object) -> Verdict:
        """AST scan: detect silent except blocks."""
        module_path = Path(subject) if isinstance(subject, (str, Path)) else None
        if module_path is None or not module_path.exists():
            ctx = context if isinstance(context, dict) else {}
            fallback = ctx.get("file_path")
            if fallback:
                module_path = Path(fallback)
            else:
                return Verdict(
                    gate_id=self.gate_id,
                    outcome=Outcome.CANNOT_DECIDE,
                    klass=self.klass,
                    diagnosis="subject is not a file path (no file_path in context)",
                )
        module_name = module_path.stem
        applies = self.rule.get("applies_to", [])
        if not any(module_name == m or module_path.name == m for m in applies):
            return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)
        try:
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        except SyntaxError as exc:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"syntax error parsing {module_path}: {exc}",
            )
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                body = node.body
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    violations.append(f"empty except (Pass only) at line {node.lineno}")
                elif len(body) == 1 and isinstance(body[0], ast.Expr):
                    if isinstance(body[0].value, ast.Constant) and body[0].value.value == Ellipsis:
                        violations.append(f"empty except (Ellipsis only) at line {node.lineno}")
        if violations:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=self.rule.get("diagnosis_hint", "silent except") + "; " + "; ".join(violations),
            )
        return Verdict(gate_id=self.gate_id, outcome=Outcome.PASS, klass=self.klass)


def make_arch_verifiers(rules_path: Path | None = None) -> list[RuleVerifier]:
    """Build one verifier per rule in arch-rules.json."""
    if rules_path is None:
        rules_path = Path(__file__).resolve().parent / "docs" / "frontier" / "arch-rules.json"
    if not rules_path.exists():
        # fallback cwd-relative
        fallback = Path.cwd() / "docs" / "frontier" / "arch-rules.json"
        if fallback.exists():
            rules_path = fallback
    if not rules_path.exists():
        raise FileNotFoundError(f"arch-rules.json not found at {rules_path}")
    with open(rules_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rules = data.get("rules", [])
    for i, r in enumerate(rules):
        _validate_rule(r, i)
    return [RuleVerifier(r) for r in rules]


def _validate_rule(rule: dict[str, Any], index: int) -> None:
    required = {"id", "kind", "klass"}
    missing = required - set(rule.keys())
    if missing:
        raise ValueError(f"arch-rules.json rule[{index}] missing required fields: {missing}")
    if rule.get("klass") not in {"HARD", "ADVISORY"}:
        raise ValueError(f"arch-rules.json rule[{index}] invalid klass: {rule.get('klass')!r}")
    known_kinds = {"forbidden-import", "no-global-mutable-state", "ast-pattern"}
    if rule.get("kind") not in known_kinds:
        raise ValueError(f"arch-rules.json rule[{index}] unknown kind: {rule.get('kind')!r}")
