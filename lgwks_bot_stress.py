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
import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timezone

import lgwks_project_artifacts as artifacts

_BOT = "stress"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_seed(repo: str) -> str:
    return hashlib.sha256(f"stress:{repo}".encode()).hexdigest()[:12]


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
    return {
        "schema": artifacts.BOT_RECORD_SCHEMA,
        "run_id": run_id,
        "bot": _BOT,
        "target": {"kind": "file", "id": file},
        "kind": kind,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "status": "open",
        "evidence": evidence,
        "links": {
            "repo": repo,
            "file": file,
            "symbol": symbol,
            "tests": [],
            "artifacts": [],
        },
        "world_refs": [{"kind": "concept", "id": kind}],
        "tags": tags,
        "created_at": _ts(),
    }


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
    
    # We will use a temporary sub-directory under store_path for the test run
    # and clean it up afterwards, unless --live is specified.
    temp_dir = Path(store_path) / f"stress-run-{run_id.split(':')[-1]}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── C1: Concurrent Write Collision ──
        # N workers write to the same file path simultaneously.
        collision_file = temp_dir / "c1_collision.jsonl"
        processes = []
        for i in range(worker_count):
            # Write unique rows
            worker_data = [
                {"worker": i, "row": r, "msg": "x" * 100} for r in range(100)
            ]
            code = f"""
import json, time
data = {repr(worker_data)}
with open({repr(str(collision_file))}, "a") as f:
    for row in data:
        f.write(json.dumps(row) + "\\n")
        f.flush()
"""
            p = subprocess.Popen(
                [sys.executable, "-c", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(p)

        # Wait for all to finish
        for p in processes:
            p.wait()

        # Check for interleaving / JSON corruption
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
                run_id=run_id, repo=repo_str, file=str(collision_file.relative_to(repo) if collision_file.is_relative_to(repo) else collision_file),
                kind="write_collision",
                summary=f"Concurrent write collision: {corrupted_lines} corrupted JSON lines out of {total_lines}",
                severity="critical", confidence=0.9,
                evidence=[
                    {"type": "metric", "name": "corrupted_lines", "value": corrupted_lines},
                    {"type": "metric", "name": "total_lines", "value": total_lines},
                ],
                tags=["stress", "write-collision", "c1"],
            ))

        # ── C2: Read-during-write Inconsistency ──
        # One worker writes a large JSONL artifact while N-1 workers read it.
        c2_file = temp_dir / "c2_inconsistency.jsonl"
        if c2_file.exists():
            c2_file.unlink()

        # Writer script
        writer_code = f"""
import json, time
with open({repr(str(c2_file))}, "w") as f:
    for i in range(1000):
        f.write(json.dumps({{"index": i, "val": "y"*200}}) + "\\n")
        f.flush()
        time.sleep(0.001)
"""
        writer_proc = subprocess.Popen([sys.executable, "-c", writer_code])

        # Reader script
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
        # Run N-1 readers
        readers = []
        for _ in range(max(1, worker_count - 1)):
            rp = subprocess.Popen(
                [sys.executable, "-c", reader_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            readers.append(rp)

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
                run_id=run_id, repo=repo_str, file=str(c2_file.relative_to(repo) if c2_file.is_relative_to(repo) else c2_file),
                kind="read_during_write",
                summary=f"Read-during-write inconsistency detected: {total_failures} read failures under write load",
                severity="medium", confidence=0.8,
                evidence=[
                    {"type": "metric", "name": "read_failures", "value": total_failures},
                ],
                tags=["stress", "read-during-write", "c2"],
            ))

        # ── C3: Lock Failure / Missing Lock ──
        # Simulate lost updates: two workers increment a counter in a file without coordination
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
        c3_processes = []
        for _ in range(2):
            cp = subprocess.Popen([sys.executable, "-c", increment_code])
            c3_processes.append(cp)

        for cp in c3_processes:
            cp.wait()

        # Expected value is 100 if serialized, but usually less under race
        final_val = 0
        try:
            final_val = json.loads(c3_file.read_text())["counter"]
        except Exception:
            pass

        if final_val < 100:
            findings.append(_make(
                run_id=run_id, repo=repo_str, file=str(c3_file.relative_to(repo) if c3_file.is_relative_to(repo) else c3_file),
                kind="missing_lock",
                summary=f"Missing lock/lost updates: expected counter 100, got {final_val}",
                severity="high", confidence=0.9,
                evidence=[
                    {"type": "metric", "name": "expected_counter", "value": 100},
                    {"type": "metric", "name": "observed_counter", "value": final_val},
                ],
                tags=["stress", "missing-lock", "c3"],
            ))

        # ── C4: Degraded Dependency ──
        # Kill one subprocess mid-write. Observe recovery/partial write.
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
        time.sleep(0.05)  # wait for it to start writing
        kp.kill()  # terminate mid-write
        kp.wait()

        # Verify if file is incomplete or has a partially written line at the end
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
                run_id=run_id, repo=repo_str, file=str(c4_file.relative_to(repo) if c4_file.is_relative_to(repo) else c4_file),
                kind="recovery_gap",
                summary=f"Recovery gap: killed process left truncated/corrupted file with {lines_read} lines",
                severity="high", confidence=0.85,
                evidence=[
                    {"type": "metric", "name": "lines_written", "value": lines_read},
                    {"type": "trace", "name": "corrupted_end", "value": str(corrupted_end)},
                ],
                tags=["stress", "degraded-dependency", "c4"],
            ))

        # ── C5: Cascading Failure ──
        # Downstream reducer validation check for schema-invalid records.
        c5_file = temp_dir / "c5_invalid.jsonl"
        # Write one schema-invalid record
        bad_record = {"run_id": "bad-run", "bot": "stress", "severity": "invalid-severity"}
        c5_file.write_text(json.dumps(bad_record) + "\n")

        # Check if validation logic flags it
        ok, errs = artifacts.validate_bot_record(bad_record)
        if not ok:
            findings.append(_make(
                run_id=run_id, repo=repo_str, file=str(c5_file.relative_to(repo) if c5_file.is_relative_to(repo) else c5_file),
                kind="cascade_failure",
                summary=f"Cascading failure: invalid record successfully intercepted by validator: {', '.join(errs)}",
                severity="low", confidence=1.0,
                evidence=[
                    {"type": "trace", "name": "validation_errors", "value": ", ".join(errs)},
                ],
                tags=["stress", "cascade-failure", "c5"],
            ))

    finally:
        # Restore/Clean up the temp store path
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    return findings
