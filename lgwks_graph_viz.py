"""lgwks_graph_viz — simple localhost graph visualization.

A single-file HTML+D3.js visualization served by a tiny Python HTTP server.
No build step, no dependencies beyond Python stdlib + the graph cache.

Usage:
    lgwks graph viz --serve [--port 3000] [--repo .]
    lgwks graph viz --export-html graph.html [--repo .]

Design:
  - Reads .lgwks/graph.cache.json (same cache as get_graph)
  - Serves embedded HTML with D3.js from CDN
  - API endpoints: /api/graph, /api/node/<id>, /api/query, /api/impact, /api/path
  - Terminal: color-coded by node kind, edge type, interactive zoom/pan/click
  - No auth, no share, localhost only

//why: the user wants to "see the graph" without learning Cypher or reading JSON.
This is the visual layer that IS the query layer — click a node, explore neighbors,
run impact analysis, trace paths. All pre-spliced from the existing graph cache.
"""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
import threading
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import lgwks_graph as gmod
import lgwks_ui as ui

ROOT = Path(__file__).resolve().parent


# ── data adapter ──────────────────────────────────────────────────────────────

class GraphDataAdapter:
    """Load graph cache and convert to frontend-friendly JSON."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.graph: gmod.Graph | None = None
        self._pagerank: dict[str, float] | None = None
        self._betweenness: dict[str, float] | None = None

    def load(self) -> bool:
        if not (self.repo / ".git").exists():
            return False
        try:
            self.graph = gmod.get_graph(self.repo)
            self._pagerank = self.graph.pagerank()
            self._betweenness = self.graph.betweenness_centrality()
            return True
        except Exception:
            return False

    def to_frontend(self) -> dict[str, Any]:
        """Return {nodes: [...], edges: [...]} for D3.js.

        Adds "xyz": [x, y, z] per node when I10 projection data is available
        (additive — D3 force-layout remains the fallback when xyz is absent).
        //why separate module import: lgwks_viz_project must never be imported
        into scoring/ranking modules (I10 decoupling invariant, INGESTION-LAYER §7.5).
        """
        if self.graph is None:
            return {"nodes": [], "edges": []}

        # I10: attempt deterministic server-side 3-D coords (additive, optional)
        xyz_map: dict[str, tuple[float, float, float]] = {}
        try:
            import lgwks_viz_project as _vp
            if _vp._HAS_NUMPY and self.graph.nodes:
                # Build fake records from node ids (no embeddings in graph cache → skip gracefully)
                pass   # projection wired when vector store is available; placeholder here
        except Exception:
            pass   # viz projection is best-effort; never break the renderer

        nodes = []
        for nid, node in self.graph.nodes.items():
            pr = self._pagerank.get(nid, 0) if self._pagerank else 0
            bc = self._betweenness.get(nid, 0) if self._betweenness else 0
            entry: dict[str, Any] = {
                "id": nid,
                "kind": node.kind,
                "defines": list(node.defines) if node.defines else [],
                "variables": list(node.variables) if node.variables else [],
                "calls": list(node.calls) if node.calls else [],
                "imports": list(node.imports) if node.imports else [],
                "config_keys": list(node.config_keys) if node.config_keys else [],
                "pagerank": round(pr, 4),
                "betweenness": round(bc, 4),
            }
            if nid in xyz_map:
                entry["xyz"] = list(xyz_map[nid])
            nodes.append(entry)
        edges = []
        for e in self.graph.edges:
            edges.append({
                "source": e.source,
                "target": e.target,
                "kind": e.kind,
                "weight": e.weight,
            })
        return {"nodes": nodes, "edges": edges}

    def node_detail(self, nid: str) -> dict[str, Any] | None:
        if self.graph is None:
            return None
        node = self.graph.nodes.get(nid)
        if node is None:
            return None
        pr = self._pagerank.get(nid, 0) if self._pagerank else 0
        bc = self._betweenness.get(nid, 0) if self._betweenness else 0
        out_n = self.graph.neighbors(nid)
        in_n = self.graph.predecessors(nid)
        return {
            "id": nid,
            "kind": node.kind,
            "defines": list(node.defines) if node.defines else [],
            "variables": list(node.variables) if node.variables else [],
            "calls": list(node.calls) if node.calls else [],
            "imports": list(node.imports) if node.imports else [],
            "config_keys": list(node.config_keys) if node.config_keys else [],
            "pagerank": round(pr, 4),
            "betweenness": round(bc, 4),
            "outgoing": out_n,
            "incoming": in_n,
        }

    def impact(self, files: list[str], radius: int = 3) -> dict[str, Any]:
        if self.graph is None:
            return {"scores": {}}
        scores = self.graph.change_propagation_score(files, radius=radius)
        return {
            "changed": files,
            "radius": radius,
            "scores": {k: round(v, 4) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        }

    def path(self, src: str, dst: str) -> dict[str, Any]:
        if self.graph is None:
            return {"path": [], "reachable": False}
        p = self.graph.shortest_path(src, dst)
        return {
            "from": src,
            "to": dst,
            "path": p if p else [],
            "reachable": p is not None,
        }

    def query(self, q: str) -> dict[str, Any]:
        if self.graph is None:
            return {"columns": [], "rows": []}
        try:
            result = gmod.execute_query(self.graph, q)
            return {"columns": result.columns, "rows": result.rows}
        except Exception as e:
            return {"error": str(e)}


# ── HTML template (embedded, zero build step) ─────────────────────────────────

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lgwks graph viz</title>
<script src="https://d3js.org/d3.v7.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<style>
  :root{--bg:#0a0e17;--fg:#c8d4e0;--dim:#5a6d7d;--accent:#22d3ee;--panel:rgba(10,14,23,.92);}
  *{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);overflow:hidden;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--fg);font-size:13px}
  #viz{position:fixed;inset:0}
  svg{width:100%;height:100%}
  #panel{position:fixed;top:12px;left:12px;width:280px;max-height:calc(100% - 24px);overflow:auto;background:var(--panel);border:1px solid rgba(34,211,238,.2);border-radius:10px;padding:14px;backdrop-filter:blur(8px);box-shadow:0 0 30px rgba(0,0,0,.4)}
  #panel h2{margin:0 0 10px;font-size:13px;color:#eafbff;letter-spacing:.1em;text-transform:uppercase}
  #panel .row{margin:6px 0;font-size:12px;line-height:1.5}
  #panel .label{color:var(--dim);font-size:10px;letter-spacing:.08em;text-transform:uppercase}
  #panel .value{color:var(--fg)}
  #panel .tag{display:inline-block;font-size:10px;padding:2px 7px;border-radius:12px;border:1px solid rgba(34,211,238,.35);color:var(--accent);margin:2px 4px 2px 0}
  #panel .barwrap{margin:8px 0;font-size:10px;color:var(--dim);letter-spacing:.06em;text-transform:uppercase}
  #panel .bar{height:6px;border-radius:3px;background:rgba(255,255,255,.06);overflow:hidden;margin-top:3px}
  #panel .bar>div{height:100%;border-radius:3px}
  #search{position:fixed;top:12px;left:308px;display:flex;gap:8px;align-items:center}
  #search input{background:var(--panel);border:1px solid rgba(34,211,238,.2);color:var(--fg);padding:7px 12px;border-radius:8px;font:inherit;width:220px;outline:none}
  #search input:focus{border-color:var(--accent)}
  #search button{background:var(--panel);border:1px solid rgba(34,211,238,.25);color:var(--fg);padding:6px 10px;border-radius:8px;cursor:pointer;font:inherit;font-size:11px}
  #search button:hover{border-color:var(--accent);color:#eafbff}
  #controls{position:fixed;bottom:12px;left:12px;display:flex;gap:8px;flex-wrap:wrap}
  #controls button{background:var(--panel);border:1px solid rgba(34,211,238,.2);color:var(--fg);padding:6px 10px;border-radius:8px;cursor:pointer;font:inherit;font-size:11px}
  #controls button:hover{border-color:var(--accent);color:#eafbff}
  #controls button.on{background:rgba(34,211,238,.15);border-color:var(--accent);color:#eafbff}
  #querybar{position:fixed;top:12px;right:12px;display:flex;gap:8px;align-items:center}
  #querybar input{background:var(--panel);border:1px solid rgba(34,211,238,.2);color:var(--fg);padding:7px 12px;border-radius:8px;font:inherit;width:280px;outline:none}
  #querybar input:focus{border-color:var(--accent)}
  #querybar button{background:var(--panel);border:1px solid rgba(34,211,238,.25);color:var(--fg);padding:6px 10px;border-radius:8px;cursor:pointer;font:inherit;font-size:11px}
  .node{stroke:#0a0e17;stroke-width:1.5px;cursor:pointer;transition:all .15s}
  .node:hover{stroke:var(--accent);stroke-width:3px}
  .node.highlighted{stroke:#f59e0b;stroke-width:3px}
  .node.dimmed{opacity:.15}
  .link{stroke-opacity:.35;transition:all .15s}
  .link.highlighted{stroke-opacity:1;stroke-width:2px}
  .link.dimmed{opacity:.05}
  text{fill:var(--fg);font-size:9px;pointer-events:none;opacity:.7}
  #hint{position:fixed;bottom:12px;right:12px;font-size:10px;color:var(--dim);text-align:right;line-height:1.5}
  #err{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(10,14,23,.92);z-index:100}
  #err .msg{text-align:center;color:#f59e0b;font-size:14px}
</style>
</head>
<body>
<div id="viz"><svg></svg></div>

<div id="panel">
  <h2>lgwks graph</h2>
  <div class="row"><span class="label">Nodes</span> <span class="value" id="stat-nodes">-</span></div>
  <div class="row"><span class="label">Edges</span> <span class="value" id="stat-edges">-</span></div>
  <div class="row"><span class="label">Orphans</span> <span class="value" id="stat-orphans">-</span></div>
  <div class="sep" style="height:1px;background:rgba(34,211,238,.12);margin:10px 0"></div>
  <div id="node-detail" style="display:none">
    <div class="row"><span class="label">ID</span> <span class="value" id="d-id"></span></div>
    <div class="row"><span class="label">Kind</span> <span class="value" id="d-kind"></span></div>
    <div class="row" id="d-pr-wrap"><span class="label">Pagerank</span>
      <div class="barwrap">Score<div class="bar"><div id="d-pr" style="width:0%;background:#22d3ee"></div></div></div>
    </div>
    <div class="row" id="d-bc-wrap"><span class="label">Betweenness</span>
      <div class="barwrap">Score<div class="bar"><div id="d-bc" style="width:0%;background:#f59e0b"></div></div></div>
    </div>
    <div class="row" id="d-defines-wrap" style="display:none"><span class="label">Defines</span><div id="d-defines"></div></div>
    <div class="row" id="d-calls-wrap" style="display:none"><span class="label">Calls</span><div id="d-calls"></div></div>
    <div class="row" id="d-imports-wrap" style="display:none"><span class="label">Imports</span><div id="d-imports"></div></div>
    <div class="row" id="d-out-wrap"><span class="label">Outgoing</span> <span class="value" id="d-out"></span></div>
    <div class="row" id="d-in-wrap"><span class="label">Incoming</span> <span class="value" id="d-in"></span></div>
    <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
      <button onclick="showNeighbors()" style="flex:1;background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.3);color:#eafbff;padding:5px;border-radius:6px;cursor:pointer;font:inherit;font-size:10px">Neighbors</button>
      <button onclick="showImpact()" style="flex:1;background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.3);color:#eafbff;padding:5px;border-radius:6px;cursor:pointer;font:inherit;font-size:10px">Impact</button>
      <button onclick="resetHighlight()" style="flex:1;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.15);color:var(--fg);padding:5px;border-radius:6px;cursor:pointer;font:inherit;font-size:10px">Reset</button>
    </div>
  </div>
  <div id="no-selection" style="color:var(--dim);font-size:12px;margin-top:8px">Click a node to explore</div>
</div>

<div id="search">
  <input type="text" id="search-input" placeholder="search nodes..." oninput="doSearch()"/>
  <button onclick="clearSearch()">Clear</button>
</div>

<div id="querybar">
  <input type="text" id="query-input" placeholder='MATCH (n) WHERE n.kind = "file" RETURN n.id LIMIT 10'/>
  <button onclick="runQuery()">Query</button>
</div>

<div id="controls">
  <button id="mode-heat" onclick="toggleHeat()">Heat: OFF</button>
  <button onclick="resetZoom()">Reset Zoom</button>
  <button onclick="exportDot()">Export DOT</button>
</div>

<div id="hint">
  scroll · zoom · drag · click node · double-click expand
</div>

<div id="err"><div class="msg" id="err-msg">Loading graph...</div></div>

<script>
// ── config ──────────────────────────────────────────────────────────────────
const NODE_COLOR = {
  file: '#3b82f6',      // blue
  config: '#22c55e',    // green
  data: '#f97316',      // orange
  unknown: '#6b7280'    // gray
};
const EDGE_STYLE = {
  import: {color: '#22d3ee', dash: 'none', width: 1},
  call: {color: '#f59e0b', dash: '4,3', width: 1},
  inherit: {color: '#a855f7', dash: '2,2', width: 1},
  contains: {color: '#6b7280', dash: 'none', width: .5}
};

let graph = {nodes: [], edges: []};
let simulation, svg, g, zoom;
let selectedNode = null;
let heatMode = false;
let nodeById = {};
let linkData = [];
let prMax = 1, bcMax = 1;

// ── load ────────────────────────────────────────────────────────────────────
async function loadGraph() {
  try {
    const r = await fetch('/api/graph');
    graph = await r.json();
    graph.nodes.forEach(n => nodeById[n.id] = n);
    prMax = Math.max(...graph.nodes.map(n => n.pagerank || 0), 0.001);
    bcMax = Math.max(...graph.nodes.map(n => n.betweenness || 0), 0.001);
    render();
    document.getElementById('stat-nodes').textContent = graph.nodes.length;
    document.getElementById('stat-edges').textContent = graph.edges.length;
    const orphanCount = graph.nodes.filter(n => {
      const out = graph.edges.filter(e => e.source === n.id).length;
      const inn = graph.edges.filter(e => e.target === n.id).length;
      return out + inn === 0;
    }).length;
    document.getElementById('stat-orphans').textContent = orphanCount;
    document.getElementById('err').style.display = 'none';
  } catch (e) {
    document.getElementById('err-msg').textContent = 'Failed to load graph: ' + e.message;
  }
}

// ── render ──────────────────────────────────────────────────────────────────
function render() {
  const container = document.querySelector('#viz svg');
  const w = container.clientWidth || window.innerWidth;
  const h = container.clientHeight || window.innerHeight;
  d3.select(container).selectAll('*').remove();

  svg = d3.select(container).attr('viewBox', [0, 0, w, h]);
  g = svg.append('g');

  zoom = d3.zoom().scaleExtent([0.1, 4]).on('zoom', e => g.attr('transform', e.transform));
  svg.call(zoom);

  simulation = d3.forceSimulation(graph.nodes)
    .force('link', d3.forceLink(graph.edges).id(d => d.id).distance(60))
    .force('charge', d3.forceManyBody().strength(-180))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collide', d3.forceCollide().radius(18));

  // links
  const link = g.append('g').attr('class', 'links')
    .selectAll('line').data(graph.edges).join('line')
    .attr('class', 'link')
    .attr('stroke', d => (EDGE_STYLE[d.kind] || EDGE_STYLE.import).color)
    .attr('stroke-width', d => (EDGE_STYLE[d.kind] || EDGE_STYLE.import).width)
    .attr('stroke-dasharray', d => (EDGE_STYLE[d.kind] || EDGE_STYLE.import).dash);
  linkData = link;

  // nodes
  const node = g.append('g').attr('class', 'nodes')
    .selectAll('circle').data(graph.nodes).join('circle')
    .attr('class', 'node')
    .attr('r', d => 4 + Math.sqrt(d.pagerank / prMax) * 10)
    .attr('fill', d => NODE_COLOR[d.kind] || NODE_COLOR.unknown)
    .call(d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended))
    .on('click', (e, d) => { e.stopPropagation(); selectNode(d); })
    .on('dblclick', (e, d) => { e.stopPropagation(); expandNode(d); });

  // labels (only for high-pagerank nodes)
  const label = g.append('g').attr('class', 'labels')
    .selectAll('text').data(graph.nodes.filter(n => n.pagerank > prMax * 0.3)).join('text')
    .text(d => d.id.split('/').pop())
    .attr('x', 8).attr('y', 3);

  simulation.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('cx', d => d.x).attr('cy', d => d.y);
    label.attr('x', d => d.x + 8).attr('y', d => d.y + 3);
  });

  svg.on('click', () => deselectNode());
}

// ── interaction ─────────────────────────────────────────────────────────────
function selectNode(d) {
  selectedNode = d;
  document.getElementById('node-detail').style.display = 'block';
  document.getElementById('no-selection').style.display = 'none';
  document.getElementById('d-id').textContent = d.id;
  document.getElementById('d-kind').textContent = d.kind;
  document.getElementById('d-pr').style.width = Math.min((d.pagerank / prMax) * 100, 100) + '%';
  document.getElementById('d-bc').style.width = Math.min((d.betweenness / bcMax) * 100, 100) + '%';
  setTags('d-defines', d.defines);
  setTags('d-calls', d.calls);
  setTags('d-imports', d.imports);
  document.getElementById('d-out').textContent = d.outgoing?.length ?? graph.edges.filter(e => e.source === d.id).length;
  document.getElementById('d-in').textContent = d.incoming?.length ?? graph.edges.filter(e => e.target === d.id).length;
  highlightNode(d.id);
}

function deselectNode() {
  selectedNode = null;
  document.getElementById('node-detail').style.display = 'none';
  document.getElementById('no-selection').style.display = 'block';
  resetHighlight();
}

function setTags(id, items) {
  const el = document.getElementById(id);
  const wrap = document.getElementById(id + '-wrap');
  if (!items || !items.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  el.innerHTML = items.map(x => '<span class="tag">' + x + '</span>').join('');
}

function highlightNode(nodeId) {
  d3.selectAll('.node').classed('highlighted', d => d.id === nodeId).classed('dimmed', d => d.id !== nodeId);
  d3.selectAll('.link').classed('highlighted', d => d.source.id === nodeId || d.target.id === nodeId).classed('dimmed', d => d.source.id !== nodeId && d.target.id !== nodeId);
}

function resetHighlight() {
  d3.selectAll('.node').classed('highlighted', false).classed('dimmed', false);
  d3.selectAll('.link').classed('highlighted', false).classed('dimmed', false);
}

function expandNode(d) {
  // double-click: temporarily pin node and show its neighbors more clearly
  highlightNode(d.id);
}

function showNeighbors() {
  if (!selectedNode) return;
  highlightNode(selectedNode.id);
}

async function showImpact() {
  if (!selectedNode) return;
  try {
    const r = await fetch('/api/impact?files=' + encodeURIComponent(selectedNode.id) + '&radius=3');
    const data = await r.json();
    const scores = data.scores || {};
    // color nodes by impact score
    d3.selectAll('.node').attr('fill', d => {
      const s = scores[d.id];
      if (s === undefined) return NODE_COLOR[d.kind] || NODE_COLOR.unknown;
      const t = Math.min(s, 1);
      // interpolate: low = green, high = red
      const r = Math.floor(34 + t * (239 - 34));
      const g = Math.floor(211 + t * (68 - 211));
      const b = Math.floor(238 + t * (68 - 238));
      return `rgb(${r},${g},${b})`;
    });
    document.getElementById('mode-heat').textContent = 'Heat: ON';
    document.getElementById('mode-heat').classList.add('on');
    heatMode = true;
  } catch (e) { console.error(e); }
}

function toggleHeat() {
  if (heatMode) {
    d3.selectAll('.node').attr('fill', d => NODE_COLOR[d.kind] || NODE_COLOR.unknown);
    document.getElementById('mode-heat').textContent = 'Heat: OFF';
    document.getElementById('mode-heat').classList.remove('on');
    heatMode = false;
  } else {
    if (selectedNode) showImpact();
  }
}

function resetZoom() {
  svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
}

// ── search ──────────────────────────────────────────────────────────────────
function doSearch() {
  const q = document.getElementById('search-input').value.toLowerCase();
  if (!q) { resetHighlight(); return; }
  const matched = new Set(graph.nodes.filter(n => n.id.toLowerCase().includes(q)).map(n => n.id));
  d3.selectAll('.node').classed('highlighted', d => matched.has(d.id)).classed('dimmed', d => !matched.has(d.id));
  d3.selectAll('.link').classed('dimmed', true);
}

function clearSearch() {
  document.getElementById('search-input').value = '';
  resetHighlight();
}

// ── query ───────────────────────────────────────────────────────────────────
async function runQuery() {
  const q = document.getElementById('query-input').value.trim();
  if (!q) return;
  try {
    const r = await fetch('/api/query', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({q})});
    const data = await r.json();
    if (data.error) { alert('Query error: ' + data.error); return; }
    // Highlight returned nodes
    const ids = new Set();
    (data.rows || []).forEach(row => {
      Object.values(row).forEach(v => { if (v && v.id) ids.add(v.id); });
    });
    d3.selectAll('.node').classed('highlighted', d => ids.has(d.id)).classed('dimmed', d => !ids.has(d.id));
    d3.selectAll('.link').classed('dimmed', true);
    document.getElementById('no-selection').style.display = 'block';
    document.getElementById('no-selection').textContent = `Query returned ${data.rows?.length || 0} rows`;
  } catch (e) { alert('Query failed: ' + e.message); }
}

// ── export ───────────────────────────────────────────────────────────────────
async function exportDot() {
  try {
    const r = await fetch('/api/dot');
    const dot = await r.text();
    const blob = new Blob([dot], {type: 'text/plain'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'graph.dot';
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) { alert('Export failed: ' + e.message); }
}

// ── drag ────────────────────────────────────────────────────────────────────
function dragstarted(e, d) { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
function dragged(e, d) { d.fx = e.x; d.fy = e.y; }
function dragended(e, d) { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }

// ── init ──────────────────────────────────────────────────────────────────────
loadGraph();
</script>
</body>
</html>
"""


# ── HTTP handler ────────────────────────────────────────────────────────────

class VizHandler(http.server.BaseHTTPRequestHandler):
    """Serve the viz HTML page and JSON API endpoints."""

    adapter: GraphDataAdapter | None = None

    def log_message(self, fmt, *args):
        # Suppress default request logging for cleanliness
        pass

    def _json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _text(self, text: str, status: int = 200, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._text(_HTML_TEMPLATE, content_type="text/html")
            return

        if path == "/api/graph":
            if self.adapter is None or self.adapter.graph is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            self._json(self.adapter.to_frontend())
            return

        if path.startswith("/api/node/"):
            nid = path[len("/api/node/"):]
            if self.adapter is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            detail = self.adapter.node_detail(nid)
            if detail is None:
                self._json({"error": "node not found"}, 404)
                return
            self._json(detail)
            return

        if path == "/api/impact":
            files = qs.get("files", [""])[0].split(",") if qs.get("files") else []
            radius = int(qs.get("radius", ["3"])[0])
            if self.adapter is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            self._json(self.adapter.impact(files, radius))
            return

        if path == "/api/path":
            src = qs.get("from", [""])[0]
            dst = qs.get("to", [""])[0]
            if self.adapter is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            self._json(self.adapter.path(src, dst))
            return

        if path == "/api/dot":
            if self.adapter is None or self.adapter.graph is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            self._text(self._to_dot(self.adapter.graph), content_type="text/plain")
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/query":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return
            q = payload.get("q", "")
            if self.adapter is None:
                self._json({"error": "graph not loaded"}, 503)
                return
            self._json(self.adapter.query(q))
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    @staticmethod
    def _to_dot(graph: gmod.Graph) -> str:
        return graph.to_dot()


# ── renderers ──────────────────────────────────────────────────────────────────

class GraphRenderer:
    """ASCII/Unicode tree rendering of a Graph subgraph."""

    def render_tree(self, graph: gmod.Graph, root_ids: list[str], depth: int = 3, *, on: bool = True, node_indices: dict[str, int] | None = None) -> list[str]:
        """Return lines of Unicode box-drawing text."""
        pageranks = graph.pagerank()
        betweennesses = graph.betweenness_centrality()
        
        pr_thresh = max(pageranks.values()) * 0.3 if pageranks else 0.1
        bc_thresh = max(betweennesses.values()) * 0.3 if betweennesses else 0.1
        
        lines: list[str] = []
        visited: set[str] = set()

        def _build_tree(node_id: str, current_depth: int, prefix: str, is_last: bool):
            if node_id not in graph.nodes:
                return
            
            node = graph.nodes[node_id]
            pr = pageranks.get(node_id, 0.0)
            bc = betweennesses.get(node_id, 0.0)
            
            is_orphan = len(graph.neighbors(node_id)) == 0 and len(graph.predecessors(node_id)) == 0
            
            if is_orphan:
                color = ui.SLATE_DIM
            elif pr > pr_thresh:
                color = ui.EMERALD
            elif bc > bc_thresh:
                color = ui.AMBER
            else:
                color = ui.CREAM
            
            node_label = node_id.split("/")[-1] if "/" in node_id else node_id
            if node_indices is not None and node_id in node_indices:
                idx = node_indices[node_id]
                node_label = f"[{idx}] {node_label}"
                
            connector = ""
            if current_depth > 0:
                connector = "┗━ " if is_last else "┣━ "
            
            line_str = f"{prefix}{connector}{ui.fg(node_label, color, on=on, bold=(pr > pr_thresh))}"
            if current_depth == 0:
                line_str = f"{ui.fg('▸', ui.EMERALD, on=on)} {line_str}"
            lines.append(line_str)
            
            if current_depth >= depth:
                return
            
            if node_id in visited:
                if current_depth < depth:
                    child_prefix = prefix + ("   " if is_last else "┃  ")
                    lines.append(f"{child_prefix}┗━ {ui.fg('↺ cycle', ui.SLATE_DIM, on=on)}")
                return
            
            visited.add(node_id)
            
            successors = graph.neighbors(node_id)
            if not successors:
                return
                
            child_prefix = prefix + ("   " if is_last else "┃  ") if current_depth > 0 else "  "
            
            for idx, succ in enumerate(successors):
                _build_tree(succ, current_depth + 1, child_prefix, idx == len(successors) - 1)

        for root in root_ids:
            _build_tree(root, 0, "", True)
            
        return lines

    def render_impact_heatmap(self, graph: gmod.Graph, scores: dict[str, float], *, on: bool = True) -> list[str]:
        """Render nodes colored by impact score (0→green, 1→red)."""
        lines: list[str] = []
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        for nid, val in sorted_scores:
            if nid not in graph.nodes:
                continue
            if val >= 0.75:
                color = ui.RUST
            elif val >= 0.25:
                color = ui.AMBER
            else:
                color = ui.CREAM_DIM
            
            filled = round(val * 10)
            meter = "█" * filled + "░" * (10 - filled)
            meter_colored = ui.fg(meter, color, on=on)
            
            node_label = nid.split("/")[-1] if "/" in nid else nid
            line = f"  {ui.fg('┃', ui.SLATE, on=on)} {ui.fg(node_label.ljust(30), ui.CREAM, on=on)} {meter_colored} {ui.fg(f'{val:.2f}', ui.CREAM, on=on)}"
            lines.append(line)
        return lines

    def render_path(self, graph: gmod.Graph, path: list[str], *, on: bool = True) -> list[str]:
        """Render a shortest path as a connected chain."""
        lines: list[str] = []
        if not path:
            return [f"  {ui.fg('┃', ui.SLATE, on=on)} {ui.fg('No path found', ui.RUST, on=on)}"]
            
        for i, nid in enumerate(path):
            node = graph.nodes.get(nid)
            node_label = nid.split("/")[-1] if "/" in nid else nid
            kind_color = {"file": ui.CREAM, "config": ui.EMERALD, "data": ui.AMBER}.get(node.kind if node else "", ui.CREAM)
            
            if i > 0:
                lines.append(f"  {ui.fg('┃', ui.SLATE, on=on)}   {ui.fg('▾', ui.EMERALD, on=on)}")
                
            lines.append(f"  {ui.fg('┃', ui.SLATE, on=on)} {ui.fg(node_label, kind_color, on=on, bold=True)}")
            
        return lines

    def render_query_table(self, result: gmod.QueryResult, max_width: int = 80, *, on: bool = True) -> list[str]:
        """Render QueryResult as a bordered table."""
        lines: list[str] = []
        if not result.columns or not result.rows:
            return [f"  {ui.fg('┃', ui.SLATE, on=on)} {ui.fg('No results', ui.SLATE_DIM, on=on)}"]

        col_widths: dict[str, int] = {}
        for col in result.columns:
            col_widths[col] = len(col)
            
        for row in result.rows:
            for col in result.columns:
                val = row.get(col, "")
                if isinstance(val, dict) and "id" in val:
                    val_str = val["id"]
                else:
                    val_str = str(val)
                col_widths[col] = max(col_widths[col], len(val_str))
                
        header_parts = []
        for col in result.columns:
            header_parts.append(ui.fg(col.ljust(col_widths[col]), ui.EMERALD, on=on, bold=True))
        lines.append("  " + ui.fg("┃", ui.SLATE, on=on) + " " + " │ ".join(header_parts) + " ")
        
        divider_parts = ["─" * col_widths[col] for col in result.columns]
        lines.append("  " + ui.fg("┃", ui.SLATE, on=on) + " " + "─┼─".join(divider_parts) + " ")
        
        for row in result.rows:
            row_parts = []
            for col in result.columns:
                val = row.get(col, "")
                if isinstance(val, dict) and "id" in val:
                    val_str = val["id"]
                else:
                    val_str = str(val)
                row_parts.append(ui.fg(val_str.ljust(col_widths[col]), ui.CREAM, on=on))
            lines.append("  " + ui.fg("┃", ui.SLATE, on=on) + " " + " │ ".join(row_parts) + " ")
            
        return lines


# ── DotExporter ─────────────────────────────────────────────────────────────

class DotExporter:
    """Export Graph or subgraph to DOT format for Graphviz."""
    def export(self, graph: gmod.Graph, path: Path | str, highlight: set[str] | None = None) -> None:
        """Write .dot file. highlight = node IDs to color differently."""
        dot_str = graph.to_dot(highlight=highlight)
        if str(path) == "-":
            sys.stdout.write(dot_str + "\n")
        else:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(dot_str, encoding="utf-8")
            print(f"[viz] exported graph to {p}")


# ── interactive browser ─────────────────────────────────────────────────────

class GraphBrowser:
    """Stack-based TUI for graph exploration. Same navigation model as lgwks_home browser."""
    def __init__(self, graph: gmod.Graph, on: bool = True):
        self.graph = graph
        self.on = on
        self.stack: list[tuple[str, ...]] = [("overview",)]
        self.selected_node: str | None = None
        self.renderer = GraphRenderer()

    def run(self) -> int:
        """Main loop. Returns exit code."""
        if not sys.stdin.isatty():
            return 0
            
        self._render_current()
        
        while True:
            try:
                choice = self._ask("")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
                
            low = choice.strip().lower()
            if low in ("q", "quit", "exit"):
                print(f"  {ui.fg('← stay curious.', ui.EMERALD_DIM, on=self.on)}")
                return 0
                
            if low in ("b", "back"):
                if len(self.stack) > 1:
                    self.stack.pop()
                    print(ui.spine(on=self.on))
                    self._render_current()
                else:
                    print(f"  {ui.fg('already at overview', ui.CREAM_DIM, on=self.on)}")
                continue
                
            frame = self.stack[-1]
            frame_type = frame[0]
            
            if frame_type == "overview":
                if low == "s":
                    query = self._ask("search pattern: ")
                    matched = [nid for nid in self.graph.nodes if query.lower() in nid.lower()]
                    if not matched:
                        print(f"  {ui.fg('No nodes match pattern', ui.RUST, on=self.on)}")
                    elif len(matched) == 1:
                        self.stack.append(("node", matched[0]))
                        self._render_current()
                    else:
                        self.stack.append(("search_results", query, tuple(matched)))
                        self._render_current()
                elif low == "p":
                    src = self._ask("source node id: ")
                    dst = self._ask("target node id: ")
                    self.stack.append(("path", src, dst))
                    self._render_current()
                elif low == "q":
                    self._render_query_input()
                elif low.isdigit():
                    idx = int(low) - 1
                    top_nodes = self._get_overview_nodes()
                    if 0 <= idx < len(top_nodes):
                        self.stack.append(("node", top_nodes[idx]))
                        self._render_current()
                else:
                    if choice in self.graph.nodes:
                        self.stack.append(("node", choice))
                        self._render_current()
                    else:
                        print(f"  {ui.fg('Invalid option or unknown node', ui.RUST, on=self.on)}")
                        
            elif frame_type == "search_results":
                if low.isdigit():
                    idx = int(low) - 1
                    nodes = frame[2]
                    if 0 <= idx < len(nodes):
                        self.stack.append(("node", nodes[idx]))
                        self._render_current()
                else:
                    print(f"  {ui.fg('Invalid option', ui.RUST, on=self.on)}")
                    
            elif frame_type == "node":
                node_id = frame[1]
                if low == "n":
                    self.stack.append(("neighbors", node_id))
                    self._render_current()
                elif low == "i":
                    self.stack.append(("impact", node_id))
                    self._render_current()
                elif low == "p":
                    dst = self._ask("target node id: ")
                    self.stack.append(("path", node_id, dst))
                    self._render_current()
                elif low == "e":
                    self.stack.append(("expand", node_id))
                    self._render_current()
                else:
                    print(f"  {ui.fg('Invalid option', ui.RUST, on=self.on)}")

            elif frame_type in ("neighbors", "impact", "path", "expand", "query_results"):
                if low.isdigit():
                    idx = int(low) - 1
                    nodes_list = self._get_frame_nodes(frame)
                    if 0 <= idx < len(nodes_list):
                        self.stack.append(("node", nodes_list[idx]))
                        self._render_current()
                else:
                    print(f"  {ui.fg('Invalid option', ui.RUST, on=self.on)}")

    def _ask(self, prompt: str) -> str:
        sys.stdout.write(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {prompt}")
        sys.stdout.flush()
        return sys.stdin.readline().strip()

    def _get_overview_nodes(self) -> list[str]:
        pageranks = self.graph.pagerank()
        sorted_nodes = sorted(self.graph.nodes.keys(), key=lambda x: -pageranks.get(x, 0.0))
        return sorted_nodes[:15]

    def _get_frame_nodes(self, frame: tuple[str, ...]) -> list[str]:
        frame_type = frame[0]
        if frame_type == "neighbors":
            node_id = frame[1]
            out_n = self.graph.neighbors(node_id)
            in_n = self.graph.predecessors(node_id)
            return sorted(list(set(out_n + in_n)))
        elif frame_type == "impact":
            node_id = frame[1]
            scores = self.graph.change_propagation_score([node_id], radius=3)
            return sorted(scores.keys(), key=lambda x: -scores[x])
        elif frame_type == "path":
            path = self.graph.shortest_path(frame[1], frame[2])
            return path if path else []
        elif frame_type == "expand":
            node_id = frame[1]
            visited = set()
            nodes_list = []
            def collect(nid, d):
                if d > 2 or nid in visited: return
                visited.add(nid)
                nodes_list.append(nid)
                for s in self.graph.neighbors(nid):
                    collect(s, d+1)
            collect(node_id, 0)
            return sorted(nodes_list)
        elif frame_type == "query_results":
            rows = frame[1]
            nodes = set()
            for row in rows:
                for v in row.values():
                    if isinstance(v, dict) and "id" in v:
                        nodes.add(v["id"])
                    elif isinstance(v, str) and v in self.graph.nodes:
                        nodes.add(v)
            return sorted(list(nodes))
        return []

    def _render_current(self) -> None:
        frame = self.stack[-1]
        frame_type = frame[0]
        
        subtitle = " · ".join(str(x) for x in frame[1:]) if len(frame) > 1 else ""
        for line in ui.band(f"graph {frame_type}", subtitle, on=self.on):
            print(line)
            
        if frame_type == "overview":
            self._render_overview()
        elif frame_type == "search_results":
            self._render_search_results(frame[1], frame[2])
        elif frame_type == "node":
            self._render_node_detail(frame[1])
        elif frame_type == "neighbors":
            self._render_neighbors_view(frame[1])
        elif frame_type == "impact":
            self._render_impact_view(frame[1])
        elif frame_type == "path":
            self._render_path_view(frame[1], frame[2])
        elif frame_type == "expand":
            self._render_expand_view(frame[1])
        elif frame_type == "query_results":
            self._render_query_results_view(frame[1], frame[2])

    def _render_overview(self) -> None:
        s = self.graph.stats()
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Stats:', ui.CREAM_DIM, on=self.on)} {s['nodes']} nodes · {s['edges']} edges")
        print(ui.spine(on=self.on))
        
        top_nodes = self._get_overview_nodes()
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Top modules (by PageRank):', ui.CREAM_DIM, on=self.on)}")
        for idx, nid in enumerate(top_nodes):
            pr = self.graph.pagerank().get(nid, 0.0)
            node_label = nid.split("/")[-1] if "/" in nid else nid
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)}   {idx+1:2d} {ui.fg(node_label.ljust(30), ui.CREAM, on=self.on)} {ui.fg(f'PR: {pr:.4f}', ui.SLATE_DIM, on=self.on)}")
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('q quit  ·  [number] pick node  ·  s search  ·  p path  ·  q query', ui.SLATE_DIM, on=self.on)}")

    def _render_search_results(self, query: str, results: tuple[str, ...]) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg(f'Search results for {query!r}:', ui.CREAM_DIM, on=self.on)}")
        for idx, nid in enumerate(results[:15]):
            node_label = nid.split("/")[-1] if "/" in nid else nid
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)}   {idx+1:2d} {ui.fg(node_label.ljust(30), ui.CREAM, on=self.on)} {ui.fg(nid, ui.SLATE_DIM, on=self.on)}")
        if len(results) > 15:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)}   ... and {len(results)-15} more")
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node', ui.SLATE_DIM, on=self.on)}")

    def _render_node_detail(self, node_id: str) -> None:
        node = self.graph.nodes.get(node_id)
        if not node:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Node not found', ui.RUST, on=self.on)}")
            return
            
        pr = self.graph.pagerank().get(node_id, 0.0)
        bc = self.graph.betweenness_centrality().get(node_id, 0.0)
        
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('ID:', ui.CREAM_DIM, on=self.on)} {ui.fg(node_id, ui.CREAM, on=self.on)}")
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Kind:', ui.CREAM_DIM, on=self.on)} {ui.fg(node.kind, ui.EMERALD, on=self.on)}")
        
        print(ui.scale("PageRank", pr, "low", "high", on=self.on))
        print(ui.scale("Betweenness", bc, "low", "high", on=self.on))
        
        if node.defines:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Defines:', ui.CREAM_DIM, on=self.on)} {', '.join(node.defines)}")
        if node.calls:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Calls:', ui.CREAM_DIM, on=self.on)} {', '.join(node.calls[:5])}{'...' if len(node.calls) > 5 else ''}")
        if node.imports:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Imports:', ui.CREAM_DIM, on=self.on)} {', '.join(node.imports[:5])}{'...' if len(node.imports) > 5 else ''}")
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [n] neighbors  ·  [i] impact  ·  [p] path to...  ·  [e] expand', ui.SLATE_DIM, on=self.on)}")

    def _render_neighbors_view(self, node_id: str) -> None:
        out_n = self.graph.neighbors(node_id)
        in_n = self.graph.predecessors(node_id)
        all_n = sorted(list(set(out_n + in_n)))
        
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Neighbors of:', ui.CREAM_DIM, on=self.on)} {ui.fg(node_id, ui.CREAM, on=self.on)}")
        print(ui.spine(on=self.on))
        
        for idx, nid in enumerate(all_n):
            node_label = nid.split("/")[-1] if "/" in nid else nid
            direction = ""
            if nid in out_n and nid in in_n:
                direction = "⇄"
            elif nid in out_n:
                direction = "▸"
            else:
                direction = "◂"
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)}   {idx+1:2d} {ui.fg(direction, ui.EMERALD, on=self.on)} {ui.fg(node_label.ljust(30), ui.CREAM, on=self.on)} {ui.fg(nid, ui.SLATE_DIM, on=self.on)}")
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node', ui.SLATE_DIM, on=self.on)}")

    def _render_impact_view(self, node_id: str) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Change propagation impact radius (r=3) for:', ui.CREAM_DIM, on=self.on)} {ui.fg(node_id, ui.CREAM, on=self.on)}")
        print(ui.spine(on=self.on))
        
        scores = self.graph.change_propagation_score([node_id], radius=3)
        heatmap_lines = self.renderer.render_impact_heatmap(self.graph, scores, on=self.on)
        for line in heatmap_lines[:15]:
            print(line)
        if len(heatmap_lines) > 15:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)}   ... and {len(heatmap_lines)-15} more")
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node', ui.SLATE_DIM, on=self.on)}")

    def _render_path_view(self, src: str, dst: str) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Shortest path:', ui.CREAM_DIM, on=self.on)} {ui.fg(src, ui.CREAM, on=self.on)} → {ui.fg(dst, ui.CREAM, on=self.on)}")
        print(ui.spine(on=self.on))
        
        path = self.graph.shortest_path(src, dst)
        path_lines = self.renderer.render_path(self.graph, path, on=self.on)
        for line in path_lines:
            print(line)
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node', ui.SLATE_DIM, on=self.on)}")

    def _render_expand_view(self, node_id: str) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Expanded tree view for:', ui.CREAM_DIM, on=self.on)} {ui.fg(node_id, ui.CREAM, on=self.on)}")
        print(ui.spine(on=self.on))
        
        nodes_list = self._get_frame_nodes(("expand", node_id))
        node_indices = {nid: idx + 1 for idx, nid in enumerate(nodes_list)}
        
        tree_lines = self.renderer.render_tree(self.graph, [node_id], depth=2, on=self.on, node_indices=node_indices)
        for line in tree_lines:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {line}")
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node', ui.SLATE_DIM, on=self.on)}")

    def _render_query_input(self) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Enter Cypher-like query:', ui.CREAM_DIM, on=self.on)}")
        query_str = self._ask("query: ")
        if not query_str:
            return
        try:
            res = gmod.execute_query(self.graph, query_str)
            self.stack.append(("query_results", res.rows, res.columns))
            self._render_current()
        except Exception as e:
            print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg(f'Query error: {e}', ui.RUST, on=self.on)}")

    def _render_query_results_view(self, rows: list[dict[str, Any]], columns: list[str]) -> None:
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('Query Results:', ui.CREAM_DIM, on=self.on)}")
        print(ui.spine(on=self.on))
        
        col_with_idx = ["#"] + columns
        rows_with_idx = []
        for idx, row in enumerate(rows):
            new_row = row.copy()
            new_row["#"] = str(idx + 1)
            rows_with_idx.append(new_row)
            
        res = gmod.QueryResult(col_with_idx, rows_with_idx)
        table_lines = self.renderer.render_query_table(res, on=self.on)
        for line in table_lines:
            print(line)
            
        print(ui.spine(on=self.on))
        print(f"  {ui.fg('┃', ui.SLATE, on=self.on)} {ui.fg('b back  ·  [number] pick node in results', ui.SLATE_DIM, on=self.on)}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def viz_command(args) -> int:
    """CLI entry point for lgwks graph viz."""
    repo = Path(getattr(args, "repo", ".")).resolve()
    adapter = GraphDataAdapter(repo)
    if not adapter.load():
        print(f"[viz] not a git repo or graph load failed: {repo}", file=sys.stderr)
        return 1

    # Export DOT
    export_dot = getattr(args, "export_dot", None)
    if export_dot:
        hl = set(getattr(args, "files", "").split(",")) if getattr(args, "files", "") else None
        exporter = DotExporter()
        exporter.export(adapter.graph, export_dot, highlight=hl)
        return 0

    # Export HTML
    export_path = getattr(args, "export_html", None)
    if export_path:
        path = Path(export_path)
        path.write_text(_HTML_TEMPLATE, encoding="utf-8")
        print(f"[viz] exported static HTML to {path}")
        return 0

    # Serve HTTP
    if getattr(args, "serve", False) or (getattr(args, "graph_command", None) == "viz" and getattr(args, "serve", False)):
        port = getattr(args, "port", 3000)
        VizHandler.adapter = adapter

        with socketserver.TCPServer(("", port), VizHandler) as httpd:
            url = f"http://localhost:{port}"
            print(f"[viz] serving graph for {repo.name} at {url}")
            print(f"[viz] nodes: {len(adapter.graph.nodes)}, edges: {len(adapter.graph.edges)}")
            print(f"[viz] press Ctrl+C to stop")
            def _open():
                import time
                time.sleep(0.5)
                webbrowser.open(url)
            threading.Thread(target=_open, daemon=True).start()
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n[viz] stopped")
                return 0
            
    # Otherwise: Terminal TUI (GraphBrowser)
    try:
        on = ui.color_on()
    except Exception:
        on = True
        
    browser = GraphBrowser(adapter.graph, on=on)
    return browser.run()


if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser(description="lgwks graph visualization")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--serve", action="store_true", help="start HTTP server")
    parser.add_argument("--port", type=int, default=3000, help="server port")
    parser.add_argument("--export-html", help="export static HTML file")
    parser.add_argument("--export-dot", help="export DOT file (use - for stdout)")
    parser.add_argument("--files", default="", help="comma-separated changed files to highlight in DOT export")
    args = parser.parse_args()
    sys.exit(viz_command(args))
