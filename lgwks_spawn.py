"""
lgwks_spawn — AI-AI handoff packet assembler (#9 harness layer).

Produces a single JSON artifact (`spawn.json`) that bundles everything the next
AI needs to continue work deterministically: AUP verdict, context pack,
capability manifest, intent trail, and state matrix. No prose, no guessing.

The packet is the boundary between one AI session and the next. The emitting AI
writes it; the receiving AI reads it. Both use the same schema so there is no
drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _git_sha(cwd: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _load_aup_verdict(run_dir: Path) -> dict[str, Any] | None:
    """Read the latest AUP verdict from the run directory if it exists."""
    p = run_dir / "aup.verdict.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def _load_do_run(run_dir: Path) -> dict[str, Any] | None:
    """Read the DoRun artifact if present."""
    p = run_dir / "do.run.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def _load_context_meta(run_dir: Path) -> dict[str, Any]:
    """Derive context pack metadata without re-reading full files."""
    cdir = run_dir / "context"
    meta: dict[str, Any] = {"path": str(cdir), "exists": cdir.exists()}
    if not cdir.exists():
        return meta

    # Tiers: count files per tier
    for tier in ("raw", "full", "compact", "ultra"):
        d = cdir / tier
        meta[f"{tier}_count"] = len(list(d.glob("*.json"))) if d.exists() else 0

    # State matrix
    matrix = cdir / "state_matrix.json"
    meta["has_state_matrix"] = matrix.exists()

    # Context md
    ctx = cdir / "CONTEXT.md"
    meta["has_context_md"] = ctx.exists()
    if ctx.exists():
        meta["context_md_lines"] = len(ctx.read_text().splitlines())

    # Round ledger
    ledger = run_dir / "rounds.ledger.jsonl"
    meta["has_ledger"] = ledger.exists()
    if ledger.exists():
        meta["ledger_lines"] = len(ledger.read_text().splitlines())

    return meta


def _load_capabilities() -> dict[str, Any]:
    """Pull live capability matrix from the manifest."""
    import lgwks_manifest
    import lgwks_home
    verbs = lgwks_manifest._collect_verbs()
    return {
        "verb_count": len(verbs),
        "verbs": verbs,
        "domains": lgwks_home._DOMAINS,
    }


def assemble_packet(run_dir: Path) -> dict[str, Any]:
    """Build the spawn handoff packet from a run directory."""
    run_dir = Path(run_dir)
    aup = _load_aup_verdict(run_dir)
    do_run = _load_do_run(run_dir)
    ctx_meta = _load_context_meta(run_dir)
    caps = _load_capabilities()

    packet = {
        "schema": "lgwks.spawn.v1",
        "timestamp": time.time(),
        "run_dir": str(run_dir.resolve()),
        "aup": aup or {"verdict": "unknown", "note": "no aup.verdict.json found"},
        "do_run": do_run or {"note": "no do.run.json found"},
        "context": ctx_meta,
        "capabilities": caps,
        "provenance": {
            "git_sha": _git_sha(run_dir),
            "hostname": socket.gethostname(),
            "version": "lgwks.spawn.v1",
        },
    }
    return packet


def write_packet(run_dir: Path) -> Path | None:
    """Write spawn.json to the run directory. Returns path or None if run_dir invalid."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        return None
    packet = assemble_packet(run_dir)
    out = run_dir / "spawn.json"
    out.write_text(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("spawn", help="assemble AI-AI handoff packet from a run directory")
    p.add_argument("--run-dir", required=True, help="path to a run directory")
    p.add_argument("--json", action="store_true", help="emit full packet JSON (default: summary)")
    p.set_defaults(func=_spawn_command)


def _spawn_command(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"error: not a directory: {run_dir}", file=sys.stderr)
        return 2

    out = write_packet(run_dir)
    if out is None:
        print("error: failed to write packet", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        packet = assemble_packet(run_dir)
        print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        packet = assemble_packet(run_dir)
        print(f"  spawn packet: {out}")
        print(f"    schema:     {packet['schema']}")
        print(f"    aup:        {packet['aup'].get('verdict', 'unknown')}")
        print(f"    context:    {packet['context'].get('has_context_md', False)}")
        print(f"    do_run:     {bool(packet['do_run'].get('phases'))}")
        print(f"    verbs:      {packet['capabilities']['verb_count']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: lgwks_spawn.py <run_dir>", file=sys.stderr)
        return 2
    out = write_packet(Path(args[0]))
    if out is None:
        print("error: failed to write packet", file=sys.stderr)
        return 1
    print(f"spawn packet written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
