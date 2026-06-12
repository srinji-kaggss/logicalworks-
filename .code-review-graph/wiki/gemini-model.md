# gemini-model

## Overview

Directory-based community: lgwks_model_hub

- **Size**: 29 nodes
- **Cohesion**: 0.1948
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _models_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 70-72 |
| _ensure_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 75-76 |
| _run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 79-80 |
| _safe_name | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 83-90 |
| _assert_under | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 93-98 |
| _temporary_env | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 102-111 |
| list_models | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 114-116 |
| find_model_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 119-123 |
| load_model | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 126-141 |
| _python_coreml_eligible | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 144-154 |
| _catalog_entry_status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 157-174 |
| doctor | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 177-258 |
| scrub_model_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 261-287 |
| convert_to_coreml | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 290-354 |
| _MeanWrapper | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 329-335 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 330-332 |
| forward | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 334-335 |
| train_text_classifier | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 357-454 |
| _TextDS | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 407-416 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 408-410 |
| __len__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 412-413 |
| __getitem__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 415-416 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 457-487 |
| _model_hub_list_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 490-496 |
| _model_hub_load_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 499-502 |
| _model_hub_convert_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 505-512 |
| _model_hub_train_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 515-520 |
| _model_hub_doctor_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 523-525 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py | 528-572 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `str` (17 edge(s))
- `add_argument` (16 edge(s))
- `print` (14 edge(s))
- `dumps` (11 edge(s))
- `len` (8 edge(s))
- `Path` (8 edge(s))
- `getattr` (7 edge(s))
- `set_defaults` (6 edge(s))
- `type` (6 edge(s))
- `bool` (5 edge(s))
- `get` (5 edge(s))
- `items` (4 edge(s))
- `exists` (4 edge(s))
- `loads` (4 edge(s))
- `read_text` (4 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_model_hub.py` (25 edge(s))
