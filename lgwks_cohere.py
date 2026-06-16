"""
lgwks_cohere — Coherence Engine pipeline (spec-00).

Composes gates in canonical order G0 → G1 → G3 → G2:
  G0 compiler/test   (HARD)
  G1 architecture    (HARD per arch-rules.json)
  G3 framework-reality (HARD)
  G2 idiom           (ADVISORY)

HARD non-PASS blocks ship with diagnosis for retry.
ADVISORY accumulates into a report.
Every Verdict is appended to the cognition-log.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from lgwks_verify import GateRegistry, Klass, Outcome, Verdict, run_pipeline


class G0Verifier:
    """Compiler / type / test gate. Shells out to cargo build + cargo test."""
    gate_id = "compiler"
    klass = Klass.HARD

    def __init__(self, crate_dir: str | Path | None = None) -> None:
        self.crate_dir = Path(crate_dir) if crate_dir else None

    def check(self, subject: object, context: object) -> Verdict:
        ctx = context if isinstance(context, dict) else {}
        crate_dir = ctx.get("crate_dir")
        if crate_dir:
            self.crate_dir = Path(crate_dir)
        if not self.crate_dir or not self.crate_dir.exists():
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis="no --crate-dir provided for G0; cannot compile without project context",
            )
        # cargo build
        build = subprocess.run(
            ["cargo", "build"],
            cwd=self.crate_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if build.returncode != 0:
            # surface the first rustc error line as diagnosis
            err = build.stderr or build.stdout or ""
            first_err = err.strip().splitlines()[0] if err.strip() else "cargo build failed"
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"G0 compile error: {first_err}",
            )
        # cargo test
        test = subprocess.run(
            ["cargo", "test"],
            cwd=self.crate_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if test.returncode != 0:
            err = test.stderr or test.stdout or ""
            first_err = err.strip().splitlines()[0] if err.strip() else "cargo test failed"
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.FAIL,
                klass=self.klass,
                diagnosis=f"G0 test failure: {first_err}",
            )
        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.PASS,
            klass=self.klass,
            evidence=["cargo build and cargo test passed"],
        )


def _log_verdicts(verdicts: list[Verdict]) -> None:
    """Append every Verdict to the cognition-log for audit and replay."""
    try:
        import lgwks_cognition
        log = lgwks_cognition.CognitionLog("coherence")
        for v in verdicts:
            log.append("gate", v.to_dict())
    except Exception:
        pass  # //why: fail-soft on cognition-log unavailability; pipeline still returns verdicts


def cohere(subject: str | Path, crate_dir: Path, rules_path: Path | None = None) -> tuple[bool, list[Verdict], str]:
    """
    Run the coherence pipeline. Returns (shippable, verdicts, report).
    subject may be a code string (for in-memory candidates) or a Path (existing file).
    """
    from lgwks_gate_arch import make_arch_verifiers
    from lgwks_gate_framework import G3Verifier
    from lgwks_gate_idiom import IdiomVerifier

    file_path: Path | None = subject if isinstance(subject, Path) else None
    context: dict[str, Any] = {"crate_dir": str(crate_dir)}
    if file_path:
        context["file_path"] = str(file_path)

    reg = GateRegistry()
    reg.hard.append(G0Verifier(crate_dir=crate_dir))
    for v in make_arch_verifiers(rules_path):
        reg.hard.append(v)
    reg.hard.append(G3Verifier(crate_dir=crate_dir))
    reg.advisory.append(IdiomVerifier(corpus_dir=crate_dir))

    ok, verdicts = run_pipeline(subject, context, reg)
    _log_verdicts(verdicts)

    # Build report
    lines: list[str] = []
    lines.append(f"Coherence pipeline: {'PASS' if ok else 'BLOCKED'}")
    for v in verdicts:
        lines.append(f"  {v.gate_id} [{v.klass.value}] = {v.outcome.value}")
        if v.diagnosis:
            lines.append(f"    diagnosis: {v.diagnosis}")
        if v.score is not None:
            lines.append(f"    score: {v.score}")
        if v.evidence:
            for e in v.evidence:
                lines.append(f"    evidence: {e}")
    report = "\n".join(lines)
    return ok, verdicts, report


def cohere_command(args) -> int:
    """CLI: `lgwks cohere --file candidate.rs --crate-dir /path/to/crate [--json]`"""
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 1

    crate_dir = Path(args.crate_dir)
    if not crate_dir.exists():
        print(f"error: crate directory not found: {crate_dir}", file=sys.stderr)
        return 1
    # Pass the subject Path to cohere.
    ok, verdicts, report = cohere(file_path, crate_dir)
    if getattr(args, "json", False):
        print(json.dumps({
            "shippable": ok,
            "verdicts": [v.to_dict() for v in verdicts],
            "report": report,
        }, indent=2, ensure_ascii=False))
        return 0 if ok else 1
    print(report)
    return 0 if ok else 1


def add_parser(sub) -> None:
    p = sub.add_parser("cohere", help="Coherence Engine pipeline G0→G1→G3→G2")
    p.add_argument("--file", required=True, help="candidate source file to verify")
    p.add_argument("--crate-dir", required=True, help="Rust crate directory for G0/G3")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cohere_command)
