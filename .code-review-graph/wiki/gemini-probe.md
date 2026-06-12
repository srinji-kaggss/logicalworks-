# gemini-probe

## Overview

Directory-based community: lgwks_intent

- **Size**: 29 nodes
- **Cohesion**: 0.1392
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _classify_risk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 78-82 |
| _audit_log_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 87-88 |
| _audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 91-103 |
| _validate_slug | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 108-114 |
| _validate_number | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 117-120 |
| _validate_next_if_keys | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 123-127 |
| _scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 130-131 |
| _safe_substitute | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 134-145 |
| IntentDoc | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 151-159 |
| RouteResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 163-174 |
| _run_probe | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 179-196 |
| _probe_issue_open | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 199-213 |
| _probe_issue_closed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 216-218 |
| _probe_pr_draft | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 221-235 |
| _probe_pr_open | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 238-252 |
| _probe_pr_closed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 255-257 |
| _probe_tests_fail | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 260-266 |
| _probe_tests_pass | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 269-271 |
| _probe_review_danger | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 274-288 |
| _probe_review_warn | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 291-305 |
| _probe_dirty | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 308-315 |
| _probe_clean | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 318-320 |
| _resolve_intent | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 340-369 |
| _route | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 372-425 |
| _default_intent | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 430-446 |
| init_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 449-453 |
| route_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 456-530 |
| next_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 533-542 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py | 547-566 |

## Execution Flows

- **next_command** (criticality: 0.45, depth: 4)
- **_probe_issue_closed** (criticality: 0.38, depth: 3)
- **_probe_pr_closed** (criticality: 0.38, depth: 3)
- **_probe_clean** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `get` (18 edge(s))
- `append` (15 edge(s))
- `str` (12 edge(s))
- `print` (11 edge(s))
- `spine` (10 edge(s))
- `strip` (8 edge(s))
- `add_argument` (8 edge(s))
- `fg` (8 edge(s))
- `loads` (6 edge(s))
- `getattr` (5 edge(s))
- `ValueError` (4 edge(s))
- `replace` (4 edge(s))
- `dumps` (3 edge(s))
- `items` (3 edge(s))
- `len` (3 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_intent.py` (40 edge(s))
