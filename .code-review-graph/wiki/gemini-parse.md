# gemini-parse

## Overview

Directory-based community: lgwks_expression

- **Size**: 34 nodes
- **Cohesion**: 0.3586
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ExpressionParseError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 37-44 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 40-44 |
| VerbResolutionError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 47-49 |
| _make_step | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 59-60 |
| _check_injection | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 78-85 |
| _Parser | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 100-262 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 103-105 |
| _peek | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 109-110 |
| _rest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 112-113 |
| _advance | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 115-118 |
| _expect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 120-127 |
| parse_pipeline | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 131-144 |
| parse_step | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 146-153 |
| parse_verb_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 155-173 |
| parse_kv_list | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 175-183 |
| parse_kv | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 185-204 |
| parse_value | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 206-229 |
| parse_string | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 231-262 |
| parse | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 270-280 |
| _canonical_step | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 288-313 |
| _canonicalise | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 316-324 |
| _plan_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 327-328 |
| _manifest_capability_entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 340-344 |
| _is_live_mcp_wiring | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 347-351 |
| _risk_for_primitive | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 354-375 |
| _max_risk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 378-381 |
| _resolve_verb_against_manifest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 389-424 |
| _schema_for_verb | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 427-435 |
| _schemas_compatible | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 443-457 |
| _validate_plan_schema | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 465-545 |
| compile_from_string | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 553-639 |
| compile | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 643-719 |
| approval_for_plan | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 727-740 |
| is_expression_string | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py | 748-767 |

## Execution Flows

- **compile_from_string** (criticality: 0.49, depth: 6)
- **compile** (criticality: 0.46, depth: 2)

## Dependencies

### Outgoing

- `append` (19 edge(s))
- `get` (18 edge(s))
- `startswith` (10 edge(s))
- `len` (9 edge(s))
- `match` (9 edge(s))
- `isinstance` (7 edge(s))
- `group` (4 edge(s))
- `join` (4 edge(s))
- `sorted` (4 edge(s))
- `strip` (4 edge(s))
- `end` (3 edge(s))
- `lower` (2 edge(s))
- `items` (2 edge(s))
- `start` (2 edge(s))
- `bool` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_expression.py` (24 edge(s))
