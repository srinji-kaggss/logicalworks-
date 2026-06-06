"""lgwks_entity_graph — offline document entity graph builder.

Three extraction tiers (always graceful-degrade):
  T1: regex enumeration lookup (always runs, zero deps)
  T2: CoreML text classifier (optional; needs lgwks_coreml + a trained .mlpackage)
  T3: Foundation Models structured extraction (optional; macOS 26+, M4+, on-device)

Output: SQLite DB (nodes + edges + chunks) + JSON export for git sync.
No cloud, no remote inference, no HuggingFace, no Ollama. All local.

//why: Fundserv research lives on a managed laptop (EPM, no elevation).
A three-tier local stack gives extraction even without a trained model (T1),
gets better classification when one is available (T2), and can interpret
genuinely ambiguous structure locally once Foundation Models ships (T3).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_sqlite

# ── entity taxonomy ───────────────────────────────────────────────────────────

ENTITY_TYPES = (
    "ACCOUNT",       # registered/non-registered account (RRSP, RRIF, TFSA …)
    "PLAN_TYPE",     # the plan registration type label
    "TRANSACTION",   # a single transaction instance
    "TX_TYPE",       # transaction type (Purchase, Redemption, Switch, Transfer …)
    "FUND",          # a specific fund (code + series)
    "FUNDSERV_CODE", # network message code (NFS, NFR, NSW, TR01, TR02 …)
    "PARTICIPANT",   # actor: client, advisor, dealer, sponsor
    "FORM",          # regulatory form (T2033, T4RSP …)
    "SETTLEMENT",    # settlement record
    "AMOUNT",        # dollar/unit quantity extracted from text
    "DATE",          # date mention
    "UNKNOWN",       # classifier fallback
)

# ── T1 regex patterns ─────────────────────────────────────────────────────────

_PLAN_TYPES = re.compile(
    r"\b(RRSP|Spousal RRSP|sRRSP|RRIF|TFSA|LIRA|LRSP|LIF|RLIF|PRIF|RESP|PRPP|SPP|RPP|NONREG|Non-Reg(?:istered)?)\b",
    re.IGNORECASE,
)
_FUNDSERV_CODES = re.compile(
    r"\b(NFS|NFR|NSW|TR0[12]|ATON|PAC|SWP|SWI|SWO)\b",
)
_FORMS = re.compile(
    r"\b(T2033|T2030|T4RSP|T4RIF|T2151|T2220|T1036)\b",
)
_ACCOUNT_STRUCTURES = re.compile(
    r"\b(Client[\s-]?Name|Nominee|Omnibus)\b",
    re.IGNORECASE,
)
_AMOUNTS = re.compile(
    r"\$\s*[\d,]+(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d+)?\s*(?:units?|%)\b",
    re.IGNORECASE,
)
_DATES = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s*\d{4})\b",
    re.IGNORECASE,
)

@dataclass
class EntityMention:
    entity_type: str
    text: str
    start: int
    end: int


def extract_mentions(text: str) -> list[EntityMention]:
    """T1: enumerate all entity mentions in text via regex."""
    mentions: list[EntityMention] = []

    for m in _PLAN_TYPES.finditer(text):
        mentions.append(EntityMention("PLAN_TYPE", m.group(), m.start(), m.end()))

    for m in _FUNDSERV_CODES.finditer(text):
        mentions.append(EntityMention("FUNDSERV_CODE", m.group(), m.start(), m.end()))

    for m in _FORMS.finditer(text):
        mentions.append(EntityMention("FORM", m.group(), m.start(), m.end()))

    for m in _ACCOUNT_STRUCTURES.finditer(text):
        mentions.append(EntityMention("PARTICIPANT", m.group(), m.start(), m.end()))

    for m in _AMOUNTS.finditer(text):
        mentions.append(EntityMention("AMOUNT", m.group(), m.start(), m.end()))

    for m in _DATES.finditer(text):
        mentions.append(EntityMention("DATE", m.group(), m.start(), m.end()))

    # Sort by position so callers can read them in-order
    mentions.sort(key=lambda e: e.start)
    return mentions


# ── SQLite graph DB ───────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id  TEXT PRIMARY KEY,
    type     TEXT NOT NULL,
    label    TEXT NOT NULL,
    attrs    TEXT NOT NULL DEFAULT '{}'  -- JSON
);
CREATE TABLE IF NOT EXISTS edges (
    edge_id  TEXT PRIMARY KEY,
    src      TEXT NOT NULL REFERENCES nodes(node_id),
    dst      TEXT NOT NULL REFERENCES nodes(node_id),
    rel      TEXT NOT NULL,
    attrs    TEXT NOT NULL DEFAULT '{}'  -- JSON
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    url       TEXT,
    text      TEXT NOT NULL,
    hash      TEXT NOT NULL,
    schema    TEXT NOT NULL DEFAULT 'UNKNOWN',
    labels    TEXT NOT NULL DEFAULT '[]'  -- JSON array of entity types found
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_schema ON chunks(schema);
"""


@dataclass
class GraphDB:
    """SQLite-backed entity graph. All writes are idempotent (INSERT OR REPLACE)."""
    db_path: Path
    _conn: sqlite3.Connection = field(default=None, repr=False, init=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def upsert_node(self, node_id: str, node_type: str, label: str, attrs: dict | None = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO nodes (node_id, type, label, attrs) VALUES (?, ?, ?, ?)",
            (node_id, node_type, label, json.dumps(attrs or {})),
        )

    def upsert_edge(self, src: str, dst: str, rel: str, attrs: dict | None = None) -> None:
        edge_id = hashlib.sha256(f"{src}|{dst}|{rel}".encode()).hexdigest()[:16]
        # Ensure referenced nodes exist as UNKNOWN stubs if not yet inserted
        for nid in (src, dst):
            self._conn.execute(
                "INSERT OR IGNORE INTO nodes (node_id, type, label) VALUES (?, 'UNKNOWN', ?)",
                (nid, nid),
            )
        self._conn.execute(
            "INSERT OR REPLACE INTO edges (edge_id, src, dst, rel, attrs) VALUES (?, ?, ?, ?, ?)",
            (edge_id, src, dst, rel, json.dumps(attrs or {})),
        )

    def upsert_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        url: str = "",
        schema: str = "UNKNOWN",
        labels: list[str] | None = None,
    ) -> None:
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        self._conn.execute(
            "INSERT OR REPLACE INTO chunks (chunk_id, doc_id, url, text, hash, schema, labels) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, doc_id, url, text, h, schema, json.dumps(labels or [])),
        )

    def commit(self) -> None:
        self._conn.commit()

    def seed_directional_edges(self, matrix_path: Path | None = None) -> int:
        """Load eligibility matrix and create directed edges between plan-type nodes.
        Returns number of edges seeded."""
        if matrix_path is None:
            matrix_path = Path(__file__).parent.parent / "config" / "eligibility_matrix.json"
        if not matrix_path.exists():
            return 0
        try:
            data = json.loads(matrix_path.read_text())
        except Exception:
            return 0
        count = 0
        for rule in data.get("rules", []):
            src = f"PLAN_TYPE:{rule['from'].lower()}"
            dst = f"PLAN_TYPE:{rule['to'].lower()}"
            self.upsert_node(src, "PLAN_TYPE", rule["from"])
            self.upsert_node(dst, "PLAN_TYPE", rule["to"])
            rel = "allows_transfer" if rule.get("legal") else "blocks_transfer"
            self.upsert_edge(src, dst, rel, {"note": rule.get("note", "")})
            count += 1
        self.commit()
        return count

    def query_nodes(self, node_type: str | None = None, match: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT node_id, type, label, attrs FROM nodes"
        clauses: list[str] = []
        params: list[Any] = []
        if node_type:
            clauses.append("type = ?")
            params.append(node_type)
        if match:
            clauses.append("(lower(node_id) LIKE ? OR lower(label) LIKE ?)")
            needle = f"%{match.lower()}%"
            params.extend([needle, needle])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY type, label LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [
            {"node_id": r[0], "type": r[1], "label": r[2], "attrs": json.loads(r[3])}
            for r in rows
        ]

    def query_edges(self, rel: str | None = None, match: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT edge_id, src, dst, rel, attrs FROM edges"
        clauses: list[str] = []
        params: list[Any] = []
        if rel:
            clauses.append("rel = ?")
            params.append(rel)
        if match:
            clauses.append("(lower(src) LIKE ? OR lower(dst) LIKE ? OR lower(rel) LIKE ?)")
            needle = f"%{match.lower()}%"
            params.extend([needle, needle, needle])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY rel, src, dst LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [
            {"edge_id": r[0], "src": r[1], "dst": r[2], "rel": r[3], "attrs": json.loads(r[4])}
            for r in rows
        ]

    def resolve_nodes(self, query: str, limit: int = 20) -> list[dict]:
        exact = self._conn.execute(
            "SELECT node_id, type, label, attrs FROM nodes WHERE node_id = ? OR lower(label) = ? ORDER BY label LIMIT ?",
            (query, query.lower(), limit),
        ).fetchall()
        rows = exact if exact else self._conn.execute(
            "SELECT node_id, type, label, attrs FROM nodes WHERE lower(node_id) LIKE ? OR lower(label) LIKE ? ORDER BY label LIMIT ?",
            (f"%{query.lower()}%", f"%{query.lower()}%", limit),
        ).fetchall()
        return [
            {"node_id": r[0], "type": r[1], "label": r[2], "attrs": json.loads(r[3])}
            for r in rows
        ]

    def neighbors(self, node_id: str, direction: str = "both", rel: str | None = None, limit: int = 100) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if direction == "out":
            clauses.append("src = ?")
            params.append(node_id)
        elif direction == "in":
            clauses.append("dst = ?")
            params.append(node_id)
        else:
            clauses.append("(src = ? OR dst = ?)")
            params.extend([node_id, node_id])
        if rel:
            clauses.append("rel = ?")
            params.append(rel)
        sql = (
            "SELECT edge_id, src, dst, rel, attrs FROM edges WHERE "
            + " AND ".join(clauses)
            + " ORDER BY rel, src, dst LIMIT ?"
        )
        params.append(limit)
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        out: list[dict] = []
        for r in rows:
            src, dst = r[1], r[2]
            out.append({
                "edge_id": r[0],
                "src": src,
                "dst": dst,
                "rel": r[3],
                "attrs": json.loads(r[4]),
                "neighbor": dst if src == node_id else src,
                "direction": "out" if src == node_id else "in",
            })
        return out

    def shortest_path(self, src: str, dst: str, max_depth: int = 6) -> list[dict]:
        if src == dst:
            return []
        queue: deque[tuple[str, list[dict]]] = deque([(src, [])])
        seen = {src}
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for edge in self.neighbors(current, direction="out", limit=500):
                nxt = edge["neighbor"]
                step = {"src": current, "dst": nxt, "rel": edge["rel"], "edge_id": edge["edge_id"]}
                next_path = path + [step]
                if nxt == dst:
                    return next_path
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, next_path))
        return []

    def stats(self) -> dict[str, Any]:
        n = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        e = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        c = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        u = self._conn.execute("SELECT COUNT(*) FROM chunks WHERE schema='UNKNOWN'").fetchone()[0]
        return {"nodes": n, "edges": e, "chunks": c, "unknown_chunks": u}

    def export_json(self, out_path: Path) -> None:
        """Dump full graph to JSON for git-sync."""
        data = {
            "nodes": self.query_nodes(),
            "edges": self.query_edges(),
            "stats": self.stats(),
        }
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(out_path)

    def export_mermaid(self, out_path: Path, max_edges: int = 80) -> None:
        """Export a Mermaid flowchart of the top-N edges (human-readable)."""
        edges = self.query_edges()[:max_edges]
        lines = ["flowchart LR"]
        seen_nodes: set[str] = set()
        for e in edges:
            s, d = e["src"].replace('"', ""), e["dst"].replace('"', "")
            lines.append(f'    {s} -- "{e["rel"]}" --> {d}')
            seen_nodes.update([s, d])
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── ingestion ─────────────────────────────────────────────────────────────────

def ingest_chunk(
    db: GraphDB,
    chunk: dict[str, Any],
    classifier_fn: Any | None = None,
) -> None:
    """Ingest one parsed chunk into the graph.

    chunk keys expected: chunk_id, document_id, url, text, hash, [schema]
    classifier_fn: callable(text: str) -> {"schema": str, "confidence": float} or None
    //why: schema from parser is structural (DOM fingerprint); classifier gives semantic label
    """
    text = chunk.get("text", "")
    chunk_id = chunk["chunk_id"]
    doc_id = chunk.get("document_id", "")
    url = chunk.get("url", "")

    # T2: run classifier if available
    schema = chunk.get("schema", "UNKNOWN")
    if classifier_fn and schema == "UNKNOWN":
        try:
            result = classifier_fn(text)
            if result.get("confidence", 0.0) >= 0.60:
                schema = result["schema"]
        except Exception:
            pass  # T2 failure is silent; T1 still runs

    mentions = extract_mentions(text)
    labels = list({m.entity_type for m in mentions})

    # T3: Foundation Models fallback for genuinely ambiguous mentions
    if not mentions or all(m.entity_type == "UNKNOWN" for m in mentions):
        try:
            import lgwks_foundation
            fm_result = lgwks_foundation.extract_entities(text, entity_types=list(ENTITY_TYPES))
            if fm_result.status == "ok" and fm_result.entities:
                for e in fm_result.entities:
                    mentions.append(ExtractedMention(e.text, e.type, e.start, e.end))
                labels = list({m.entity_type for m in mentions})
        except Exception:
            pass  # T3 unavailable is silent

    db.upsert_chunk(chunk_id, doc_id, text, url=url, schema=schema, labels=labels)

    # Build nodes + edges from mentions
    for mention in mentions:
        nid = f"{mention.entity_type}:{mention.text.lower()}"
        db.upsert_node(nid, mention.entity_type, mention.text)
        # Edge: chunk → entity
        db.upsert_edge(chunk_id, nid, "mentions")

    # Co-occurrence edges between entity mentions in same chunk
    for i, a in enumerate(mentions):
        for b in mentions[i + 1:]:
            if a.entity_type == b.entity_type:
                continue  # skip same-type co-occurrence (too noisy)
            src = f"{a.entity_type}:{a.text.lower()}"
            dst = f"{b.entity_type}:{b.text.lower()}"
            db.upsert_edge(src, dst, "co-occurs")


def ingest_chunks(
    db: GraphDB,
    chunks: list[dict[str, Any]],
    classifier_fn: Any | None = None,
) -> None:
    """Ingest a batch of chunks. Commits after all inserts."""
    for chunk in chunks:
        ingest_chunk(db, chunk, classifier_fn=classifier_fn)
    db.commit()


# ── git sync ──────────────────────────────────────────────────────────────────

def git_sync(repo_path: Path, message: str = "entity-graph: auto-sync") -> bool:
    """Stage all changes in repo_path, commit, and push.

    //why: SQLite is binary and can't be diffed; JSON export is the git artifact.
    Push is the 'DB layer' that persists to GitHub without any hosted service.
    Returns True on success.
    """
    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args), cwd=str(repo_path),
            capture_output=True, text=True, timeout=60,
        )

    status = _run("git", "status", "--porcelain")
    if not status.stdout.strip():
        print("[git-sync] nothing to commit", file=sys.stderr)
        return True

    _run("git", "add", "-A")
    commit = _run("git", "commit", "-m", message)
    if commit.returncode != 0:
        print(f"[git-sync] commit failed: {commit.stderr.strip()}", file=sys.stderr)
        return False

    push = _run("git", "push")
    if push.returncode != 0:
        print(f"[git-sync] push failed: {push.stderr.strip()}", file=sys.stderr)
        return False

    print(f"[git-sync] pushed: {message}", file=sys.stderr)
    return True


# ── CLI entry point ───────────────────────────────────────────────────────────

def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "entity-graph",
        help="build/query local entity graph from parsed document chunks",
    )
    p.add_argument("--chunks", metavar="FILE", help="JSONL file of parsed chunks to ingest")
    p.add_argument("--db", metavar="PATH", default=".lgwks/entity_graph.db",
                   help="SQLite database path (default: .lgwks/entity_graph.db)")
    p.add_argument("--export", metavar="PATH", help="export graph to JSON file")
    p.add_argument("--mermaid", metavar="PATH", help="export Mermaid diagram")
    p.add_argument("--stats", action="store_true", help="print graph statistics and exit")
    p.add_argument("--nodes", action="store_true", help="list nodes")
    p.add_argument("--edges", action="store_true", help="list edges")
    p.add_argument("--node-type", metavar="TYPE", help="filter nodes by type")
    p.add_argument("--rel", metavar="REL", help="filter edges or neighbors by relation")
    p.add_argument("--match", metavar="TEXT", help="case-insensitive node/edge label match")
    p.add_argument("--neighbors", metavar="NODE", help="show neighbors for a node id or label")
    p.add_argument("--direction", choices=["out", "in", "both"], default="both",
                   help="neighbor direction (default: both)")
    p.add_argument("--path", nargs=2, metavar=("SRC", "DST"),
                   help="shortest directed path between two node ids or labels")
    p.add_argument("--max-depth", type=int, default=6, help="path search depth limit")
    p.add_argument("--limit", type=int, default=200, help="row limit for query output")
    p.add_argument("--json", action="store_true", help="emit structured query output")
    p.add_argument("--sync", action="store_true", help="git add + commit + push after ingest")
    p.add_argument("--sync-repo", metavar="PATH", default=".", help="repo root for git sync")
    p.set_defaults(func=_entity_graph_command)


def _resolve_single_node(db: GraphDB, query: str) -> tuple[dict[str, Any] | None, str | None]:
    matches = db.resolve_nodes(query)
    if not matches:
        return None, f"no node matches {query!r}"
    if len(matches) > 1:
        preview = ", ".join(m["node_id"] for m in matches[:5])
        return None, f"ambiguous node {query!r}; candidates: {preview}"
    return matches[0], None


def _emit_query(args: Any, payload: dict[str, Any]) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return
    print(json.dumps(payload, indent=2))


def _entity_graph_command(args: Any) -> None:
    db_path = Path(args.db)
    db = GraphDB(db_path)

    if args.stats:
        print(json.dumps(db.stats(), indent=2))
        db.close()
        return

    if args.chunks:
        chunks_file = Path(args.chunks)
        if not chunks_file.exists():
            print(f"[entity-graph] chunks file not found: {chunks_file}", file=sys.stderr)
            sys.exit(1)

        # Optional T2 classifier
        classifier_fn = None
        try:
            from lgwks_coreml import classify_page  # type: ignore[import]
            classifier_fn = classify_page
        except ImportError:
            pass

        chunks: list[dict] = []
        for line in chunks_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        ingest_chunks(db, chunks, classifier_fn=classifier_fn)
        print(f"[entity-graph] ingested {len(chunks)} chunks → {db_path}", file=sys.stderr)
        print(json.dumps(db.stats(), indent=2))

    if args.nodes:
        _emit_query(args, {
            "schema": "lgwks.entity-graph.nodes.v0",
            "db": str(db_path),
            "nodes": db.query_nodes(node_type=args.node_type, match=args.match, limit=args.limit),
        })

    if args.edges:
        _emit_query(args, {
            "schema": "lgwks.entity-graph.edges.v0",
            "db": str(db_path),
            "edges": db.query_edges(rel=args.rel, match=args.match, limit=args.limit),
        })

    if args.neighbors:
        node, err = _resolve_single_node(db, args.neighbors)
        if err:
            print(f"[entity-graph] {err}", file=sys.stderr)
            db.close()
            sys.exit(1)
        _emit_query(args, {
            "schema": "lgwks.entity-graph.neighbors.v0",
            "db": str(db_path),
            "node": node,
            "neighbors": db.neighbors(node["node_id"], direction=args.direction, rel=args.rel, limit=args.limit),
        })

    if args.path:
        src, err = _resolve_single_node(db, args.path[0])
        if err:
            print(f"[entity-graph] {err}", file=sys.stderr)
            db.close()
            sys.exit(1)
        dst, err = _resolve_single_node(db, args.path[1])
        if err:
            print(f"[entity-graph] {err}", file=sys.stderr)
            db.close()
            sys.exit(1)
        _emit_query(args, {
            "schema": "lgwks.entity-graph.path.v0",
            "db": str(db_path),
            "src": src,
            "dst": dst,
            "path": db.shortest_path(src["node_id"], dst["node_id"], max_depth=args.max_depth),
        })

    if args.export:
        out = Path(args.export)
        db.export_json(out)
        print(f"[entity-graph] exported JSON → {out}", file=sys.stderr)

    if args.mermaid:
        out = Path(args.mermaid)
        db.export_mermaid(out)
        print(f"[entity-graph] exported Mermaid → {out}", file=sys.stderr)

    if args.sync:
        git_sync(Path(args.sync_repo))

    db.close()
