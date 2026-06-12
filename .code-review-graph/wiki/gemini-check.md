# gemini-check

## Overview

Directory-based community: lgwks_bot_code_hacker

- **Size**: 36 nodes
- **Cohesion**: 0.3642
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _finding_fingerprint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 50-63 |
| Baseline | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 66-106 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 73-81 |
| is_suppressed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 83-87 |
| record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 89-106 |
| Source | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 112-116 |
| Sink | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 120-124 |
| TaintTracker | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 127-169 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 145-147 |
| register_source | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 149-151 |
| check_flow | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 153-169 |
| RiskScore | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 175-193 |
| __post_init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 182-184 |
| severity | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 186-193 |
| SARIFConverter | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 198-257 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 206-208 |
| convert | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 210-252 |
| _severity_to_level | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 255-257 |
| _ts | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 262-263 |
| _run_seed | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 266-267 |
| _make | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 270-303 |
| _failure_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 306-317 |
| _is_net_safe | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 320-321 |
| _Visitor | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 326-504 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 333-342 |
| _add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 344-370 |
| _check_h1 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 374-403 |
| _check_h2 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 407-417 |
| _flag_net_import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 421-428 |
| visit_Import | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 430-433 |
| visit_ImportFrom | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 435-438 |
| visit_Assign | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 442-459 |
| _check_h4 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 461-496 |
| visit_Call | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 500-504 |
| _scan_file | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 509-520 |
| run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py | 525-593 |

## Execution Flows

- **visit_Assign** (criticality: 0.45, depth: 2)
- **visit_Import** (criticality: 0.39, depth: 4)
- **visit_ImportFrom** (criticality: 0.39, depth: 4)
- **visit_Call** (criticality: 0.39, depth: 4)
- **run** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `isinstance` (20 edge(s))
- `get` (10 edge(s))
- `search` (5 edge(s))
- `str` (5 edge(s))
- `append` (4 edge(s))
- `any` (4 edge(s))
- `generic_visit` (4 edge(s))
- `dumps` (3 edge(s))
- `read_text` (2 edge(s))
- `mkdir` (2 edge(s))
- `write_text` (2 edge(s))
- `next` (2 edge(s))
- `bool` (2 edge(s))
- `hexdigest` (2 edge(s))
- `sha256` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_bot_code_hacker.py` (15 edge(s))
