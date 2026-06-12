# gemini-render

## Overview

Directory-based community: lgwks_graph_viz

- **Size**: 43 nodes
- **Cohesion**: 0.2103
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| GraphDataAdapter | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 44-165 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 47-51 |
| load | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 53-62 |
| to_frontend | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 64-111 |
| node_detail | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 113-135 |
| impact | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 137-145 |
| path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 147-156 |
| query | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 158-165 |
| VizHandler | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 524-633 |
| log_message | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 529-531 |
| _json | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 533-538 |
| _text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 540-544 |
| do_GET | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 546-600 |
| do_POST | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 602-622 |
| do_OPTIONS | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 624-629 |
| _to_dot | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 632-633 |
| GraphRenderer | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 638-789 |
| render_tree | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 641-708 |
| _build_tree | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 652-703 |
| render_impact_heatmap | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 710-731 |
| render_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 733-749 |
| render_query_table | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 751-789 |
| DotExporter | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 794-805 |
| export | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 796-805 |
| GraphBrowser | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 810-1134 |
| __init__ | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 812-817 |
| run | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 819-918 |
| _ask | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 920-923 |
| _get_overview_nodes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 925-928 |
| _get_frame_nodes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 930-966 |
| collect | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 948-953 |
| _render_current | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 968-991 |
| _render_overview | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 993-1006 |
| _render_search_results | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1008-1016 |
| _render_node_detail | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1018-1041 |
| _render_neighbors_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1043-1063 |
| _render_impact_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1065-1077 |
| _render_path_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1079-1089 |
| _render_expand_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1091-1103 |
| _render_query_input | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1105-1115 |
| _render_query_results_view | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1117-1134 |
| viz_command | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1139-1191 |
| _open | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py | 1173-1176 |

## Execution Flows

- **do_POST** (criticality: 0.44, depth: 1)
- **viz_command** (criticality: 0.43, depth: 5)

## Dependencies

### Outgoing

- `print` (66 edge(s))
- `fg` (52 edge(s))
- `append` (26 edge(s))
- `get` (22 edge(s))
- `len` (18 edge(s))
- `spine` (15 edge(s))
- `list` (14 edge(s))
- `sorted` (8 edge(s))
- `split` (8 edge(s))
- `join` (7 edge(s))
- `enumerate` (7 edge(s))
- `str` (6 edge(s))
- `neighbors` (6 edge(s))
- `set` (6 edge(s))
- `ljust` (6 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_graph_viz.py` (8 edge(s))
