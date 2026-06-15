"""lgwks_cortex — the Transcript Cortex (PRD-06 U5).

Tails agent JSONL transcripts and converts them into per-turn records for the
Subconscious Engine. This is the sensory organ that allows the daemon to
detect "lies," intent drift, and unresolved commitments.

Contract: emits `lgwks.cortex.v1`
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_hashing
import lgwks_transcript
from lgwks_clock import now_iso as _now

@dataclass
class CortexTurn:
    turn_id: str
    session_id: str
    role: str
    intent_class: str = "unknown"
    phase: str = "observation"
    entities: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    content: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "role": self.role,
            "intent_class": self.intent_class,
            "phase": self.phase,
            "entities": self.entities,
            "attention": self.attention,
            "ts": self.ts,
        }

class TranscriptCortex:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.cortex_dir = repo_root / "store" / "cortex"
        self.cortex_dir.mkdir(parents=True, exist_ok=True)

    def process_transcript(self, transcript_path: Path, session_id: str) -> list[CortexTurn]:
        """Convert a raw JSONL transcript into a sequence of CortexTurns."""
        # Layer 1: Entry Point Validation
        if not transcript_path.exists():
            return []

        # Tail the last 50 turns with content
        # PRD-06: "deterministic extraction first, BERT salience when 05 lands"
        import lgwks_intent_classifier as ic
        clf = ic.IntentClassifier.load()
        processed: list[CortexTurn] = []

        raw_turns = lgwks_transcript.tail(transcript_path, n=50, include_content=True)

        for turn in raw_turns:
            content = turn.get("content", "")

            # Layer 2: Business Logic (ModernBERT Salience)
            entities = self._extract_entities(content)
            res = clf.classify(content)
            intent = res.label

            ct = CortexTurn(
                turn_id=turn["turn_id"],
                session_id=session_id,
                role=turn["role"],
                intent_class=intent,
                entities=entities,
                attention=entities[:3], # Simple attention baseline
                content=content
            )
            
            # Layer 3: Neural Tokenization (Aetherius Neural Tokenizer)
            try:
                import lgwks_tokenizer as ant
                tokenizer = ant.AetheriusTokenizer(self.repo_root)
                tokenized = tokenizer.tokenize_trajectory(ct.to_dict())
                ct.attention.extend([f"ant:{t}" for t in tokenized.tokens[:5]])
            except Exception:
                pass

            processed.append(ct)
            
            # Layer 4: Audit (Telemetry)
            self._persist_turn(ct)

        return processed

    def _extract_entities(self, text: str) -> list[str]:
        """Find repo entities (files, modules) mentioned in text."""
        # Simple regex-based extraction for now
        import re
        # Match potential file paths or module names
        matches = re.findall(r'\b[a-zA-Z0-9_\-/]+\.(?:py|rs|js|ts|md|json)\b', text)
        return sorted(list(set(matches)))

    def _classify_intent(self, text: str) -> str:
        """Heuristic intent classification."""
        text_lower = text.lower()
        if "research" in text_lower or "find" in text_lower:
            return "research_orchestration"
        if "test" in text_lower or "pytest" in text_lower:
            return "quality_assurance"
        if "fix" in text_lower or "refactor" in text_lower:
            return "code_mutation"
        return "unknown"

    def _persist_turn(self, turn: CortexTurn):
        """Save the turn to the local cortex store (JSONL)."""
        path = self.cortex_dir / f"{turn.session_id}.cortex.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict()) + "\n")

def index_command(args) -> int:
    """CLI entrypoint for indexing."""
    from pathlib import Path
    cortex = TranscriptCortex(Path(args.repo))
    cortex.process_transcript(Path(args.path), args.session_id)
    return 0
