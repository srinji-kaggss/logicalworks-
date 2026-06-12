# gemini-event

## Overview

Directory-based community: lgwks_daemon_event

- **Size**: 11 nodes
- **Cohesion**: 0.1868
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 38-39 |
| _require_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 42-45 |
| _require_choice | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 48-52 |
| _canonical_body | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 55-56 |
| _event_id_for | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 59-62 |
| validate_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 65-109 |
| build_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 112-153 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 156-176 |
| _build_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 179-197 |
| _validate_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 200-204 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py | 207-212 |

## Execution Flows

- **_validate_command** (criticality: 0.49, depth: 2)
- **_build_command** (criticality: 0.41, depth: 3)

## Dependencies

### Outgoing

- `add_argument` (12 edge(s))
- `ValueError` (9 edge(s))
- `sorted` (7 edge(s))
- `dumps` (5 edge(s))
- `isinstance` (4 edge(s))
- `loads` (2 edge(s))
- `print` (2 edge(s))
- `replace` (2 edge(s))
- `join` (2 edge(s))
- `add_subparsers` (2 edge(s))
- `set_defaults` (2 edge(s))
- `hexdigest` (1 edge(s))
- `blake2b` (1 edge(s))
- `encode` (1 edge(s))
- `isoformat` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_event.py` (12 edge(s))
