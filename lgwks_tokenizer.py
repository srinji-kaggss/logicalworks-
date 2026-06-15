"""lgwks_tokenizer — the Aetherius Neural Tokenizer (ANT).

Proprietary byte-level BPE tokenizer optimized for 'Space-Time' trajectories.
Treats code entities, logic-paths, and terminal events as atomic primitives.

Vocab Layers:
  0-255:    Raw Bytes
  256-511:  Aetherius Tokens (Transitions, States, Surprise Signals)
  512+:     BPE Merges (Code-specific patterns)
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TokenizedTrajectory:
    tokens: list[int]
    hashes: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

class AetheriusTokenizer:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.vocab_path = repo_root / "store" / "models" / "ant_vocab.json"
        self.vocab = self._load_vocab()
        
    def _load_vocab(self) -> dict[str, int]:
        if self.vocab_path.exists():
            return json.loads(self.vocab_path.read_text())
        
        # Seed Base Vocab
        v = {chr(i): i for i in range(256)}
        # Aetherius Core Tokens
        core = [
            "[BEG]", "[END]", "[TRN]", "[CAU]", "[SYM]",
            "[ERR]", "[FIX]", "[AXI]", "[LIQ]", "[REASON]",
            "[SURPRISE]", "[MAYDAY]", "[GROUNDED]", "[HOLE]"
        ]
        for i, t in enumerate(core):
            v[t] = 256 + i
        return v

    def encode_entity(self, entity_id: str) -> int:
        """Hash a code entity into a proprietary token ID."""
        h = hashlib.blake3(entity_id.encode()).digest()
        # Map to a high-range token space reserved for entities
        return 1_000_000 + (int.from_bytes(h[:4], "little") % 10_000_000)

    def tokenize_trajectory(self, turn_data: dict[str, Any]) -> TokenizedTrajectory:
        """Encode a reasoning turn into Aetherius tokens."""
        tokens = []
        hashes = []
        
        # Encode Transition
        tokens.append(self.vocab["[TRN]"])
        
        # Encode Role
        role = turn_data.get("role", "unknown")
        tokens.extend([ord(c) for c in role])
        
        # Encode Entities as atomic tokens
        for entity in turn_data.get("entities", []):
            tok = self.encode_entity(entity)
            tokens.append(tok)
            hashes.append(hashlib.blake3(entity.encode()).hexdigest()[:8])
            
        # Encode Intent
        intent = turn_data.get("intent_class", "unknown")
        tokens.append(self.vocab["[BEG]"])
        tokens.extend([ord(c) for c in intent])
        tokens.append(self.vocab["[END]"])
        
        return TokenizedTrajectory(tokens=tokens, hashes=hashes)

    def save(self):
        self.vocab_path.parent.mkdir(parents=True, exist_ok=True)
        self.vocab_path.write_text(json.dumps(self.vocab, indent=2))

def main(args):
    tokenizer = AetheriusTokenizer(Path(args.repo))
    # Test logic
    test_turn = {
        "role": "assistant",
        "intent_class": "code_mutation",
        "entities": ["lgwks_codebase.py", "tui/src/main.rs"]
    }
    traj = tokenizer.tokenize_trajectory(test_turn)
    print(f"Tokenized Trajectory: {traj.tokens[:10]}... (len: {len(traj.tokens)})")
    print(f"Entity Hashes: {traj.hashes}")
    return 0
