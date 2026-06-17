#!/usr/bin/env python3
"""lgwks_subconscious_hook — vendor-agnostic agent observer.

This script is the unified entry point for any CLI agent (Claude, Gemini, Codex)
to report tool usage and enforce governance rules.

Usage (generic):
  python3 lgwks_subconscious_hook.py <stage> <payload_json>

Stages:
  pre_tool  — Enforces scope guard (Issue #3). Blocks if unauthorized (exit 2).
  post_tool — Enforces //why nudge (Issue #2) and emits telemetry (exit 0).

Environment:
  LGWKS_AGENT_ID  — Name of the agent (e.g., 'claude', 'gemini'). Default: 'unknown'.
  LGWKS_TENANT_ID — The current tenant/repo.
"""
import json
import os
import sys
from pathlib import Path

# Constants from lgwks core
CODE_EXTENSIONS = {'.py', '.rs', '.go', '.js', '.ts', '.c', '.cpp', '.h', '.hpp', '.sh', '.md'}

def is_code_file(path: str) -> bool:
    return any(path.endswith(ext) for ext in CODE_EXTENSIONS)

def _get_repo_root(cwd: str) -> Path:
    p = Path(cwd).resolve()
    while p != p.parent:
        if (p / "lgwks").exists() or (p / ".git").exists():
            return p
        p = p.parent
    return Path(cwd).resolve()

def _emit(repo_root: Path, stage: str, tool_name: str, payload: dict, trust="model_proposed") -> None:
    """Emit a normalized event to the daemon store."""
    try:
        sys.path.insert(0, str(repo_root))
        import lgwks_daemon_event
        from lgwks_daemon_store import DaemonEventStore
        
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        if not db.parent.exists():
            return

        agent_id = os.environ.get("LGWKS_AGENT_ID", "unknown")
        tenant_id = os.environ.get("LGWKS_TENANT_ID", f"repo:{repo_root.name}")
        transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
        session_id = Path(transcript).stem if transcript else f"session-{os.getpid()}"

        event = lgwks_daemon_event.build_event(
            tenant_id=tenant_id,
            agent_id=agent_id,
            session_id=session_id,
            actor="agent",
            client=agent_id,
            lane="control" if stage == "pre_tool" else "telemetry",
            kind="workflow_event" if stage == "pre_tool" else "tool_call",
            scope="agent_local",
            payload=payload,
            source="model",
            trust=trust,
        )
        store = DaemonEventStore(db)
        try:
            store.append(event)
        finally:
            store.close()
    except Exception:
        pass # Hooks must NEVER block the user if the daemon is down

def handle_pre_tool(repo_root: Path, tool_name: str, tool_input: dict) -> int:
    """Enforce Issue #3: Scope Creep Guard."""
    scope_file = repo_root / ".lgwks" / "active-scope.json"
    if not scope_file.exists():
        return 0

    try:
        scope = json.loads(scope_file.read_text())
        allowed_files = scope.get("files", [])
        allowed_commands = scope.get("commands", [])
        
        target = ""
        is_blocked = False
        
        # Check files
        if tool_name in ["read_file", "write_file", "replace", "list_directory", "grep_search", "glob"]:
            target = tool_input.get("file_path") or tool_input.get("dir_path") or tool_input.get("pattern") or ""
            if target and allowed_files:
                target_abs = Path(target).resolve()
                if not any(target_abs.is_relative_to((repo_root / f).resolve()) for f in allowed_files):
                    is_blocked = True

        # Check commands
        if tool_name == "run_shell_command":
            cmd = tool_input.get("command") or ""
            if cmd and allowed_commands:
                if not any(cmd.startswith(c) for f in allowed_commands):
                    target = cmd
                    is_blocked = True

        if is_blocked:
            print(f"[SCOPE CREEP DETECTED] Unauthorized use of {tool_name} on {target}.", file=sys.stderr)
            _emit(repo_root, "pre_tool", tool_name, {"blocked": True, "target": target}, trust="deterministic")
            return 2
            
    except Exception:
        pass
    return 0

def handle_post_tool(repo_root: Path, tool_name: str, tool_input: dict) -> int:
    """Enforce Issue #2: //why nudge."""
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if file_path and is_code_file(file_path):
        print("\n💡 [subconscious] Document non-obvious decisions with '//why <rationale>' to prevent reasoning drift.")
        _emit(repo_root, "post_tool", tool_name, {"nudge": "why_annotation", "path": file_path})
    return 0

def main():
    if len(sys.argv) < 2:
        return 0
        
    stage = sys.argv[1] # 'pre_tool' or 'post_tool'
    try:
        # Many CLIs pipe JSON to stdin for hooks
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    repo_root = _get_repo_root(cwd)

    if stage == "pre_tool":
        sys.exit(handle_pre_tool(repo_root, tool_name, tool_input))
    elif stage == "post_tool":
        sys.exit(handle_post_tool(repo_root, tool_name, tool_input))
    
    return 0

if __name__ == "__main__":
    main()
