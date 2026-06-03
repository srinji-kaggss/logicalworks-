# Spec: feat(agent-os): implement sticky //why hook [N5]

## 1. Intent & Requirements
- **Goal**: Implement a sticky `PostToolUse` hook for Claude Code to remind/nudge coding agents to annotate non-obvious code changes with `//why ...` comments.
- **Trigger**: Runs after any tool modifying a code file (e.g. `.py`, `.rs`, `.go`, `.js`, `.ts`, etc.) finishes execution.
- **Behavior**:
  - Intercept the `PostToolUse` event in `~/.claude/settings.json`.
  - Extract the modified file path from the tool inputs.
  - If a code file was modified, print a non-disruptive nudge/reminder to `stdout`:
    `💡 [//why hook] Remember to document non-obvious design decisions using '//why <rationale>' comments in the codebase to prevent reasoning drift.`
  - Exit with code `0` (non-blocking).

## 2. Design & Implementation
- **Hook Config**: Add the hook to `PostToolUse` event in `~/.claude/settings.json` matching file edit tools.
- **Hook Script**: Implement `~/.claude/hooks/why-annotation-nudge.py`.
