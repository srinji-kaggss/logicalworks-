"""
lgwks_comprehend — the Comprehension Gate (spec-01).

A HARD Verifier that forces an implementing agent to prove understanding of a build
unit before writing code. It reads the authoritative units.json and runs deterministic
coverage / subset / vocabulary checks on the agent's ComprehensionArtifact.

The anti-drift mechanism: Intention × Understanding, machine-checked.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lgwks_verify import Klass, Outcome, Verdict


@dataclass(frozen=True)
class ComprehensionArtifact:
    unit_id: str
    restated_intent: str
    steps: list[dict[str, Any]]          # each step may declare "covers": [...]
    invariants: list[str]
    gates: list[str]
    files_touched: list[str]
    out_of_scope: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ComprehensionArtifact":
        return cls(
            unit_id=d["unit_id"],
            restated_intent=d["restated_intent"],
            steps=list(d.get("steps", [])),
            invariants=list(d.get("invariants", [])),
            gates=list(d.get("gates", [])),
            files_touched=list(d.get("files_touched", [])),
            out_of_scope=list(d.get("out_of_scope", [])),
        )


class ComprehensionVerifier:
    gate_id = "comprehension"
    klass = Klass.HARD

    def __init__(self, units_path: Path | None = None) -> None:
        self._units_path = units_path or Path(__file__).resolve().parent / "docs" / "frontier" / "units.json"
        self._units_path = self._units_path.resolve()
        self._data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            # //why: if the repo is run from a different cwd, resolve against this module's location
            if not self._units_path.exists():
                # fallback: try cwd-relative (the spec ships at docs/frontier/units.json)
                fallback = Path.cwd() / "docs" / "frontier" / "units.json"
                if fallback.exists():
                    self._units_path = fallback
            with open(self._units_path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        return self._data

    def _unit(self, unit_id: str) -> dict[str, Any] | None:
        data = self._load()
        for u in data.get("units", []):
            if u.get("id") == unit_id:
                return u
        return None

    def check(self, subject: object, context: object) -> Verdict:
        """
        subject: ComprehensionArtifact (the agent's plan)
        context: str (unit_id) or dict (raw unit spec)
        """
        artifact = subject if isinstance(subject, ComprehensionArtifact) else ComprehensionArtifact.from_dict(subject)  # type: ignore[arg-type]
        unit_id = artifact.unit_id
        unit = self._unit(unit_id) if isinstance(context, str) else context
        if unit is None:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"unit {unit_id} not found in {self._units_path}",
            )

        # 1. Coverage: every acceptance[] entry must be addressed by ≥1 step's "covers"
        acceptance = list(unit.get("acceptance", []))
        covered: set[int] = set()
        for step in artifact.steps:
            if isinstance(step, dict):
                for c in step.get("covers", []):
                    # deterministic match: try exact string match against acceptance entries
                    for idx, acc in enumerate(acceptance):
                        if c == acc:
                            covered.add(idx)
        uncovered = [acceptance[i] for i in range(len(acceptance)) if i not in covered]
        if uncovered:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"uncovered acceptance criteria: {uncovered}",
            )

        # 2. Write surface: files_touched ⊆ unit.file_targets
        allowed = set(unit.get("file_targets", []))
        extra = [f for f in artifact.files_touched if f not in allowed]
        if extra:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"undeclared files_touched: {extra}",
            )

        # 3. Subset: invariants ⊇ unit.invariants and gates ⊇ unit.gates
        required_invariants = set(unit.get("invariants", []))
        actual_invariants = set(artifact.invariants)
        missing_invariants = required_invariants - actual_invariants
        if missing_invariants:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"missing invariants: {sorted(missing_invariants)}",
            )

        required_gates = set(unit.get("gates", []))
        actual_gates = set(artifact.gates)
        missing_gates = required_gates - actual_gates
        if missing_gates:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"missing gates: {sorted(missing_gates)}",
            )

        # 4. Scope boundary: out_of_scope non-empty AND every entry ∈ out_of_scope_vocab
        vocab = set(self._load().get("out_of_scope_vocab", []))
        if not artifact.out_of_scope:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis="out_of_scope is empty — scope-creep guard requires a non-empty boundary declaration",
            )
        unknown = [s for s in artifact.out_of_scope if s not in vocab]
        if unknown:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"out_of_scope tokens not in controlled vocabulary: {unknown}",
            )

        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.PASS,
            klass=self.klass,
            evidence=[f"unit {unit_id} comprehension checks passed"],
        )


def comprehend_command(args) -> int:
    """CLI: `lgwks comprehend --unit U1 --file plan.json [--json]`"""
    import json as _json
    import lgwks_inline
    unit_id = args.unit
    
    try:
        from pathlib import Path
        raw = Path(args.file).read_text(encoding="utf-8")
        artifact = ComprehensionArtifact.from_dict(_json.loads(raw))
    except Exception as exc:
        print(f"error: failed to resolve plan: {exc}", file=sys.stderr)
        return 1

    verifier = ComprehensionVerifier()
    verdict = verifier.check(artifact, unit_id)
    if getattr(args, "json", False) or getattr(args, "json", None) is None:
        print(_json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False))
        return 0 if verdict.outcome is Outcome.PASS else 1
    # human render
    print(f"[{verdict.outcome.value.upper()}] {verdict.gate_id}")
    if verdict.diagnosis:
        print(f"  diagnosis: {verdict.diagnosis}")
    if verdict.evidence:
        for e in verdict.evidence:
            print(f"  evidence: {e}")
    return 0 if verdict.outcome is Outcome.PASS else 1


def add_parser(sub) -> None:
    p = sub.add_parser("comprehend", help="Comprehension Gate — verify an agent's plan against units.json")
    p.add_argument("--unit", required=True, help="unit id (e.g. U1)")
    p.add_argument("--file", required=True, help="path to the ComprehensionArtifact JSON")
    p.add_argument("--json", action="store_true", help="structured Verdict JSON")
    p.set_defaults(func=comprehend_command)
