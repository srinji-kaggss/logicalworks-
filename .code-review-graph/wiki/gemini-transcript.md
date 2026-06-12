# gemini-transcript

## Overview

Directory-based community: lgwks_waste

- **Size**: 12 nodes
- **Cohesion**: 0.0833
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _detect_use | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 61-67 |
| _load_transcript | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 74-88 |
| _extract_turn_texts | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 91-115 |
| build_ledger | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 122-214 |
| _session_id_from_transcript | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 217-224 |
| _waste_rate_from_totals | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 227-231 |
| waste_rate | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 238-240 |
| worst_item | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 243-248 |
| persist_ledger | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 255-264 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 271-286 |
| _cmd_report | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 289-323 |
| _cmd_info | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py | 326-338 |

## Execution Flows

- **_cmd_report** (criticality: 0.40, depth: 2)

## Dependencies

### Outgoing

- `get` (19 edge(s))
- `isinstance` (11 edge(s))
- `print` (8 edge(s))
- `append` (8 edge(s))
- `add_argument` (4 edge(s))
- `dumps` (2 edge(s))
- `getattr` (2 edge(s))
- `lower` (2 edge(s))
- `max` (2 edge(s))
- `set_defaults` (2 edge(s))
- `str` (2 edge(s))
- `add` (2 edge(s))
- `sum` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestWasteRate.test_all_unused` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestWasteRate.test_all_used` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_waste.py` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestWasteRate.test_all_unused` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestWasteRate.test_all_used` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestWasteRate.test_partial_use_exact_value` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestAttributable.test_worst_item_identified` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestAttributable.test_no_worst_item_when_all_used` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestDeterministic.test_different_window_different_result` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestSumsReconcile.test_sum_matches_depth_handles` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestSumsReconcile.test_zero_packs_zero_injected` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestSumsReconcile.test_multiple_packs_sum` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestNoProse.test_no_prose_in_ledger` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestNoProse.test_items_typed_fields_only` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestThresholdPreRegistered.test_ledger_does_not_contain_threshold` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestDeterministic._build` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_waste.py::TestDeterministic.test_transcript_path_env_var` (1 edge(s))
