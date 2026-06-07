"""lgwks_axiom - CLI harness over the standalone Axiom byte framework.

This module is intentionally above `axiom/`: it may import the byte framework,
git, subprocess, and CLI concerns. The byte framework must never import this
module. The shape mirrors the JVM/Wasm boundary: capture real emissions, encode
them as verified artifacts, then let higher layers render or compare them.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from axiom.capsule import Capsule
from axiom.cid import require_cid
from axiom.fabric import Fabric

SCHEMA = "lgwks.axiom.harness.v0"
RUN_ROOT = Path(".lgwks") / "axiom" / "runs"
HARNESS_KEY = b"lgwks-axiom-harness-v0"
HARNESS_GRANTS = frozenset({"observe", "diff", "test", "narrate"})


@dataclass(frozen=True)
class CapturedFact:
    kind: str
    label: str
    value: dict[str, Any]


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _run_id(repo: Path, intent: str) -> str:
    seed = f"{repo.resolve()}|{intent}|{time.time_ns()}"
    return f"axiom-{_sha(seed, 20)}"


def _git(repo: Path, *args: str, timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def _sign(capsule: Capsule, key: bytes = HARNESS_KEY) -> Capsule:
    unsigned = Capsule(
        capsule.kind,
        capsule.claim,
        capsule.on,
        capsule.needs,
        capsule.grants,
        capsule.params,
        capsule.is_hole,
        capsule.is_genesis,
        b"",
        capsule.by,
    )
    sig = hmac.new(key, unsigned.to_bytes(), hashlib.blake2b).digest()
    return Capsule(
        capsule.kind,
        capsule.claim,
        capsule.on,
        capsule.needs,
        capsule.grants,
        capsule.params,
        capsule.is_hole,
        capsule.is_genesis,
        sig,
        capsule.by,
    )


def _genesis() -> Capsule:
    return _sign(Capsule("capability", "lgwks harness genesis", is_genesis=True, grants=HARNESS_GRANTS, by="lgwks"))


def _capsule_for_fact(fact: CapturedFact, genesis_cid: str) -> Capsule:
    payload = json.dumps(fact.value, sort_keys=True, separators=(",", ":"))
    return Capsule(
        "evidence",
        f"{fact.kind}:{fact.label}:{payload}",
        on=(genesis_cid,),
        needs=frozenset({"observe"}),
        by="lgwks-harness",
    )


def _emit_capsule(fabric: Fabric, capsule: Capsule, event: str) -> dict[str, Any]:
    cid, verdict = fabric.propose(capsule, window=1)
    if cid is None:
        return {
            "event": event,
            "ok": False,
            "reason": verdict.reason,
            "requires_confirm": verdict.requires_confirm,
        }
    return {
        "event": event,
        "ok": verdict.ok,
        "cid": cid,
        "capsule": {
            "kind": capsule.kind,
            "claim": capsule.claim,
            "on": list(capsule.on),
            "needs": sorted(capsule.needs),
            "grants": sorted(capsule.grants),
            "is_hole": capsule.is_hole,
            "is_genesis": capsule.is_genesis,
            "by": capsule.by,
        },
        "bytes_hex": capsule.to_bytes().hex(),
        "requires_confirm": verdict.requires_confirm,
    }


def _repo_facts(repo: Path) -> list[CapturedFact]:
    facts: list[CapturedFact] = []
    rc, out, err = _git(repo, "rev-parse", "--is-inside-work-tree")
    facts.append(CapturedFact("repo", "is_git_repo", {"ok": rc == 0 and out == "true", "error": err}))
    rc, out, _ = _git(repo, "branch", "--show-current")
    facts.append(CapturedFact("repo", "branch", {"returncode": rc, "branch": out}))
    rc, out, _ = _git(repo, "rev-parse", "--short", "HEAD")
    facts.append(CapturedFact("repo", "head", {"returncode": rc, "sha": out}))
    rc, out, _ = _git(repo, "status", "--short")
    status_lines = [ln for ln in out.splitlines() if ln.strip()]
    facts.append(CapturedFact("repo", "status", {"returncode": rc, "dirty_count": len(status_lines), "lines": status_lines[:80]}))
    rc, out, _ = _git(repo, "diff", "--name-only")
    diff_files = [ln for ln in out.splitlines() if ln.strip()]
    facts.append(CapturedFact("repo", "diff", {"returncode": rc, "file_count": len(diff_files), "files": diff_files[:120]}))
    return facts


def _test_fact(command: str, repo: Path, timeout: int) -> CapturedFact:
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CapturedFact(
            "test",
            "command",
            {
                "command": command,
                "returncode": proc.returncode,
                "elapsed_seconds": round(time.time() - started, 3),
                "stdout_tail": (proc.stdout or "")[-2000:],
                "stderr_tail": (proc.stderr or "")[-2000:],
            },
        )
    except subprocess.TimeoutExpired as exc:
        return CapturedFact(
            "test",
            "command",
            {
                "command": command,
                "returncode": 124,
                "elapsed_seconds": round(time.time() - started, 3),
                "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                "stderr_tail": "timeout",
            },
        )


def build_capture(repo: Path, intent: str = "", test_command: str = "", timeout: int = 120, out_dir: Path | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    run_id = _run_id(repo, intent)
    root = (out_dir or (repo / RUN_ROOT / run_id)).resolve()
    root.mkdir(parents=True, exist_ok=True)

    fabric = Fabric(trusted_key=HARNESS_KEY)
    genesis = _genesis()
    genesis_record = _emit_capsule(fabric, genesis, "genesis")
    genesis_cid = genesis_record["cid"]

    facts = _repo_facts(repo)
    if intent:
        facts.append(CapturedFact("intent", "operator", {"text": intent}))
    if test_command:
        facts.append(_test_fact(test_command, repo, timeout))

    emissions = [genesis_record]
    for fact in facts:
        record = _emit_capsule(fabric, _capsule_for_fact(fact, genesis_cid), fact.kind)
        record["fact"] = asdict(fact)
        emissions.append(record)

    packet = {
        "schema": SCHEMA,
        "run_id": run_id,
        "created_at": _utc(),
        "repo": str(repo),
        "intent": intent,
        "paths": {
            "root": str(root),
            "emissions": str(root / "emissions.jsonl"),
            "fabric_log": str(root / "fabric-log.json"),
            "packet": str(root / "packet.json"),
        },
        "counts": {
            "facts": len(facts),
            "emissions": len(emissions),
            "fabric_log_entries": len(fabric.log),
        },
        "fabric": {
            "chain_ok": fabric.verify_chain(),
            "log": [asdict(entry) for entry in fabric.log],
        },
        "emissions": emissions,
    }
    (root / "emissions.jsonl").write_text("\n".join(json.dumps(e, sort_keys=True) for e in emissions) + "\n", encoding="utf-8")
    (root / "fabric-log.json").write_text(json.dumps(packet["fabric"], indent=2, sort_keys=True), encoding="utf-8")
    (root / "packet.json").write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return packet


def _load_emissions(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        path = path / "emissions.jsonl"
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def replay_emissions(path: Path) -> dict[str, Any]:
    """Replay persisted emission bytes into a fresh fabric and verify CID/log integrity.

    This is the IR reloader: if the on-disk emissions are the real artifact, they
    must reconstruct without trusting narration or the original packet summary.
    """
    root = path if path.is_dir() else path.parent
    emissions = _load_emissions(path)
    fabric = Fabric(trusted_key=HARNESS_KEY)
    replayed: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, emission in enumerate(emissions):
        cid = emission.get("cid")
        raw_hex = emission.get("bytes_hex")
        if not isinstance(cid, str) or not isinstance(raw_hex, str):
            failures.append({"index": str(index), "reason": "missing cid or bytes_hex"})
            continue
        try:
            raw = bytes.fromhex(raw_hex)
            capsule = Capsule.from_bytes(raw)
            require_cid(raw, cid)
            replay_cid, verdict = fabric.propose(capsule, window=1)
        except Exception as exc:
            failures.append({"index": str(index), "cid": cid, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        if replay_cid != cid or not verdict.ok:
            failures.append({
                "index": str(index),
                "cid": cid,
                "reason": f"replay mismatch: replay_cid={replay_cid} ok={verdict.ok} reason={verdict.reason}",
            })
            continue
        replayed.append({"index": index, "cid": cid, "event": emission.get("event", ""), "ok": True})

    expected_log_path = root / "fabric-log.json"
    expected_log: list[dict[str, Any]] | None = None
    log_matches = None
    if expected_log_path.exists():
        try:
            expected_payload = json.loads(expected_log_path.read_text(encoding="utf-8"))
            expected_log = list(expected_payload.get("log", []))
            actual_log = [asdict(entry) for entry in fabric.log]
            log_matches = expected_log == actual_log
            if not log_matches:
                failures.append({"index": "log", "reason": "fabric-log.json does not match replayed log"})
        except Exception as exc:
            failures.append({"index": "log", "reason": f"could not read fabric-log.json: {type(exc).__name__}: {exc}"})
            log_matches = False

    return {
        "schema": "lgwks.axiom.replay.v0",
        "source": str(path),
        "ok": not failures and fabric.verify_chain(),
        "counts": {
            "emissions": len(emissions),
            "replayed": len(replayed),
            "failures": len(failures),
            "fabric_log_entries": len(fabric.log),
        },
        "chain_ok": fabric.verify_chain(),
        "log_matches": log_matches,
        "failures": failures,
        "replayed": replayed,
    }


def check_narration(claim: str, emissions: list[dict[str, Any]]) -> dict[str, Any]:
    text = claim.lower()
    facts = [e.get("fact", {}) for e in emissions if isinstance(e.get("fact"), dict)]
    test_facts = [f for f in facts if f.get("kind") == "test"]
    status_facts = [f for f in facts if f.get("kind") == "repo" and f.get("label") == "status"]
    diff_facts = [f for f in facts if f.get("kind") == "repo" and f.get("label") == "diff"]

    findings: list[dict[str, str]] = []
    if "test" in text and any(word in text for word in ("pass", "passed", "green")):
        if not test_facts:
            findings.append({"level": "pan_pan", "claim": "tests passed", "evidence": "no captured test command"})
        elif not any(f.get("value", {}).get("returncode") == 0 for f in test_facts):
            findings.append({"level": "mayday", "claim": "tests passed", "evidence": "captured test command did not pass"})
    if any(word in text for word in ("changed", "modified", "implemented", "edited")):
        dirty = sum(int(f.get("value", {}).get("dirty_count", 0)) for f in status_facts)
        diff_files = sum(int(f.get("value", {}).get("file_count", 0)) for f in diff_facts)
        if dirty == 0 and diff_files == 0:
            findings.append({"level": "pan_pan", "claim": "work changed files", "evidence": "captured git status/diff is clean"})
    if any(phrase in text for phrase in ("no changes", "clean worktree", "nothing changed")):
        dirty = sum(int(f.get("value", {}).get("dirty_count", 0)) for f in status_facts)
        if dirty > 0:
            findings.append({"level": "pan_pan", "claim": "clean worktree", "evidence": f"captured dirty_count={dirty}"})
    return {
        "schema": "lgwks.axiom.divergence.v0",
        "claim": claim,
        "ok": not findings,
        "findings": findings,
        "evidence_counts": {
            "tests": len(test_facts),
            "status": len(status_facts),
            "diff": len(diff_facts),
            "emissions": len(emissions),
        },
    }


def independence_report(root: Path) -> dict[str, Any]:
    axiom_dir = root / "axiom"
    violations: list[dict[str, str]] = []
    for path in sorted(axiom_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if mod.startswith("lgwks"):
                        violations.append({"file": str(path), "import": mod})
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("lgwks"):
                    violations.append({"file": str(path), "import": mod})
    return {
        "schema": "lgwks.axiom.doctor.v0",
        "axiom_dir": str(axiom_dir),
        "independent": not violations,
        "violations": violations,
    }


def _print_packet(packet: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
        return
    print(f"axiom run: {packet['run_id']}")
    print(f"repo: {packet['repo']}")
    print(f"facts: {packet['counts']['facts']} emissions: {packet['counts']['emissions']}")
    print(f"chain_ok: {packet['fabric']['chain_ok']}")
    print(f"packet: {packet['paths']['packet']}")


def capture_command(args: argparse.Namespace) -> int:
    packet = build_capture(Path(args.repo), args.intent, args.test_command, args.timeout, Path(args.out) if args.out else None)
    _print_packet(packet, args.json or os.environ.get("LGWRS_MACHINE") == "1")
    return 0


def check_command(args: argparse.Namespace) -> int:
    result = check_narration(args.claim, _load_emissions(Path(args.run)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


def replay_command(args: argparse.Namespace) -> int:
    result = replay_emissions(Path(args.run))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def doctor_command(args: argparse.Namespace) -> int:
    report = independence_report(Path(args.repo).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["independent"] else 1


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("axiom", help="Axiom harness: capture emissions, verify divergence, inspect layers")
    sp = p.add_subparsers(dest="axiom_command", required=True)

    capture = sp.add_parser("capture", help="capture repo/test facts as verified Axiom capsules")
    capture.add_argument("--repo", default=".", help="repo to capture")
    capture.add_argument("--intent", default="", help="operator intent/narration seed to preserve as captured data")
    capture.add_argument("--test", dest="test_command", default="", help="optional test command to run and capture")
    capture.add_argument("--timeout", type=int, default=120, help="test command timeout in seconds")
    capture.add_argument("--out", default="", help="optional output directory; default .lgwks/axiom/runs/<id>")
    capture.add_argument("--json", action="store_true", help="print full packet JSON")
    capture.set_defaults(func=capture_command)

    check = sp.add_parser("check", help="compare a narration claim against captured emissions")
    check.add_argument("run", help="run directory or emissions.jsonl path")
    check.add_argument("--claim", required=True, help="narration claim to verify against captured facts")
    check.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    check.set_defaults(func=check_command)

    replay = sp.add_parser("replay", help="replay persisted emissions into a fresh verified fabric")
    replay.add_argument("run", help="run directory or emissions.jsonl path")
    replay.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    replay.set_defaults(func=replay_command)

    doctor = sp.add_parser("doctor", help="check Axiom byte-layer independence")
    doctor.add_argument("--repo", default=".", help="repo root")
    doctor.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    doctor.set_defaults(func=doctor_command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command", required=True))
    parsed = parser.parse_args()
    sys.exit(parsed.func(parsed))
