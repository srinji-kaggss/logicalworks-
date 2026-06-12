# gemini-cmd

## Overview

Directory-based community: lgwks_hooks

- **Size**: 34 nodes
- **Cohesion**: 0.1534
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _lgwks_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 154-159 |
| _audit_log | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 162-163 |
| _registry_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 166-167 |
| _registry_lock_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 170-171 |
| _exclusive_lock | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 175-182 |
| _resolve_within_root | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 185-193 |
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 198-199 |
| _session_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 202-207 |
| _scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 212-225 |
| build_event | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 230-246 |
| _sha256 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 251-252 |
| _last_line_hash | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 255-276 |
| audit_append | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 281-306 |
| _validate_hook_entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 311-327 |
| _load_registry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 330-359 |
| _save_registry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 362-374 |
| _mutate_registry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 377-384 |
| _builtin_why_nudge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 389-396 |
| _builtin_secret_scrub | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 399-408 |
| _builtin_token_watcher | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 411-419 |
| _builtin_git_drift | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 422-430 |
| _builtin_scope_mirror | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 433-443 |
| fire | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 475-548 |
| verify_chain | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 553-591 |
| _cmd_list | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 596-620 |
| _cmd_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 623-639 |
| _cmd_add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 642-683 |
| mutate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 707-713 |
| _cmd_remove | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 686-700 |
| _cmd_toggle | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 703-722 |
| _cmd_audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 725-800 |
| _cmd_verify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 803-813 |
| _cmd_install | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 816-844 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py | 849-895 |

## Execution Flows

- **_cmd_verify** (criticality: 0.48, depth: 3)
- **_cmd_list** (criticality: 0.45, depth: 4)
- **_cmd_run** (criticality: 0.44, depth: 4)
- **_cmd_audit** (criticality: 0.44, depth: 4)
- **_cmd_add** (criticality: 0.44, depth: 5)
- **_cmd_remove** (criticality: 0.44, depth: 5)

## Dependencies

### Outgoing

- `get` (39 edge(s))
- `write` (21 edge(s))
- `print` (21 edge(s))
- `getattr` (19 edge(s))
- `add_argument` (15 edge(s))
- `Path` (11 edge(s))
- `len` (11 edge(s))
- `resolve` (10 edge(s))
- `cwd` (10 edge(s))
- `str` (9 edge(s))
- `strip` (9 edge(s))
- `set_defaults` (9 edge(s))
- `dumps` (8 edge(s))
- `isinstance` (7 edge(s))
- `exists` (5 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_hooks.py` (42 edge(s))
