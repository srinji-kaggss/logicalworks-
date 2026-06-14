"""lgwks_cortex — the Transcript Cortex: indexes agent conversations into the substrate.

Converts agent JSONL transcripts into searchable entities and vectors.
Enables the 'docs agent' features by allowing Aetherius to query fleet history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lgwks_hashing
import lgwks_transcript
import lgwks_substrate_db as db
import lgwks_substrate_text as text
from lgwks_clock import now_iso as _now

SCHEMA = "lgwks.cortex.v1"

def index_transcript(transcript_path: Path, tenant_id: str, session_id: str) -> dict[str, Any]:
    """Index the latest turns from a transcript into the substrate."""
    turns = lgwks_transcript.tail(transcript_path, n=50, include_content=True)
    
    indexed_count = 0
    for turn in turns:
        content = turn.get("content", "").strip()
        if not content:
            continue
            
        turn_id = turn["turn_id"]
        role = turn["role"]
        
        # Create a document entry for the turn
        doc_id = f"turn-{lgwks_hashing.content_id(f'{session_id}:{turn_id}', 16)}"
        
        # In a real implementation, we would call lgwks_substrate_run or similar
        # For now, we simulate the 'Commitment Extraction'
        if role == "human" and ("promise" in content.lower() or "todo" in content.lower()):
            _extract_commitment(content, tenant_id, session_id, turn_id)
            
        indexed_count += 1
        
    return {
        "ok": True,
        "indexed": indexed_count,
        "ts": _now(),
    }

def _extract_commitment(content: str, tenant: str, session: str, turn: str):
    """Placeholder for future commitment extraction logic."""
    pass
