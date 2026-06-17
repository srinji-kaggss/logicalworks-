#!/usr/bin/env python3
"""Claude PreToolUse hook — blocks scope creep.

Reads Claude Code's PreToolUse JSON payload on stdin:
  {"tool_name": "...", "tool_input": {...}, "cwd": "..."}

Checks against .lgwks/active-scope.json in repo root.
If unauthorized, prints a warning to stderr and exits with code 2 to block.
Otherwise, exits with code 0 to allow.

Also emits a scope_creep_blocked event to the daemon store if blocked.
"""
import json
import os
import sys
from pathlib import Path

def _emit_blocked(repo_root: Path, tool_name: str, target: str, session_id: str) -> None:
    try:
        import lgwks_daemon_event
        from lgwks_daemon_store import DaemonEventStore
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        if not db.parent.exists():
            return
        tenant_id = f"repo:{repo_root.name}"
        event = lgwks_daemon_event.build_event(
            tenant_id=tenant_id,
            agent_id="claude",
            session_id=session_id or f"claude:{repo_root.name}",
            actor="system",
            client="claude",
            lane="control",
            kind="workflow_event",
            scope="agent_local",
            payload={
                "action": "scope_creep_blocked",
                "tool_name": tool_name,
                "target": target,
            },
            source="terminal",
            trust="deterministic",
        )
        store = DaemonEventStore(db)
        try:
            store.append(event)
        finally:
            store.close()
    except Exception:
        pass

def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
        if not tool_name:
            return 0
        
        cwd = payload.get("cwd") or os.getcwd()
        repo_root = Path(cwd).resolve()
        # Find repo root if in subdirectory
        while repo_root != repo_root.parent and not (repo_root / ".git").exists() and not (repo_root / "lgwks").exists():
            repo_root = repo_root.parent
            
        scope_file = repo_root / ".lgwks" / "active-scope.json"
        if not scope_file.exists():
            return 0
            
        scope = json.loads(scope_file.read_text())
        allowed_files = scope.get("files", [])
        allowed_commands = scope.get("commands", [])
        
        tool_input = payload.get("tool_input") or {}
        target = ""
        is_blocked = False
        
        # 1. Check file/dir access
        if tool_name in ["read_file", "write_file", "replace", "list_directory", "grep_search", "glob"]:
            target = tool_input.get("file_path") or tool_input.get("dir_path") or tool_input.get("pattern") or ""
            if target and allowed_files:
                # Basic check: target must be under one of the allowed paths
                target_abs = Path(target).resolve()
                is_allowed = False
                for allowed in allowed_files:
                    allowed_abs = (repo_root / allowed).resolve()
                    try:
                        if target_abs.is_relative_to(allowed_abs):
                            is_allowed = True
                            break
                    except ValueError:
                        continue
                if not is_allowed:
                    is_blocked = True

        # 2. Check command access
        if tool_name == "run_shell_command":
            cmd = tool_input.get("command") or ""
            if cmd and allowed_commands:
                is_allowed = False
                for allowed in allowed_commands:
                    if cmd.startswith(allowed):
                        is_allowed = True
                        break
                if not is_allowed:
                    target = cmd
                    is_blocked = True

        if is_blocked:
            msg = f"[SCOPE CREEP DETECTED] Attempted to use tool '{tool_name}' on unauthorized target. Downstream nodes: {target}. Please stop and ask the user to log/sequence this work before proceeding."
            print(msg, file=sys.stderr)
            
            # Optional event emission
            if (repo_root / "lgwks").exists():
                sys.path.insert(0, str(repo_root))
                transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
                session_id = Path(transcript).stem if transcript else ""
                _emit_blocked(repo_root, tool_name, target, session_id)
            
            return 2 # Blocking code
                
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
