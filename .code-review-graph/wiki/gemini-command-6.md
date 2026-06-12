# gemini-command

## Overview

Directory-based community: lgwks_session

- **Size**: 17 nodes
- **Cohesion**: 0.0933
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 34-35 |
| _write_marker | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 38-42 |
| _last_marker | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 45-60 |
| _shell_history_last_n | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 63-89 |
| _git_activity_since | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 92-139 |
| _summarize_activity | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 142-273 |
| _categorize_token | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 213-221 |
| session_begin | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 276-284 |
| session_end | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 287-298 |
| _maybe_append_waste | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 301-341 |
| session_summary | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 344-350 |
| _render_summary | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 355-396 |
| begin_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 399-409 |
| end_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 412-422 |
| summary_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 425-435 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 438-464 |
| capability_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py | 467-505 |

## Execution Flows

- **end_command** (criticality: 0.67, depth: 3)
- **begin_command** (criticality: 0.66, depth: 3)
- **summary_command** (criticality: 0.66, depth: 3)

## Dependencies

### Outgoing

- `get` (27 edge(s))
- `append` (22 edge(s))
- `print` (16 edge(s))
- `add_argument` (12 edge(s))
- `getattr` (11 edge(s))
- `len` (9 edge(s))
- `spine` (9 edge(s))
- `join` (9 edge(s))
- `items` (9 edge(s))
- `any` (8 edge(s))
- `fg` (8 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py::_git` (7 edge(s))
- `str` (7 edge(s))
- `splitlines` (6 edge(s))
- `twig` (6 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py` (17 edge(s))
