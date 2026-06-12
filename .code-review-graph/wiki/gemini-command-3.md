# gemini-command

## Overview

Directory-based community: lgwks_daemon_store

- **Size**: 30 nodes
- **Cohesion**: 0.2226
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 36-37 |
| _ser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 158-161 |
| DaemonEventStore | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 164-665 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 167-173 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 175-176 |
| append | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 178-218 |
| _touch_session_head | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 220-276 |
| list_events | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 278-305 |
| list_session_heads | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 307-332 |
| enqueue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 336-369 |
| dequeue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 371-410 |
| complete_item | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 412-423 |
| fail_item | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 425-436 |
| queue_depth | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 438-454 |
| get_packet | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 456-483 |
| register_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 488-512 |
| list_runs | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 514-526 |
| mark_run_exported | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 529-543 |
| get_run_export_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 545-557 |
| open_worktree | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 561-592 |
| close_worktree | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 594-607 |
| get_worktree | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 609-627 |
| list_worktrees | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 629-665 |
| _append_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 668-676 |
| _events_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 679-691 |
| _sessions_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 694-701 |
| _enqueue_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 704-712 |
| _queue_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 715-722 |
| _packet_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 725-737 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py | 740-782 |

## Execution Flows

- **_serve_command** (criticality: 0.48, depth: 4)
- **_sessions_command** (criticality: 0.48, depth: 1)
- **_export_verify_command** (criticality: 0.48, depth: 3)
- **_export_session_command** (criticality: 0.48, depth: 3)
- **_research_command** (criticality: 0.46, depth: 3)
- **_enqueue_command** (criticality: 0.46, depth: 3)
- **_queue_command** (criticality: 0.46, depth: 3)
- **_packet_command** (criticality: 0.46, depth: 3)
- **_worktree_create_command** (criticality: 0.46, depth: 3)
- **_worktree_close_command** (criticality: 0.46, depth: 3)
- *... and 7 more flows.*

## Dependencies

### Outgoing

- `execute` (47 edge(s))
- `add_argument` (13 edge(s))
- `get` (12 edge(s))
- `dumps` (12 edge(s))
- `strip` (8 edge(s))
- `str` (8 edge(s))
- `print` (7 edge(s))
- `add_parser` (7 edge(s))
- `set_defaults` (7 edge(s))
- `fetchall` (6 edge(s))
- `max` (4 edge(s))
- `fetchone` (3 edge(s))
- `ValueError` (3 edge(s))
- `len` (3 edge(s))
- `int` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py` (11 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::SessionDaemon.run_forever` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_research_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_enqueue_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_queue_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_packet_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_worktree_create_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_worktree_close_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_worktree_list_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_export_run_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_export_verify_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_cleanup_run_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py::_export_session_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_claude_adapter.py::TestClaudeAdapter.test_emit_writes_human_message` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_claude_adapter.py::TestClaudeAdapter.test_emit_session_fallback_when_no_transcript` (1 edge(s))
