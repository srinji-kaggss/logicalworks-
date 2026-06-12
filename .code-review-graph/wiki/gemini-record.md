# gemini-record

## Overview

Directory-based community: lgwks_vector

- **Size**: 24 nodes
- **Cohesion**: 0.1220
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| VectorError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 54-55 |
| SpaceMismatchError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 58-59 |
| VectorRecord | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 67-80 |
| floats | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 78-80 |
| _pack_f32 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 87-88 |
| _norm_l2 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 91-92 |
| _normalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 95-100 |
| _canonical_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 103-119 |
| encode_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 122-157 |
| decode_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 160-173 |
| cosine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 180-192 |
| require_same_space | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 195-200 |
| _connect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 207-219 |
| create_store | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 222-225 |
| AdminOnlyError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 241-242 |
| _require_admin | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 245-251 |
| upsert_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 254-275 |
| get_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 278-294 |
| query_by_source | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 297-319 |
| query_for_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 326-360 |
| get_record_for_tenant | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 363-394 |
| promote_cid_to_world | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 397-421 |
| store_count | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 424-425 |
| migrate_code_embeddings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py | 432-499 |

## Execution Flows

- **query_by_source** (criticality: 0.56, depth: 4)
- **embed_to_record** (criticality: 0.53, depth: 3)
- **migrate_code_embeddings** (criticality: 0.50, depth: 3)

## Dependencies

### Outgoing

- `execute` (13 edge(s))
- `len` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_tenant_isolation.py::TestSecureCidResolver.test_10k_randomized_ab_zero_leak` (5 edge(s))
- `encode` (4 edge(s))
- `str` (4 edge(s))
- `fetchone` (4 edge(s))
- `fetchall` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_promotion_audit.py::TestPromotionAudit.test_promoted_row_visible_to_all_promotes_only_target` (4 edge(s))
- `connect` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_tenant_isolation.py::TestWALConcurrency.test_concurrent_writers_no_corruption` (3 edge(s))
- `commit` (2 edge(s))
- `sum` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestCrossSpaceGuard.test_cosine_of_identical_normalized_is_one` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestRoundTrip.test_bit_identical_floats` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/cid.py::compute_cid` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vector.py` (24 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_tenant_isolation.py::TestSecureCidResolver.test_10k_randomized_ab_zero_leak` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py::migrate_json_embeddings` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_promotion_audit.py::TestPromotionAudit.test_promoted_row_visible_to_all_promotes_only_target` (4 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_i8_tenant_isolation.py::TestWALConcurrency.test_concurrent_writers_no_corruption` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestCrossSpaceGuard.test_different_space_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestNormalization.test_zero_vector_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestValidation.test_empty_space_id_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestValidation.test_unknown_modality_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestValidation.test_empty_floats_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestCrossSpaceGuard.test_cosine_of_identical_normalized_is_one` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestRoundTrip.test_bit_identical_floats` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestDedup.test_same_inputs_same_cid` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestDedup.test_different_source_different_cid` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_vector_record.py::TestDedup.test_different_space_different_cid` (2 edge(s))
