# gemini-score

## Overview

Directory-based community: lgwks_score

- **Size**: 12 nodes
- **Cohesion**: 0.0743
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| FactoredRelation | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 51-69 |
| _invert_perm | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 72-77 |
| build_operators | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 87-131 |
| score_triple | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 139-191 |
| _normalize_value | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 200-216 |
| canonicalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 219-230 |
| content_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 233-235 |
| score_mdl | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 238-259 |
| ScoreRecord | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 268-275 |
| score_instance | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 278-311 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 319-325 |
| _cmd_relations | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py | 328-343 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `len` (16 edge(s))
- `ValueError` (9 edge(s))
- `items` (5 edge(s))
- `print` (4 edge(s))
- `isinstance` (4 edge(s))
- `range` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionality.test_directed_relation_asymmetric` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionality.test_symmetric_relation_equal` (3 edge(s))
- `get` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionalActivation.test_symmetric_relation_stays_symmetric` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestHardening.test_score_triple_rejects_perm_length_mismatch` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestHardening.test_score_triple_rejects_mask_length_mismatch` (2 edge(s))
- `sorted` (2 edge(s))
- `dumps` (2 edge(s))
- `float` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_score.py` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionality.test_directed_relation_asymmetric` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionality.test_symmetric_relation_equal` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionalActivation.test_symmetric_relation_stays_symmetric` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestHardening.test_score_triple_rejects_perm_length_mismatch` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestHardening.test_score_triple_rejects_mask_length_mismatch` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionalActivation.test_operators_replayable` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestReplayDeterminism.test_operators_deterministic_across_builds` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestReplayDeterminism.test_score_triple_deterministic` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestCrossModelCid.test_key_order_independent` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestCrossModelCid.test_s_ai_excluded_from_canonical` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestCrossModelCid.test_cid_is_blake2b_of_canonical` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestHardening.test_int_float_cid_equal` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestDirectionalActivation.test_every_directed_relation_is_asymmetric` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_score.py::TestMarginalIdentity.setUp` (1 edge(s))
