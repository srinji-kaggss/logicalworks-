# gemini-embed

## Overview

Directory-based community: lgwks_embed_port

- **Size**: 25 nodes
- **Cohesion**: 0.2300
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| EmbedUnavailableError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 89-90 |
| EmbedDimError | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 93-94 |
| _mlx_worker_script | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 111-181 |
| _transformers_worker_script | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 184-258 |
| _l2_normalize | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 265-269 |
| _mrl_slice | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 272-275 |
| _WorkerState | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 283-285 |
| EmbedPort | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 288-509 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 306-318 |
| _detect_tier | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 322-346 |
| _start_worker | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 350-371 |
| _rpc | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 373-389 |
| embed_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 393-397 |
| embed_image | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 399-416 |
| embed_video | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 418-439 |
| embed_from_item | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 441-474 |
| space_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 476-478 |
| embed_to_record | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 480-495 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 497-503 |
| __enter__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 505-506 |
| __exit__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 508-509 |
| migrate_json_embeddings | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 517-586 |
| _src_cid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 536-538 |
| load_graphify | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 607-641 |
| load_all_graphs | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py | 644-653 |

## Execution Flows

- **embed_to_record** (criticality: 0.53, depth: 3)
- **embed_from_item** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `str` (9 edge(s))
- `len` (9 edge(s))
- `Path` (6 edge(s))
- `getattr` (6 edge(s))
- `ValueError` (5 edge(s))
- `exists` (4 edge(s))
- `write` (3 edge(s))
- `dumps` (3 edge(s))
- `loads` (3 edge(s))
- `get` (3 edge(s))
- `isinstance` (3 edge(s))
- `execute` (3 edge(s))
- `run` (2 edge(s))
- `poll` (2 edge(s))
- `NamedTemporaryFile` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_embed_port.py` (12 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestL2Normalize.test_zero_vector_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestMrlSlice.test_k_gt_dim_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestEmbedPortConstructor.test_dim_exceeds_max_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestTierDetection.test_neither_available_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestEmbedPortConstructor.test_unknown_tier_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestLoadGraphify.test_idempotent_reload` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::_make_port` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestTierDetection._detect` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestRpc.test_dead_process_raises` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestRpc.test_empty_response_raises` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestRpc.test_worker_error_propagates` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestRpc.test_null_embedding_raises` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestL2Normalize.test_unit_vector_unchanged` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_embed_port.py::TestL2Normalize.test_norm_is_one` (1 edge(s))
