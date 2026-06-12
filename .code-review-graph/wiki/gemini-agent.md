# gemini-agent

## Overview

Directory-based community: lgwks_agent_os

- **Size**: 24 nodes
- **Cohesion**: 0.2389
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ContextTarget | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 46-51 |
| AgentManifest | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 58-64 |
| _parse_agent_manifest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 67-105 |
| SpawnRecord | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 112-120 |
| FleetOrchestrator | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 123-316 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 135-146 |
| _git | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 151-160 |
| scan_agents | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 165-177 |
| spawn | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 182-249 |
| collect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 251-274 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 276-290 |
| _audit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 295-316 |
| _sha256 | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 322-323 |
| _fleet_home | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 326-328 |
| _claude_agents_dir | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 331-334 |
| load_manifest | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 337-341 |
| resolve_manifest_entries | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 344-361 |
| bootstrap_context | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 364-382 |
| _agent_card_payload | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 385-421 |
| write_agent_cards | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 424-426 |
| doctor | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 429-461 |
| _agent_os_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 468-509 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 512-530 |
| main | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py | 533-549 |

## Execution Flows

- **main** (criticality: 0.39, depth: 4)

## Dependencies

### Outgoing

- `str` (19 edge(s))
- `dumps` (12 edge(s))
- `exists` (11 edge(s))
- `strip` (10 edge(s))
- `resolve` (8 edge(s))
- `get` (8 edge(s))
- `read_text` (6 edge(s))
- `print` (6 edge(s))
- `add_argument` (6 edge(s))
- `time` (4 edge(s))
- `loads` (4 edge(s))
- `ValueError` (4 edge(s))
- `write_text` (4 edge(s))
- `Path` (4 edge(s))
- `search` (4 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_agent_os.py` (18 edge(s))
