# gemini-repo

## Overview

Directory-based community: lgwks_repo

- **Size**: 29 nodes
- **Cohesion**: 0.2093
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _git | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 34-39 |
| _gh | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 42-48 |
| _git_stderr | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 51-57 |
| _is_repo | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 60-62 |
| _head_sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 65-67 |
| _current_branch | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 70-72 |
| _merged_branches | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 75-80 |
| AuditFinding | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 84-88 |
| RecoverGroup | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 92-94 |
| repo_audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 97-178 |
| _file_exists_in_head | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 181-183 |
| repo_recover | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 186-215 |
| repo_cleanup | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 218-266 |
| _resolve_conflict_keep_both_classes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 269-286 |
| repl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 276-281 |
| _resolve_conflict_sort_argparse | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 289-332 |
| repo_merge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 335-389 |
| repo_handoff | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 392-417 |
| repo_graph | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 420-457 |
| _v0_define | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 460-467 |
| audit_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 472-500 |
| recover_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 503-530 |
| cleanup_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 533-546 |
| handoff_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 549-556 |
| merge_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 559-575 |
| graph_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 578-592 |
| repo_sync | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 595-676 |
| sync_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 679-696 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py | 699-739 |

## Execution Flows

- **end_command** (criticality: 0.67, depth: 3)
- **begin_command** (criticality: 0.66, depth: 3)
- **summary_command** (criticality: 0.66, depth: 3)
- **do_natural_command** (criticality: 0.47, depth: 4)
- **do_command** (criticality: 0.46, depth: 3)

## Dependencies

### Outgoing

- `append` (37 edge(s))
- `print` (33 edge(s))
- `len` (25 edge(s))
- `add_argument` (17 edge(s))
- `getattr` (16 edge(s))
- `splitlines` (15 edge(s))
- `get` (14 edge(s))
- `str` (13 edge(s))
- `startswith` (13 edge(s))
- `strip` (12 edge(s))
- `resolve` (11 edge(s))
- `Path` (11 edge(s))
- `set_defaults` (7 edge(s))
- `dumps` (7 edge(s))
- `join` (5 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_repo.py` (29 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py::_git_activity_since` (7 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_review.py::_git_diff` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py::_do_code` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py::_do_govern` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py::_do_cleanup` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_do.py::_do_ship` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_review.py::review_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py::begin_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py::end_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_session.py::summary_command` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py::_do_audit_trail` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py::_do_migration_check` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_review.py::review_repo` (1 edge(s))
