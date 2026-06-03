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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
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

    def query_nodes(self, node_type: str | None = None) -> list[dict]:
        if node_type:
            rows = self._conn.execute(
                "SELECT node_id, type, label, attrs FROM nodes WHERE type = ?", (node_type,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT node_id, type, label, attrs FROM nodes"
            ).fetchall()
        return [
            {"node_id": r[0], "type": r[1], "label": r[2], "attrs": json.loads(r[3])}
            for r in rows
        ]

    def query_edges(self, rel: str | None = None) -> list[dict]:
        if rel:
            rows = self._conn.execute(
                "SELECT edge_id, src, dst, rel, attrs FROM edges WHERE rel = ?", (rel,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT edge_id, src, dst, rel, attrs FROM edges"
            ).fetchall()
        return [
            {"edge_id": r[0], "src": r[1], "dst": r[2], "rel": r[3], "attrs": json.loads(r[4])}
            for r in rows
        ]

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
    p.add_argument("--sync", action="store_true", help="git add + commit + push after ingest")
    p.add_argument("--sync-repo", metavar="PATH", default=".", help="repo root for git sync")
    p.set_defaults(func=_entity_graph_command)


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
