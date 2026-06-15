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

    def process_transcript(
        self,
        transcript_path: Path,
        session_id: str,
        n: int = 0,
        gate: Any = None,
    ) -> list[CortexTurn]:
        """Convert a raw JSONL transcript into a sequence of CortexTurns.

        Each turn is ANT-tokenized and emitted as a tokenized artifact onto the
        State Fabric (Causal Tape + TokenIndex) — the durable, replayable training
        trajectory. n=0 processes the whole file. A caller may pass its own `gate`
        (it owns the lifecycle); otherwise a per-session gate is opened/closed here.
        """
        # Layer 1: Entry Point Validation
        if not transcript_path.exists():
            return []

        # PRD-06: "deterministic extraction first, BERT salience when 05 lands"
        import lgwks_intent_classifier as ic
        import lgwks_tokenizer as atok

        clf = ic.IntentClassifier.load()
        tokenizer = atok.AetheriusTokenizer(self.repo_root)

        own_gate = gate is None
        if own_gate:
            import lgwks_storage
            gate = lgwks_storage.get_gate("cortex", tenant_id=session_id)

        processed: list[CortexTurn] = []
        try:
            raw_turns = lgwks_transcript.tail(transcript_path, n=n, include_content=True)

            for turn in raw_turns:
                content = turn.get("content", "")

                # Layer 2: Business Logic (ModernBERT Salience)
                entities = self._extract_entities(content)
                res = clf.classify(content)

                ct = CortexTurn(
                    turn_id=turn["turn_id"],
                    session_id=session_id,
                    role=turn["role"],
                    intent_class=res.label,
                    entities=entities,
                    attention=entities[:3],  # Simple attention baseline
                    content=content,
                )

                # Layer 3: Neural Tokenization (Aetherius Neural Tokenizer).
                # Tokenize the full turn (content + entities + modality anchors) —
                # not the metadata-only to_dict() that previously dropped content.
                tokens: tuple[int, ...] = ()
                try:
                    traj = tokenizer.tokenize_trajectory({
                        "content": content,
                        "entities": entities,
                        "image_hash": turn.get("image_hash", ""),
                        "tty_hash": turn.get("tty_hash", ""),
                    })
                    tokens = tuple(traj.tokens)
                    ct.attention.extend([f"atok:{t}" for t in tokens[:5]])
                except Exception:
                    tokens = ()

                # Layer 4: persist. The durable, replayable training trajectory
                # goes on the Causal Tape (+ TokenIndex); the JSONL is a mirror.
                self._emit_trajectory(gate, ct, content, tokens)
                self._persist_turn(ct)
                processed.append(ct)
        finally:
            if own_gate:
                gate.close()

        return processed

    def _emit_trajectory(self, gate: Any, ct: CortexTurn, content: str, tokens: tuple[int, ...]) -> None:
        """Append one turn to the State Fabric as a tokenized reasoning artifact.

        Best-effort: trajectory capture must never break transcript processing
        (the gate isolates projection failures; we only guard the tape append).
        """
        import time

        import lgwks_artifact_tokenized as artifact_mod

        try:
            payload_cid = lgwks_hashing.content_id(content or ct.turn_id)
            artifact = artifact_mod.build_artifact(
                tenant_id=ct.session_id,
                source="daemon_event",
                modality="reasoning",
                tokenization_id=gate.tokenizers.default_aetherius_id(),
                token_stream=tokens,
                payload_cid=payload_cid,
                payload_meta={
                    "turn_id": ct.turn_id,
                    "role": ct.role,
                    "intent_class": ct.intent_class,
                    "phase": ct.phase,
                    "entities": ct.entities,
                    "ts": ct.ts,
                    "text": content[:2000],
                },
                capability_id="cap:cortex",
                timestamp=time.time(),
            )
            gate.ingest_artifact(artifact)
        except Exception:
            pass

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
