# gemini-complete

## Overview

Directory-based community: lgwks_repl

- **Size**: 24 nodes
- **Cohesion**: 0.1684
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _domain_for | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 46-50 |
| _live_commands | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 53-78 |
| ReplCompleter | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 98-168 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 101-103 |
| set_graph_nodes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 105-106 |
| complete | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 108-137 |
| _complete_graph | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 139-145 |
| _complete_substrate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 147-150 |
| _complete_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 152-168 |
| _cmd_help | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 176-201 |
| _suggest_commands | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 215-227 |
| _cmd_history | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 230-234 |
| GraphContext | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 239-267 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 241-244 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 246-254 |
| stats | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 256-259 |
| refresh | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 261-267 |
| _dispatch_inline | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 282-306 |
| _argv_to_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 309-339 |
| Args | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 311-312 |
| _dispatch_subprocess | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 342-354 |
| _prompt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 359-370 |
| run_repl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 375-488 |
| repl_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py | 493-496 |

## Execution Flows

- **repl_command** (criticality: 0.39, depth: 4)

## Dependencies

### Outgoing

- `print` (22 edge(s))
- `startswith` (18 edge(s))
- `append` (14 edge(s))
- `str` (6 edge(s))
- `list` (4 edge(s))
- `keys` (4 edge(s))
- `get` (4 edge(s))
- `getattr` (4 edge(s))
- `split` (3 edge(s))
- `len` (3 edge(s))
- `join` (3 edge(s))
- `run` (3 edge(s))
- `Path` (2 edge(s))
- `exists` (2 edge(s))
- `get_graph` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repl.py` (15 edge(s))
