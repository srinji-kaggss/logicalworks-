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
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from axiom.capsule import Capsule
from axiom.cid import require_cid
from axiom.fabric import Fabric

import lgwks_run

SCHEMA = "lgwks.axiom.harness.v0"
RUN_ROOT = Path(".lgwks") / "axiom" / "runs"
HARNESS_KEY = b"lgwks-axiom-harness-v0"
HARNESS_GRANTS = frozenset({"observe", "diff", "test", "narrate"})
MATRIX_SCHEMA = "lgwks.axiom.test_matrix.v0"
NARRATION_SCHEMA = "lgwks.axiom.narration.v0"
MAX_TEST_TIMEOUT = 3600
MAX_MATRIX_TESTS = 50
MAX_JSON_BYTES = 1_000_000
NARRATION_KINDS = frozenset({"tests_passed", "worktree_clean", "files_changed", "work_implemented"})


class CommandPolicyError(ValueError):
    pass


def _argv_from_command(command: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(command, str):
        try:
            argv = tuple(shlex.split(command))
        except ValueError as exc:
            raise CommandPolicyError(f"invalid command quoting: {exc}") from exc
    else:
        argv = tuple(str(part) for part in command)
    if not argv or any(part == "" for part in argv):
        raise CommandPolicyError("command argv must not be empty")
    return argv


def classify_argv(argv: tuple[str, ...], repo: Path) -> dict[str, Any]:
    if not argv:
        return {"risk": "blocked", "reason": "empty command"}
    
    cmd = argv[0]
    cmd_name = Path(cmd).name
    repo_abs = repo.resolve()
    cmd_is_untrusted_absolute = False
    if os.path.isabs(cmd) and not _is_relative_to(Path(cmd).resolve(), repo_abs):
        resolved_tool = shutil.which(cmd_name)
        cmd_is_untrusted_absolute = resolved_tool is None or Path(resolved_tool).resolve() != Path(cmd).resolve()
    
    # Check for absolute paths outside repo
    for arg in argv[1:]:
        if os.path.isabs(arg):
            arg_path = Path(arg).resolve()
            if not _is_relative_to(arg_path, repo_abs):
                return {"risk": "blocked", "reason": f"absolute path outside repo: {arg}"}

    # Allow list
    if cmd_name in ("python", "python3", "uv", "pytest"):
        if cmd_is_untrusted_absolute:
            return {"risk": "risky", "reason": f"absolute command path is not the PATH-resolved {cmd_name}: {cmd}"}
        # HARDEN: Block dangerous python -c
        if cmd_name in ("python", "python3") and "-c" in argv:
            idx = argv.index("-c")
            if idx + 1 < len(argv):
                code = argv[idx + 1]
                for dangerous in ("import os", "import subprocess", "import shutil", "eval(", "exec("):
                    if dangerous in code:
                        return {"risk": "blocked", "reason": f"dangerous code in {cmd_name} -c"}
        return {"risk": "safe"}
    
    if cmd_name == "git":
        if cmd_is_untrusted_absolute:
            return {"risk": "risky", "reason": f"absolute command path is not the PATH-resolved git: {cmd}"}
        if len(argv) > 1:
            sub = argv[1]
            if sub in ("status", "diff", "log", "rev-parse"):
                return {"risk": "safe"}
            if sub == "branch" and "--show-current" in argv:
                return {"risk": "safe"}
            
            # Block list for git
            if sub in ("push", "reset", "checkout", "clean", "commit", "merge", "rebase"):
                return {"risk": "blocked", "reason": f"destructive git command: {sub}"}
        else:
            return {"risk": "safe"} # bare git is safe (shows help)

    # Block list
    if cmd_name in ("rm", "mv", "chmod", "chown", "curl", "wget", "ssh", "scp"):
        return {"risk": "blocked", "reason": f"blocked tool: {cmd_name}"}
    
    if cmd_name == "cp":
        if any(arg in ("-r", "-R", "--recursive") for arg in argv):
            return {"risk": "blocked", "reason": "recursive copy blocked"}
        return {"risk": "safe"} # non-recursive cp is likely ok

    return {"risk": "risky", "reason": "unknown command"}


@dataclass(frozen=True)
class CapturedFact:
    kind: str
    label: str
    value: dict[str, Any]


@dataclass(frozen=True)
class TestSpec:
    label: str
    command: tuple[str, ...]
    timeout: int


@dataclass(frozen=True)
class NarrationClaim:
    kind: str
    source: str
    requires: tuple[str, ...]
    confidence: float = 1.0


@dataclass(frozen=True)
class NarrationHole:
    source: str
    why_unmatched: str
    nearest_known: tuple[str, ...]


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


from lgwks_hashing import content_id as _sha  # canonical content-id (one source of truth)


def _run_id(repo: Path, intent: str) -> str:
    seed = f"{repo.resolve()}|{intent}|{time.time_ns()}"
    return f"axiom-{_sha(seed, 20)}"


def write_run_index(root: Path, run_id: str, artifacts: list[dict[str, str]]) -> dict[str, Any]:
    index_path = root / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            index = {}
    else:
        index = {}

    index.setdefault("schema", "lgwks.axiom.run_index.v0")
    index.setdefault("run_id", run_id)
    index.setdefault("root", str(root))
    index.setdefault("created_at", _utc())
    existing_artifacts = index.get("artifacts", [])
    if not isinstance(existing_artifacts, list):
        existing_artifacts = []
    
    # Merge artifacts by kind and path
    artifact_map = {
        (a["kind"], a["path"]): a
        for a in existing_artifacts
        if isinstance(a, dict) and isinstance(a.get("kind"), str) and isinstance(a.get("path"), str)
    }
    for a in artifacts:
        # HARDEN: Ensure path is relative and safe
        p = Path(a["path"])
        if p.is_absolute() or ".." in p.parts:
            continue
        artifact_map[(a["kind"], a["path"])] = a
    
    index["artifacts"] = sorted(
        [v for v in artifact_map.values()],
        key=lambda x: (x["kind"], x["path"])
    )
    
    root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    return index


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


def _capsule_for_narration_claim(claim: NarrationClaim, genesis_cid: str) -> Capsule:
    payload = json.dumps(asdict(claim), sort_keys=True, separators=(",", ":"))
    return Capsule(
        "evidence",
        f"narration:{claim.kind}:{payload}",
        on=(genesis_cid,),
        needs=frozenset({"narrate"}),
        by="lgwks-narration",
    )


def _capsule_for_narration_hole(hole: NarrationHole, genesis_cid: str) -> Capsule:
    payload = json.dumps(asdict(hole), sort_keys=True, separators=(",", ":"))
    return Capsule(
        "constraint",
        f"narration-hole:{payload}",
        on=(genesis_cid,),
        is_hole=True,
        by="lgwks-narration",
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


def _normalize_label(label: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-")
    if not clean:
        raise ValueError("test label must not be empty")
    return clean[:64]


def _normalize_timeout(value: Any, default: int = 120) -> int:
    try:
        timeout = int(value if value is not None else default)
    except Exception as exc:
        raise ValueError(f"timeout must be an integer, got {value!r}") from exc
    if timeout < 1 or timeout > MAX_TEST_TIMEOUT:
        raise ValueError(f"timeout must be in 1..{MAX_TEST_TIMEOUT}, got {timeout}")
    return timeout


def load_test_matrix(path: Path, default_timeout: int = 120) -> list[TestSpec]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"test matrix exceeds {MAX_JSON_BYTES} bytes")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_tests = payload.get("tests") if isinstance(payload, dict) else payload
    if not isinstance(raw_tests, list) or not raw_tests:
        raise ValueError("test matrix requires a non-empty tests list")
    if len(raw_tests) > MAX_MATRIX_TESTS:
        raise ValueError(f"test matrix may contain at most {MAX_MATRIX_TESTS} tests")
    tests: list[TestSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_tests):
        if not isinstance(item, dict):
            raise ValueError(f"test #{index} must be an object")
        label = _normalize_label(str(item.get("label", "")))
        if label in seen:
            raise ValueError(f"duplicate test label: {label}")
        seen.add(label)
        raw_command = item.get("command")
        if isinstance(raw_command, list):
            command = tuple(str(part) for part in raw_command)
        elif isinstance(raw_command, str):
            raise ValueError(f"test {label!r} command must be an argv list, not a shell string")
        else:
            command = ()
        if not command or any(not part for part in command):
            raise ValueError(f"test {label!r} command must not be empty")
        timeout = _normalize_timeout(item.get("timeout"), default_timeout)
        tests.append(TestSpec(label, command, timeout))
    return tests


def parse_narration(text: str) -> dict[str, Any]:
    raw = text.strip()
    lower = raw.lower()
    claims: list[NarrationClaim] = []
    holes: list[NarrationHole] = []
    known = ("tests_passed", "worktree_clean", "files_changed", "work_implemented")
    if not raw:
        holes.append(NarrationHole(raw, "empty narration", known))
    else:
        if "test" in lower and any(word in lower for word in ("pass", "passed", "green")):
            claims.append(NarrationClaim("tests_passed", raw, ("test:returncode=0:all",)))
        if any(phrase in lower for phrase in ("clean worktree", "worktree clean", "no changes", "nothing changed")):
            claims.append(NarrationClaim("worktree_clean", raw, ("repo:status.dirty_count=0",)))
        if any(word in lower for word in ("changed", "modified", "edited")):
            claims.append(NarrationClaim("files_changed", raw, ("repo:diff.file_count>0|repo:status.dirty_count>0",)))
        if any(word in lower for word in ("implemented", "built", "added")):
            claims.append(NarrationClaim("work_implemented", raw, ("repo:diff.file_count>0|repo:status.dirty_count>0",)))
        if not claims:
            holes.append(NarrationHole(raw, "no supported narration claim matched", known))
    return {
        "schema": NARRATION_SCHEMA,
        "source": raw,
        "claims": [asdict(c) for c in claims],
        "holes": [asdict(h) for h in holes],
    }


def load_narration(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"narration file exceeds {MAX_JSON_BYTES} bytes")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != NARRATION_SCHEMA:
        raise ValueError(f"narration file must have schema {NARRATION_SCHEMA}")
    payload.setdefault("claims", [])
    payload.setdefault("holes", [])
    if not isinstance(payload["claims"], list) or not isinstance(payload["holes"], list):
        raise ValueError("narration claims/holes must be lists")
    for item in payload["claims"]:
        if not isinstance(item, dict):
            raise ValueError("narration claim entries must be objects")
        kind = item.get("kind")
        if kind not in NARRATION_KINDS:
            raise ValueError(f"unsupported narration claim kind: {kind}")
        confidence = float(item.get("confidence", 1.0))
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"narration confidence must be in 0..1, got {confidence}")
    for item in payload["holes"]:
        if not isinstance(item, dict):
            raise ValueError("narration hole entries must be objects")
    return payload


def build_narration_artifact(
    claim_text: str = "",
    claims_file: Path | None = None,
    run: Path | None = None,
    adopt: bool = True
) -> dict[str, Any]:
    narration = load_narration(claims_file) if claims_file else parse_narration(claim_text)
    default_root = Path.cwd().resolve() / RUN_ROOT
    root = run.resolve() if run else (default_root / f"narration-{_sha(json.dumps(narration, sort_keys=True), 20)}").resolve()
    root.mkdir(parents=True, exist_ok=True)
    fabric = Fabric(trusted_key=HARNESS_KEY)
    genesis = _genesis()
    genesis_record = _emit_capsule(fabric, genesis, "genesis")
    genesis_cid = genesis_record["cid"]
    emissions: list[dict[str, Any]] = [genesis_record]
    for item in narration["claims"]:
        claim = NarrationClaim(
            kind=str(item["kind"]),
            source=str(item.get("source", narration.get("source", ""))),
            requires=tuple(str(x) for x in item.get("requires", [])),
            confidence=float(item.get("confidence", 1.0)),
        )
        record = _emit_capsule(fabric, _capsule_for_narration_claim(claim, genesis_cid), "narration")
        record["narration_claim"] = asdict(claim)
        emissions.append(record)
    for item in narration["holes"]:
        hole = NarrationHole(
            source=str(item.get("source", narration.get("source", ""))),
            why_unmatched=str(item.get("why_unmatched", "unknown narration")),
            nearest_known=tuple(str(x) for x in item.get("nearest_known", [])),
        )
        record = _emit_capsule(fabric, _capsule_for_narration_hole(hole, genesis_cid), "narration-hole")
        record["narration_hole"] = asdict(hole)
        emissions.append(record)
    artifact = {
        "schema": NARRATION_SCHEMA,
        "run": str(root),
        "paths": {
            "narration": str(root / "narration.json"),
            "emissions": str(root / "narration-emissions.jsonl"),
        },
        "source": narration.get("source", ""),
        "claims": narration["claims"],
        "holes": narration["holes"],
        "emissions": emissions,
        "fabric": {
            "chain_ok": fabric.verify_chain(),
            "log": [asdict(entry) for entry in fabric.log],
        },
    }
    (root / "narration.json").write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    (root / "narration-emissions.jsonl").write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in emissions) + "\n",
        encoding="utf-8",
    )
    (root / "narration-fabric-log.json").write_text(
        json.dumps(artifact["fabric"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    
    # Update run index
    write_run_index(root, f"narration-{_sha(json.dumps(narration, sort_keys=True), 20)}", [
        {"kind": "narration", "path": "narration.json", "schema": NARRATION_SCHEMA},
        {"kind": "narration_emissions", "path": "narration-emissions.jsonl"},
        {"kind": "narration_fabric_log", "path": "narration-fabric-log.json"}
    ])
    
    if adopt:
        try:
            lgwks_run.adopt_axiom_run(root, repo=Path.cwd())
        except Exception:
            pass # Adoption failure should not break narration build

    return artifact


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _command_display(command: str | tuple[str, ...]) -> str:
    return command if isinstance(command, str) else " ".join(command)


def _test_fact(
    command: str | tuple[str, ...],
    repo: Path,
    timeout: int,
    label: str = "command",
    policy: dict[str, Any] | None = None
) -> CapturedFact:
    started = time.time()
    argv = list(_argv_from_command(command))

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        val = {
            "label": label,
            "command": " ".join(argv),
            "argv": argv,
            "returncode": proc.returncode,
            "elapsed_seconds": round(time.time() - started, 3),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
        if policy:
            val["policy"] = policy
        return CapturedFact("test", label, val)
    except subprocess.TimeoutExpired as exc:
        val = {
            "label": label,
            "command": " ".join(argv),
            "argv": argv,
            "returncode": 124,
            "elapsed_seconds": round(time.time() - started, 3),
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": "timeout",
        }
        if policy:
            val["policy"] = policy
        return CapturedFact("test", label, val)


def build_capture(
    repo: Path,
    intent: str = "",
    test_command: str = "",
    timeout: int = 120,
    out_dir: Path | None = None,
    test_specs: list[TestSpec] | None = None,
    allow_risky: bool = False,
    adopt: bool = True
) -> dict[str, Any]:
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
    
    specs = test_specs or []
    if not specs and test_command:
        specs = [TestSpec("command", _argv_from_command(test_command), timeout)]

    for spec in specs:
        policy = classify_argv(spec.command, repo)
        if policy["risk"] == "blocked":
            raise CommandPolicyError(f"Policy blocked command {spec.command!r}: {policy.get('reason')}")
        
        if policy["risk"] == "risky" and not allow_risky:
            raise CommandPolicyError(
                f"Policy flagged command {spec.command!r} as risky. "
                "Use --allow-risky to proceed."
            )
        
        # Record if allowed by flag
        if policy["risk"] == "risky" and allow_risky:
            policy["allowed_by"] = "flag"
            
        facts.append(_test_fact(spec.command, repo, spec.timeout, spec.label, policy=policy))

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
    
    # Update run index
    write_run_index(root, run_id, [
        {"kind": "capture", "path": "packet.json", "schema": SCHEMA},
        {"kind": "emissions", "path": "emissions.jsonl"},
        {"kind": "fabric_log", "path": "fabric-log.json"}
    ])
    
    if adopt:
        try:
            lgwks_run.adopt_axiom_run(root, repo=repo)
        except Exception:
            pass # Adoption failure should not break capture build

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

    # Find expected log path based on emission file name
    log_name = "fabric-log.json"
    if path.name == "narration-emissions.jsonl":
        log_name = "narration-fabric-log.json"
    
    expected_log_path = root / log_name
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


def replay_run(root: Path) -> dict[str, Any]:
    """Replay all artifacts in a run directory."""
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")

    index_path = root / "index.json"
    emission_paths: list[tuple[str, Path]] = []

    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict) or index.get("schema") != "lgwks.axiom.run_index.v0":
                return {
                    "schema": "lgwks.axiom.replay_all.v0",
                    "ok": False,
                    "artifacts": [],
                    "failures": [{"path": "index.json", "reason": "invalid run index schema"}],
                }
            for art in index.get("artifacts", []):
                if not isinstance(art, dict):
                    continue
                kind = art.get("kind")
                art_path = art.get("path")
                if kind in ("emissions", "narration_emissions") and isinstance(art_path, str):
                    p = Path(art_path)
                    # HARDEN: Path traversal protection
                    if p.is_absolute() or ".." in p.parts:
                        continue
                    full_path = root / p
                    if full_path.exists():
                        emission_paths.append((kind, full_path))
        except Exception as exc:
            return {
                "schema": "lgwks.axiom.replay_all.v0",
                "ok": False,
                "artifacts": [],
                "failures": [{"path": "index.json", "reason": f"{type(exc).__name__}: {exc}"}],
            }
    
    if not emission_paths:
        # Fallback detection
        for p in (root / "emissions.jsonl", root / "narration-emissions.jsonl"):
            if p.exists():
                kind = "emissions" if p.name == "emissions.jsonl" else "narration"
                emission_paths.append((kind, p))

    results: list[dict[str, Any]] = []
    overall_ok = True
    for kind, path in emission_paths:
        res = replay_emissions(path)
        results.append({
            "kind": "capture" if kind == "emissions" else "narration",
            "ok": res["ok"],
            "path": str(path.relative_to(root) if _is_relative_to(path, root) else path)
        })
        if not res["ok"]:
            overall_ok = False

    return {
        "schema": "lgwks.axiom.replay_all.v0",
        "ok": overall_ok and bool(results),
        "artifacts": results,
        "failures": [],
    }


def _claims_from_input(claim: str = "", claims: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    payload = claims if claims is not None else parse_narration(claim)
    return list(payload.get("claims", [])), list(payload.get("holes", [])), str(payload.get("source", claim))


def check_narration(claim: str, emissions: list[dict[str, Any]], claims: dict[str, Any] | None = None) -> dict[str, Any]:
    typed_claims, holes, source = _claims_from_input(claim, claims)
    facts = [e.get("fact", {}) for e in emissions if isinstance(e.get("fact"), dict)]
    test_facts = [f for f in facts if f.get("kind") == "test"]
    status_facts = [f for f in facts if f.get("kind") == "repo" and f.get("label") == "status"]
    diff_facts = [f for f in facts if f.get("kind") == "repo" and f.get("label") == "diff"]

    findings: list[dict[str, str]] = []
    for hole in holes:
        findings.append({"level": "pan_pan", "claim": "unsupported narration", "evidence": str(hole.get("why_unmatched", "unknown"))})
    for typed in typed_claims:
        kind = typed.get("kind")
        if kind == "tests_passed":
            if not test_facts:
                findings.append({"level": "pan_pan", "claim": "tests_passed", "evidence": "no captured test command"})
            elif not all(f.get("value", {}).get("returncode") == 0 for f in test_facts):
                findings.append({"level": "mayday", "claim": "tests_passed", "evidence": "one or more captured test commands did not pass"})
        elif kind in {"files_changed", "work_implemented"}:
            dirty = sum(int(f.get("value", {}).get("dirty_count", 0)) for f in status_facts)
            diff_files = sum(int(f.get("value", {}).get("file_count", 0)) for f in diff_facts)
            if dirty == 0 and diff_files == 0:
                findings.append({"level": "pan_pan", "claim": str(kind), "evidence": "captured git status/diff is clean"})
        elif kind == "worktree_clean":
            dirty = sum(int(f.get("value", {}).get("dirty_count", 0)) for f in status_facts)
            if dirty > 0:
                findings.append({"level": "pan_pan", "claim": "worktree_clean", "evidence": f"captured dirty_count={dirty}"})
        else:
            findings.append({"level": "pan_pan", "claim": str(kind), "evidence": "unsupported typed claim kind"})
    return {
        "schema": "lgwks.axiom.divergence.v0",
        "claim": source,
        "typed_claims": typed_claims,
        "holes": holes,
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
    try:
        packet = build_capture(
            Path(args.repo),
            args.intent,
            args.test_command,
            args.timeout,
            Path(args.out) if args.out else None,
            allow_risky=getattr(args, "allow_risky", False),
            adopt=not getattr(args, "no_adopt", False)
        )
    except CommandPolicyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    _print_packet(packet, args.json or os.environ.get("LGWRS_MACHINE") == "1")
    return 0


def test_matrix_command(args: argparse.Namespace) -> int:
    try:
        specs = load_test_matrix(Path(args.file), args.timeout)
        packet = build_capture(
            Path(args.repo),
            args.intent,
            out_dir=Path(args.out) if args.out else None,
            test_specs=specs,
            allow_risky=getattr(args, "allow_risky", False),
            adopt=not getattr(args, "no_adopt", False)
        )
    except (ValueError, CommandPolicyError) as exc:
        print(json.dumps({"schema": MATRIX_SCHEMA, "ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    packet["matrix"] = {"schema": MATRIX_SCHEMA, "tests": [asdict(spec) for spec in specs]}
    packet_path = Path(packet["paths"]["packet"])
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    _print_packet(packet, args.json or os.environ.get("LGWRS_MACHINE") == "1")
    return 0


def narrate_command(args: argparse.Namespace) -> int:
    if not args.claim and not args.claims:
        print(json.dumps({"schema": NARRATION_SCHEMA, "ok": False, "error": "provide --claim or --claims"}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    try:
        run = Path(args.run).resolve() if args.run else None
        if run and not _is_relative_to(run, Path.cwd().resolve()):
            raise ValueError("narration --run must stay within the current repo/worktree")
        artifact = build_narration_artifact(
            args.claim,
            Path(args.claims) if args.claims else None,
            run,
            adopt=not getattr(args, "no_adopt", False)
        )
    except ValueError as exc:
        print(json.dumps({"schema": NARRATION_SCHEMA, "ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


def check_command(args: argparse.Namespace) -> int:
    claims = load_narration(Path(args.claims)) if getattr(args, "claims", "") else None
    if claims is None and not args.claim:
        print(json.dumps({"schema": "lgwks.axiom.divergence.v0", "ok": False, "error": "provide --claim or --claims"}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    result = check_narration(args.claim, _load_emissions(Path(args.run)), claims)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


def replay_command(args: argparse.Namespace) -> int:
    run_path = Path(args.run)
    if getattr(args, "all", False):
        result = replay_run(run_path)
    else:
        result = replay_emissions(run_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def doctor_command(args: argparse.Namespace) -> int:
    report = independence_report(Path(args.repo).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["independent"] else 1


def index_command(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    if not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"not a directory: {run_dir}"}, indent=2), file=sys.stderr)
        return 1
    index_path = run_dir / "index.json"
    if not index_path.exists():
        print(json.dumps({"ok": False, "error": f"index.json not found in {run_dir}"}, indent=2), file=sys.stderr)
        return 1
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        print(json.dumps(index, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("axiom", help="Axiom harness: capture emissions, verify divergence, inspect layers")
    sp = p.add_subparsers(dest="axiom_command", required=True)

    capture = sp.add_parser("capture", help="capture repo/test facts as verified Axiom capsules")
    capture.add_argument("--repo", default=".", help="repo to capture")
    capture.add_argument("--intent", default="", help="operator intent/narration seed to preserve as captured data")
    capture.add_argument("--test", dest="test_command", default="", help="optional test command to run and capture")
    capture.add_argument("--timeout", type=int, default=120, help="test command timeout in seconds")
    capture.add_argument("--out", default="", help="optional output directory; default .lgwks/axiom/runs/<id>")
    capture.add_argument("--allow-risky", action="store_true", help="allow risky commands to proceed")
    capture.add_argument("--no-adopt", action="store_true", help="do not adopt into the universal run spine")
    capture.add_argument("--json", action="store_true", help="print full packet JSON")
    capture.set_defaults(func=capture_command)

    check = sp.add_parser("check", help="compare a narration claim against captured emissions")
    check.add_argument("run", help="run directory or emissions.jsonl path")
    check.add_argument("--claim", default="", help="raw narration claim to verify against captured facts")
    check.add_argument("--claims", default="", help="typed lgwks.axiom.narration.v0 claims file")
    check.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    check.set_defaults(func=check_command)

    replay = sp.add_parser("replay", help="replay persisted emissions into a fresh verified fabric")
    replay.add_argument("run", help="run directory or emissions.jsonl path")
    replay.add_argument("--all", action="store_true", help="replay all artifact types in the run")
    replay.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    replay.set_defaults(func=replay_command)

    matrix = sp.add_parser("test-matrix", help="run a bounded labeled test matrix and capture it as Axiom IR")
    matrix.add_argument("--repo", default=".", help="repo to capture")
    matrix.add_argument("--file", required=True, help="JSON test matrix file")
    matrix.add_argument("--intent", default="", help="operator intent/narration seed")
    matrix.add_argument("--timeout", type=int, default=120, help="default timeout for tests missing timeout")
    matrix.add_argument("--out", default="", help="optional output directory; default .lgwks/axiom/runs/<id>")
    matrix.add_argument("--allow-risky", action="store_true", help="allow risky commands to proceed")
    matrix.add_argument("--no-adopt", action="store_true", help="do not adopt into the universal run spine")
    matrix.add_argument("--json", action="store_true", help="print full packet JSON")
    matrix.set_defaults(func=test_matrix_command)

    narrate = sp.add_parser("narrate", help="parse narration into typed claims or holes and persist as Axiom IR")
    narrate.add_argument("--claim", default="", help="raw narration claim")
    narrate.add_argument("--claims", default="", help="existing lgwks.axiom.narration.v0 JSON file")
    narrate.add_argument("--run", default="", help="optional run directory to store narration artifacts")
    narrate.add_argument("--no-adopt", action="store_true", help="do not adopt into the universal run spine")
    narrate.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    narrate.set_defaults(func=narrate_command)

    doctor = sp.add_parser("doctor", help="check Axiom byte-layer independence")
    doctor.add_argument("--repo", default=".", help="repo root")
    doctor.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    doctor.set_defaults(func=doctor_command)

    index = sp.add_parser("index", help="print the run index JSON")
    index.add_argument("run", help="run directory")
    index.add_argument("--json", action="store_true", help="structured output (default; flag exists for caller intent)")
    index.set_defaults(func=index_command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command", required=True))
    parsed = parser.parse_args()
    sys.exit(parsed.func(parsed))
