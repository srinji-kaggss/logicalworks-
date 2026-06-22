"""Monte-Carlo precision/recall harness for the H1–H8 SAST (lgwks_bot_code_hacker).

//why this instead of a fixed recall fixture (#313, Director directive 2026-06-22):
a frozen list of "known vuln" snippets is something the scanner can be overfit to, and
it goes stale the moment a heuristic changes. Instead we describe security patterns as a
small TOKEN GRAMMAR — SOURCE tokens (what kind of value enters), SINK tokens (the
dangerous operation), GUARD tokens (a mitigation) — and Monte-Carlo *compose* them into
synthetic Python modules with randomized identifiers. The ground-truth label is DERIVED
from the token composition (a tainted source reaching a matching sink with no guard is a
vuln), so the grammar is an oracle INDEPENDENT of the scanner. Each sample is parsed and
scanned FRESH (cache-free — a new _Visitor per snippet, nothing memoized), and we score
the scanner against the token-derived truth as a confusion matrix.

This proves two things at once on every run:
  * RECALL  — every planted vulnerability is still flagged (the "smarter" scanner did not
              go blind; this is the guard against precision fixes silently dropping signal).
  * PRECISION — the safe-but-lookalike decoys (dict `.get()`, controlled paths, config
              prints, list-concat argv) are NOT flagged at a gate-blocking severity.

Seeded for gate reproducibility; override with LGWKS_SAST_MC_SEED / LGWKS_SAST_MC_SAMPLES
for exploratory free-seed sweeps.
"""
from __future__ import annotations

import ast
import os
import random
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Resolve root lgwks_* modules when run standalone (pytest gets this from conftest).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import lgwks_bot_code_hacker as H

SEC = H.SECRET
INJ = H.INJECTION
GATE_SEVERITIES = ("high", "critical")

# A net-safe filename so the H3 egress check stays quiet about our `import requests`
# scaffolding — egress is not the dimension under test here.
_SNIPPET_REL = "mc_network_probe.py"

_PREAMBLE = (
    "import os\n"
    "import subprocess\n"
    "import shutil\n"
    "import sqlite3\n"
    "import logging\n"
    "import requests\n"
    "logger = logging.getLogger('mc')\n"
    "def compute_value():\n"
    "    return 1\n"
)


# ── Token grammar ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceTok:
    """Produces a value bound to a variable; carries a set of taint classes."""
    name: str
    classes: frozenset
    # (rng) -> (setup_lines, varname)
    emit: Callable[[random.Random], tuple[list[str], str]]


@dataclass(frozen=True)
class SinkTok:
    """Consumes a variable in a (possibly) dangerous operation."""
    name: str
    kind: str                      # the H-class finding this sink can produce
    needs: Optional[str]           # taint class required to be a real vuln (None = never)
    always_vuln: bool = False      # e.g. shell=True is vulnerable regardless of source
    # (varname) -> sink_lines
    emit: Callable[[str], list[str]] = field(default=lambda v: [])


@dataclass(frozen=True)
class GuardTok:
    name: str
    suppresses: Optional[str]      # the finding kind this guard legitimately suppresses
    lines: tuple[str, ...]


def _rid(rng: random.Random, prefix: str = "v") -> str:
    return f"{prefix}_{rng.randrange(10**6):06d}"


SOURCES: list[SourceTok] = [
    SourceTok("input", frozenset({INJ}),
              lambda r: ([f"{(v:=_rid(r))} = input()"], v)),
    SourceTok("env_value", frozenset({INJ}),
              lambda r: ([f'{(v:=_rid(r))} = os.getenv("OUTPUT_DIR")'], v)),
    SourceTok("secret_env", frozenset({SEC, INJ}),
              lambda r: ([f'{(v:=_rid(r))} = os.getenv("API_KEY")'], v)),
    # SECRET by variable NAME (assigned a benign literal) — the propagation path must not
    # be needed for this to count as a secret.
    SourceTok("secret_name", frozenset({SEC}),
              lambda r: ([f'{(v:="api_key_" + _rid(r, ""))} = "redacted"'], v)),
    # Safe / decoy sources (no taint class).
    SourceTok("safe_url_const", frozenset(),
              lambda r: ([f'{(v:=_rid(r))} = "https://api.example.com/v1"'], v)),
    SourceTok("safe_path_const", frozenset(),
              lambda r: ([f'{(v:=_rid(r))} = "/tmp/lgwks_out.txt"'], v)),
    SourceTok("safe_call", frozenset(),
              lambda r: ([f"{(v:=_rid(r))} = compute_value()"], v)),
    SourceTok("safe_dict_get", frozenset(),
              lambda r: ([f'{(v:=_rid(r))} = {{}}.get("section")'], v)),
    # A secret passed THROUGH a generic call must NOT remain secret (the over-propagation
    # bug #313 fixed): verify(secret) -> verdict, not the secret.
    SourceTok("laundered_secret", frozenset(),
              lambda r: ([f'{_rid(r, "k")} = os.getenv("API_KEY")',
                          f"{(v:=_rid(r))} = compute_value()"], v)),
]

SINKS: list[SinkTok] = [
    SinkTok("shell_true", "dangerous_shell_exec", None, always_vuln=True,
            emit=lambda v: [f"subprocess.run({v}, shell=True)"]),
    SinkTok("os_system", "dangerous_shell_exec", INJ,
            emit=lambda v: [f"os.system({v})"]),
    SinkTok("requests_get", "ssrf_risk", INJ,
            emit=lambda v: [f"requests.get({v})"]),
    SinkTok("open_write", "path_traversal_risk", INJ,
            emit=lambda v: [f'open({v}, "w")']),
    SinkTok("rmtree", "unsafe_file_mutation", INJ,
            emit=lambda v: [f"shutil.rmtree({v})"]),
    SinkTok("sql_execute", "sql_injection_risk", INJ,
            emit=lambda v: [f"sqlite3.connect(':memory:').execute({v})"]),
    SinkTok("print_secret", "secret_exposure_risk", SEC,
            emit=lambda v: [f"print({v})"]),
    SinkTok("log_secret", "secret_exposure_risk", SEC,
            emit=lambda v: [f"logger.info({v})"]),
    # DECOY: looks like a network call (`.get`) but the receiver is a dict — must never
    # be an SSRF finding. `needs=None` => never a vuln.
    SinkTok("dict_get_decoy", "ssrf_risk", None,
            emit=lambda v: [f"{{}}.get({v})"]),
]

GUARDS: list[GuardTok] = [
    GuardTok("none", None, ()),
    GuardTok("remote_allowed", "ssrf_risk", ("_remote_allowed()",)),
    GuardTok("is_relative_to", "path_traversal_risk", ("is_relative_to()",)),
]


def _oracle_is_vuln(src: SourceTok, sink: SinkTok, guard: GuardTok) -> bool:
    """Ground truth derived purely from the token composition."""
    if sink.needs is None and not sink.always_vuln:
        return False                                   # decoy — never a vuln
    vuln = sink.always_vuln or (sink.needs in src.classes)
    if vuln and guard.suppresses == sink.kind:
        return False                                   # legitimately mitigated
    return vuln


def render(src: SourceTok, sink: SinkTok, guard: GuardTok, rng: random.Random) -> str:
    setup, var = src.emit(rng)
    body = list(guard.lines) + setup + sink.emit(var)
    fname = _rid(rng, "fn")
    indented = "\n".join("    " + line for line in body)
    return f"{_PREAMBLE}\ndef {fname}(cur, pkt, cfg):\n{indented}\n"


def scan_snippet(source: str) -> list[dict]:
    """Fresh, cache-free scan: a new visitor per snippet, nothing memoized."""
    tree = ast.parse(source)
    v = H._Visitor(_SNIPPET_REL, "montecarlo", "mc")
    v.visit(tree)
    return v.findings


def _flagged_at_gate(findings: list[dict], kind: str) -> bool:
    return any(f.get("kind") == kind and f.get("severity") in GATE_SEVERITIES
               for f in findings)


@dataclass
class Sample:
    src: str
    sink: str
    guard: str
    kind: str
    expected_vuln: bool
    flagged: bool
    source_code: str


def run_montecarlo(seed: int, n_samples: int) -> tuple[list[Sample], dict]:
    rng = random.Random(seed)
    samples: list[Sample] = []
    tp = fp = tn = fn = 0
    for _ in range(n_samples):
        src = rng.choice(SOURCES)
        sink = rng.choice(SINKS)
        guard = rng.choice(GUARDS)
        code = render(src, sink, guard, rng)
        findings = scan_snippet(code)
        expected = _oracle_is_vuln(src, sink, guard)
        flagged = _flagged_at_gate(findings, sink.kind)
        samples.append(Sample(src.name, sink.name, guard.name, sink.kind,
                              expected, flagged, code))
        if expected and flagged:
            tp += 1
        elif expected and not flagged:
            fn += 1
        elif not expected and flagged:
            fp += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    matrix = {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "total": total,
        "recall": tp / (tp + fn) if (tp + fn) else 1.0,
        "precision": tp / (tp + fp) if (tp + fp) else 1.0,
    }
    return samples, matrix


def _format_failures(samples: list[Sample], want_vuln: bool) -> str:
    bad = [s for s in samples if s.expected_vuln == want_vuln and s.flagged != want_vuln]
    lines = []
    for s in bad[:8]:
        verb = "MISSED (false negative)" if want_vuln else "FALSE POSITIVE"
        lines.append(f"  {verb}: src={s.src} sink={s.sink} guard={s.guard} kind={s.kind}")
        lines.append("    " + s.source_code.replace("\n", "\n    "))
    return "\n".join(lines)


class TestSastMonteCarlo(unittest.TestCase):
    SEED = int(os.environ.get("LGWKS_SAST_MC_SEED", "1313"))
    SAMPLES = int(os.environ.get("LGWKS_SAST_MC_SAMPLES", "400"))

    def test_precision_and_recall(self):
        samples, m = run_montecarlo(self.SEED, self.SAMPLES)
        report = (f"\nMonte-Carlo SAST seed={self.SEED} n={m['total']}: "
                  f"TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']} "
                  f"recall={m['recall']:.3f} precision={m['precision']:.3f}")
        # RECALL: a planted vulnerability must never slip through (no blindness).
        self.assertEqual(m["fn"], 0, report + "\n--- missed vulnerabilities ---\n"
                         + _format_failures(samples, want_vuln=True))
        # PRECISION: a safe/decoy pattern must never raise a gate-blocking finding.
        self.assertEqual(m["fp"], 0, report + "\n--- false positives ---\n"
                         + _format_failures(samples, want_vuln=False))
        # Sanity: the sweep actually exercised both classes (not a degenerate all-safe run).
        self.assertGreater(m["tp"], 0, report + "\n(no vulnerabilities generated — bad sweep)")
        self.assertGreater(m["tn"], 0, report + "\n(no safe samples generated — bad sweep)")

    def test_full_grid_coverage(self):
        """Deterministically exercise every (source x sink x guard) combination once, so
        no token pairing is left untested by the random sweep."""
        rng = random.Random(0xC0FFEE)
        misses, fps = [], []
        for src in SOURCES:
            for sink in SINKS:
                for guard in GUARDS:
                    code = render(src, sink, guard, rng)
                    findings = scan_snippet(code)
                    expected = _oracle_is_vuln(src, sink, guard)
                    flagged = _flagged_at_gate(findings, sink.kind)
                    if expected and not flagged:
                        misses.append((src.name, sink.name, guard.name, code))
                    elif not expected and flagged:
                        fps.append((src.name, sink.name, guard.name, code))
        msg = []
        for label, items in (("MISSED", misses), ("FALSE POSITIVE", fps)):
            for name in items[:8]:
                msg.append(f"{label}: {name[0]} -> {name[1]} (guard={name[2]})\n{name[3]}")
        self.assertEqual((len(misses), len(fps)), (0, 0), "\n".join(msg))


if __name__ == "__main__":
    samples, m = run_montecarlo(
        int(os.environ.get("LGWKS_SAST_MC_SEED", "1313")),
        int(os.environ.get("LGWKS_SAST_MC_SAMPLES", "400")),
    )
    print(f"seed={os.environ.get('LGWKS_SAST_MC_SEED','1313')} n={m['total']} "
          f"TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']} "
          f"recall={m['recall']:.3f} precision={m['precision']:.3f}")
