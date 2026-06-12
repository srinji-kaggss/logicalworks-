# tools-cmd

## Overview

Directory-based community: tools

- **Size**: 18 nodes
- **Cohesion**: 0.1793
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| utc_now | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 39-40 |
| service_name | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 43-44 |
| _read_records | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 47-55 |
| _core | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 58-60 |
| _append | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 63-85 |
| verify_chain | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 88-97 |
| _latest_status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 100-109 |
| _keychain_has | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 112-118 |
| cmd_add | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 121-137 |
| cmd_stale | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 140-145 |
| cmd_check | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 148-154 |
| cmd_ls | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 157-173 |
| build_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 176-195 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth | 198-200 |
| build_dataset | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/train_intent_classifier.py | 29-60 |
| train | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/train_intent_classifier.py | 67-113 |
| _export_coreml | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/train_intent_classifier.py | 116-129 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/tools/train_intent_classifier.py | 136-149 |

## Execution Flows

- **cmd_add** (criticality: 0.62, depth: 2)
- **cmd_stale** (criticality: 0.62, depth: 2)
- **cmd_check** (criticality: 0.62, depth: 2)
- **cmd_ls** (criticality: 0.62, depth: 2)
- **main** (criticality: 0.61, depth: 1)

## Dependencies

### Outgoing

- `print` (17 edge(s))
- `add_argument` (11 edge(s))
- `get` (6 edge(s))
- `SystemExit` (4 edge(s))
- `len` (4 edge(s))
- `add_parser` (4 edge(s))
- `set_defaults` (4 edge(s))
- `dumps` (3 edge(s))
- `append` (3 edge(s))
- `mac` (2 edge(s))
- `items` (2 edge(s))
- `run` (2 edge(s))
- `exists` (2 edge(s))
- `read_text` (2 edge(s))
- `loads` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/tools/lgwks-auth` (15 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tools/train_intent_classifier.py` (5 edge(s))
