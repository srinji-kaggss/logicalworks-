"""lgwks_tokenizer — the Aetherius Neural Tokenizer (ANT).

//note: ANT (ours) is the Aetherius Neural Tokenizer. Unrelated to the 
//Anthropic 'ant' CLI. Code identifiers use 'atok' or 'ant_tok' to 
//avoid collision.

Proprietary byte-level BPE tokenizer optimized for 'Space-Time' trajectories.
Treats code entities, logic-paths, and terminal events as atomic primitives.

Vocab Layers:
  0-255:    Raw Bytes
  256-511:  Aetherius Core (Transitions, States, Surprise Signals)
  512-1023: Modal Anchors (IMG, TTY, VOICE, SENS)
  1024+:    BPE Merges & Phonetic Primitives
"""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import lgwks_hashing

@dataclass
class TokenizedTrajectory:
    tokens: list[int]
    hashes: list[str]
    modality_map: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

class AetheriusTokenizer:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.vocab_path = repo_root / "store" / "models" / "ant_vocab.json"
        self.vocab = self._load_vocab()
        # System primitives for spelling correction
        self.primitives = {
            "git", "lgwks", "codebase", "search", "cortex", "daemon",
            "axiom", "liquid", "engine", "status", "begin", "probe",
            "research", "substrate", "harvest", "token", "mesh"
        }
        
    def _load_vocab(self) -> dict[str, int]:
        if self.vocab_path.exists():
            return json.loads(self.vocab_path.read_text())
        
        v = {chr(i): i for i in range(256)}
        # Aetherius Core Tokens (256-511)
        core = [
            "[BEG]", "[END]", "[TRN]", "[CAU]", "[SYM]",
            "[ERR]", "[FIX]", "[AXI]", "[LIQ]", "[REASON]",
            "[SURPRISE]", "[MAYDAY]", "[GROUNDED]", "[HOLE]"
        ]
        for i, t in enumerate(core):
            v[t] = 256 + i
            
        # Modal Anchors (512-1023)
        modals = ["[IMG]", "[TTY]", "[VOICE]", "[SENS]", "[ANE]", "[MEM]"]
        for i, t in enumerate(modals):
            v[t] = 512 + i
            
        return v

    def _smart_correct(self, text: str) -> str:
        """Frontier spelling correction: maps noisy input to system primitives."""
        words = text.split()
        corrected = []
        for word in words:
            w_lower = word.lower().strip(".,!?;:")
            if len(w_lower) < 3:
                corrected.append(word)
                continue
            
            # Simple Levenshtein distance check against primitives
            match = word
            for prim in self.primitives:
                if self._levenshtein(w_lower, prim) <= 1:
                    match = prim
                    break
            corrected.append(match)
        return " ".join(corrected)

    def _levenshtein(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if not s2:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def encode_modality(self, kind: str, data_hash: str) -> list[int]:
        """Encodes non-text modalities into the token stream."""
        anchor = f"[{kind.upper()}]"
        tokens = [self.vocab.get(anchor, self.vocab["[SYM]"])]
        # Encode the first 4 bytes of the hash as positional tokens
        tokens.extend([int(data_hash[i:i+2], 16) for i in range(0, 8, 2)])
        return tokens

    def tokenize_trajectory(self, turn_data: dict[str, Any]) -> TokenizedTrajectory:
        """Encode a true multimodal reasoning turn into Aetherius tokens."""
        tokens = []
        hashes = []
        m_map = {}
        
        # 1. Normalize Intent (Smart Correction)
        content = turn_data.get("content", "")
        clean_content = self._smart_correct(content)
        
        # 2. Encode Modal Context (Images/Screenshots/TTY)
        # If the turn has an image (visual reasoning)
        if turn_data.get("image_hash"):
            h = turn_data["image_hash"]
            tokens.extend(self.encode_modality("IMG", h))
            m_map[h] = "image/png"
            
        # If the turn has TTY output (terminal reasoning)
        if turn_data.get("tty_hash"):
            h = turn_data["tty_hash"]
            tokens.extend(self.encode_modality("TTY", h))
            m_map[h] = "text/x-terminal"

        # 3. Encode Core Transition
        tokens.append(self.vocab["[TRN]"])
        
        # 4. Encode Entities
        for entity in turn_data.get("entities", []):
            h_hex = lgwks_hashing.blake_id(entity, size=4)
            h = bytes.fromhex(h_hex)
            tok = 1_000_000 + (int.from_bytes(h, "little") % 10_000_000)
            tokens.append(tok)
            hashes.append(h_hex)

            
        # 5. Encode Clean Content
        tokens.append(self.vocab["[BEG]"])
        tokens.extend([ord(c) for c in clean_content[:1000]]) # Cap for efficiency
        tokens.append(self.vocab["[END]"])
        
        return TokenizedTrajectory(tokens=tokens, hashes=hashes, modality_map=m_map)

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
