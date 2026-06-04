"""
lgwks_agent_os — fleet startup/bootstrap helpers for the Logical Works prompt layer (#1).

The prompt bundle under vision/prompts is the shared startup surface for every agent, but the old
layout depended on machine-local absolute symlinks. This module makes that layer explicit:

  * manifest-driven context bootstrap for prompts/context/
  * doctor checks for startup files, context links, and native role subagents
  * agent-card emission for the cross-spawn roles (A2A-style metadata)

It stays stdlib-only and never shells out. The point is portability + verifiability, not ceremony.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS_ROOT = ROOT / "vision" / "prompts"
CONTEXT_DIR = PROMPTS_ROOT / "context"
MANIFEST_PATH = CONTEXT_DIR / "manifest.json"
AGENT_CARD_PATH = PROMPTS_ROOT / "agent_cards.json"

ROLE_SUBAGENTS = ("architect", "coder", "hacker", "qa-refiner", "orchestrator")
PROMPT_FILES = ("GLOBAL.md", "_doctrine.md")


@dataclass(frozen=True)
class ContextTarget:
    name: str
    kind: str
    required: bool
    resolved: Path | None
    raw: dict


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
    args = p.parse_args(argv)
    if args.command == "bootstrap":
        write_agent_cards()
        print(json.dumps({"results": bootstrap_context()}, indent=2))
        return 0
    if args.command == "cards":
        out = write_agent_cards()
        print(str(out))
        return 0
    print(json.dumps(doctor(), indent=2))
    return 0 if doctor()["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
