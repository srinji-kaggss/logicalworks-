# gemini-issue

## Overview

Directory-based community: lgwks_gh

- **Size**: 34 nodes
- **Cohesion**: 0.2070
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _gh_meta | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 34-41 |
| _audit_log_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 55-56 |
| _audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 59-71 |
| _validate_slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 76-83 |
| _validate_number | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 86-94 |
| _scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 97-99 |
| _gh | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 104-127 |
| _gh_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 130-138 |
| _repo_slug_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 141-144 |
| _auth_ok | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 147-149 |
| NextAction | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 155-159 |
| IssueView | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 163-174 |
| RepoState | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 178-186 |
| _compute_issue_next | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 191-238 |
| _compute_state_next | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 241-252 |
| _issues_list | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 257-280 |
| _issue_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 283-330 |
| _prs_list | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 333-349 |
| _pr_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 352-368 |
| _repo_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 371-430 |
| _harden | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 433-506 |
| _current_repo_slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 509-525 |
| _git_log_has_issue_ref | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 527-543 |
| _local_branches_for_issue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 546-566 |
| _render_issue | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 571-588 |
| _render_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 591-605 |
| issues_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 610-633 |
| issue_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 636-681 |
| prs_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 684-707 |
| pr_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 710-747 |
| state_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 750-775 |
| harden_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 778-807 |
| auth_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 810-831 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py | 836-879 |

## Execution Flows

- **_auth_ok** (criticality: 0.48, depth: 1)
- **auth_command** (criticality: 0.44, depth: 1)
- **pr_command** (criticality: 0.43, depth: 2)
- **issue_command** (criticality: 0.41, depth: 3)
- **issues_command** (criticality: 0.41, depth: 2)
- **prs_command** (criticality: 0.41, depth: 2)
- **state_command** (criticality: 0.40, depth: 3)
- **harden_command** (criticality: 0.40, depth: 2)

## Dependencies

### Outgoing

- `append` (61 edge(s))
- `get` (24 edge(s))
- `print` (24 edge(s))
- `spine` (22 edge(s))
- `add_argument` (20 edge(s))
- `fg` (19 edge(s))
- `getattr` (17 edge(s))
- `strip` (12 edge(s))
- `join` (12 edge(s))
- `len` (10 edge(s))
- `str` (9 edge(s))
- `dumps` (9 edge(s))
- `search` (9 edge(s))
- `loads` (7 edge(s))
- `band` (7 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_gh.py` (34 edge(s))
