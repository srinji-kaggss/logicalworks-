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
        """Return {nodes: [...], edges: [...]} for D3.js."""
        if self.graph is None:
            return {"nodes": [], "edges": []}
        nodes = []
        for nid, node in self.graph.nodes.items():
            pr = self._pagerank.get(nid, 0) if self._pagerank else 0
            bc = self._betweenness.get(nid, 0) if self._betweenness else 0
            nodes.append({
                "id": nid,
                "kind": node.kind,
                "defines": list(node.defines) if node.defines else [],
                "variables": list(node.variables) if node.variables else [],
                "calls": list(node.calls) if node.calls else [],
                "imports": list(node.imports) if node.imports else [],
                "config_keys": list(node.config_keys) if node.config_keys else [],
                "pagerank": round(pr, 4),
                "betweenness": round(bc, 4),
            })
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
        lines = ["digraph lgwks {", "  rankdir=LR;", "  node [shape=box, fontname=\"monospace\", fontsize=10];"]
        kind_color = {"file": "#3b82f6", "config": "#22c55e", "data": "#f97316"}
        for nid, node in graph.nodes.items():
            color = kind_color.get(node.kind, "#6b7280")
            label = nid.split("/")[-1] if "/" in nid else nid
            lines.append(f'  "{nid}" [label="{label}", color="{color}", fontcolor="#e2e8f0"];')
        for e in graph.edges:
            style = {"import": "solid", "call": "dashed", "inherit": "dotted", "contains": "solid"}.get(e.kind, "solid")
            lines.append(f'  "{e.source}" -> "{e.target}" [style={style}, color="#64748b", fontsize=9];')
        lines.append("}")
        return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

def viz_command(args) -> int:
    """CLI entry point: lgwks graph viz --serve [--port 3000] [--repo .] [--export-html file]"""
    repo = Path(getattr(args, "repo", ".")).resolve()
    adapter = GraphDataAdapter(repo)
    if not adapter.load():
        print(f"[viz] not a git repo or graph load failed: {repo}", file=sys.stderr)
        return 1

    # Export HTML
    export_path = getattr(args, "export_html", None)
    if export_path:
        path = Path(export_path)
        path.write_text(_HTML_TEMPLATE, encoding="utf-8")
        print(f"[viz] exported static HTML to {path}")
        return 0

    # Serve
    if not getattr(args, "serve", False):
        print("[viz] use --serve to start the visualization server", file=sys.stderr)
        return 1

    port = getattr(args, "port", 3000)
    VizHandler.adapter = adapter

    with socketserver.TCPServer(("", port), VizHandler) as httpd:
        url = f"http://localhost:{port}"
        print(f"[viz] serving graph for {repo.name} at {url}")
        print(f"[viz] nodes: {len(adapter.graph.nodes)}, edges: {len(adapter.graph.edges)}")
        print(f"[viz] press Ctrl+C to stop")
        # Open browser in background thread so server stays responsive
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


if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser(description="lgwks graph visualization")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--serve", action="store_true", help="start HTTP server")
    parser.add_argument("--port", type=int, default=3000, help="server port")
    parser.add_argument("--export-html", help="export static HTML file")
    args = parser.parse_args()
    sys.exit(viz_command(args))
