# gemini-secret

## Overview

Directory-based community: lgwks_keyvault

- **Size**: 8 nodes
- **Cohesion**: 0.2000
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _env | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 34-37 |
| get_secret | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 40-58 |
| is_configured | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 61-63 |
| set_secret | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 66-83 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 86-99 |
| _keyvault_set_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 102-103 |
| _keyvault_check_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 106-113 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py | 116-127 |

## Execution Flows

- **main** (criticality: 0.49, depth: 2)
- **_keyvault_set_command** (criticality: 0.48, depth: 1)
- **is_configured** (criticality: 0.45, depth: 2)

## Dependencies

### Outgoing

- `print` (7 edge(s))
- `get` (3 edge(s))
- `strip` (3 edge(s))
- `add_argument` (3 edge(s))
- `set_defaults` (3 edge(s))
- `bool` (2 edge(s))
- `list` (2 edge(s))
- `run` (2 edge(s))
- `join` (2 edge(s))
- `getattr` (1 edge(s))
- `dumps` (1 edge(s))
- `add_subparsers` (1 edge(s))
- `len` (1 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_keyvault.py` (9 edge(s))
