# gemini-command

## Overview

Directory-based community: lgwks_axiom

- **Size**: 44 nodes
- **Cohesion**: 0.1421
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| CommandPolicyError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 45-46 |
| _argv_from_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 49-59 |
| classify_argv | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 62-120 |
| CapturedFact | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 124-127 |
| TestSpec | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 131-134 |
| NarrationClaim | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 138-142 |
| NarrationHole | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 146-149 |
| _utc | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 152-153 |
| _sha | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 156-157 |
| _run_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 160-162 |
| write_run_index | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 165-203 |
| _git | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 206-217 |
| _sign | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 220-245 |
| _genesis | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 248-249 |
| _capsule_for_fact | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 252-260 |
| _capsule_for_narration_claim | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 263-271 |
| _capsule_for_narration_hole | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 274-282 |
| _emit_capsule | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 285-310 |
| _repo_facts | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 313-327 |
| _normalize_label | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 330-334 |
| _normalize_timeout | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 337-344 |
| load_test_matrix | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 347-376 |
| parse_narration | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 379-403 |
| load_narration | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 406-428 |
| build_narration_artifact | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 431-504 |
| _is_relative_to | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 507-512 |
| _command_display | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 515-516 |
| _test_fact | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 519-563 |
| build_capture | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 566-657 |
| _load_emissions | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 660-669 |
| replay_emissions | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 672-740 |
| replay_run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 743-806 |
| _claims_from_input | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 809-811 |
| check_narration | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 814-855 |
| independence_report | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 858-879 |
| _print_packet | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 882-890 |
| capture_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 893-908 |
| test_matrix_command | Test | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 911-929 |
| narrate_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 932-950 |
| check_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 953-960 |
| replay_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 963-970 |
| doctor_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 973-976 |
| index_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 979-994 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py | 997-1052 |

## Execution Flows

- **replay_command** (criticality: 0.56, depth: 4)
- **narrate_command** (criticality: 0.54, depth: 3)
- **capture_command** (criticality: 0.54, depth: 3)
- **check_command** (criticality: 0.39, depth: 4)

## Dependencies

### Outgoing

- `get` (38 edge(s))
- `str` (35 edge(s))
- `append` (35 edge(s))
- `add_argument` (32 edge(s))
- `dumps` (27 edge(s))
- `isinstance` (21 edge(s))
- `ValueError` (20 edge(s))
- `print` (19 edge(s))
- `Path` (19 edge(s))
- `len` (16 edge(s))
- `resolve` (12 edge(s))
- `asdict` (11 edge(s))
- `write_text` (8 edge(s))
- `any` (7 edge(s))
- `loads` (7 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_axiom.py` (45 edge(s))
