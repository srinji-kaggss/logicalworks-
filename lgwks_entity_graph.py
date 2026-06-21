"""lgwks_entity_graph — offline document entity graph builder.

Extraction and schema classification both route through the unified model port
(`lgwks_model_port`), which owns the escalation ladder — this module no longer
re-implements its own resolve-degrade logic:
  • entity mentions  → port.extract_entities  (deterministic regex → Foundation)
  • chunk schema      → port.classify          (sensor CoreML → defer)

Output: SQLite DB (nodes + edges + chunks) + JSON export for git sync.
No cloud, no remote inference, no HuggingFace, no Ollama. All local.

//why: research runs on a managed laptop (EPM, no elevation). The port's ladder
gives extraction even without a trained model (regex always runs), gets a semantic
schema label when a local classifier is present, and interprets the genuinely
ambiguous long tail via on-device Foundation Models — degrading silently, never
fabricating, exactly once, in one place.
"""

from __future__ import annotations

import lgwks_hashing
import json
import re
import sqlite3
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_crdt as crdt
import lgwks_sqlite

# ── entity taxonomy ───────────────────────────────────────────────────────────

ENTITY_TYPES = (
    "EMAIL",         # email address
    "URL",           # web address
    "IP_ADDRESS",    # IPv4/v6 address
    "UUID",          # standard UUIDs
    "MONEY",         # dollar/unit quantity
    "DATE",          # date mention
    "IMAGE",         # visual evidence (PNG, JPG, etc.)
    "VIDEO",         # video evidence (MP4, etc.)
    "UNKNOWN",       # classifier fallback
)

# ── T1 regex patterns ─────────────────────────────────────────────────────────

_EMAILS = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
_URLS = re.compile(
    r"\b(?:https?|ftp)://[^\s/$.?#].[^\s]*\b"
)
_IPS = re.compile(
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
)
_UUIDS = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE
)
_MONEY = re.compile(
    r"\$\s*[\d,]+(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d+)?\s*(?:USD|EUR|GBP)\b",
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

    for m in _EMAILS.finditer(text):
        mentions.append(EntityMention("EMAIL", m.group(), m.start(), m.end()))

    for m in _URLS.finditer(text):
        mentions.append(EntityMention("URL", m.group(), m.start(), m.end()))

    for m in _IPS.finditer(text):
        mentions.append(EntityMention("IP_ADDRESS", m.group(), m.start(), m.end()))

    for m in _UUIDS.finditer(text):
        mentions.append(EntityMention("UUID", m.group(), m.start(), m.end()))

    for m in _MONEY.finditer(text):
        mentions.append(EntityMention("MONEY", m.group(), m.start(), m.end()))

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
    attrs    TEXT NOT NULL DEFAULT '{}',  -- JSON
    artifact_cid TEXT,                    -- #165 step 2: contributing artifact (tape provenance)
    tier     TEXT                         -- #165 step 2: world ⊕ tenant ownership
);
CREATE TABLE IF NOT EXISTS edges (
    edge_id  TEXT PRIMARY KEY,
    src      TEXT NOT NULL REFERENCES nodes(node_id),
    dst      TEXT NOT NULL REFERENCES nodes(node_id),
    rel      TEXT NOT NULL,
    attrs    TEXT NOT NULL DEFAULT '{}',  -- JSON
    artifact_cid TEXT,                    -- #165 step 2: contributing artifact (tape provenance)
    tier     TEXT                         -- #165 step 2: world ⊕ tenant ownership
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    url       TEXT,
    text      TEXT NOT NULL,
    hash      TEXT NOT NULL,
    schema    TEXT NOT NULL DEFAULT 'UNKNOWN',
    labels    TEXT NOT NULL DEFAULT '[]',  -- JSON array of entity types found
    artifact_cid TEXT,                     -- #165 step 2: contributing artifact (tape provenance)
    tier     TEXT                          -- #165 step 2: world ⊕ tenant ownership
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_schema ON chunks(schema);
"""

# Indices over the #165-step-2 cid/tier columns. Created AFTER the column migration
# so they also apply to legacy graph.db files whose tables predate those columns.
_CID_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_nodes_tier ON nodes(tier);
CREATE INDEX IF NOT EXISTS idx_edges_tier ON edges(tier);
CREATE INDEX IF NOT EXISTS idx_nodes_artifact ON nodes(artifact_cid);
CREATE INDEX IF NOT EXISTS idx_edges_artifact ON edges(artifact_cid);
"""

# #165 step 2: cid/tier columns are added to pre-existing graph.db files in place
# (existing rows keep NULL — backward compatible). New-DB DDL above already has them;
# this only matters for graphs created before step 2. node-level artifact_cid is the
# MOST-RECENT contributing artifact (last-writer-wins under INSERT OR REPLACE); the
# authoritative many-to-many provenance lives on `mentions` edges. Refining node
# provenance to a dedicated table is deferred to #165 step 3.
_MIGRATION_COLUMNS = (
    ("nodes", "artifact_cid"),
    ("nodes", "tier"),
    ("edges", "artifact_cid"),
    ("edges", "tier"),
    ("chunks", "artifact_cid"),
    ("chunks", "tier"),
)


@dataclass
class GraphDB:
    """SQLite-backed entity graph. All writes are idempotent (INSERT OR REPLACE)."""
    db_path: Path
    _conn: sqlite3.Connection = field(default=None, repr=False, init=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = lgwks_sqlite.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_DDL)
        self._migrate_cid_columns()
        self._conn.executescript(_CID_INDEX_DDL)
        self._conn.commit()
        self._crdt_path = self.db_path.with_suffix(self.db_path.suffix + ".crdt.json")

    def _migrate_cid_columns(self) -> None:
        """Add #165-step-2 cid/tier columns to graph.db files created before step 2.

        Idempotent: ALTER TABLE ADD COLUMN only when the column is absent (existing
        rows keep NULL). New DBs already carry the columns from _DDL, so this is a
        no-op for them.
        """
        for table, column in _MIGRATION_COLUMNS:
            cols = {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")

    def _require_nonempty(self, value: str, field: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field} must not be empty")
        return value

    def _edge_id(self, src: str, dst: str, rel: str) -> str:
        return lgwks_hashing.content_id(f"{src}|{dst}|{rel}")

    def _membership_sink(self) -> crdt.JsonFileSink:
        return crdt.JsonFileSink(self._crdt_path)

    def _membership_state(self) -> dict[str, crdt.ORSet] | None:
        if not self._crdt_path.exists():
            return None
        state = self._membership_sink().load()
        nodes = state.get("nodes")
        edges = state.get("edges")
        if nodes is not None and not isinstance(nodes, crdt.ORSet):
            raise ValueError("entity-graph membership state is corrupt: nodes must be ORSet")
        if edges is not None and not isinstance(edges, crdt.ORSet):
            raise ValueError("entity-graph membership state is corrupt: edges must be ORSet")
        return {
            "nodes": nodes if isinstance(nodes, crdt.ORSet) else crdt.ORSet(),
            "edges": edges if isinstance(edges, crdt.ORSet) else crdt.ORSet(),
        }

    def _visible_members(self, key: str) -> set[str] | None:
        state = self._membership_state()
        if state is None:
            return None
        return set(state[key].value())

    def _track_node_membership(self, node_id: str) -> None:
        crdt.reconverge(self._membership_sink(), {"nodes": crdt.ORSet().add(node_id)})

    def _track_edge_membership(self, edge_id: str) -> None:
        crdt.reconverge(self._membership_sink(), {"edges": crdt.ORSet().add(edge_id)})

    def _remove_member(self, key: str, elem: str) -> None:
        state_map = self._membership_state()
        if state_map is None:
            return
        state = state_map[key]
        observed = state._adds.get(elem, frozenset())
        delta = crdt.ORSet().remove(elem, observed)
        crdt.reconverge(self._membership_sink(), {key: delta})

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def upsert_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        attrs: dict | None = None,
        *,
        artifact_cid: str | None = None,
        tier: str | None = None,
    ) -> None:
        node_id = self._require_nonempty(node_id, "node_id")
        node_type = self._require_nonempty(node_type, "node_type")
        label = self._require_nonempty(label, "label")
        self._track_node_membership(node_id)
        self._conn.execute(
            "INSERT OR REPLACE INTO nodes (node_id, type, label, attrs, artifact_cid, tier) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (node_id, node_type, label, json.dumps(attrs or {}), artifact_cid, tier),
        )

    def upsert_edge(
        self,
        src: str,
        dst: str,
        rel: str,
        attrs: dict | None = None,
        *,
        artifact_cid: str | None = None,
        tier: str | None = None,
    ) -> None:
        src = self._require_nonempty(src, "src")
        dst = self._require_nonempty(dst, "dst")
        rel = self._require_nonempty(rel, "rel")
        edge_id = self._edge_id(src, dst, rel)
        self._track_node_membership(src)
        self._track_node_membership(dst)
        self._track_edge_membership(edge_id)
        # Ensure referenced nodes exist as UNKNOWN stubs if not yet inserted. Stub
        # rows carry the same tier/provenance as the edge so they are not orphaned
        # outside the world ⊕ tenant view.
        for nid in (src, dst):
            self._conn.execute(
                "INSERT OR IGNORE INTO nodes (node_id, type, label, artifact_cid, tier) "
                "VALUES (?, 'UNKNOWN', ?, ?, ?)",
                (nid, nid, artifact_cid, tier),
            )
        self._conn.execute(
            "INSERT OR REPLACE INTO edges (edge_id, src, dst, rel, attrs, artifact_cid, tier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (edge_id, src, dst, rel, json.dumps(attrs or {}), artifact_cid, tier),
        )

    def remove_edge(self, src: str, dst: str, rel: str) -> None:
        src = self._require_nonempty(src, "src")
        dst = self._require_nonempty(dst, "dst")
        rel = self._require_nonempty(rel, "rel")
        edge_id = self._edge_id(src, dst, rel)
        self._remove_member("edges", edge_id)
        self._conn.execute("DELETE FROM edges WHERE edge_id = ?", (edge_id,))

    def remove_node(self, node_id: str) -> None:
        node_id = self._require_nonempty(node_id, "node_id")
        edge_rows = self._conn.execute(
            "SELECT src, dst, rel FROM edges WHERE src = ? OR dst = ?",
            (node_id, node_id),
        ).fetchall()
        for src, dst, rel in edge_rows:
            self.remove_edge(src, dst, rel)
        self._remove_member("nodes", node_id)
        self._conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))

    def upsert_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        url: str = "",
        schema: str = "UNKNOWN",
        labels: list[str] | None = None,
        *,
        artifact_cid: str | None = None,
        tier: str | None = None,
    ) -> None:
        h = lgwks_hashing.content_id(text)
        self._conn.execute(
            "INSERT OR REPLACE INTO chunks (chunk_id, doc_id, url, text, hash, schema, labels, "
            "artifact_cid, tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, doc_id, url, text, h, schema, json.dumps(labels or []), artifact_cid, tier),
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
        visible_nodes = self._visible_members("nodes")
        sql = "SELECT node_id, type, label, attrs FROM nodes"
        clauses: list[str] = []
        params: list[Any] = []
        if visible_nodes is not None:
            placeholders = ",".join("?" for _ in visible_nodes)
            if not placeholders:
                return []
            clauses.append(f"node_id IN ({placeholders})")
            params.extend(sorted(visible_nodes))
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
        visible_edges = self._visible_members("edges")
        sql = "SELECT edge_id, src, dst, rel, attrs FROM edges"
        clauses: list[str] = []
        params: list[Any] = []
        if visible_edges is not None:
            placeholders = ",".join("?" for _ in visible_edges)
            if not placeholders:
                return []
            clauses.append(f"edge_id IN ({placeholders})")
            params.extend(sorted(visible_edges))
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
    *,
    artifact_cid: str | None = None,
    tier: str | None = None,
) -> int:
    """Ingest one parsed chunk into the graph. Returns the number of mentions found.

    chunk keys expected: chunk_id, document_id, url, text, hash, [schema|chunk_kind]
    classifier_fn: legacy callable(text) -> {"schema","confidence"}; when None the
        unified model port supplies schema classification (the canonical path).
    artifact_cid/tier: #165 step 2 — tape provenance + world ⊕ tenant ownership
        stamped on every node/edge/chunk this call writes. Falls back to the same
        keys carried on the chunk dict (substrate chunks already carry artifact_cid).

    Extraction escalates through the model port's ladder (regex → Foundation), so
    the engine, not this caller, owns the resolve-degrade policy. //why: schema from
    a parser is structural (DOM fingerprint); the classifier gives a semantic label.
    """
    import lgwks_model_port as port

    text = chunk.get("text", "")
    chunk_id = chunk["chunk_id"]
    doc_id = chunk.get("document_id", "")
    url = chunk.get("url", "")

    # #196: substrate chunks carry `chunk_kind`, not `schema`. Accept either so the
    # graph builds from ordinary substrate output, not just FundServ-shaped input.
    schema = chunk.get("schema") or chunk.get("chunk_kind") or "UNKNOWN"
    if schema == "UNKNOWN":
        if classifier_fn is not None:  # legacy injected classifier
            try:
                result = classifier_fn(text)
                if result.get("confidence", 0.0) >= 0.60:
                    schema = result["schema"]
            except Exception:
                pass  # classification failure is non-fatal; extraction still runs
        else:  # canonical path: schema classification through the unified port
            verdict = port.classify(text)
            if verdict["ok"] and verdict["value"]:
                schema = verdict["value"]["schema"]

    # Entity extraction via the port ladder: T1 regex → T3 Foundation (fix for the
    # prior `ExtractedMention` crash — the port returns typed {type,text,start,end}
    # dicts, never an undefined symbol). T2 page-schema classification is a separate
    # role (handled above), not an entity-extraction tier.
    extraction = port.extract_entities(text, entity_types=list(ENTITY_TYPES))
    mentions = [
        EntityMention(m["type"], m["text"], m["start"], m["end"])
        for m in (extraction["value"] or [])
    ]
    labels = list({m.entity_type for m in mentions})

    # Provenance: explicit arg wins; else the chunk's own artifact_cid/tier (#165).
    acid = artifact_cid or chunk.get("artifact_cid")
    row_tier = tier or chunk.get("tier")

    db.upsert_chunk(chunk_id, doc_id, text, url=url, schema=schema, labels=labels,
                    artifact_cid=acid, tier=row_tier)

    # Build nodes + edges from mentions
    for mention in mentions:
        nid = f"{mention.entity_type}:{mention.text.lower()}"
        db.upsert_node(nid, mention.entity_type, mention.text, artifact_cid=acid, tier=row_tier)
        # Edge: chunk → entity
        db.upsert_edge(chunk_id, nid, "mentions", artifact_cid=acid, tier=row_tier)

    # Co-occurrence edges between entity mentions in same chunk
    for i, a in enumerate(mentions):
        for b in mentions[i + 1:]:
            if a.entity_type == b.entity_type:
                continue  # skip same-type co-occurrence (too noisy)
            src = f"{a.entity_type}:{a.text.lower()}"
            dst = f"{b.entity_type}:{b.text.lower()}"
            db.upsert_edge(src, dst, "co-occurs", artifact_cid=acid, tier=row_tier)

    return len(mentions)


def ingest_chunks(
    db: GraphDB,
    chunks: list[dict[str, Any]],
    classifier_fn: Any | None = None,
    *,
    artifact_cid: str | None = None,
    tier: str | None = None,
) -> dict[str, int]:
    """Ingest a batch of chunks. Commits after all inserts.

    Returns {"chunks","mentions","empty_chunks"}. #196: when chunks yield zero
    mentions we surface a loud warning with a hint instead of silently building an
    empty graph — the failure mode that made `entity-graph` look broken on
    ordinary (non-FundServ) substrate output.

    artifact_cid/tier (#165 step 2): tape provenance + world ⊕ tenant ownership
    applied to every row written; per-chunk artifact_cid/tier keys override.
    """
    total_mentions = 0
    empty = 0
    for chunk in chunks:
        found = ingest_chunk(db, chunk, classifier_fn=classifier_fn,
                             artifact_cid=artifact_cid, tier=tier)
        total_mentions += found
        empty += 1 if found == 0 else 0
    db.commit()

    if chunks and total_mentions == 0:
        print(
            f"[entity-graph] WARNING: ingested {len(chunks)} chunk(s) but extracted "
            f"0 entities. Recognised types: {', '.join(ENTITY_TYPES)}. If your text "
            f"has none of these, no nodes are expected; otherwise verify the chunk "
            f"`text` field is populated (substrate chunks use `chunk_kind`, accepted).",
            file=sys.stderr,
        )
    return {"chunks": len(chunks), "mentions": total_mentions, "empty_chunks": empty}


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

        # Schema classification flows through the unified model port (classifier_fn
        # left None → ingest_chunk calls port.classify). The port owns CoreML
        # availability + the confidence gate, so this command no longer probes it.
        classifier_fn = None

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
