# hooks-emit

## Overview

Directory-based community: hooks

- **Size**: 9 nodes
- **Cohesion**: 0.0849
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _emit_daemon_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/codex_inbound.py | 15-38 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/codex_inbound.py | 41-63 |
| _emit_daemon_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/gemini_inbound.py | 15-38 |
| _extract_prompt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/gemini_inbound.py | 41-54 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/gemini_inbound.py | 57-72 |
| _clean | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/subconscious_inbound.py | 20-30 |
| _format_context | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/subconscious_inbound.py | 33-59 |
| _emit_daemon_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/subconscious_inbound.py | 62-86 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/hooks/subconscious_inbound.py | 89-108 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `get` (25 edge(s))
- `Path` (8 edge(s))
- `append` (7 edge(s))
- `join` (6 edge(s))
- `strip` (5 edge(s))
- `len` (4 edge(s))
- `str` (4 edge(s))
- `build_event` (3 edge(s))
- `DaemonEventStore` (3 edge(s))
- `close` (3 edge(s))
- `load` (3 edge(s))
- `resolve` (3 edge(s))
- `insert` (3 edge(s))
- `isinstance` (3 edge(s))
- `split` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/hooks/subconscious_inbound.py` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/hooks/gemini_inbound.py` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/hooks/codex_inbound.py` (3 edge(s))
