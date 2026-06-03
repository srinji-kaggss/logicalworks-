# Spec: feat(agent-os): implement sticky scope-creep guard [N6]

## 1. Intent & Requirements
- **Goal**: Implement a sticky `PreToolUse` hook for Claude Code to intercept scope creep during agent runs.
- **Trigger**: When an agent attempts to edit files or run commands outside the configured active scope.
- **Behavior**:
  - Intercept tool invocation via `PreToolUse` event.
  - Read `.lgwks/active-scope.json` from the repository root.
  - If the tool targets a file or command not listed in the active scope, print a clear warning to `stderr` identifying the downstream nodes/scope creep and exit with code `2` (blocking the tool execution).
  - Provide a reminder to the agent to ask the user for logging/sequencing before proceeding.

## 2. Design & Implementation
- **Hook Config**: Add the hook to `PreToolUse` event in `~/.claude/settings.json`.
- **Hook Script**: Implement `~/.claude/hooks/scope-creep-guard.py`.
- **Activation file**: `.lgwks/active-scope.json` in repository root.

### `~/.claude/hooks/scope-creep-guard.py` Implementation Details:
- Standard input parses the JSON event payload: `{"tool_name": "...", "tool_input": "...", "cwd": "..."}`.
- Resolve absolute and relative paths for files.
- Compare commands against prefix allowlists.
- If invalid, print to `stderr`:
  `[SCOPE CREEP DETECTED] Attempted to use tool '{tool_name}' on unauthorized target. Downstream nodes: {target}. Please stop and ask the user to log/sequence this work before proceeding.`
- Exit with code `2` to block.
