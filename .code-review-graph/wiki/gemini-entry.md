# gemini-entry

## Overview

Directory-based community: lgwks_vault

- **Size**: 21 nodes
- **Cohesion**: 0.2848
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| AuditEvent | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 60-80 |
| to_dict | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 70-80 |
| _audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 83-94 |
| _derive_vault_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 100-116 |
| _encode_versioned_ciphertext | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 119-124 |
| _decode_versioned_ciphertext | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 127-138 |
| _get_version_salt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 141-146 |
| _aesgcm_encrypt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 152-157 |
| _aesgcm_decrypt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 160-162 |
| _legacy_fernet | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 168-175 |
| _legacy_decrypt | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 178-182 |
| _derive_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 188-195 |
| is_unlocked | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 198-199 |
| _entry_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 202-205 |
| set_entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 212-239 |
| get_entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 242-293 |
| delete_entry | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 296-308 |
| keys | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 311-314 |
| status | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 317-328 |
| re_encrypt_entries | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 334-391 |
| rotate_vault_key | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py | 394-401 |

## Execution Flows

- **rotate_vault_key** (criticality: 0.45, depth: 3)
- **get_entry** (criticality: 0.41, depth: 2)
- **set_entry** (criticality: 0.40, depth: 2)

## Dependencies

### Outgoing

- `time` (8 edge(s))
- `getpid` (8 edge(s))
- `getuid` (8 edge(s))
- `encode` (5 edge(s))
- `signing_key` (4 edge(s))
- `PermissionError` (4 edge(s))
- `chmod` (3 edge(s))
- `decode` (3 edge(s))
- `sha256` (3 edge(s))
- `exists` (3 edge(s))
- `str` (3 edge(s))
- `len` (3 edge(s))
- `AESGCM` (2 edge(s))
- `decrypt` (2 edge(s))
- `mkdir` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_vault.py` (20 edge(s))
