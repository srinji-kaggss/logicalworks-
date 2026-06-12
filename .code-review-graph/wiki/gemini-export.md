# gemini-export

## Overview

Directory-based community: lgwks_daemon_export

- **Size**: 8 nodes
- **Cohesion**: 0.1930
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _sha256_file | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 25-30 |
| _default_export_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 33-36 |
| ExportManager | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 39-163 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 42-44 |
| export_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 46-76 |
| verify_export | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 78-99 |
| cleanup_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 101-134 |
| export_session | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py | 136-163 |

## Execution Flows

- **cleanup_run** (criticality: 0.45, depth: 2)
- **export_session** (criticality: 0.44, depth: 1)

## Dependencies

### Outgoing

- `str` (7 edge(s))
- `get_run_export_state` (3 edge(s))
- `ValueError` (3 edge(s))
- `Path` (3 edge(s))
- `open` (3 edge(s))
- `is_dir` (2 edge(s))
- `resolve` (1 edge(s))
- `get` (1 edge(s))
- `rmtree` (1 edge(s))
- `FileNotFoundError` (1 edge(s))
- `add` (1 edge(s))
- `mark_run_exported` (1 edge(s))
- `list_events` (1 edge(s))
- `replace` (1 edge(s))
- `write` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_daemon_export.py` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_daemon_export.py::TestExportRun._mgr` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_daemon_export.py::TestVerifyExport._mgr` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_daemon_export.py::TestCleanupRun._mgr` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_daemon_export.py::TestExportSession._mgr` (1 edge(s))
