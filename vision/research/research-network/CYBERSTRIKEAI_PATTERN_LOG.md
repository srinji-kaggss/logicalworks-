# CyberStrikeAI Pattern Log

Source repo inspected: `/Users/srinji/CyberStrikeAI`

## Adopted

- **Tool manifest shape**: one file per tool, explicit name, command, enabled flag, short description, long description, and typed parameters.
- **Audit API shape**: summary, filters, pagination, export caps, and resource availability checks.
- **HITL shape**: pending interrupt rows, runtime config, mode normalization, approval/review-edit/reject, and orphan cancellation on restart.
- **Task event bus shape**: non-blocking publish, per-conversation subscribers, and close-on-completion semantics.
- **Knowledge-base shape**: source material as durable records, not transient prompt context.

## Rejected For This Bot

- Offensive tool execution.
- C2/session/tasking primitives.
- Automatic execution of arbitrary shell/Python from research output.
- AI-controlled mutation of graph facts.

## Translation

CyberStrikeAI is useful here because it treats AI as an orchestrator over auditable tools. LGWKS Research Network narrows that idea:

- research acquisition is a tool;
- graph compilation is a compiler;
- advisory reasoning is sandboxed;
- HITL is promotion control;
- SQLite is the shared object index;
- Git versions schemas and command code, not generated research storage.
