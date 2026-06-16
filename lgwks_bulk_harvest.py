"""lgwks_bulk_harvest — multi-source historical ingestion (Phase 1 Expeditor).

Scans .claude, .gemini, and .codex directories for historical transcripts and
processes them through the Aetherius Neural Tokenizer (ANT) and Transcript Cortex.

Speeds up Phase 1 by bootstrapping the 1M turn goal with existing data.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import lgwks_cortex
from lgwks_clock import now_iso as _now

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("lgwks.bulk_harvest")

# Common historical paths
HISTORICAL_DIRS = [
    Path.home() / ".claude",
    Path.home() / ".gemini",
    Path.home() / ".codex",
]

def bulk_harvest(repo_root: Path, limit: int | None = None) -> dict[str, Any]:
    """Find and process all historical transcripts."""
    cortex = lgwks_cortex.TranscriptCortex(repo_root)
    total_turns = 0
    file_count = 0
    
    # Identify search roots (home dirs + current project dirs)
    roots = list(HISTORICAL_DIRS)
    roots.append(repo_root)
    
    found_files = []
    for root in roots:
        if not root.exists():
            continue
        logger.info(f"Scanning {root}...")
        for path in root.rglob("*.jsonl"):
            # Skip already processed cortex/store files
            if "store/cortex" in str(path) or "store/daemon" in str(path):
                continue
            found_files.append(path)

    logger.info(f"Found {len(found_files)} potential transcript files.")
    
    for path in found_files:
        if limit and total_turns >= limit:
            break
            
        try:
            # Generate a stable session ID from the path hash
            import lgwks_hashing
            session_id = f"hist-{lgwks_hashing.blake_id(str(path), size=6)}"
            
            # Process up to the remaining limit
            n_turns = 0
            if limit:
                n_turns = max(1, limit - total_turns)

            turns = cortex.process_transcript(path, session_id, n=n_turns)
            if turns:
                file_count += 1
                total_turns += len(turns)
                logger.info(f"  Ingested {len(turns)} turns from {path.name}")
        except Exception as e:
            logger.info(f"  Failed to process {path.name}: {e}")


    return {
        "files_processed": file_count,
        "turns_ingested": total_turns,
        "ts": _now()
    }

def main(args):
    repo = Path(args.repo).resolve()
    logger.info(f"Starting Bulk Harvest for Aetherius (Goal: 1M Turns)")
    result = bulk_harvest(repo, limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0

def add_parser(sub) -> None:
    p = sub.add_parser("bulk-harvest", help="ingest historical .claude/.gemini/.codex transcripts")
    p.add_argument("--repo", default=".", help="repo root")
    p.add_argument("--limit", type=int, help="max turns to ingest")
    p.set_defaults(func=main)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    main(args)
