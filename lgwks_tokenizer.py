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
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import lgwks_hashing

# Entity tokens live in a high, disjoint range (above bytes 0-255, core 256-511,
# modal 512-1023, and BPE merges 1024+). The token value is the entity's content
# hash offset by this base.
ENTITY_TOKEN_BASE = 1_000_000

# Width of the entity content hash, in bytes. 7 bytes = 56 bits: the largest hash
# that, offset by ENTITY_TOKEN_BASE, stays well inside SQLite's signed-INTEGER
# ceiling (2^63-1) where TokenIndex.token lives — 8 bytes would overflow it. At
# 56 bits the birthday-collision point is ~2^28 (~268M) distinct entities, vs ~2^16
# (~77k) at the old 4-byte width; injective for any realistic ANT corpus. This is
# the future model's token-id substrate — fixed BEFORE a model trains on the ids,
# never narrower than it can afford (#293, irreversible-substrate discipline).
ENTITY_HASH_BYTES = 7

# Content is bounded so a single turn can't produce an unbounded token stream.
# Truncation is RECORDED in the trajectory metadata (never silent) — the causal
# tape must be honest about what it dropped (#180 verifiable-tape contract).
_MAX_CONTENT_CHARS = 1000


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
        """Map noisy tokens to known system primitives (Levenshtein <= 1).

        Deterministic: `self.primitives` is a set (non-deterministic iteration
        order across processes under hash randomisation), so we scan it SORTED and
        keep the closest match (lowest distance, then lexicographic). The previous
        first-match-over-a-set made the output depend on iteration order — a
        reproducibility bug for anything downstream that must be replayable.

        NOTE: this is input-normalisation for the NLU / intent-matching path. It is
        deliberately NOT applied to the causal tape — `tokenize_trajectory` records
        content verbatim so the logged (state) matches the input that produced the
        consequence (#180 ground-truth requirement)."""
        words = text.split()
        corrected = []
        for word in words:
            w_lower = word.lower().strip(".,!?;:")
            if len(w_lower) < 3:
                corrected.append(word)
                continue
            best: tuple[int, str] | None = None
            for prim in sorted(self.primitives):
                d = self._levenshtein(w_lower, prim)
                if d <= 1 and (best is None or d < best[0]):
                    best = (d, prim)
            corrected.append(best[1] if best else word)
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
        """Encode a non-text modality anchor + a compact reference to its content.

        Emits the anchor token followed by the first 4 bytes of the (hex) content
        hash as positional byte-tokens; the FULL hash is preserved in the
        trajectory's `modality_map`, so the 4-byte prefix is only a locator, not the
        identity. Malformed input (short / non-hex hash) yields the anchor alone
        rather than raising — a bad upstream hash must not crash the tape encoder
        (cortex would otherwise swallow the exception into an empty token stream,
        silently dropping the whole turn from the training corpus)."""
        anchor = f"[{kind.upper()}]"
        tokens = [self.vocab.get(anchor, self.vocab["[SYM]"])]
        h = str(data_hash or "")
        if len(h) >= 8 and all(c in "0123456789abcdefABCDEF" for c in h[:8]):
            tokens.extend(int(h[i:i + 2], 16) for i in range(0, 8, 2))
        return tokens

    def tokenize_trajectory(self, turn_data: dict[str, Any]) -> TokenizedTrajectory:
        """Encode a true multimodal reasoning turn into Aetherius tokens."""
        tokens = []
        hashes = []
        m_map = {}

        # 1. Content is recorded VERBATIM. The causal tape is ground-truth training
        # data (#180): the logged (state) must be exactly what produced the
        # downstream consequence/residual. Spell-correcting it here (the old
        # `_smart_correct(content)`) desynced the tape from reality and silently
        # rewrote history — input-normalisation belongs in the NLU/intent path.
        content = turn_data.get("content", "")
        if not isinstance(content, str):
            content = str(content)

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
            h_hex = lgwks_hashing.blake_id(entity, size=ENTITY_HASH_BYTES)
            h = bytes.fromhex(h_hex)
            # Full 56-bit hash, not `% 10_000_000`. The modulo collapsed a wide
            # space into 10M, multiplying birthday collisions — and a collision
            # here is a false posting in the token index (a token query returns the
            # wrong artifact). The entity range is disjoint from byte/core/modal/
            # merge tokens, and 56 bits keeps it injective for the corpus while
            # staying inside the INTEGER column (see ENTITY_HASH_BYTES).
            tok = ENTITY_TOKEN_BASE + int.from_bytes(h, "little")
            tokens.append(tok)
            hashes.append(h_hex)

        # 5. Encode content — byte-level (UTF-8), never codepoint.
        # `ord(c)` was codepoint-level: any char >255 (e.g. '—' -> 8212) collided
        # with the core/modal/entity token ranges and corrupted the stream. UTF-8
        # bytes are always 0-255, matching the byte layer this tokenizer promises.
        # Slicing by char before encode is codepoint-safe (no mid-char byte split).
        truncated = len(content) > _MAX_CONTENT_CHARS
        tokens.append(self.vocab["[BEG]"])
        tokens.extend(content[:_MAX_CONTENT_CHARS].encode("utf-8"))
        tokens.append(self.vocab["[END]"])

        metadata = {
            "content_chars": len(content),
            "content_truncated": truncated,
            "entity_count": len(hashes),
        }
        return TokenizedTrajectory(
            tokens=tokens, hashes=hashes, modality_map=m_map, metadata=metadata
        )

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
