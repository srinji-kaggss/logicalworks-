# tests-cid

## Overview

Directory-based community: axiom

- **Size**: 107 nodes
- **Cohesion**: 0.3869
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| CapsuleError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 39-40 |
| _pack_f64 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 43-50 |
| _unpack_f64 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 53-59 |
| Capsule | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 63-153 |
| validate_structure | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 75-80 |
| to_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 82-108 |
| cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 110-111 |
| from_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 114-153 |
| _decode_param | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py | 156-170 |
| CidError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/cid.py | 27-28 |
| compute_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/cid.py | 31-36 |
| verify_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/cid.py | 39-45 |
| require_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/cid.py | 48-51 |
| TxState | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 31-34 |
| LogEntry | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 38-42 |
| FabricError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 45-46 |
| Fabric | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 49-143 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 50-57 |
| tick | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 60-64 |
| now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 67-68 |
| resolve | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 71-79 |
| _append_log | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 81-85 |
| propose | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 88-101 |
| status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 103-110 |
| abandon | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 112-119 |
| supersede | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 121-129 |
| verify_chain | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/fabric.py | 132-143 |
| compute_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/src/lib.rs | 4-9 |
| Cli | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/src/main.rs | 9-12 |
| Commands | Class | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/src/main.rs | 15-22 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/src/main.rs | 24-61 |
| test_deterministic_and_distinct | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/tests/test_cid.rs | 6-9 |
| test_full_width_256_bit | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/tests/test_cid.rs | 12-17 |
| test_cli_accepts_exact_stdin_limit | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/rust/tests/test_cid.rs | 20-43 |
| test_roundtrip_claim | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 15-18 |
| test_roundtrip_with_params_and_on | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 21-25 |
| test_hole_with_grants_rejected | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 28-31 |
| test_hole_with_needs_rejected | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 34-37 |
| test_valid_hole_roundtrips | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 40-42 |
| test_nan_param_rejected | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 45-48 |
| test_inf_param_rejected | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 51-54 |
| test_negative_zero_normalized | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 57-60 |
| test_cid_independent_of_set_order | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 63-66 |
| test_genesis_and_signature_survive_roundtrip | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 69-73 |
| test_bool_fields_reject_non_bool_varints | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py | 76-79 |
| test_deterministic_and_distinct | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py | 14-16 |
| test_full_width_256_bit | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py | 19-23 |
| test_verify_true_and_false | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py | 26-31 |
| test_require_raises_on_mismatch | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py | 34-38 |
| test_non_bytes_rejected | Test | /Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py | 41-43 |

*... and 57 more members.*

## Execution Flows

- **replay_command** (criticality: 0.56, depth: 4)
- **query_by_source** (criticality: 0.56, depth: 4)
- **narrate_command** (criticality: 0.54, depth: 3)
- **capture_command** (criticality: 0.54, depth: 3)
- **embed_to_record** (criticality: 0.53, depth: 3)
- **migrate_code_embeddings** (criticality: 0.50, depth: 3)
- **verify_chain** (criticality: 0.48, depth: 1)
- **cid** (criticality: 0.43, depth: 3)
- **from_bytes** (criticality: 0.41, depth: 2)
- **supersede** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `frozenset` (29 edge(s))
- `raises` (22 edge(s))
- `bytes` (21 edge(s))
- `cid` (17 edge(s))
- `append` (13 edge(s))
- `to_bytes` (13 edge(s))
- `len` (12 edge(s))
- `encode` (11 edge(s))
- `propose` (10 edge(s))
- `set` (9 edge(s))
- `resolve` (8 edge(s))
- `decode` (7 edge(s))
- `sorted` (5 edge(s))
- `ValueError` (5 edge(s))
- `from_bytes` (5 edge(s))

### Incoming

- `frozenset` (24 edge(s))
- `raises` (22 edge(s))
- `cid` (15 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_fabric.py` (13 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_verify.py` (13 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_capsule.py` (11 edge(s))
- `to_bytes` (9 edge(s))
- `propose` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_wire.py` (9 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_varint.py` (8 edge(s))
- `len` (6 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/capsule.py` (5 edge(s))
- `from_bytes` (5 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/axiom/tests/test_cid.py` (5 edge(s))
- `tick` (5 edge(s))
