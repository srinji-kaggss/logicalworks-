"""lgwks_substrate_text — text processing: chunking, scoring, stemming, fact extraction.

Defense-in-Depth:
- Layer 1 (entry): empty/whitespace input returns empty results immediately.
- Layer 2 (business): score thresholds prevent noise from entering the fact pipeline.
- Layer 3 (environment): overlap calculation avoids degenerate step=0.
- Layer 4 (debug): all functions are pure (no side effects), fully testable.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from lgwks_substrate_config import (
    CODE_RE,
    NARRATIVE_TERMS,
    NUMERIC_RE,
    PREVIOUS_VERSION_RE,
    PROCEDURE_TERMS,
    REF_RE,
    SENTENCE_SPLIT_RE,
    UPCOMING_EFFECTIVE_DATE,
    VERSION_BUCKETS,
)


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _fact_score(text: str) -> float:
    """Score a sentence for factual density. Higher = more procedural/rule-like."""
    if not text:
        return 0.0
    words = text.lower().split()
    if not words:
        return 0.0
    proc = sum(1 for w in words if w.rstrip(",.") in PROCEDURE_TERMS)
    narr = sum(1 for w in words if w.rstrip(",.") in NARRATIVE_TERMS)
    numeric = 1.0 if NUMERIC_RE.search(text) else 0.0
    code = 1.0 if CODE_RE.search(text) else 0.0
    ref = 1.0 if REF_RE.search(text) else 0.0
    return (proc / len(words) * 2.0) - (narr / len(words) * 1.5) + numeric + code + ref


def _chunk_kind(text: str, fact_score: float) -> str:
    if fact_score >= 1.0:
        return "rule"
    if fact_score >= 0.6:
        return "fact"
    return "narrative"


def _stem_text(text: str, threshold: float) -> str:
    """Filter to sentences that meet the factual-density threshold."""
    chosen: list[str] = []
    for sentence in _split_sentences(text):
        s = _fact_score(sentence)
        if s >= threshold or NUMERIC_RE.search(sentence) or REF_RE.search(sentence) or CODE_RE.search(sentence):
            clean = sentence.strip()
            if clean:
                chosen.append(clean)
    return " ".join(chosen).strip()


def _chunk_text(text: str, size: int = 320, overlap: int = 48) -> list[str]:
    """Sliding-window chunking by word count. Delegates to the canonical chunker
    (#265); byte-exact with the prior copy. overlap is clamped to size-1 so the old
    step=max(1,size-overlap) tolerance is preserved instead of raising."""
    from lgwks_chunking import SlidingWindowChunking
    return SlidingWindowChunking(size, min(overlap, size - 1)).chunk(text)


def _fact_sentences(text: str, threshold: float) -> list[str]:
    """Extract unique factual sentences from text."""
    out: list[str] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        s = _fact_score(sentence)
        if s >= threshold or NUMERIC_RE.search(sentence) or REF_RE.search(sentence) or CODE_RE.search(sentence):
            clean = sentence.strip()
            if clean and clean not in seen:
                seen.add(clean)
                out.append(clean)
    return out


def _version_bucket(text: str, *, as_of: date) -> str:
    """Classify a fact into Current / Upcoming / Previous based on version cues."""
    low = text.lower()
    if "v36" in low:
        return "Upcoming" if as_of < UPCOMING_EFFECTIVE_DATE else "Current"
    if "upcoming" in low or "future" in low or "effective june 15, 2026" in low or "effective 2026-06-15" in low:
        return "Upcoming"
    if "previous" in low or "prior" in low or "retired" in low or "legacy" in low or "deprecated" in low or "superseded" in low:
        return "Previous"
    if PREVIOUS_VERSION_RE.search(text):
        return "Previous"
    return "Current"


def _bucket_facts(facts: list[dict[str, Any]], *, as_of: date, limit: int) -> dict[str, list[dict[str, Any]]]:
    """Distribute facts into version buckets, highest score first, capped per bucket."""
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in VERSION_BUCKETS}
    sorted_facts = sorted(
        facts,
        key=lambda row: (float(row.get("fact_score") or 0), row.get("fact_id", "")),
        reverse=True,
    )
    for row in sorted_facts:
        text = str(row.get("fact_text", ""))
        if not text.strip():
            continue
        bucket = _version_bucket(text, as_of=as_of)
        if len(buckets[bucket]) >= limit:
            continue
        buckets[bucket].append({
            "fact_id": row.get("fact_id", ""),
            "chunk_id": row.get("chunk_id", ""),
            "document_id": row.get("document_id", ""),
            "fact_score": row.get("fact_score", 0),
            "chunk_kind": row.get("chunk_kind", ""),
            "text": text,
        })
    return buckets
