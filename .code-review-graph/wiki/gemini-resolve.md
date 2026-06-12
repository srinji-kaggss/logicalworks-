# gemini-resolve

## Overview

Directory-based community: lgwks_access

- **Size**: 32 nodes
- **Cohesion**: 0.3571
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| VerifiedCap | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 28-39 |
| CapabilityPort | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 47-93 |
| resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 57-64 |
| verify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 66-71 |
| require_scope | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 73-78 |
| principal_of | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 80-82 |
| cap_ref | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 84-86 |
| mint_promote | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 88-93 |
| HmacCapToken | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 102-110 |
| HmacCapabilityPort | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 113-235 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 126-127 |
| _item_name | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 129-130 |
| _load_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 132-155 |
| _store_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 157-170 |
| resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 172-188 |
| verify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 190-201 |
| require_scope | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 203-211 |
| principal_of | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 213-215 |
| cap_ref | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 217-219 |
| mint_promote | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 221-235 |
| TenantStore | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 243-328 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 254-258 |
| _verified | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 260-261 |
| read | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 263-282 |
| write | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 284-298 |
| query | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 300-312 |
| promote | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 314-328 |
| resolve_capability_for_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 336-344 |
| resolve_promote_capability_for_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 347-354 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 362-377 |
| _access_resolve_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 380-417 |
| _access_promote_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py | 420-458 |

## Execution Flows

- **query** (criticality: 0.46, depth: 2)
- **write** (criticality: 0.43, depth: 2)
- **resolve** (criticality: 0.42, depth: 2)
- **mint_promote** (criticality: 0.42, depth: 2)
- **read** (criticality: 0.41, depth: 2)
- **_access_promote_command** (criticality: 0.41, depth: 3)
- **_access_resolve_command** (criticality: 0.41, depth: 2)

## Dependencies

### Outgoing

- `print` (14 edge(s))
- `add_argument` (7 edge(s))
- `twig` (6 edge(s))
- `getattr` (5 edge(s))
- `CapabilityError` (4 edge(s))
- `sorted` (4 edge(s))
- `get` (4 edge(s))
- `dumps` (4 edge(s))
- `spine` (4 edge(s))
- `fg` (4 edge(s))
- `issue_token` (3 edge(s))
- `run` (2 edge(s))
- `RuntimeError` (2 edge(s))
- `isinstance` (2 edge(s))
- `get_record_for_tenant` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_access.py` (10 edge(s))
