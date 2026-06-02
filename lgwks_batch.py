"""
lgwks_batch — schema-validated batch execution for real shell commands.

The user lists CLI path + intention in a typed schema. The Machine (Tier-E, non-LLM)
validates each command against its declared intent and risk class. The human gets ONE
preview for the whole batch and approves once — not 9 separate confirmations.

Design:
  • batch spec = typed JSON with cwd + List[{intent, argv, risk, expected_output}]
  • validation = heuristic classifier checks argv matches intent + risk is consistent
  • human preview = table of all commands with validation status + risk summary
  • execution = argv list (no shell), per-command exit code, transcript persisted
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import lgwks_ui as ui
from lgwks_ui import AMBER, CREAM, CREAM_DIM, EMERALD, MUTED, SLATE_DIM

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "batch-runs"
EMBED_DIMS = 128

# ── schema ─────────────────────────────────────────────────────────────────────
BATCH_SCHEMA = "lgwks-batch/1"
RISK_ORDER = {"read": 0, "mutate": 1, "destructive": 2, "unknown": 3}

# Heuristic: known safe commands and their risk classes. The Machine validates declared risk
# against this table; mismatches are flagged.
_KNOWN_COMMANDS: dict[str, str] = {
    "ls": "read", "pwd": "read", "cat": "read", "echo": "read", "head": "read",
    "tail": "read", "grep": "read", "find": "read", "git.status": "read", "git.log": "read",
    "git.diff": "read", "git.branch": "read", "git.show": "read", "git.remote": "read",
    "npm.test": "mutate", "npm.run": "mutate", "npm.install": "mutate",
    "git.add": "mutate", "git.commit": "mutate", "git.push": "mutate", "git.pull": "mutate",
    "git.checkout": "mutate", "git.merge": "mutate", "git.rebase": "mutate",
    "git.reset": "destructive", "git.clean": "destructive", "rm": "destructive",
    "rmdir": "destructive", "mv": "destructive", "cp": "mutate",
}


def _classify_argv(argv: list[str]) -> str:
    """Heuristic risk classification for an argv list."""
    if not argv:
        return "unknown"
    cmd = argv[0]
    # git subcommands: join as git.status for table lookup
    if cmd == "git" and len(argv) > 1:
        key = f"git.{argv[1]}"
    elif cmd in ("npm", "yarn", "pnpm") and len(argv) > 1:
        key = f"{cmd}.{argv[1]}"
    else:
        key = cmd
    # flag analysis: destructive flags outrank base command
    flags = " ".join(argv[1:])
    if any(f in flags for f in ("-rf", "-fr", "--hard", "-d", "-D", "--delete", "-f", "--force")):
        return "destructive"
    return _KNOWN_COMMANDS.get(key, "unknown")


def _intent_match_score(intent: str, argv: list[str]) -> float:
    """Crude heuristic: does the intent text overlap with the argv tokens?"""
    intent_words = set(intent.lower().split())
    argv_words = set(" ".join(argv).lower().split())
    if not intent_words or not argv_words:
        return 0.0
    overlap = len(intent_words & argv_words)
    return round(overlap / max(len(intent_words), 3), 2)


# ── validation ─────────────────────────────────────────────────────────────────

def validate_command(entry: dict, idx: int) -> dict:
    """Validate one batch entry: risk classification, intent match, cwd exists."""
    argv = entry.get("argv", [])
    declared_risk = entry.get("risk", "unknown")
    intent = entry.get("intent", "")
    cwd = entry.get("cwd", ".")
    inferred_risk = _classify_argv(argv)
    intent_score = _intent_match_score(intent, argv)
    risk_mismatch = RISK_ORDER.get(inferred_risk, 99) > RISK_ORDER.get(declared_risk, 99)
    unknown = inferred_risk == "unknown"
    cwd_ok = Path(cwd).expanduser().exists()
    status = "ok"
    if not cwd_ok:
        status = "cwd_missing"
    elif unknown:
        status = "unknown_command"
    elif risk_mismatch:
        status = "risk_mismatch"
    elif intent_score < 0.2:
        status = "intent_weak"
    return {
        "seq": idx + 1,
        "argv": argv,
        "intent": intent,
        "declared_risk": declared_risk,
        "inferred_risk": inferred_risk,
        "intent_score": intent_score,
        "cwd": cwd,
        "cwd_ok": cwd_ok,
        "status": status,
        "needs_review": status != "ok",
    }


def validate_batch(spec: dict) -> dict:
    """Run validation over every command in the batch spec."""
    commands = spec.get("commands", [])
    results = [validate_command(c, i) for i, c in enumerate(commands)]
    ok = sum(1 for r in results if r["status"] == "ok")
    review = [r for r in results if r["needs_review"]]
    max_risk = max((RISK_ORDER.get(r["inferred_risk"], 0) for r in results), default=0)
    approval = "auto_allowed" if ok == len(results) and max_risk <= RISK_ORDER["read"] else (
        "ask" if ok == len(results) else "blocked"
    )
    return {
        "schema": BATCH_SCHEMA,
        "batch_id": spec.get("batch_id", f"batch-{hash(json.dumps(commands, sort_keys=True)) & 0xFFFFFFFF:08x}"),
        "cwd": spec.get("cwd", "."),
        "command_count": len(results),
        "ok_count": ok,
        "review_count": len(review),
        "max_risk": [k for k, v in RISK_ORDER.items() if v == max_risk][0],
        "approval": approval,
        "results": results,
    }


# ── human preview ──────────────────────────────────────────────────────────────

def human_preview(report: dict) -> str:
    on = ui.color_on()
    lines = [""]
    for ln in ui.band("batch", f"{report['command_count']} commands · {report['ok_count']} ok · {report['review_count']} need review", on=on):
        lines.append(ln)
    for r in report["results"]:
        mark = "◆" if r["status"] == "ok" else "▲"
        color = EMERALD if r["status"] == "ok" else AMBER
        risk_label = f"{r['declared_risk']}→{r['inferred_risk']}"
        cmd = " ".join(r["argv"])
        lines.append(ui.spine(
            ui.fg(f"  {mark} ", color, on=on, bold=True)
            + ui.fg(f"{r['seq']:02d} ", CREAM_DIM, on=on)
            + ui.fg(cmd, CREAM, on=on)
            + ui.fg(f"   [{risk_label}]", CREAM_DIM, on=on)
            + (ui.fg(f"   ({r['status']})", AMBER, on=on) if r["needs_review"] else "")
            , on=on))
        if r["needs_review"]:
            lines.append(ui.spine(
                ui.fg(f"      ∵ intent='{r['intent']}' score={r['intent_score']:.2f} cwd={r['cwd']} ok={r['cwd_ok']}", MUTED, on=on)
                , on=on))
    lines.append(ui.spine(on=on))
    if report["approval"] == "blocked":
        lines.append(ui.spine(ui.fg("  ✗ blocked — fix review items before running", ui.RUST, on=on), on=on))
    elif report["approval"] == "ask":
        lines.append(ui.spine(ui.fg("  ▲ ask — all commands known but some carry risk; approve once to run", AMBER, on=on), on=on))
    else:
        lines.append(ui.spine(ui.fg("  ◆ auto — all read-only and known", EMERALD, on=on), on=on))
    return "\n".join(lines)


# ── execution ──────────────────────────────────────────────────────────────────

def _run_one(argv: list[str], cwd: str) -> dict:
    """Run a single command via argv list (no shell)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, timeout=60)
        return {
            "argv": argv,
            "cwd": cwd,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "out": proc.stdout[:2000],
            "err": proc.stderr[:1000],
        }
    except Exception as exc:
        return {"argv": argv, "cwd": cwd, "ok": False, "returncode": -1,
                "out": "", "err": str(exc)}


def execute_batch(report: dict, *, yes: bool = False, force: bool = False, dry_run: bool = False,
                  keep_going: bool = False) -> dict:
    """Execute validated batch. Returns transcript."""
    if report["approval"] == "blocked":
        return {"ok": False, "error_code": "batch_blocked", "error": "validation blocked; fix review items"}
    max_risk = RISK_ORDER.get(report["max_risk"], 0)
    needs_approval = report["approval"] == "ask"
    destructive = max_risk >= RISK_ORDER["destructive"]
    if needs_approval and not yes:
        return {"ok": False, "error_code": "batch_needs_approval", "error": "pass --yes to approve this batch"}
    if destructive and not force:
        return {"ok": False, "error_code": "batch_destructive_needs_force", "error": "destructive batch requires --force"}
    if dry_run:
        return {"ok": True, "dry_run": True, "results": [
            {"argv": r["argv"], "cwd": r["cwd"], "ok": True, "returncode": 0, "out": "(dry-run)", "err": ""}
            for r in report["results"]
        ]}
    results = []
    for r in report["results"]:
        res = _run_one(r["argv"], r["cwd"])
        results.append(res)
        if not res["ok"] and not keep_going:
            break
    return {"ok": all(r["ok"] for r in results), "results": results}


# ── persistence ────────────────────────────────────────────────────────────────

def _sha(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _persist(spec: dict, report: dict, transcript: dict) -> Path:
    batch_id = report["batch_id"]
    run_dir = RUN_ROOT / batch_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "batch-spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "validation-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "transcript.json").write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
    return run_dir


# ── command entry ──────────────────────────────────────────────────────────────

def batch_command(args: argparse.Namespace) -> int:
    # read spec
    spec: dict
    if args.file:
        spec = json.loads(Path(args.file).expanduser().read_text(encoding="utf-8"))
    else:
        spec = json.loads(sys.stdin.read())
    if spec.get("schema") != BATCH_SCHEMA:
        print(json.dumps({"ok": False, "error_code": "schema_mismatch", "expected": BATCH_SCHEMA}))
        return 2

    # validate
    report = validate_batch(spec)
    if getattr(args, "json", False) and not getattr(args, "render", False):
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["approval"] != "blocked" else 2

    # human preview (default)
    print(human_preview(report))
    if report["approval"] == "blocked":
        return 2

    # execute if approved
    transcript = execute_batch(report, yes=getattr(args, "yes", False),
                               force=getattr(args, "force", False),
                               dry_run=getattr(args, "dry_run", False),
                               keep_going=getattr(args, "keep_going", False))
    if not transcript["ok"]:
        print(json.dumps(transcript, indent=2) if getattr(args, "json", False) else transcript.get("error", "failed"))
        return 2

    # persist + summary
    run_dir = _persist(spec, report, transcript)
    ok_count = sum(1 for r in transcript["results"] if r["ok"])
    total = len(transcript["results"])
    print(f"\n  batch {report['batch_id']} · {ok_count}/{total} ok · run_dir: {run_dir}")
    return 0


def add_parser(sub) -> None:
    b = sub.add_parser("batch", help="schema-validated batch execution for shell commands (one approval)")
    b.add_argument("--file", help="path to batch spec JSON; omit to read stdin")
    b.add_argument("--yes", action="store_true", help="non-interactive approve (read-only or known-risk batches)")
    b.add_argument("--force", action="store_true", help="allow destructive batches non-interactively")
    b.add_argument("--dry-run", action="store_true", dest="dry_run", help="validate + preview, run nothing")
    b.add_argument("--keep-going", action="store_true", dest="keep_going", help="continue after a command fails")
    b.add_argument("--json", action="store_true", help="structured validation report + transcript")
    b.add_argument("--render", action="store_true", help="human preview instead of JSON (default)")
    b.set_defaults(func=batch_command)


import sys
