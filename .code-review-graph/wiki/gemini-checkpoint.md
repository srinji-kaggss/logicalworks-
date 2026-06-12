# gemini-checkpoint

## Overview

Directory-based community: lgwks_workflows

- **Size**: 38 nodes
- **Cohesion**: 0.2742
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _workflow_for_intent | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 175-183 |
| PhaseResult | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 191-199 |
| WorkflowRun | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 203-246 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 219-246 |
| _now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 249-250 |
| _verdict_from_phases | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 253-263 |
| _cache_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 274-277 |
| _cached_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 280-295 |
| _cache_put | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 298-303 |
| _checkpoint_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 313-315 |
| _save_checkpoint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 318-322 |
| _load_checkpoint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 325-337 |
| _clear_checkpoint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 340-341 |
| _run_phase | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 348-361 |
| _browser_engine_from_args | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 364-369 |
| _do_research_inline | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 372-496 |
| slugify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 499-501 |
| _do_deep_research | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 504-615 |
| _do_quick_scan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 618-705 |
| _do_audit_trail | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 708-732 |
| _do_health_check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 735-756 |
| _doctor_env | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 759-768 |
| _do_onboard | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 771-794 |
| _do_migration_check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 797-821 |
| _do_code_wrapper | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 824-826 |
| _do_govern_wrapper | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 829-831 |
| _do_cleanup_wrapper | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 834-836 |
| _do_ship_wrapper | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 839-841 |
| _do_prove | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 844-846 |
| _do_extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 849-851 |
| _do_compare | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 854-856 |
| _emit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 863-888 |
| workflow_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 891-949 |
| do_natural_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 952-977 |
| list_workflows | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 980-1001 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 1004-1137 |
| _common_flags | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 1010-1015 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py | 1140-1144 |

## Execution Flows

- **do_natural_command** (criticality: 0.47, depth: 4)

## Dependencies

### Outgoing

- `add_argument` (50 edge(s))
- `append` (46 edge(s))
- `getattr` (32 edge(s))
- `time` (25 edge(s))
- `get` (22 edge(s))
- `str` (21 edge(s))
- `set_defaults` (15 edge(s))
- `Path` (9 edge(s))
- `Namespace` (9 edge(s))
- `spine` (9 edge(s))
- `fg` (8 edge(s))
- `max` (7 edge(s))
- `print` (7 edge(s))
- `dumps` (6 edge(s))
- `strip` (5 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_workflows.py` (38 edge(s))
