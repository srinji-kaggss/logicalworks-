"""lgwks_translate_rag — Translation RAG pipeline built on the lgwks ingestion spine.

Zero-loss, permanent, RAG-friendly. Reuses:
  - lgwks_vector (I1): content-addressed binary float32 storage, CID dedup
  - lgwks_embed_port (I4): Qwen3-VL-Embedding-8B, 4096-d semantic space
  - lgwks_sqlite: hardened SQLite (WAL, PRAGMAs, retry)

Dedup strategy:
  CID = blake2b(source_text + target_text + target_lang)
  - Same source+target+lang → same CID (idempotent ingest, zero duplication)
  - Different target text → different CID (multiple translations coexist)
  - Domain/provenance are metadata, not CID (same pair in different contexts = one CID)
  - Quality score is metadata (a post_edit can upgrade quality without changing CID)

Observability (not bolted on — structural):
  - Every retrieval logs: query_hash, top_k, similarities, filter results, latency_ms
  - Every ingest logs: cid, source_lang, target_lang, domain, provenance, embedding_ms
  - Drift detection: QE distribution shift, retrieval quality degradation
  - Provenance chain: corpus → model → post_edit → preference_pair → fine-tune

Authority: spec/second-harness/INGESTION-LAYER.md, spec/second-harness/INGESTION-PLAN.md
Schema: lgwks.translate.rag.v1
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_vecmath as _vm

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lgwks_vector import (
    SCHEMA as VECTOR_SCHEMA,
    ADMIN as VECTOR_ADMIN,
    VectorRecord,
    create_store,
    upsert_record,
)
from lgwks_embed_port import EmbedPort
from lgwks_sqlite import connect as sqlite_connect

SCHEMA = "lgwks.translate.rag.v1"
SPACE_ID = "translate-rag-v1"

logger = logging.getLogger("lgwks.translate.rag")

# ─────────────────────────────────────────────────────────────────────────────
# Observability — structural, not bolted on
# ─────────────────────────────────────────────────────────────────────────────

OBSERVABILITY_DDL = """
CREATE TABLE IF NOT EXISTS rag_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    detail      TEXT NOT NULL,
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS re_type ON rag_events(event_type);
CREATE INDEX IF NOT EXISTS re_ts ON rag_events(ts);
"""


def _log_event(conn, event_type: str, detail: dict) -> None:
    """Append-only observability log. Every structural decision is recorded."""
    conn.execute(
        "INSERT INTO rag_events (event_type, detail, ts) VALUES (?,?,?)",
        (event_type, json.dumps(detail, sort_keys=True, default=str),
         time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Translation pair record
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TranslationPair:
    """A source→target translation pair with full provenance."""
    cid: str                    # blake2b(source_text + target_text + target_lang)
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    domain: str
    component_type: str
    glossary_terms: dict[str, str]
    source_embedding: bytes     # float32 binary
    provenance: str             # "human", "model", "post_edit", "corpus"
    quality_score: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            object.__setattr__(self, 'timestamp', time.strftime("%Y-%m-%dT%H:%M:%S"))


def make_cid(source_text: str, target_text: str, target_lang: str) -> str:
    """CID = blake2b(source + target + lang). Deterministic, collision-resistant."""
    return hashlib.blake2b(
        (source_text + target_text + target_lang).encode("utf-8"),
        digest_size=16,
    ).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Translation RAG store
# ─────────────────────────────────────────────────────────────────────────────

TRANSLATION_PAIRS_DDL = """
CREATE TABLE IF NOT EXISTS translation_pairs (
    cid             TEXT PRIMARY KEY,
    source_text     TEXT NOT NULL,
    target_text     TEXT NOT NULL,
    source_lang     TEXT NOT NULL,
    target_lang     TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT '',
    component_type  TEXT NOT NULL DEFAULT '',
    glossary_terms  TEXT NOT NULL DEFAULT '{}',
    provenance      TEXT NOT NULL DEFAULT 'corpus',
    quality_score   REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tp_lang_pair ON translation_pairs(source_lang, target_lang);
CREATE INDEX IF NOT EXISTS tp_domain ON translation_pairs(domain);
CREATE INDEX IF NOT EXISTS tp_quality ON translation_pairs(quality_score DESC);
CREATE INDEX IF NOT EXISTS tp_source ON translation_pairs(source_text);
"""


class TranslationRAGStore:
    """Permanent, zero-loss translation memory backed by lgwks_vector."""

    def __init__(self, store_path: Path, embed_port: EmbedPort | None = None):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite_connect(store_path, check_same_thread=False)
        self._conn.row_factory = None
        self._conn.executescript(TRANSLATION_PAIRS_DDL + OBSERVABILITY_DDL)
        self._conn.commit()

        self._embed_port = embed_port
        self._owns_port = embed_port is None

        self._vector_store_path = store_path.parent / f"{store_path.stem}_vectors.db"
        self._vector_store = create_store(self._vector_store_path)

        # Embedding cache — avoid re-embedding identical text
        self._embed_cache: dict[str, list[float]] = {}

    def _get_port(self) -> EmbedPort:
        if self._embed_port is None:
            self._embed_port = EmbedPort()
        return self._embed_port

    def _embed(self, text: str) -> list[float] | None:
        """Embed with caching and explicit error logging (never silent)."""
        cache_key = hashlib.blake2b(text.encode(), digest_size=8).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        t0 = time.perf_counter()
        try:
            port = self._get_port()
            vec = port.embed_text(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._embed_cache[cache_key] = vec
            _log_event(self._conn, "embed", {
                "text_hash": cache_key, "dim": len(vec) if vec else 0,
                "latency_ms": round(elapsed_ms, 1), "status": "ok",
            })
            return vec
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            _log_event(self._conn, "embed", {
                "text_hash": cache_key, "latency_ms": round(elapsed_ms, 1),
                "status": "error", "error": str(e),
            })
            logger.error("embed failed: %s", e)
            return None

    def ingest_pair(self, pair: TranslationPair) -> str:
        """Store a translation pair. Idempotent by CID.

        INSERT OR REPLACE means: if the same CID exists, the new pair
        overwrites the old one. This is correct for quality upgrades
        (post_edit overwrites model output for same source+target+lang).
        """
        # Compute actual norm from embedding bytes
        dim = len(pair.source_embedding) // 4
        floats = struct.unpack(f">{dim}f", pair.source_embedding)
        actual_norm = sum(f * f for f in floats) ** 0.5

        vec_record = VectorRecord(
            cid=pair.cid,
            modality="text",
            embedding=pair.source_embedding,
            norm=actual_norm,
            dim=dim,
            space_id=SPACE_ID,
            tenant="",
            source_cid=pair.cid,
        )
        upsert_record(self._vector_store, vec_record, admin=VECTOR_ADMIN)

        self._conn.execute(
            """INSERT OR REPLACE INTO translation_pairs
               (cid, source_text, target_text, source_lang, target_lang,
                domain, component_type, glossary_terms, provenance,
                quality_score, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pair.cid, pair.source_text, pair.target_text,
             pair.source_lang, pair.target_lang, pair.domain,
             pair.component_type, json.dumps(pair.glossary_terms),
             pair.provenance, pair.quality_score, pair.timestamp),
        )
        self._conn.commit()

        _log_event(self._conn, "ingest", {
            "cid": pair.cid, "source_lang": pair.source_lang,
            "target_lang": pair.target_lang, "domain": pair.domain,
            "provenance": pair.provenance, "quality": pair.quality_score,
            "source_len": len(pair.source_text), "target_len": len(pair.target_text),
        })
        return pair.cid

    def ingest_batch(self, pairs: list[TranslationPair]) -> int:
        """Batch ingest with single commit (not per-pair)."""
        count = 0
        t0 = time.perf_counter()
        for pair in pairs:
            # Compute norm
            dim = len(pair.source_embedding) // 4
            floats = struct.unpack(f">{dim}f", pair.source_embedding)
            actual_norm = sum(f * f for f in floats) ** 0.5

            vec_record = VectorRecord(
                cid=pair.cid, modality="text",
                embedding=pair.source_embedding, norm=actual_norm, dim=dim,
                space_id=SPACE_ID, tenant="", source_cid=pair.cid,
            )
            upsert_record(self._vector_store, vec_record, admin=VECTOR_ADMIN)

            self._conn.execute(
                """INSERT OR REPLACE INTO translation_pairs
                   (cid, source_text, target_text, source_lang, target_lang,
                    domain, component_type, glossary_terms, provenance,
                    quality_score, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pair.cid, pair.source_text, pair.target_text,
                 pair.source_lang, pair.target_lang, pair.domain,
                 pair.component_type, json.dumps(pair.glossary_terms),
                 pair.provenance, pair.quality_score, pair.timestamp),
            )
            count += 1

        self._conn.commit()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log_event(self._conn, "ingest_batch", {
            "count": count, "latency_ms": round(elapsed_ms, 1),
            "pairs_per_sec": round(count / max(elapsed_ms / 1000, 0.001), 1),
        })
        return count

    def retrieve(self, source_text: str, target_lang: str,
                 top_k: int = 5, domain_filter: str | None = None,
                 min_quality: float = 0.0) -> list[dict]:
        """Retrieve nearest translation pairs. Full observability on every call."""
        t0 = time.perf_counter()
        query_hash = hashlib.blake2b(source_text.encode(), digest_size=8).hexdigest()

        query_embedding = self._embed(source_text)
        if query_embedding is None:
            _log_event(self._conn, "retrieve", {
                "query_hash": query_hash, "target_lang": target_lang,
                "status": "embed_failed", "latency_ms": 0,
            })
            return []

        results = self._vector_search(query_embedding, top_k * 3)

        # Filter by target_lang, quality, domain
        filtered = []
        lang_filtered = 0
        quality_filtered = 0
        for cid, similarity in results:
            pair = self._get_pair(cid)
            if pair is None:
                continue
            if pair["target_lang"] != target_lang:
                lang_filtered += 1
                continue
            if pair["quality_score"] < min_quality:
                quality_filtered += 1
                continue
            if domain_filter and pair["domain"] != domain_filter:
                continue
            filtered.append({
                "cid": cid,
                "source": pair["source_text"],
                "target": pair["target_text"],
                "similarity": round(similarity, 4),
                "domain": pair["domain"],
                "component_type": pair["component_type"],
                "glossary_terms": json.loads(pair["glossary_terms"]),
                "provenance": pair["provenance"],
                "quality_score": pair["quality_score"],
            })
            if len(filtered) >= top_k:
                break

        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log_event(self._conn, "retrieve", {
            "query_hash": query_hash, "target_lang": target_lang,
            "domain_filter": domain_filter, "min_quality": min_quality,
            "candidates_scanned": len(results), "lang_filtered": lang_filtered,
            "quality_filtered": quality_filtered, "returned": len(filtered),
            "top_similarity": filtered[0]["similarity"] if filtered else 0,
            "latency_ms": round(elapsed_ms, 1), "status": "ok",
        })

        return filtered

    def _vector_search(self, query_embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        """Cosine similarity search. Brute-force for < 1M pairs."""
        cursor = self._vector_store.execute(
            "SELECT cid, embedding FROM vector_records WHERE space_id = ?", (SPACE_ID,)
        )

        results = []
        for row in cursor:
            cid = row[0]
            stored_bytes = row[1]
            stored = struct.unpack(f">{len(stored_bytes)//4}f", stored_bytes)
            sim = _cosine_similarity(query_embedding, list(stored))
            results.append((cid, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _get_pair(self, cid: str) -> dict | None:
        row = self._conn.execute(
            "SELECT cid, source_text, target_text, source_lang, target_lang, "
            "domain, component_type, glossary_terms, provenance, quality_score "
            "FROM translation_pairs WHERE cid = ?", (cid,)
        ).fetchone()
        if row is None:
            return None
        return {
            "cid": row[0], "source_text": row[1], "target_text": row[2],
            "source_lang": row[3], "target_lang": row[4], "domain": row[5],
            "component_type": row[6], "glossary_terms": row[7],
            "provenance": row[8], "quality_score": row[9],
        }

    def detect_drift(self, window: int = 1000) -> dict:
        """Detect quality drift in recent ingestions."""
        rows = self._conn.execute(
            "SELECT quality_score, provenance FROM translation_pairs "
            "ORDER BY created_at DESC LIMIT ?", (window,)
        ).fetchall()
        if len(rows) < 10:
            return {"status": "insufficient_data", "count": len(rows)}

        scores = [r[0] for r in rows]
        mid = len(scores) // 2
        first_half = sum(scores[:mid]) / mid
        second_half = sum(scores[mid:]) / (len(scores) - mid)
        drift = second_half - first_half

        return {
            "status": "drift_detected" if abs(drift) > 0.05 else "ok",
            "avg_quality": round(sum(scores) / len(scores), 4),
            "quality_trend": round(drift, 4),
            "window": window,
            "count": len(rows),
        }

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM translation_pairs").fetchone()[0]
        by_lang = {}
        for row in self._conn.execute(
            "SELECT source_lang, target_lang, COUNT(*) FROM translation_pairs "
            "GROUP BY source_lang, target_lang"
        ):
            by_lang[f"{row[0]}→{row[1]}"] = row[2]
        by_domain = {}
        for row in self._conn.execute(
            "SELECT domain, COUNT(*) FROM translation_pairs GROUP BY domain"
        ):
            by_domain[row[0]] = row[1]
        by_provenance = {}
        for row in self._conn.execute(
            "SELECT provenance, COUNT(*) FROM translation_pairs GROUP BY provenance"
        ):
            by_provenance[row[0]] = row[1]
        avg_quality = self._conn.execute(
            "SELECT AVG(quality_score) FROM translation_pairs"
        ).fetchone()[0] or 0.0

        # Observability: recent event counts
        event_counts = {}
        for row in self._conn.execute(
            "SELECT event_type, COUNT(*) FROM rag_events GROUP BY event_type"
        ):
            event_counts[row[0]] = row[1]

        return {
            "total_pairs": total,
            "by_language_pair": by_lang,
            "by_domain": by_domain,
            "by_provenance": by_provenance,
            "avg_quality": round(avg_quality, 4),
            "vector_store_size": self._vector_store_path.stat().st_size if self._vector_store_path.exists() else 0,
            "event_counts": event_counts,
            "embed_cache_size": len(self._embed_cache),
        }

    def close(self) -> None:
        self._conn.close()
        self._vector_store.close()
        if self._owns_port and self._embed_port is not None:
            self._embed_port.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# Corpus ingestion
# ─────────────────────────────────────────────────────────────────────────────

def ingest_parallel_corpus(
    store: TranslationRAGStore,
    source_texts: list[str],
    target_texts: list[str],
    source_lang: str,
    target_lang: str,
    domain: str = "",
    provenance: str = "corpus",
    glossary: dict[str, str] | None = None,
) -> int:
    """Ingest a parallel corpus. CID includes target_text for proper dedup."""
    pairs = []
    for src, tgt in zip(source_texts, target_texts):
        if not src.strip() or not tgt.strip():
            continue

        cid = make_cid(src, tgt, target_lang)
        embedding = store._embed(src)
        if embedding is None:
            continue

        pairs.append(TranslationPair(
            cid=cid, source_text=src, target_text=tgt,
            source_lang=source_lang, target_lang=target_lang,
            domain=domain, component_type="",
            glossary_terms=glossary or {},
            source_embedding=embedding,
            provenance=provenance,
            quality_score=1.0 if provenance == "human" else 0.8,
        ))

    if not pairs:
        return 0
    return store.ingest_batch(pairs)


def ingest_from_hf_dataset(
    store: TranslationRAGStore,
    dataset_name: str,
    source_lang: str,
    target_lang: str,
    domain: str = "general",
    split: str = "train",
    max_samples: int = 10000,
) -> int:
    """Ingest from a HuggingFace parallel dataset."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("  ⚠ datasets library not available. Install: pip install datasets")
        return 0

    print(f"  Loading {dataset_name} ({split})...")
    ds = load_dataset(dataset_name, split=split, streaming=True)

    source_texts = []
    target_texts = []

    for i, row in enumerate(ds):
        if i >= max_samples:
            break

        # Handle different dataset formats
        if "translation" in row and isinstance(row["translation"], dict):
            src = row["translation"].get(source_lang, "")
            tgt = row["translation"].get(target_lang, "")
        elif "source" in row and "target" in row:
            src = row["source"]
            tgt = row["target"]
        elif "src" in row and "tgt" in row:
            src = row["src"]
            tgt = row["tgt"]
        else:
            continue

        if src and tgt:
            source_texts.append(src)
            target_texts.append(tgt)

    if not source_texts:
        print(f"  ⚠ No parallel pairs found in {dataset_name}")
        return 0

    print(f"  Found {len(source_texts)} pairs. Ingesting...")
    return ingest_parallel_corpus(
        store, source_texts, target_texts,
        source_lang, target_lang, domain=domain, provenance="corpus",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Self-improving feedback loop
# ─────────────────────────────────────────────────────────────────────────────

FEEDBACK_DDL = """
CREATE TABLE IF NOT EXISTS translation_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text     TEXT NOT NULL,
    model_output    TEXT NOT NULL,
    human_edit      TEXT,
    target_lang     TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT '',
    qe_score        REAL NOT NULL DEFAULT 0.0,
    was_accepted    INTEGER NOT NULL DEFAULT 0,
    was_edited      INTEGER NOT NULL DEFAULT 0,
    edit_distance   REAL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tf_lang ON translation_feedback(target_lang);
CREATE INDEX IF NOT EXISTS tf_domain ON translation_feedback(domain);
"""


class FeedbackStore:
    """Collects human post-edits → preference pairs for DPO."""

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite_connect(store_path, check_same_thread=False)
        self._conn.row_factory = None
        self._conn.executescript(FEEDBACK_DDL + OBSERVABILITY_DDL)
        self._conn.commit()

    def record(self, source: str, model_output: str, target_lang: str,
               human_edit: str | None = None, qe_score: float = 0.0,
               domain: str = "") -> None:
        was_accepted = 1 if human_edit is None or human_edit == model_output else 0
        was_edited = 1 if human_edit is not None and human_edit != model_output else 0
        edit_dist = _edit_distance(model_output, human_edit) if human_edit else None

        self._conn.execute(
            """INSERT INTO translation_feedback
               (source_text, model_output, human_edit, target_lang, domain,
                qe_score, was_accepted, was_edited, edit_distance, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source, model_output, human_edit, target_lang, domain,
             qe_score, was_accepted, was_edited, edit_dist,
             time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        self._conn.commit()

        _log_event(self._conn, "feedback", {
            "source_len": len(source), "target_lang": target_lang,
            "domain": domain, "was_accepted": was_accepted,
            "was_edited": was_edited, "edit_distance": edit_dist,
            "qe_score": qe_score,
        })

    def get_preference_pairs(self, min_edit_distance: float = 0.1) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source_text, model_output, human_edit, target_lang, domain, qe_score "
            "FROM translation_feedback WHERE was_edited = 1 AND edit_distance > ?",
            (min_edit_distance,),
        ).fetchall()

        return [{
            "source": row[0], "rejected": row[1], "chosen": row[2],
            "target_lang": row[3], "domain": row[4], "qe_score": row[5],
        } for row in rows]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM translation_feedback").fetchone()[0]
        accepted = self._conn.execute("SELECT COUNT(*) FROM translation_feedback WHERE was_accepted = 1").fetchone()[0]
        edited = self._conn.execute("SELECT COUNT(*) FROM translation_feedback WHERE was_edited = 1").fetchone()[0]
        avg_edit = self._conn.execute("SELECT AVG(edit_distance) FROM translation_feedback WHERE was_edited = 1").fetchone()[0] or 0.0

        return {
            "total": total, "accepted": accepted, "edited": edited,
            "acceptance_rate": round(accepted / total, 4) if total else 0,
            "edit_rate": round(edited / total, 4) if total else 0,
            "avg_edit_distance": round(avg_edit, 4),
            "preference_pairs": len(self.get_preference_pairs()),
        }

    def close(self) -> None:
        self._conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    from lgwks_vecmath import ZeroVectorError
    try:
        return _vm.cosine(a, b)
    except ZeroVectorError:
        return 0.0


def _edit_distance(a: str, b: str) -> float:
    """Normalized Levenshtein distance."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n] / max(m, n)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Translation RAG pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest-hf", help="Ingest from HuggingFace dataset")
    p_ingest.add_argument("--dataset", required=True)
    p_ingest.add_argument("--source-lang", default="en")
    p_ingest.add_argument("--target-lang", default="fr")
    p_ingest.add_argument("--domain", default="general")
    p_ingest.add_argument("--max-samples", type=int, default=10000)
    p_ingest.add_argument("--store", default="store/translate_rag.db")

    p_stats = sub.add_parser("stats", help="Show store statistics")
    p_stats.add_argument("--store", default="store/translate_rag.db")

    p_retrieve = sub.add_parser("retrieve", help="Retrieve nearest translations")
    p_retrieve.add_argument("source")
    p_retrieve.add_argument("--target-lang", default="fr")
    p_retrieve.add_argument("--top-k", type=int, default=5)
    p_retrieve.add_argument("--store", default="store/translate_rag.db")

    p_drift = sub.add_parser("drift", help="Check for quality drift")
    p_drift.add_argument("--store", default="store/translate_rag.db")

    args = parser.parse_args()
    store_path = Path(args.store)

    if args.cmd == "ingest-hf":
        store = TranslationRAGStore(store_path)
        count = ingest_from_hf_dataset(
            store, args.dataset, args.source_lang, args.target_lang,
            domain=args.domain, max_samples=args.max_samples,
        )
        print(f"  ✓ Ingested {count} pairs")
        print(f"  Stats: {json.dumps(store.stats(), indent=2)}")
        store.close()

    elif args.cmd == "stats":
        store = TranslationRAGStore(store_path)
        print(json.dumps(store.stats(), indent=2))
        store.close()

    elif args.cmd == "retrieve":
        store = TranslationRAGStore(store_path)
        results = store.retrieve(args.source, args.target_lang, top_k=args.top_k)
        if not results:
            print("  No results found.")
        for r in results:
            print(f"  [{r['similarity']:.4f}] {r['source'][:60]}")
            print(f"    → {r['target'][:60]}")
            print(f"    domain={r['domain']} provenance={r['provenance']} quality={r['quality_score']}")
        store.close()

    elif args.cmd == "drift":
        store = TranslationRAGStore(store_path)
        print(json.dumps(store.detect_drift(), indent=2))
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
