"""
lgwks_bot_stress — U8: Concurrent Stress Bot.

Runs N concurrent subprocesses to surface real race conditions,
artifact corruption, read/write inconsistency, lock failures,
and recovery gaps.

Restores the store to a clean state after execution.
All findings conform to the lgwks.bot.record.v1 schema.
"""

from __future__ import annotations

import json
import os
import sys
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Any

import lgwks_project_artifacts as artifacts

_BOT = "stress"


def _run_seed(repo: str) -> str:
    return artifacts.run_seed(_BOT, repo)


def _make(
    *,
    run_id: str,
    repo: str,
    file: str,
    kind: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence: list[dict],
    tags: list[str],
    symbol: Optional[str] = None,
) -> dict:
    return artifacts.make_record(
        bot=_BOT, run_id=run_id, kind=kind, summary=summary, severity=severity,
        confidence=confidence, evidence=evidence, tags=tags, target_id=file,
        links={"repo": repo, "file": file, "symbol": symbol, "tests": [], "artifacts": []},
        world_refs=[{"kind": "concept", "id": kind}],
    )


def _display_path(repo: Path, path: Path) -> str:
    return str(path.relative_to(repo) if path.is_relative_to(repo) else path)


def _append_write_collision(
    findings: list[dict],
    *,
    temp_dir: Path,
    worker_count: int,
    run_id: str,
    repo: Path,
    repo_str: str,
) -> None:
    collision_file = temp_dir / "c1_collision.jsonl"
    processes = []
    for i in range(worker_count):
        worker_data = [{"worker": i, "row": r, "msg": "x" * 100} for r in range(100)]
        code = f"""
import json, time
data = {repr(worker_data)}
with open({repr(str(collision_file))}, "a") as f:
    for row in data:
        f.write(json.dumps(row) + "\\n")
        f.flush()
"""
        processes.append(subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ))

    for p in processes:
        p.wait()

    corrupted_lines = 0
    total_lines = 0
    if collision_file.exists():
        with collision_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                try:
                    json.loads(line)
                except Exception:
                    corrupted_lines += 1

    if corrupted_lines > 0 or total_lines < (worker_count * 100):
        findings.append(_make(
            run_id=run_id, repo=repo_str, file=_display_path(repo, collision_file),
            kind="write_collision",
            summary=f"Concurrent write collision: {corrupted_lines} corrupted JSON lines out of {total_lines}",
            severity="critical", confidence=0.9,
            evidence=[
                {"type": "metric", "name": "corrupted_lines", "value": corrupted_lines},
                {"type": "metric", "name": "total_lines", "value": total_lines},
            ],
            tags=["stress", "write-collision", "c1"],
        ))


def _append_read_during_write(
    findings: list[dict],
    *,
    temp_dir: Path,
    worker_count: int,
    run_id: str,
    repo: Path,
    repo_str: str,
) -> None:
    c2_file = temp_dir / "c2_inconsistency.jsonl"
    if c2_file.exists():
        c2_file.unlink()

    writer_code = f"""
import json, time
with open({repr(str(c2_file))}, "w") as f:
    for i in range(1000):
        f.write(json.dumps({{"index": i, "val": "y"*200}}) + "\\n")
        f.flush()
        time.sleep(0.001)
"""
    writer_proc = subprocess.Popen([sys.executable, "-c", writer_code])

    reader_code = f"""
import json, time
failures = 0
for _ in range(50):
    time.sleep(0.005)
    try:
        with open({repr(str(c2_file))}, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
    except Exception:
        failures += 1
print(failures)
"""
    readers = [
        subprocess.Popen(
            [sys.executable, "-c", reader_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(max(1, worker_count - 1))
    ]

    writer_proc.wait()
    total_failures = 0
    for rp in readers:
        out, _ = rp.communicate()
        try:
            total_failures += int(out.strip())
        except Exception:
            pass

    if total_failures > 0:
        findings.append(_make(
            run_id=run_id, repo=repo_str, file=_display_path(repo, c2_file),
            kind="read_during_write",
            summary=f"Read-during-write inconsistency detected: {total_failures} read failures under write load",
            severity="medium", confidence=0.8,
            evidence=[
                {"type": "metric", "name": "read_failures", "value": total_failures},
            ],
            tags=["stress", "read-during-write", "c2"],
        ))


def _append_missing_lock(
    findings: list[dict],
    *,
    temp_dir: Path,
    run_id: str,
    repo: Path,
    repo_str: str,
) -> None:
    c3_file = temp_dir / "c3_lock.json"
    c3_file.write_text(json.dumps({"counter": 0}))

    increment_code = f"""
import json, time
for _ in range(50):
    try:
        with open({repr(str(c3_file))}, "r+") as f:
            data = json.load(f)
            val = data["counter"]
            time.sleep(0.001)  # force race
            f.seek(0)
            f.truncate()
            json.dump({{"counter": val + 1}}, f)
    except Exception:
        pass
"""
    processes = [subprocess.Popen([sys.executable, "-c", increment_code]) for _ in range(2)]
    for cp in processes:
        cp.wait()

    final_val = 0
    try:
        final_val = json.loads(c3_file.read_text())["counter"]
    except Exception:
        pass

    if final_val < 100:
        findings.append(_make(
            run_id=run_id, repo=repo_str, file=_display_path(repo, c3_file),
            kind="missing_lock",
            summary=f"Missing lock/lost updates: expected counter 100, got {final_val}",
            severity="high", confidence=0.9,
            evidence=[
                {"type": "metric", "name": "expected_counter", "value": 100},
                {"type": "metric", "name": "observed_counter", "value": final_val},
            ],
            tags=["stress", "missing-lock", "c3"],
        ))


def _append_recovery_gap(
    findings: list[dict],
    *,
    temp_dir: Path,
    run_id: str,
    repo: Path,
    repo_str: str,
) -> None:
    c4_file = temp_dir / "c4_degraded.jsonl"
    killer_code = f"""
import json, time, sys
with open({repr(str(c4_file))}, "w") as f:
    for i in range(500):
        f.write(json.dumps({{"id": i, "val": "z"*200}}) + "\\n")
        f.flush()
        time.sleep(0.002)
"""
    kp = subprocess.Popen([sys.executable, "-c", killer_code])
    time.sleep(0.05)
    kp.kill()
    kp.wait()

    corrupted_end = False
    lines_read = 0
    if c4_file.exists():
        with c4_file.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                lines_read += 1
                try:
                    json.loads(line)
                except Exception:
                    corrupted_end = True

    if corrupted_end or (0 < lines_read < 500):
        findings.append(_make(
            run_id=run_id, repo=repo_str, file=_display_path(repo, c4_file),
            kind="recovery_gap",
            summary=f"Recovery gap: killed process left truncated/corrupted file with {lines_read} lines",
            severity="high", confidence=0.85,
            evidence=[
                {"type": "metric", "name": "lines_written", "value": lines_read},
                {"type": "trace", "name": "corrupted_end", "value": str(corrupted_end)},
            ],
            tags=["stress", "degraded-dependency", "c4"],
        ))


def _append_cascade_failure(
    findings: list[dict],
    *,
    temp_dir: Path,
    run_id: str,
    repo: Path,
    repo_str: str,
) -> None:
    c5_file = temp_dir / "c5_invalid.jsonl"
    bad_record = {"run_id": "bad-run", "bot": "stress", "severity": "invalid-severity"}
    c5_file.write_text(json.dumps(bad_record) + "\n")

    ok, errs = artifacts.validate_bot_record(bad_record)
    if not ok:
        findings.append(_make(
            run_id=run_id, repo=repo_str, file=_display_path(repo, c5_file),
            kind="cascade_failure",
            summary=f"Cascading failure: invalid record successfully intercepted by validator: {', '.join(errs)}",
            severity="low", confidence=1.0,
            evidence=[
                {"type": "trace", "name": "validation_errors", "value": ", ".join(errs)},
            ],
            tags=["stress", "cascade-failure", "c5"],
        ))


def run(
    repo: Path | str,
    store_path: str,
    run_id: Optional[str] = None,
    worker_count: int = 4,
) -> list[dict]:
    """
    Run stress scenarios C1–C5 against the shared store.
    """
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = "stress:" + _run_seed(repo_str)

    findings: list[dict] = []
    temp_dir = Path(store_path) / f"stress-run-{run_id.split(':')[-1]}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        _append_write_collision(
            findings, temp_dir=temp_dir, worker_count=worker_count,
            run_id=run_id, repo=repo, repo_str=repo_str,
        )
        _append_read_during_write(
            findings, temp_dir=temp_dir, worker_count=worker_count,
            run_id=run_id, repo=repo, repo_str=repo_str,
        )
        _append_missing_lock(
            findings, temp_dir=temp_dir, run_id=run_id, repo=repo,
            repo_str=repo_str,
        )
        _append_recovery_gap(
            findings, temp_dir=temp_dir, run_id=run_id, repo=repo,
            repo_str=repo_str,
        )
        _append_cascade_failure(
            findings, temp_dir=temp_dir, run_id=run_id, repo=repo,
            repo_str=repo_str,
        )
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    return findings
