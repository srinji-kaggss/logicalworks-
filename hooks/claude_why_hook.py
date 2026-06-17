#!/usr/bin/env python3
"""Claude PostToolUse hook — nudges for //why annotations.

Reads Claude Code's PostToolUse JSON payload on stdin:
  {"tool_name": "...", "tool_input": {...}, "tool_response": {...}}

If a code file was modified, prints a nudge to stdout.
Also emits an annotation_nudge event to the daemon store if available.

FAIL-SILENT by law: any error -> exit 0 (INV-6). A hook must never block.
"""
import json
import os
import sys
from pathlib import Path

CODE_EXTENSIONS = {'.py', '.rs', '.go', '.js', '.ts', '.c', '.cpp', '.h', '.hpp', '.sh', '.md'}

def is_code_file(path: str) -> bool:
    return any(path.endswith(ext) for ext in CODE_EXTENSIONS)

def _emit(repo_root: Path, tool_name: str, file_path: str, session_id: str) -> None:
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
            lane="telemetry",
            kind="model_output", # Reusing v2 kind
            scope="agent_local",
            payload={
                "nudge": "why_annotation",
                "tool_name": tool_name,
                "file_path": file_path,
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
        
        tool_input = payload.get("tool_input") or {}
        file_path = ""
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path") or tool_input.get("path") or ""
            
        if file_path and is_code_file(file_path):
            # The nudge requested by spec
            print("\n💡 [//why hook] Remember to document non-obvious design decisions using '//why <rationale>' comments in the codebase to prevent reasoning drift.")
            
            # Optional event emission
            repo_root = Path(__file__).resolve().parent.parent
            if (repo_root / "lgwks").exists():
                sys.path.insert(0, str(repo_root))
                transcript = os.environ.get("LGWKS_TRANSCRIPT_PATH", "")
                session_id = Path(transcript).stem if transcript else ""
                _emit(repo_root, tool_name, file_path, session_id)
                
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
