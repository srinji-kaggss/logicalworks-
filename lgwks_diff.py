"""
lgwks_diff — generic semantic diffing engine.

Compares two sets of parsed document chunks (e.g. current vs future versions of
regulatory standards, code files, or web pages) and extracts structured changes:
- Added chunks / rules / tables
- Removed chunks / rules / tables
- Modified chunks (matched by structural similarity or section boundaries)
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DiffRecord:
    status: str  # "added" | "removed" | "modified" | "unchanged"
    section_id: str
    section_title: str
    chunk_type: str
    before_text: str | None
    after_text: str | None
    similarity: float  # 0.0 to 1.0


def _similarity(s1: str, s2: str) -> float:
    """Compute structural similarity score between two text blocks."""
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def diff_chunks(prev_chunks: list[dict[str, Any]], curr_chunks: list[dict[str, Any]], similarity_threshold: float = 0.6) -> list[DiffRecord]:
    """Diff two list of chunks semantically.

    Matches modified chunks by comparing text similarity within the same section and chunk type.
    """
    diffs: list[DiffRecord] = []
    
    # Group by (section_id, chunk_type) to find potential matches
    prev_by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in prev_chunks:
        key = (c.get("section_id", "root"), c.get("chunk_type", "rule"))
        prev_by_group.setdefault(key, []).append(c)
        
    curr_by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in curr_chunks:
        key = (c.get("section_id", "root"), c.get("chunk_type", "rule"))
        curr_by_group.setdefault(key, []).append(c)
        
    # Set of matched hashes to prevent double matching
    matched_prev_hashes: set[str] = set()
    matched_curr_hashes: set[str] = set()
    
    # Process each group (section_id, chunk_type)
    all_groups = set(prev_by_group.keys()) | set(curr_by_group.keys())
    
    for key in all_groups:
        prev_list = prev_by_group.get(key, [])
        curr_list = curr_by_group.get(key, [])
        
        # 1. First pass: exact hash matches (unchanged)
        for c in curr_list:
            c_hash = c.get("hash") or c.get("content_sha256") or hashlib.sha256(c["text"].encode()).hexdigest()[:16]
            for p in prev_list:
                p_hash = p.get("hash") or p.get("content_sha256") or hashlib.sha256(p["text"].encode()).hexdigest()[:16]
                if p_hash == c_hash and p_hash not in matched_prev_hashes and c_hash not in matched_curr_hashes:
                    matched_prev_hashes.add(p_hash)
                    matched_curr_hashes.add(c_hash)
                    diffs.append(DiffRecord(
                        status="unchanged",
                        section_id=c.get("section_id", "root"),
                        section_title=c.get("section_title", ""),
                        chunk_type=c.get("chunk_type", "rule"),
                        before_text=p["text"],
                        after_text=c["text"],
                        similarity=1.0
                    ))
                    break
                    
        # 2. Second pass: partial matches (modified)
        unmatched_prev = [p for p in prev_list if (p.get("hash") or p.get("content_sha256") or hashlib.sha256(p["text"].encode()).hexdigest()[:16]) not in matched_prev_hashes]
        unmatched_curr = [c for c in curr_list if (c.get("hash") or c.get("content_sha256") or hashlib.sha256(c["text"].encode()).hexdigest()[:16]) not in matched_curr_hashes]
        
        for c in unmatched_curr:
            best_match = None
            best_sim = 0.0
            c_hash = c.get("hash") or c.get("content_sha256") or hashlib.sha256(c["text"].encode()).hexdigest()[:16]
            
            for p in unmatched_prev:
                p_hash = p.get("hash") or p.get("content_sha256") or hashlib.sha256(p["text"].encode()).hexdigest()[:16]
                if p_hash in matched_prev_hashes:
                    continue
                sim = _similarity(p["text"], c["text"])
                if sim > best_sim:
                    best_sim = sim
                    best_match = p
                    
            if best_match and best_sim >= similarity_threshold:
                p_hash = best_match.get("hash") or best_match.get("content_sha256") or hashlib.sha256(best_match["text"].encode()).hexdigest()[:16]
                matched_prev_hashes.add(p_hash)
                matched_curr_hashes.add(c_hash)
                diffs.append(DiffRecord(
                    status="modified",
                    section_id=c.get("section_id", "root"),
                    section_title=c.get("section_title", ""),
                    chunk_type=c.get("chunk_type", "rule"),
                    before_text=best_match["text"],
                    after_text=c["text"],
                    similarity=round(best_sim, 3)
                ))
                
        # 3. Third pass: remaining unmatched are added or removed
        for p in prev_list:
            p_hash = p.get("hash") or p.get("content_sha256") or hashlib.sha256(p["text"].encode()).hexdigest()[:16]
            if p_hash not in matched_prev_hashes:
                diffs.append(DiffRecord(
                    status="removed",
                    section_id=p.get("section_id", "root"),
                    section_title=p.get("section_title", ""),
                    chunk_type=p.get("chunk_type", "rule"),
                    before_text=p["text"],
                    after_text=None,
                    similarity=0.0
                ))
                
        for c in curr_list:
            c_hash = c.get("hash") or c.get("content_sha256") or hashlib.sha256(c["text"].encode()).hexdigest()[:16]
            if c_hash not in matched_curr_hashes:
                diffs.append(DiffRecord(
                    status="added",
                    section_id=c.get("section_id", "root"),
                    section_title=c.get("section_title", ""),
                    chunk_type=c.get("chunk_type", "rule"),
                    before_text=None,
                    after_text=c["text"],
                    similarity=0.0
                ))
                
    return diffs
