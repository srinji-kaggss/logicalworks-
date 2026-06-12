# gemini-edge

## Overview

Directory-based community: lgwks_entity_graph

- **Size**: 36 nodes
- **Cohesion**: 0.2904
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| EntityMention | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 76-80 |
| extract_mentions | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 83-107 |
| GraphDB | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 143-450 |
| __post_init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 148-153 |
| _require_nonempty | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 155-159 |
| _edge_id | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 161-162 |
| _membership_sink | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 164-165 |
| _membership_state | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 167-180 |
| _visible_members | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 182-186 |
| _track_node_membership | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 188-189 |
| _track_edge_membership | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 191-192 |
| _remove_member | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 194-201 |
| close | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 203-205 |
| upsert_node | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 207-215 |
| upsert_edge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 217-234 |
| remove_edge | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 236-242 |
| remove_node | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 244-253 |
| upsert_chunk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 255-269 |
| commit | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 271-272 |
| seed_directional_edges | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 274-295 |
| query_nodes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 297-323 |
| query_edges | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 325-351 |
| resolve_nodes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 353-365 |
| neighbors | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 367-401 |
| shortest_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 403-421 |
| stats | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 423-428 |
| export_json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 430-439 |
| export_mermaid | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 441-450 |
| ingest_chunk | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 455-512 |
| ingest_chunks | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 515-523 |
| git_sync | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 528-558 |
| _run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 535-539 |
| add_parser | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 563-589 |
| _resolve_single_node | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 592-599 |
| _emit_query | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 602-606 |
| _entity_graph_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py | 609-704 |

## Execution Flows

- **_entity_graph_command** (criticality: 0.41, depth: 4)
- **seed_directional_edges** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `append` (29 edge(s))
- `add_argument` (18 edge(s))
- `execute` (16 edge(s))
- `print` (15 edge(s))
- `get` (11 edge(s))
- `lower` (9 edge(s))
- `dumps` (8 edge(s))
- `join` (7 edge(s))
- `fetchall` (6 edge(s))
- `loads` (6 edge(s))
- `Path` (6 edge(s))
- `finditer` (6 edge(s))
- `group` (6 edge(s))
- `start` (6 edge(s))
- `end` (6 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_entity_graph.py` (11 edge(s))
