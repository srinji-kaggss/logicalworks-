"""
lgwks_agent_os — fleet startup/bootstrap helpers for the Logical Works prompt layer (#1).

The prompt bundle under vision/prompts is the shared startup surface for every agent, but the old
layout depended on machine-local absolute symlinks. This module makes that layer explicit:

  * manifest-driven context bootstrap for prompts/context/
  * doctor checks for startup files, context links, and native role subagents
  * agent-card emission for the cross-spawn roles (A2A-style metadata)
  * FleetOrchestrator — single-node prototype for spawning agents in isolated git worktrees,
    passing scoped prompts, and collecting structured output

Historical constraint (bootstrap/doctor/cards): stdlib-only and never shells out.
FleetOrchestrator intentionally shells out to git for worktree lifecycle management.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROMPTS_ROOT = ROOT / "vision" / "prompts"
CONTEXT_DIR = PROMPTS_ROOT / "context"
MANIFEST_PATH = CONTEXT_DIR / "manifest.json"
AGENT_CARD_PATH = PROMPTS_ROOT / "agent_cards.json"

# FleetOrchestrator defaults
_FLEET_DIR = ROOT / ".fleet"
_AUDIT_LOG = ROOT / ".lgwks" / "fleet-audit.jsonl"

ROLE_SUBAGENTS = ("architect", "coder", "hacker", "qa-refiner", "orchestrator")
PROMPT_FILES = ("GLOBAL.md", "_doctrine.md")


@dataclass(frozen=True)
class ContextTarget:
    name: str
    kind: str
    required: bool
    resolved: Path | None
    raw: dict


# ---------------------------------------------------------------------------
# Agent manifest parsing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AgentManifest:
    id: str
    name: str
    home_template: str
    branch_template: str
    capabilities: list[str]
    raw: dict


def _parse_agent_manifest(path: Path) -> AgentManifest:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    name = path.stem
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        name = m.group(1).strip()

    home = ""
    branch = ""
    in_home = False
    for line in lines:
        if line.strip().startswith("## Home + isolation"):
            in_home = True
            continue
        if in_home:
            if line.strip().startswith("##"):
                break
            hm = re.search(r"Work in `([^`]+)`", line)
            if hm:
                home = hm.group(1)
            bm = re.search(r"\(branch `([^`]+)`\)", line)
            if bm:
                branch = bm.group(1)

    caps: list[str] = []
    cap_m = re.search(r"\*\*Capabilities:\*\*\s*\[(.*?)\]", text)
    if cap_m:
        caps = [c.strip().strip('"') for c in cap_m.group(1).split(",") if c.strip()]

    return AgentManifest(
        id=path.stem,
        name=name,
        home_template=home,
        branch_template=branch,
        capabilities=caps,
        raw={"path": str(path), "stem": path.stem},
    )


# ---------------------------------------------------------------------------
# Fleet orchestration primitives
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SpawnRecord:
    agent_id: str
    worktree_path: Path
    branch: str
    timestamp: float
    status: str          # queued | running | completed | failed | closed
    prompt_hash: str
    context_hash: str
    detail: str | None = None


class FleetOrchestrator:
    """Minimal single-node fleet orchestrator.

    Spawns agents in isolated git worktrees, passes scoped prompts + context JSON,
    reads structured output, and emits fleet-audit.jsonl records.

    Multi-node migration path (documented in docs/ARCHITECTURE.md):
      1. Replace local _git() calls with gRPC/HTTP agent client.
      2. Replace local worktrees with container sandboxes or VM partitions.
      3. Centralise audit logging via message bus (NATS / Kafka / Redis Streams).
    """

    def __init__(
        self,
        repo_root: Path = ROOT,
        agents_dir: Path | None = None,
        fleet_dir: Path | None = None,
        audit_log: Path | None = None,
    ):
        self.repo_root = repo_root.resolve()
        self.agents_dir = (agents_dir or PROMPTS_ROOT / "agents").resolve()
        self.fleet_dir = (fleet_dir or _FLEET_DIR).resolve()
        self.audit_log = (audit_log or _AUDIT_LOG).resolve()
        self._agents_cache: dict[str, AgentManifest] | None = None

    # ------------------------------------------------------------------
    # Git plumbing (single-node prototype)
    # ------------------------------------------------------------------
    def _git(self, *args: str, cwd: Path | None = None, timeout: int = 30) -> tuple[int, str]:
        target = cwd or self.repo_root
        try:
            p = subprocess.run(
                ["git", "-C", str(target), *args],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
            return p.returncode, (p.stdout or "").strip()
        except Exception as e:
            return 1, f"<git failed: {e}>"

    # ------------------------------------------------------------------
    # Agent manifests
    # ------------------------------------------------------------------
    def scan_agents(self, force: bool = False) -> dict[str, AgentManifest]:
        if self._agents_cache is not None and not force:
            return self._agents_cache
        agents: dict[str, AgentManifest] = {}
        if self.agents_dir.exists():
            for path in sorted(self.agents_dir.glob("*.md")):
                try:
                    manifest = _parse_agent_manifest(path)
                    agents[manifest.id] = manifest
                except Exception:
                    continue
        self._agents_cache = agents
        return agents

    # ------------------------------------------------------------------
    # Worktree lifecycle
    # ------------------------------------------------------------------
    def spawn(
        self,
        agent_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        branch_prefix: str = "fleet",
    ) -> SpawnRecord:
        """Create a unique git worktree for *agent_id*, stage inputs, and audit."""
        agents = self.scan_agents()
        if agent_id not in agents:
            raise ValueError(f"unknown agent_id: {agent_id!r}")

        context = context or {}
        ts = time.time()
        uid = uuid.uuid4().hex[:8]
        branch = f"{branch_prefix}/{agent_id}/{uid}"
        worktree = self.fleet_dir / "worktrees" / f"{agent_id}-{uid}"

        # Ensure clean state
        if worktree.exists():
            self._git("worktree", "remove", "-f", str(worktree))

        # Create worktree
        rc, out = self._git("worktree", "add", "-b", branch, str(worktree))
        if rc != 0:
            record = SpawnRecord(
                agent_id=agent_id,
                worktree_path=worktree,
                branch=branch,
                timestamp=ts,
                status="failed",
                prompt_hash=_sha256(prompt),
                context_hash=_sha256(json.dumps(context, sort_keys=True)),
                detail=f"git worktree add failed: {out}",
            )
            self._audit(record)
            raise RuntimeError(f"worktree creation failed for {agent_id}: {out}")

        # Stage inputs
        fleet_meta = worktree / ".fleet"
        fleet_meta.mkdir(parents=True, exist_ok=True)
        (worktree / "prompt.md").write_text(prompt, encoding="utf-8")
        (fleet_meta / "context.json").write_text(
            json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (fleet_meta / "spawn.json").write_text(
            json.dumps({
                "agent_id": agent_id,
                "branch": branch,
                "timestamp": ts,
                "prompt_hash": _sha256(prompt),
                "context_hash": _sha256(json.dumps(context, sort_keys=True)),
            }, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        record = SpawnRecord(
            agent_id=agent_id,
            worktree_path=worktree,
            branch=branch,
            timestamp=ts,
            status="queued",
            prompt_hash=_sha256(prompt),
            context_hash=_sha256(json.dumps(context, sort_keys=True)),
        )
        self._audit(record)
        return record

    def collect(self, record: SpawnRecord) -> dict[str, Any]:
        """Read structured output from the agent worktree."""
        output_path = record.worktree_path / ".fleet" / "output.json"
        result: dict[str, Any] = {"agent_id": record.agent_id, "worktree": str(record.worktree_path)}
        if output_path.exists():
            try:
                result["output"] = json.loads(output_path.read_text(encoding="utf-8"))
                result["status"] = "collected"
            except Exception as exc:
                result["status"] = "parse_error"
                result["error"] = str(exc)
        else:
            result["status"] = "pending"
        self._audit(SpawnRecord(
            agent_id=record.agent_id,
            worktree_path=record.worktree_path,
            branch=record.branch,
            timestamp=time.time(),
            status=result["status"],
            prompt_hash=record.prompt_hash,
            context_hash=record.context_hash,
            detail=f"collect: {result.get('status')}",
        ))
        return result

    def close(self, record: SpawnRecord) -> None:
        """Remove the worktree and prune the branch."""
        rc, out = self._git("worktree", "remove", "-f", str(record.worktree_path))
        # Best-effort branch deletion
        self._git("branch", "-D", record.branch)
        self._audit(SpawnRecord(
            agent_id=record.agent_id,
            worktree_path=record.worktree_path,
            branch=record.branch,
            timestamp=time.time(),
            status="closed",
            prompt_hash=record.prompt_hash,
            context_hash=record.context_hash,
            detail=None if rc == 0 else f"remove stderr: {out}",
        ))

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _audit(self, record: SpawnRecord) -> None:
        try:
            self.audit_log.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "ts": time.time(),
                "event": "spawn" if record.status == "queued" else "collect" if record.status in ("collected", "pending", "parse_error") else "close" if record.status == "closed" else record.status,
                "agent_id": record.agent_id,
                "branch": record.branch,
                "worktree": str(record.worktree_path),
                "prompt_hash": record.prompt_hash,
                "context_hash": record.context_hash,
                "status": record.status,
                "detail": record.detail,
            }
            line = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            with self.audit_log.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(self.audit_log, 0o600)
        except Exception:
            pass  # audit loss is non-blocking


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _fleet_home() -> Path:
    raw = os.environ.get("LGWKS_FLEET_HOME", "").strip()
    return Path(raw).expanduser() if raw else (Path.home() / "sales-landing-page")


def _claude_agents_dir() -> Path:
    home = os.environ.get("HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home()
    return base / ".claude" / "agents"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("entries"), list):
        raise ValueError("manifest entries must be a list")
    return data


def resolve_manifest_entries(manifest: dict | None = None) -> list[ContextTarget]:
    manifest = manifest or load_manifest()
    out: list[ContextTarget] = []
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("manifest entry must be an object")
        name = str(entry.get("name", "")).strip()
        kind = str(entry.get("kind", "")).strip()
        required = bool(entry.get("required", True))
        resolved: Path | None
        if kind == "relative":
            resolved = (CONTEXT_DIR / str(entry["path"])).resolve()
        elif kind == "fleet-home":
            resolved = (_fleet_home() / str(entry["path"])).resolve()
        else:
            raise ValueError(f"unknown manifest entry kind: {kind!r}")
        out.append(ContextTarget(name=name, kind=kind, required=required, resolved=resolved, raw=entry))
    return out


def bootstrap_context() -> list[dict]:
    """Create/refresh prompts/context symlinks from the manifest."""
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for target in resolve_manifest_entries():
        link = CONTEXT_DIR / target.name
        if link.is_symlink() or link.exists():
            link.unlink()
        if target.resolved is None or not target.resolved.exists():
            results.append({"name": target.name, "status": "missing", "path": str(target.resolved or "")})
            continue
        rel = (
            os.path.relpath(target.resolved, CONTEXT_DIR.resolve())
            if target.kind == "relative"
            else str(target.resolved)
        )
        os.symlink(rel, link)
        results.append({"name": target.name, "status": "linked", "path": str(target.resolved)})
    return results


def _agent_card_payload() -> dict:
    return {
        "schema": "logicalworks.agent-cards/1",
        "protocol": "A2A/1.0",
        "roles": [
            {
                "id": "orchestrator",
                "label": "Orchestrator",
                "capabilities": ["plan", "spawn_peer", "synthesize", "issue_gate"],
                "spawns": ["architect", "coder", "hacker", "qa-refiner"],
            },
            {
                "id": "architect",
                "label": "Architect",
                "capabilities": ["design", "adr", "risk_model", "spawn_peer"],
                "spawns": ["coder", "hacker", "qa-refiner"],
            },
            {
                "id": "coder",
                "label": "Coder",
                "capabilities": ["implement", "test", "refactor", "spawn_peer"],
                "spawns": ["architect", "hacker", "qa-refiner"],
            },
            {
                "id": "hacker",
                "label": "Hacker",
                "capabilities": ["adversarial_review", "trust_boundary_review", "spawn_peer"],
                "spawns": ["architect", "coder", "qa-refiner"],
            },
            {
                "id": "qa-refiner",
                "label": "QA Refiner",
                "capabilities": ["acceptance", "evidence", "regression_review", "spawn_peer"],
                "spawns": ["architect", "coder", "hacker"],
            },
        ],
    }


def write_agent_cards(path: Path = AGENT_CARD_PATH) -> Path:
    path.write_text(json.dumps(_agent_card_payload(), indent=2) + "\n", encoding="utf-8")
    return path


def doctor() -> dict:
    manifest = load_manifest()
    entries = resolve_manifest_entries(manifest)
    startup_files = {name: (PROMPTS_ROOT / name).exists() for name in PROMPT_FILES}
    context = []
    for entry in entries:
        link = CONTEXT_DIR / entry.name
        link_ok = link.is_symlink() and link.resolve().exists()
        context.append({
            "name": entry.name,
            "required": entry.required,
            "target_exists": bool(entry.resolved and entry.resolved.exists()),
            "link_ok": link_ok,
            "resolved": str(entry.resolved) if entry.resolved else "",
        })
    agents_dir = _claude_agents_dir()
    subagents = {role: (agents_dir / f"{role}.md").exists() for role in ROLE_SUBAGENTS}
    cards_ok = AGENT_CARD_PATH.exists()
    ok = (
        all(startup_files.values())
        and all(item["link_ok"] or (not item["required"] and not item["target_exists"]) for item in context)
        and all(subagents.values())
        and cards_ok
    )
    return {
        "ok": ok,
        "manifest_schema": manifest.get("schema", ""),
        "startup_files": startup_files,
        "context": context,
        "role_subagents": subagents,
        "agent_cards": str(AGENT_CARD_PATH),
        "agent_cards_present": cards_ok,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lgwks_agent_os", description="fleet startup/bootstrap helpers")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="create/refresh prompts/context symlinks from the manifest")
    sub.add_parser("doctor", help="verify startup prompt bundle, context links, and role subagents")
    sub.add_parser("cards", help="write role agent cards")
    # Fleet commands
    fleet_parser = sub.add_parser("fleet", help="fleet orchestrator commands")
    fleet_sub = fleet_parser.add_subparsers(dest="fleet_command", required=True)
    fleet_sub.add_parser("agents", help="list parsed agent manifests")
    spawn_p = fleet_sub.add_parser("spawn", help="spawn an agent in a git worktree")
    spawn_p.add_argument("--agent", required=True, help="agent id to spawn")
    spawn_p.add_argument("--prompt", required=True, help="path to prompt markdown file")
    spawn_p.add_argument("--context", help="path to context JSON file")
    fleet_sub.add_parser("audit", help="show last fleet-audit.jsonl entries")
    args = p.parse_args(argv)
    if args.command == "bootstrap":
        write_agent_cards()
        print(json.dumps({"results": bootstrap_context()}, indent=2))
        return 0
    if args.command == "cards":
        out = write_agent_cards()
        print(str(out))
        return 0
    if args.command == "fleet":
        orch = FleetOrchestrator()
        if args.fleet_command == "agents":
            agents = orch.scan_agents()
            print(json.dumps({"agents": [{"id": a.id, "name": a.name, "branch": a.branch_template} for a in agents.values()]}, indent=2))
            return 0
        if args.fleet_command == "spawn":
            prompt = Path(args.prompt).read_text(encoding="utf-8")
            ctx = {}
            if args.context:
                ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
            record = orch.spawn(args.agent, prompt, ctx)
            print(json.dumps({
                "agent_id": record.agent_id,
                "branch": record.branch,
                "worktree": str(record.worktree_path),
                "status": record.status,
            }, indent=2))
            return 0
        if args.fleet_command == "audit":
            log = _AUDIT_LOG
            lines = []
            if log.exists():
                lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
            print(json.dumps({"count": len(lines), "last": lines[-10:]}, indent=2))
            return 0
    print(json.dumps(doctor(), indent=2))
    return 0 if doctor()["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
