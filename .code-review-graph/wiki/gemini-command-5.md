# gemini-command

## Overview

Directory-based community: lgwks_debug

- **Size**: 18 nodes
- **Cohesion**: 0.1589
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _audit_log_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 46-47 |
| _audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 50-60 |
| _validate_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 65-74 |
| _scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 77-79 |
| DebugFinding | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 148-155 |
| DebugResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 159-168 |
| _run_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 173-199 |
| _match_patterns | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 202-225 |
| debug_command_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 228-263 |
| _debug_log_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 268-269 |
| _append_debug_log | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 272-287 |
| _load_last_failure | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 290-304 |
| _run_tests | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 309-372 |
| _render_findings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 377-387 |
| run_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 392-429 |
| last_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 432-459 |
| test_command | Test | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 462-489 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py | 494-513 |

## Execution Flows

- **run_command** (criticality: 0.40, depth: 3)

## Dependencies

### Outgoing

- `append` (23 edge(s))
- `spine` (11 edge(s))
- `join` (9 edge(s))
- `fg` (8 edge(s))
- `add_argument` (8 edge(s))
- `print` (8 edge(s))
- `getattr` (7 edge(s))
- `dumps` (5 edge(s))
- `perf_counter` (5 edge(s))
- `get` (4 edge(s))
- `twig` (4 edge(s))
- `round` (4 edge(s))
- `len` (4 edge(s))
- `open` (3 edge(s))
- `start` (3 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_debug.py` (18 edge(s))
