#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lgwks_openrouter
import lgwks_sqlite  # #223 family-4: route this harness's SQLite through the canonical hardened connect

NETWORK_ROOT = ROOT / "vision" / "research" / "research-network"
DEFAULT_SEED = NETWORK_ROOT / "seeds" / "gnn-compiler-expedition.json"
DEFAULT_OUTPUT_ROOT = NETWORK_ROOT / "runs"
DEFAULT_CRWL = "/Users/srinji/.local/bin/crwl"
DEFAULT_REASONING_MODEL = lgwks_openrouter.DEFAULT_MODEL

SOURCE_CATALOG = [
    {
        "url": "https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/",
        "title": "Google Research: Accelerating scientific breakthroughs with an AI co-scientist",
        "axis": "research_governance",
        "tier": "primary",
        "notes": "Co-scientist pattern: generate, debate, rank, evolve, and ground hypotheses.",
        "tags": ["coscientist", "deepmind", "hypothesis", "scientific", "multi-agent"],
    },
    {
        "url": "https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/",
        "title": "Google DeepMind AlphaEvolve",
        "axis": "neural_program_synthesis",
        "tier": "primary",
        "notes": "Evolutionary coding agent pattern for algorithm discovery.",
        "tags": ["deepmind", "evolution", "coding-agent", "algorithms"],
    },
    {
        "url": "https://arxiv.org/abs/2502.18864",
        "title": "Towards an AI co-scientist",
        "axis": "research_governance",
        "tier": "primary",
        "notes": "Technical paper for co-scientist architecture.",
        "tags": ["coscientist", "hypothesis", "research", "multi-agent"],
    },
    {
        "url": "https://arxiv.org/abs/2212.08073",
        "title": "Constitutional AI: Harmlessness from AI Feedback",
        "axis": "research_governance",
        "tier": "primary",
        "notes": "Constitutional critique/revision pattern.",
        "tags": ["constitutional-ai", "anthropic", "critique", "governance"],
    },
    {
        "url": "https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback",
        "title": "Anthropic Constitutional AI",
        "axis": "research_governance",
        "tier": "primary",
        "notes": "Official Constitutional AI explanation.",
        "tags": ["constitutional-ai", "anthropic", "safety", "governance"],
    },
]

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no",
    "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will", "with",
    "you", "your", "yours", "yourself", "yourselves", "using", "used", "use",
    "one", "two", "may", "many", "new", "like", "paper", "page", "section",
    "http", "https", "www", "com", "org", "net", "html", "docs", "latest",
    "search", "query", "searchtype", "storage", "googleapis", "readthedocs",
    "help", "info", "author", "authors", "abstract", "download", "pdf",
    "github", "figure", "table", "appendix", "reference", "references",
}

DOMAIN_PHRASES = [
    "graph neural network",
    "graph neural networks",
    "message passing",
    "node embedding",
    "edge embedding",
    "graph embedding",
    "adjacency matrix",
    "relational inductive bias",
    "graph network",
    "neural program synthesis",
    "program synthesis",
    "compiler intermediate representation",
    "intermediate representation",
    "dialect",
    "schema validation",
    "shape constraint",
    "knowledge graph",
    "semantic similarity",
    "attention mechanism",
    "transformer",
    "graph convolution",
    "graph attention",
    "node classification",
    "link prediction",
    "graph classification",
    "typed graph",
    "control flow",
    "data flow",
    "static single assignment",
    "lowering",
    "optimization pass",
    "provenance",
    "audit trail",
]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(value, fallback="item"):
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:90] or fallback


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


def append_jsonl(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, sort_keys=True) + "\n")


def write_text(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        f.write(value)


def load_sources(seed_file, explicit_urls):
    sources = []
    if seed_file:
        seed = read_json(seed_file)
        sources.extend(seed.get("sources", []))
    for url in explicit_urls:
        sources.append(
            {
                "url": url,
                "title": url,
                "axis": "unknown",
                "tier": "unknown",
                "notes": "Added from CLI.",
            }
        )
    deduped = []
    seen = set()
    for source in sources:
        url = source["url"]
        if url in seen:
            continue
        seen.add(url)
        deduped.append(source)
    return deduped


def split_chunks(text, words_per_chunk=450, overlap=80):
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + words_per_chunk, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def tokenize(text):
    return [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)]


def extract_concepts(chunks, limit=120):
    scores = {}
    joined = "\n".join(chunks).lower()
    for phrase in DOMAIN_PHRASES:
        count = joined.count(phrase)
        if count:
            scores[phrase] = scores.get(phrase, 0.0) + count * (2.0 + len(phrase.split()))

    for chunk in chunks:
        toks = [t for t in tokenize(chunk) if t not in STOPWORDS and len(t) > 2]
        for n in (1, 2, 3):
            for i in range(0, max(0, len(toks) - n + 1)):
                phrase_tokens = toks[i : i + n]
                if any(t in STOPWORDS for t in phrase_tokens):
                    continue
                phrase = " ".join(phrase_tokens)
                if len(phrase) < 4:
                    continue
                scores[phrase] = scores.get(phrase, 0.0) + 1.0 + (0.35 * (n - 1))

    filtered = {}
    for phrase, score in scores.items():
        if phrase.isdigit():
            continue
        parts = phrase.split()
        if any(part in STOPWORDS for part in parts):
            continue
        if any(part.startswith("http") for part in parts):
            continue
        if len(parts) > 1 and len(set(parts)) == 1:
            continue
        if len(phrase) > 80:
            continue
        if score < 2.0 and phrase not in DOMAIN_PHRASES:
            continue
        filtered[phrase] = score
    return sorted(filtered.items(), key=lambda item: (-item[1], item[0]))[:limit]


def deterministic_embedding(text, dims=256):
    vector = [0.0] * dims
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def ollama_embedding(text, model, host="http://127.0.0.1:11434"):
    payloads = [
        ("api/embeddings", {"model": model, "prompt": text}),
        ("api/embed", {"model": model, "input": text}),
    ]
    for endpoint, payload in payloads:
        req = urllib.request.Request(
            f"{host.rstrip('/')}/{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            if "embedding" in data and isinstance(data["embedding"], list):
                return [float(v) for v in data["embedding"]], "ollama"
            if "embeddings" in data and data["embeddings"]:
                return [float(v) for v in data["embeddings"][0]], "ollama"
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            continue
    return deterministic_embedding(text), "deterministic-fallback"


def openrouter_generate(prompt, model):
    if not model or model.lower() in {"none", "off", "deterministic"}:
        return ""
    schema = '{"markdown":"concise advisory markdown"}'
    out = lgwks_openrouter.generate_json(prompt, schema, model=model)
    if not out:
        return ""
    return str(out.get("markdown", "")).strip()


def cosine(a, b):
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    an = math.sqrt(sum(a[i] * a[i] for i in range(size)))
    bn = math.sqrt(sum(b[i] * b[i] for i in range(size)))
    if not an or not bn:
        return 0.0
    return dot / (an * bn)


def resolve_crwl(path):
    if path and Path(path).exists():
        return path
    if Path(DEFAULT_CRWL).exists():
        return DEFAULT_CRWL
    found = shutil.which("crwl")
    if found:
        return found
    raise SystemExit("crwl not found. Install it or pass --crwl /path/to/crwl.")


def run_crwl(source, index, args, run_dir):
    crwl = resolve_crwl(args.crwl)
    slug = f"{index:03d}-{slugify(source['title'] or source['url'])}"
    raw_path = run_dir / "raw" / f"{slug}.md"
    command = [
        crwl,
        "crawl",
        source["url"],
        "--deep-crawl",
        args.deep_crawl,
        "--max-pages",
        str(args.max_pages),
        "-o",
        "markdown",
        "-O",
        str(raw_path),
    ]
    if args.bypass_cache:
        command.append("--bypass-cache")

    start = time.time()
    result = {
        "source": source,
        "command": command,
        "raw_path": str(raw_path),
        "started_at": utc_now(),
    }
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
        )
        result.update(
            {
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
                "duration_seconds": round(time.time() - start, 3),
                "finished_at": utc_now(),
            }
        )
    except subprocess.TimeoutExpired as exc:
        result.update(
            {
                "returncode": 124,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                "duration_seconds": round(time.time() - start, 3),
                "finished_at": utc_now(),
                "error": "timeout",
            }
        )
    append_jsonl(run_dir / "logs" / "commands.jsonl", result)
    return raw_path, result


def normalize_markdown(text):
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def init_db(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = lgwks_sqlite.connect(db_path)
    conn.executescript(
        """
        create table if not exists runs (
          run_id text primary key,
          name text not null,
          created_at text not null,
          manifest_path text not null
        );
        create table if not exists sources (
          id text primary key,
          run_id text not null,
          url text not null,
          title text not null,
          axis text not null,
          tier text not null,
          raw_path text,
          status text not null
        );
        create table if not exists documents (
          id text primary key,
          run_id text not null,
          source_id text not null,
          title text not null,
          path text not null,
          content_sha256 text not null,
          word_count integer not null,
          chunk_count integer not null
        );
        create table if not exists chunks (
          id text primary key,
          run_id text not null,
          document_id text not null,
          source_id text not null,
          position integer not null,
          text text not null,
          content_sha256 text not null,
          word_count integer not null
        );
        create table if not exists embeddings (
          chunk_id text primary key,
          run_id text not null,
          provider text not null,
          model text not null,
          dimensions integer not null,
          vector_json text not null
        );
        create table if not exists nodes (
          id text primary key,
          run_id text not null,
          kind text not null,
          label text not null,
          weight real not null,
          metadata_json text not null
        );
        create table if not exists edges (
          id text primary key,
          run_id text not null,
          from_id text not null,
          to_id text not null,
          kind text not null,
          weight real not null,
          evidence text,
          metadata_json text not null
        );
        """
    )
    return conn


def insert_node(conn, run_id, nodes, node):
    if node["id"] in nodes:
        nodes[node["id"]]["weight"] = max(nodes[node["id"]]["weight"], node.get("weight", 1.0))
        return
    nodes[node["id"]] = node
    conn.execute(
        "insert or replace into nodes values (?, ?, ?, ?, ?, ?)",
        (
            node["id"],
            run_id,
            node["kind"],
            node["label"],
            float(node.get("weight", 1.0)),
            json.dumps(node.get("metadata", {}), sort_keys=True),
        ),
    )


def insert_edge(conn, run_id, edges, edge):
    if edge["id"] in edges:
        return
    edges[edge["id"]] = edge
    conn.execute(
        "insert or replace into edges values (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            edge["id"],
            run_id,
            edge["from"],
            edge["to"],
            edge["kind"],
            float(edge.get("weight", 1.0)),
            edge.get("evidence", ""),
            json.dumps(edge.get("metadata", {}), sort_keys=True),
        ),
    )


def make_edge(from_id, to_id, kind, weight=1.0, evidence="", metadata=None):
    edge_id = "edge-" + sha256_text(f"{from_id}|{to_id}|{kind}|{evidence}")[:16]
    return {
        "id": edge_id,
        "from": from_id,
        "to": to_id,
        "kind": kind,
        "weight": float(weight),
        "evidence": evidence,
        "metadata": metadata or {},
    }


def build_mermaid(nodes, edges, max_nodes=70, max_edges=140):
    ranked_nodes = sorted(nodes.values(), key=lambda n: (-float(n.get("weight", 1.0)), n["label"]))[:max_nodes]
    keep = {n["id"] for n in ranked_nodes}
    ranked_edges = [
        e for e in sorted(edges.values(), key=lambda e: (-float(e.get("weight", 1.0)), e["kind"]))
        if e["from"] in keep and e["to"] in keep
    ][:max_edges]
    aliases = {node_id: f"N{idx}" for idx, node_id in enumerate(keep)}
    lines = ["graph TD"]
    for node in ranked_nodes:
        label = re.sub(r"[^a-zA-Z0-9 .:_/-]", "", node["label"])[:44]
        shape = "([{}])" if node["kind"] in {"source", "concept"} else "[{}]"
        lines.append(f"  {aliases[node['id']]}{shape.format(label)}")
    for edge in ranked_edges:
        label = edge["kind"].replace("_", " ")
        lines.append(f"  {aliases[edge['from']]} -- {label} --> {aliases[edge['to']]}")
    return "\n".join(lines) + "\n"


def build_html(nodes, edges):
    top_nodes = sorted(nodes.values(), key=lambda n: (-float(n.get("weight", 1.0)), n["label"]))[:250]
    keep = {n["id"] for n in top_nodes}
    top_edges = [
        e for e in sorted(edges.values(), key=lambda e: (-float(e.get("weight", 1.0)), e["kind"]))
        if e["from"] in keep and e["to"] in keep
    ][:600]
    payload = json.dumps({"nodes": top_nodes, "edges": top_edges})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>LGWKS Research Map</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #111; color: #f3f3f3; }}
    header {{ padding: 12px 16px; border-bottom: 1px solid #333; display: flex; gap: 18px; align-items: baseline; }}
    main {{ display: grid; grid-template-columns: 1fr 360px; min-height: calc(100vh - 54px); }}
    svg {{ width: 100%; height: calc(100vh - 54px); background: #171717; }}
    aside {{ border-left: 1px solid #333; padding: 12px; overflow: auto; }}
    .node {{ cursor: pointer; }}
    .source {{ fill: #62a0ea; }}
    .concept {{ fill: #8ff0a4; }}
    .chunk {{ fill: #f8e45c; }}
    .document {{ fill: #ffbe6f; }}
    line {{ stroke: #777; stroke-opacity: .38; }}
    text {{ fill: #e8e8e8; font-size: 11px; pointer-events: none; }}
    code {{ color: #8ff0a4; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <header><strong>LGWKS Research Map</strong><span id="counts"></span></header>
  <main>
    <svg id="graph" viewBox="0 0 1200 780"></svg>
    <aside><h2>Selection</h2><div id="details">Click a node.</div></aside>
  </main>
  <script>
    const data = {payload};
    document.getElementById("counts").textContent = `${{data.nodes.length}} nodes / ${{data.edges.length}} edges`;
    const svg = document.getElementById("graph");
    const details = document.getElementById("details");
    const byId = new Map(data.nodes.map(n => [n.id, n]));
    const cols = 10;
    const gapX = 1120 / cols;
    const rows = Math.ceil(data.nodes.length / cols);
    const gapY = Math.max(70, 700 / Math.max(rows, 1));
    data.nodes.forEach((n, i) => {{
      n.x = 45 + (i % cols) * gapX;
      n.y = 45 + Math.floor(i / cols) * gapY;
    }});
    for (const e of data.edges) {{
      const a = byId.get(e.from), b = byId.get(e.to);
      if (!a || !b) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
      line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
      line.setAttribute("stroke-width", Math.max(1, Math.min(4, e.weight * 3)));
      svg.appendChild(line);
    }}
    for (const n of data.nodes) {{
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "node");
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", n.x); c.setAttribute("cy", n.y);
      c.setAttribute("r", Math.max(5, Math.min(18, 5 + n.weight)));
      c.setAttribute("class", n.kind);
      g.appendChild(c);
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", n.x + 9); t.setAttribute("y", n.y + 4);
      t.textContent = n.label.slice(0, 34);
      g.appendChild(t);
      g.addEventListener("click", () => {{
        const localEdges = data.edges.filter(e => e.from === n.id || e.to === n.id).slice(0, 40);
        details.innerHTML = `<h3>${{escapeHtml(n.label)}}</h3><p><code>${{n.kind}}</code> weight ${{n.weight.toFixed(3)}}</p><pre>${{escapeHtml(JSON.stringify(n.metadata || {{}}, null, 2))}}</pre><h3>Edges</h3><pre>${{escapeHtml(JSON.stringify(localEdges, null, 2))}}</pre>`;
      }});
      svg.appendChild(g);
    }}
    function escapeHtml(s) {{
      return String(s).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
  </script>
</body>
</html>
"""


def latest_run_dir(output_root=DEFAULT_OUTPUT_ROOT, required_child=None):
    root = Path(output_root)
    runs = [p for p in root.glob("*") if p.is_dir()]
    if required_child:
        runs = [p for p in runs if (p / required_child).exists()]
    if not runs:
        requirement = f" containing {required_child}" if required_child else ""
        raise SystemExit(f"No runs found under {root}{requirement}")
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def read_db_nodes_edges(run_dir):
    db_path = Path(run_dir) / "db" / "research.sqlite"
    if not db_path.exists():
        raise SystemExit(f"Missing research database: {db_path}")
    # Read-only consumer: wal=False so we gain retry/busy_timeout without
    # rewriting the existing DB's on-disk journal-mode header (#223 fam-4 rule).
    conn = lgwks_sqlite.connect(db_path, wal=False)
    nodes = {}
    edges = {}
    for row in conn.execute("select id, kind, label, weight, metadata_json from nodes"):
        node_id, kind, label, weight, metadata_json = row
        nodes[node_id] = {
            "id": node_id,
            "kind": kind,
            "label": label,
            "weight": float(weight),
            "metadata": json.loads(metadata_json or "{}"),
        }
    for row in conn.execute("select id, from_id, to_id, kind, weight, evidence, metadata_json from edges"):
        edge_id, from_id, to_id, kind, weight, evidence, metadata_json = row
        edges[edge_id] = {
            "id": edge_id,
            "from": from_id,
            "to": to_id,
            "kind": kind,
            "weight": float(weight),
            "evidence": evidence or "",
            "metadata": json.loads(metadata_json or "{}"),
        }
    conn.close()
    return nodes, edges


def graph_export_command(args):
    run_dir = latest_run_dir(args.output_root, "db/research.sqlite") if args.run_dir == "latest" else Path(args.run_dir)
    nodes, edges = read_db_nodes_edges(run_dir)
    write_text(run_dir / "graph" / "research-map.mmd", build_mermaid(nodes, edges, args.max_nodes, args.max_edges))
    write_text(run_dir / "graph" / "research-map.html", build_html(nodes, edges))
    print(json.dumps({"run_dir": str(run_dir), "nodes": len(nodes), "edges": len(edges)}, indent=2))


def graph_tensorize_command(args):
    run_dir = latest_run_dir(args.output_root, "db/research.sqlite") if args.run_dir == "latest" else Path(args.run_dir)
    nodes, edges = read_db_nodes_edges(run_dir)
    out_dir = run_dir / "gnn"
    out_dir.mkdir(parents=True, exist_ok=True)
    node_ids = {node_id: idx for idx, node_id in enumerate(sorted(nodes))}
    kind_ids = {kind: idx for idx, kind in enumerate(sorted({n["kind"] for n in nodes.values()}))}
    edge_kind_ids = {kind: idx for idx, kind in enumerate(sorted({e["kind"] for e in edges.values()}))}

    write_text(out_dir / "nodes.csv", "idx,id,kind,label,weight\n")
    with (out_dir / "nodes.csv").open("a", encoding="utf-8") as f:
        for node_id, idx in node_ids.items():
            node = nodes[node_id]
            label = node["label"].replace('"', '""')
            f.write(f'{idx},"{node_id}","{node["kind"]}","{label}",{node["weight"]}\n')

    write_text(out_dir / "edges.csv", "src,dst,kind,weight\n")
    with (out_dir / "edges.csv").open("a", encoding="utf-8") as f:
        for edge in edges.values():
            if edge["from"] in node_ids and edge["to"] in node_ids:
                f.write(f'{node_ids[edge["from"]]},{node_ids[edge["to"]]},"{edge["kind"]}",{edge["weight"]}\n')

    with (out_dir / "features.jsonl").open("w", encoding="utf-8") as f:
        for node_id, idx in node_ids.items():
            node = nodes[node_id]
            vector = [0.0] * (len(kind_ids) + 3)
            vector[kind_ids[node["kind"]]] = 1.0
            vector[len(kind_ids)] = min(1.0, node["weight"] / 12.0)
            vector[len(kind_ids) + 1] = min(1.0, len(node["label"]) / 120.0)
            vector[len(kind_ids) + 2] = 1.0 if node["kind"] == "concept" else 0.0
            f.write(json.dumps({"idx": idx, "id": node_id, "features": vector}) + "\n")

    summary = {
        "nodes": len(nodes),
        "edges": len(edges),
        "node_kinds": kind_ids,
        "edge_kinds": edge_kind_ids,
        "boundary": "Deterministic tensor export. No AI generation or graph compilation occurred.",
    }
    write_json(out_dir / "tensor-manifest.json", summary)
    write_text(
        out_dir / "README.md",
        "# GNN Tensor Export\n\n"
        "This folder is a deterministic graph-learning export. It is not an AI-generated ontology.\n\n"
        "- `nodes.csv` maps graph node IDs to numeric indexes.\n"
        "- `edges.csv` stores directed typed edges.\n"
        "- `features.jsonl` stores deterministic node features.\n"
        "- `tensor-manifest.json` records kind vocabularies and counts.\n\n"
        "Use this as input to PyTorch Geometric, DGL, NetworkX, or a later local GNN experiment.\n",
    )
    print(json.dumps({"run_dir": str(run_dir), "gnn_dir": str(out_dir), **summary}, indent=2))


def build_framework_sources(framework_text, include_catalog=True):
    tokens = set(tokenize(framework_text))
    sources = []
    if include_catalog:
        for item in SOURCE_CATALOG:
            tags = set(item.get("tags", []))
            title_tokens = set(tokenize(item.get("title", "")))
            notes_tokens = set(tokenize(item.get("notes", "")))
            if tokens & (tags | title_tokens | notes_tokens):
                source = {k: v for k, v in item.items() if k != "tags"}
                sources.append(source)
    if not sources:
        sources = [{k: v for k, v in item.items() if k != "tags"} for item in SOURCE_CATALOG]
    search_query = "+".join(sorted(tokens)[:12]) or "graph+neural+network+compiler"
    sources.append(
        {
            "url": f"https://arxiv.org/search/cs?query={search_query}&searchtype=all&abstracts=show&order=-announced_date_first&size=50",
            "title": f"arXiv search: {search_query.replace('+', ' ')}",
            "axis": "unknown",
            "tier": "primary",
            "notes": "Generated arXiv search source from framework vocabulary.",
        }
    )
    return sources


def bot_plan_command(args):
    framework = args.framework or ""
    if args.framework_file:
        framework = Path(args.framework_file).read_text(encoding="utf-8")
    if not framework.strip():
        raise SystemExit("Pass a framework string or --framework-file.")
    run_id = f"{slugify(args.name or 'research-bot-plan')}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    plan_dir = Path(args.output_root) / run_id / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    seed = {
        "name": args.name or run_id,
        "description": "Generated by LGWKS research bot plan. AI may advise; deterministic compiler owns DB/graph output.",
        "sources": build_framework_sources(framework),
    }
    constitution = {
        "objective": "Learn how the internet, machines, neural networks, graph structure, and compiler-visible knowledge systems work.",
        "boundaries": [
            "AI can propose hypotheses, sources, and critiques.",
            "AI cannot compile or mutate research graph facts.",
            "Embeddings can create vectors; deterministic code creates edges.",
            "Human promotion is required before research claims become compiler primitives.",
            "Offensive security tooling patterns may inform audit and orchestration, but this bot does not execute offensive tools.",
        ],
        "coscientist_pattern": ["generate", "reflect", "rank", "evolve", "ground", "human-review"],
        "constitutional_pattern": ["state principle", "critique output", "revise output", "log decision"],
        "tabula_rasa_pattern": ["start from minimal assumptions", "separate observations from interpretations", "prefer explicit evidence"],
    }
    write_text(plan_dir / "framework.txt", framework.strip() + "\n")
    write_json(plan_dir / "seed.json", seed)
    write_json(plan_dir / "constitution.json", constitution)
    write_text(
        plan_dir / "README.md",
        "# Research Bot Plan\n\n"
        "Run the generated crawl:\n\n"
        f"```bash\n./lgwks website --seed-file {plan_dir / 'seed.json'} --name {args.name or run_id}\n```\n\n"
        "Then rebuild deterministic visualization/tensors:\n\n"
        f"```bash\n./lgwks graph export {plan_dir.parent}\n./lgwks graph tensorize {plan_dir.parent}\n```\n",
    )
    print(json.dumps({"plan_dir": str(plan_dir), "seed_file": str(plan_dir / "seed.json"), "sources": len(seed["sources"])}, indent=2))


def expert_command(args):
    run_dir = latest_run_dir(args.output_root, "run-manifest.json") if args.run_dir == "latest" else Path(args.run_dir)
    report_path = run_dir / "REPORT.md"
    manifest_path = run_dir / "run-manifest.json"
    if not report_path.exists() or not manifest_path.exists():
        raise SystemExit(f"Run is missing REPORT.md or run-manifest.json: {run_dir}")
    report = report_path.read_text(encoding="utf-8", errors="ignore")[:12000]
    manifest = read_json(manifest_path)
    question = args.question or "What are the highest-leverage next research gaps?"
    prompt = f"""You are the LGWKS research expert advisory layer.

Hard boundary:
- You may generate hypotheses, source targets, critiques, and research tasks.
- You may not claim to compile the graph or mutate database facts.
- Separate observations from interpretations.
- Use a co-scientist loop: generate, critique, rank, evolve, ground.
- Use Constitutional AI style: state the rule, critique against it, revise.
- Use tabula-rasa discipline: minimize assumptions and say what evidence would change the conclusion.

Run manifest:
{json.dumps(manifest, indent=2)[:6000]}

Current report:
{report}

Question:
{question}

Return concise markdown with:
1. observations
2. hypotheses
3. research gaps
4. next crawl targets
5. graph/tensor implications
6. governance checks
"""
    if args.dry_run:
        write_text(run_dir / "advisory" / "prompt.md", prompt)
        print(json.dumps({"prompt": str(run_dir / "advisory" / "prompt.md"), "dry_run": True}, indent=2))
        return
    text = openrouter_generate(prompt, args.model)
    if not text:
        print(json.dumps({"advisory": None, "model": args.model, "reason": "no llm output"}, indent=2))
        return
    out_path = run_dir / "advisory" / f"expert-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    write_text(out_path, text + "\n")
    append_jsonl(
        run_dir / "logs" / "advisory.jsonl",
        {"created_at": utc_now(), "model": args.model, "question": question, "output_path": str(out_path)},
    )
    print(json.dumps({"advisory": str(out_path), "model": args.model}, indent=2))


def create_report(run_id, run_dir, sources, command_results, concepts, nodes, edges):
    failures = [r for r in command_results if r.get("returncode") != 0]
    similar = [e for e in edges.values() if e["kind"] == "similar_to"]
    similar = sorted(similar, key=lambda e: -e["weight"])[:25]
    concept_rows = sorted(concepts.items(), key=lambda item: (-item[1], item[0]))[:50]
    lines = [
        f"# Research Expedition Report: {run_id}",
        "",
        f"- Created: {utc_now()}",
        f"- Sources requested: {len(sources)}",
        f"- Crawl failures/timeouts: {len(failures)}",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        "",
        "## Top Concepts",
        "",
    ]
    for concept, score in concept_rows:
        lines.append(f"- `{concept}` - {score:.2f}")
    lines.extend(["", "## Strongest Semantic Links", ""])
    for edge in similar:
        lines.append(f"- `{edge['from']}` -> `{edge['to']}` score `{edge['weight']:.3f}`")
    if failures:
        lines.extend(["", "## Crawl Failures", ""])
        for result in failures:
            title = result["source"].get("title") or result["source"].get("url")
            lines.append(f"- `{title}` returned `{result.get('returncode')}`. See `logs/commands.jsonl`.")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "This report is a semantic map, not a claim verifier. Similarity edges identify candidate relationships. Promotion into compiler primitives still requires human or validator acceptance.",
            "",
        ]
    )
    write_text(run_dir / "REPORT.md", "\n".join(lines))


def website_command(args):
    seed_file = args.seed_file
    if args.no_seed:
        seed_file = None
    elif not seed_file and not args.urls:
        seed_file = DEFAULT_SEED
    sources = load_sources(seed_file, args.urls)
    if not sources:
        raise SystemExit("No sources provided. Pass URLs or --seed-file.")

    run_id = f"{slugify(args.name or 'research')}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_root) / run_id
    for subdir in ("raw", "records", "db", "graph", "logs"):
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    db_path = run_dir / "db" / "research.sqlite"
    conn = init_db(db_path)
    conn.execute(
        "insert or replace into runs values (?, ?, ?, ?)",
        (run_id, args.name or run_id, utc_now(), str(run_dir / "run-manifest.json")),
    )

    nodes = {}
    edges = {}
    all_chunks = []
    source_docs = []
    command_results = []
    global_concepts = {}

    for idx, source in enumerate(sources, start=1):
        source_id = "source-" + sha256_text(source["url"])[:16]
        insert_node(
            conn,
            run_id,
            nodes,
            {
                "id": source_id,
                "kind": "source",
                "label": source.get("title") or source["url"],
                "weight": 5.0,
                "source": source["url"],
                "metadata": source,
            },
        )
        if args.skip_crawl:
            raw_path = Path(source.get("raw_path", ""))
            result = {"source": source, "raw_path": str(raw_path), "returncode": 0, "skipped": True}
        else:
            raw_path, result = run_crwl(source, idx, args, run_dir)
        command_results.append(result)
        status = "ok" if result.get("returncode") == 0 and raw_path.exists() else "failed"
        conn.execute(
            "insert or replace into sources values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                run_id,
                source["url"],
                source.get("title") or source["url"],
                source.get("axis", "unknown"),
                source.get("tier", "unknown"),
                str(raw_path),
                status,
            ),
        )
        if status != "ok":
            continue

        text = normalize_markdown(raw_path.read_text(encoding="utf-8", errors="ignore"))
        if not text:
            continue
        doc_id = "doc-" + sha256_text(source["url"] + "|" + sha256_text(text))[:16]
        chunks = split_chunks(text, args.words_per_chunk, args.chunk_overlap)
        if args.max_chunks_per_source > 0:
            chunks = chunks[: args.max_chunks_per_source]
        document = {
            "id": doc_id,
            "source_id": source_id,
            "path": str(raw_path),
            "title": source.get("title") or source["url"],
            "content_sha256": sha256_text(text),
            "retrieved_at": utc_now(),
            "word_count": len(re.findall(r"\S+", text)),
            "chunk_count": len(chunks),
        }
        source_docs.append(document)
        append_jsonl(run_dir / "records" / "documents.jsonl", document)
        conn.execute(
            "insert or replace into documents values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                run_id,
                source_id,
                document["title"],
                document["path"],
                document["content_sha256"],
                document["word_count"],
                document["chunk_count"],
            ),
        )
        insert_node(
            conn,
            run_id,
            nodes,
            {
                "id": doc_id,
                "kind": "document",
                "label": document["title"],
                "weight": 3.0 + min(3.0, len(chunks) / 4.0),
                "source": source["url"],
                "metadata": document,
            },
        )
        insert_edge(conn, run_id, edges, make_edge(source_id, doc_id, "contains", 1.0, "source produced document"))

        concepts = extract_concepts(chunks, limit=args.concepts_per_source)
        for phrase, score in concepts:
            global_concepts[phrase] = global_concepts.get(phrase, 0.0) + score

        for pos, chunk in enumerate(chunks):
            chunk_id = "chunk-" + sha256_text(f"{doc_id}|{pos}|{sha256_text(chunk)}")[:16]
            chunk_record = {
                "id": chunk_id,
                "run_id": run_id,
                "document_id": doc_id,
                "source_id": source_id,
                "position": pos,
                "text": chunk,
                "content_sha256": sha256_text(chunk),
                "word_count": len(re.findall(r"\S+", chunk)),
            }
            append_jsonl(run_dir / "records" / "chunks.jsonl", chunk_record)
            conn.execute(
                "insert or replace into chunks values (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    run_id,
                    doc_id,
                    source_id,
                    pos,
                    chunk,
                    chunk_record["content_sha256"],
                    chunk_record["word_count"],
                ),
            )
            insert_node(
                conn,
                run_id,
                nodes,
                {
                    "id": chunk_id,
                    "kind": "chunk",
                    "label": f"{document['title']} #{pos + 1}",
                    "weight": 1.0,
                    "source": source["url"],
                    "metadata": {"document_id": doc_id, "position": pos, "preview": chunk[:240]},
                },
            )
            insert_edge(conn, run_id, edges, make_edge(doc_id, chunk_id, "contains", 1.0, "document chunk"))
            all_chunks.append(chunk_record)

    selected_chunks = all_chunks[: args.max_total_chunks] if args.max_total_chunks > 0 else all_chunks
    concept_nodes = {}
    for phrase, score in sorted(global_concepts.items(), key=lambda item: (-item[1], item[0]))[: args.max_concepts]:
        concept_id = "concept-" + sha256_text(phrase)[:16]
        concept_nodes[phrase] = concept_id
        insert_node(
            conn,
            run_id,
            nodes,
            {
                "id": concept_id,
                "kind": "concept",
                "label": phrase,
                "weight": max(1.0, min(12.0, score / 3.0)),
                "metadata": {"score": score},
            },
        )

    for chunk in selected_chunks:
        lowered = chunk["text"].lower()
        for phrase, concept_id in concept_nodes.items():
            if phrase in lowered:
                insert_edge(
                    conn,
                    run_id,
                    edges,
                    make_edge(chunk["id"], concept_id, "mentions", 1.0, phrase, {"phrase": phrase}),
                )

    embeddings = []
    for idx, chunk in enumerate(selected_chunks, start=1):
        vector, provider = ollama_embedding(chunk["text"][: args.embedding_chars], args.embed_model)
        embeddings.append((chunk, vector))
        conn.execute(
            "insert or replace into embeddings values (?, ?, ?, ?, ?, ?)",
            (
                chunk["id"],
                run_id,
                provider,
                args.embed_model,
                len(vector),
                json.dumps(vector),
            ),
        )
        if idx % 20 == 0:
            conn.commit()

    for i, (chunk_a, vector_a) in enumerate(embeddings):
        scored = []
        for j, (chunk_b, vector_b) in enumerate(embeddings):
            if i >= j:
                continue
            if chunk_a["source_id"] == chunk_b["source_id"] and abs(chunk_a["position"] - chunk_b["position"]) <= 1:
                continue
            score = cosine(vector_a, vector_b)
            if score >= args.similarity_threshold:
                scored.append((score, chunk_b))
        for score, chunk_b in sorted(scored, key=lambda item: -item[0])[: args.similarity_top_k]:
            insert_edge(
                conn,
                run_id,
                edges,
                make_edge(
                    chunk_a["id"],
                    chunk_b["id"],
                    "similar_to",
                    score,
                    f"cosine {score:.3f}",
                    {"model": args.embed_model},
                ),
            )

    for node in nodes.values():
        append_jsonl(run_dir / "records" / "nodes.jsonl", node)
    for edge in edges.values():
        append_jsonl(run_dir / "records" / "edges.jsonl", edge)

    mermaid = build_mermaid(nodes, edges)
    write_text(run_dir / "graph" / "research-map.mmd", mermaid)
    write_text(run_dir / "graph" / "research-map.html", build_html(nodes, edges))
    create_report(run_id, run_dir, sources, command_results, global_concepts, nodes, edges)

    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "name": args.name or run_id,
        "sources": sources,
        "models": {"embedding": args.embed_model, "reasoning": args.reasoning_model},
        "limits": {
            "max_pages": args.max_pages,
            "deep_crawl": args.deep_crawl,
            "max_total_chunks": args.max_total_chunks,
            "max_chunks_per_source": args.max_chunks_per_source,
            "similarity_threshold": args.similarity_threshold,
        },
        "artifacts": {
            "root": str(run_dir),
            "database": str(db_path),
            "report": str(run_dir / "REPORT.md"),
            "mermaid": str(run_dir / "graph" / "research-map.mmd"),
            "html": str(run_dir / "graph" / "research-map.html"),
            "commands": str(run_dir / "logs" / "commands.jsonl"),
        },
        "counts": {
            "sources": len(sources),
            "documents": len(source_docs),
            "chunks": len(all_chunks),
            "embedded_chunks": len(embeddings),
            "nodes": len(nodes),
            "edges": len(edges),
        },
    }
    write_json(run_dir / "run-manifest.json", manifest)
    conn.commit()
    conn.close()
    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "counts": manifest["counts"]}, indent=2))


def drive_status(args):
    root = Path(args.output_root)
    runs = sorted(root.glob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    print(f"research_root={root}")
    print(f"runs={len(runs)}")
    for run in runs[: args.limit]:
        manifest = run / "run-manifest.json"
        if manifest.exists():
            data = read_json(manifest)
            counts = data.get("counts", {})
            print(f"- {run.name}: sources={counts.get('sources')} chunks={counts.get('chunks')} nodes={counts.get('nodes')} edges={counts.get('edges')}")
        else:
            print(f"- {run.name}: manifest missing")
    print("\ngit:")
    subprocess.run(["git", "status", "--short", "--branch"], cwd=str(ROOT), check=False)


def build_parser():
    parser = argparse.ArgumentParser(prog="lgwks", description="LGWKS local research network command.")
    sub = parser.add_subparsers(dest="command", required=True)

    website = sub.add_parser("website", help="Crawl websites and build a local research graph.")
    website.add_argument("urls", nargs="*", help="URLs to crawl.")
    website.add_argument("--seed-file", default=None, help="JSON seed file with sources.")
    website.add_argument("--no-seed", action="store_true", help="Use only explicit URLs.")
    website.add_argument("--name", default="research-expedition", help="Run name.")
    website.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Run storage root.")
    website.add_argument("--crwl", default=DEFAULT_CRWL, help="Path to crwl executable.")
    website.add_argument("--deep-crawl", default="bfs", choices=["bfs", "dfs", "best-first"])
    website.add_argument("--max-pages", type=int, default=12)
    website.add_argument("--timeout-seconds", type=int, default=900)
    website.add_argument("--bypass-cache", action="store_true")
    website.add_argument("--skip-crawl", action="store_true")
    website.add_argument("--embed-model", default="qwen3-embedding:8b")
    website.add_argument("--reasoning-model", default=DEFAULT_REASONING_MODEL,
                         help="OpenRouter reasoning model id, or 'none' to record no reasoning model")
    website.add_argument("--words-per-chunk", type=int, default=450)
    website.add_argument("--chunk-overlap", type=int, default=80)
    website.add_argument("--concepts-per-source", type=int, default=80)
    website.add_argument("--max-concepts", type=int, default=140)
    website.add_argument("--max-chunks-per-source", type=int, default=24)
    website.add_argument("--max-total-chunks", type=int, default=220)
    website.add_argument("--embedding-chars", type=int, default=6000)
    website.add_argument("--similarity-threshold", type=float, default=0.72)
    website.add_argument("--similarity-top-k", type=int, default=5)
    website.set_defaults(func=website_command)

    drive = sub.add_parser("drive", help="Inspect local research object storage.")
    drive_sub = drive.add_subparsers(dest="drive_command", required=True)
    status = drive_sub.add_parser("status", help="Show research runs and git state.")
    status.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    status.add_argument("--limit", type=int, default=10)
    status.set_defaults(func=drive_status)

    graph = sub.add_parser("graph", help="Deterministic graph operations. No AI generation.")
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)
    export = graph_sub.add_parser("export", help="Rebuild Mermaid and HTML graph artifacts from SQLite.")
    export.add_argument("run_dir", nargs="?", default="latest")
    export.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    export.add_argument("--max-nodes", type=int, default=70)
    export.add_argument("--max-edges", type=int, default=140)
    export.set_defaults(func=graph_export_command)
    tensorize = graph_sub.add_parser("tensorize", help="Export deterministic GNN-ready tensors from SQLite.")
    tensorize.add_argument("run_dir", nargs="?", default="latest")
    tensorize.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    tensorize.set_defaults(func=graph_tensorize_command)

    bot = sub.add_parser("bot", help="Research bot planning. Produces seeds and policies, not compiled graph facts.")
    bot_sub = bot.add_subparsers(dest="bot_command", required=True)
    plan = bot_sub.add_parser("plan", help="Turn an architectural framework into a source seed pack.")
    plan.add_argument("framework", nargs="?", default="")
    plan.add_argument("--framework-file")
    plan.add_argument("--name", default="research-bot-plan")
    plan.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    plan.set_defaults(func=bot_plan_command)

    expert = sub.add_parser("expert", help="AI advisory over a completed run. Does not mutate DB/graph.")
    expert.add_argument("run_dir", nargs="?", default="latest")
    expert.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    expert.add_argument("--model", default=DEFAULT_REASONING_MODEL,
                        help="OpenRouter model id for advisory generation, or 'none'/'off' to skip LLM output")
    expert.add_argument("--question", default="")
    expert.add_argument("--dry-run", action="store_true")
    expert.set_defaults(func=expert_command)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
