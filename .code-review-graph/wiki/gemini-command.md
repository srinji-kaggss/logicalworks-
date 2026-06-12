# gemini-command

## Overview

Directory-based community: lgwks_daemon

- **Size**: 53 nodes
- **Cohesion**: 0.2811
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 39-40 |
| _pid_alive | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 43-50 |
| DaemonPaths | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 54-59 |
| _paths | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 62-70 |
| _read_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 73-79 |
| _write_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 82-84 |
| _rm_if_exists | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 87-91 |
| _lock_payload | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 94-100 |
| _state_payload | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 103-112 |
| _cleanup_stale_lock | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 115-123 |
| _build_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 126-144 |
| _make_substrate_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 147-173 |
| WorktreeManager | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 179-293 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 187-189 |
| _worktree_base | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 191-194 |
| _git | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 196-202 |
| _head_sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 204-206 |
| _crdt_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 208-211 |
| _crdt_add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 213-225 |
| _crdt_remove | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 227-239 |
| create | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 241-269 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 271-290 |
| list | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 292-293 |
| _dispatch_item | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 296-321 |
| SessionDaemon | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 324-500 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 325-327 |
| status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 329-347 |
| doctor | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 349-367 |
| start | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 369-395 |
| stop | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 397-425 |
| run_forever | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 427-500 |
| _stop | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 441-443 |
| _status_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 503-506 |
| _doctor_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 509-512 |
| _start_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 515-518 |
| _stop_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 521-524 |
| _serve_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 527-529 |
| _research_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 532-558 |
| _runs_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 561-571 |
| _enqueue_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 574-585 |
| _queue_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 588-598 |
| _packet_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 601-615 |
| _worktree_create_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 618-628 |
| _worktree_close_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 631-640 |
| _worktree_list_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 643-653 |
| _export_run_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 656-666 |
| _export_verify_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 669-678 |
| _cleanup_run_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 681-690 |
| _export_session_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 693-706 |
| _register_export_subcommands | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py | 709-731 |

*... and 3 more members.*

## Execution Flows

- **_serve_command** (criticality: 0.48, depth: 4)
- **_export_verify_command** (criticality: 0.48, depth: 3)
- **_export_session_command** (criticality: 0.48, depth: 3)
- **_start_command** (criticality: 0.47, depth: 3)
- **_stop_command** (criticality: 0.47, depth: 3)
- **_status_command** (criticality: 0.47, depth: 2)
- **_research_command** (criticality: 0.46, depth: 3)
- **_enqueue_command** (criticality: 0.46, depth: 3)
- **_queue_command** (criticality: 0.46, depth: 3)
- **_packet_command** (criticality: 0.46, depth: 3)
- *... and 7 more flows.*

## Dependencies

### Outgoing

- `get` (34 edge(s))
- `add_argument` (32 edge(s))
- `set_defaults` (26 edge(s))
- `Path` (22 edge(s))
- `str` (19 edge(s))
- `dumps` (17 edge(s))
- `print` (16 edge(s))
- `resolve` (15 edge(s))
- `int` (14 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_store.py::DaemonEventStore` (12 edge(s))
- `time` (7 edge(s))
- `exists` (6 edge(s))
- `mkdir` (5 edge(s))
- `strip` (5 edge(s))
- `RuntimeError` (5 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon.py` (37 edge(s))
