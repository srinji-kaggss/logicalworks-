"""
lgwks_steering — the adjustable control surface, both sides of the membrane.

HUMAN SIDE — three forced, visible dials that steer how the instrument reasons:
  • Frontierness   0=consolidated/established knowledge … 1=frontier/speculative
  • Lens          -1=philosophy (first-principles, the why) … +1=science (evidence, the how)
  • Depth          0=shallow (the single answer, terse) … 1=deep (exhaustive, edge cases)
The dials are rendered as bars so the human always SEES the active stance and can adjust it.

AI SIDE — the schema is a THOUGHT-CONTINUATION packet, not prose. As close to thinking-token →
thinking-token as a portable text channel allows: terse, compact-keyed, evidence by hash-ref (never
inline), continuation-shaped — the next call (or next agent) RESUMES the chain of thought instead of
re-parsing narrative. (Honest limit: true latent/KV-cache sharing is frontier + non-portable across
model versions and free models don't expose it; this symbolic IR is the portable approximation.)

Both sides gate on CONTEXT SUFFICIENCY: a verb refuses to run on too-thin input and names exactly
what is missing, rather than guessing — clarification is a deterministic interface duty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _clamp(x: float, lo: float, hi: float, default: float) -> float:
    # NaN-safe (IEEE-754: NaN comparisons are false) — guard finiteness explicitly, never silently propagate.
    if not isinstance(x, (int, float)) or not math.isfinite(x):
        return default
    return max(lo, min(hi, float(x)))


@dataclass
class Steering:
    frontierness: float = 0.3      # default: lean established, a little reach
    lens: float = 0.0              # default: balanced philosophy/science
    depth: float = 0.5             # default: medium
    explicit: bool = False         # did the caller set any dial, or are these defaults?

    @classmethod
    def from_args(cls, args) -> "Steering":
        f, l, d = getattr(args, "frontier", None), getattr(args, "lens", None), getattr(args, "depth", None)
        explicit = any(v is not None for v in (f, l, d))
        return cls(
            frontierness=_clamp(f if f is not None else 0.3, 0.0, 1.0, 0.3),
            lens=_clamp(l if l is not None else 0.0, -1.0, 1.0, 0.0),
            depth=_clamp(d if d is not None else 0.5, 0.0, 1.0, 0.5),
            explicit=explicit,
        )

    def prompt_fragment(self) -> str:
        """Condition the Tongue on the dials — terse directives, not prose."""
        bits = []
        bits.append("reach for frontier/speculative mechanisms and label confidence"
                    if self.frontierness >= 0.66 else
                    "stay on established, well-consolidated knowledge"
                    if self.frontierness <= 0.33 else
                    "balance established knowledge with a measured reach toward the frontier")
        bits.append("reason from first principles and concepts (the why)" if self.lens <= -0.33 else
                    "demand empirical evidence and measurement (the how)" if self.lens >= 0.33 else
                    "weave first-principles reasoning with empirical evidence")
        bits.append("give only the single most important answer, terse" if self.depth <= 0.33 else
                    "be exhaustive: mechanisms, edge cases, second-order effects" if self.depth >= 0.66 else
                    "balanced depth: the answer plus its main caveats")
        return "STANCE: " + "; ".join(bits) + "."

    def compact(self) -> dict:
        """For the AI thought-packet: short keys, rounded — token-frugal."""
        return {"front": round(self.frontierness, 2), "lens": round(self.lens, 2), "depth": round(self.depth, 2)}


# The AI-side thought-continuation schema (the "speaking to a version of yourself" channel).
THOUGHT_SCHEMA = (
    '{"v":"lgwks.thought.v0",'
    '"steer":{"front":0.0,"lens":0.0,"depth":0.0},'   # the dials, carried so the next self holds the stance
    '"intent":"<terse live aim, NOT prose>",'
    '"open":["<thread to continue>"],'                # open threads — what is still being thought
    '"hyp":[{"k":"H1","h":"<claim>","p":0.0}],'        # working hypotheses + probability
    '"ev":["<artifact-hash-ref>"],'                   # evidence BY REF, never inline (no token re-spend)
    '"killed":["<pruned dead-end>"],'                 # so the next self does not re-walk it
    '"next":"<the one move to continue from here>"}'
)


# Search/evolution direction (Director): sprawl DOWN (decompose to primitives) + OUT (breadth) BEFORE
# UP (synthesis). "Thinking up is easier after down is done." Applies to the research frontier AND the
# ML weight fleet (many small specialised models = out; each grounded to a primitive = down; meta = up).
_DIR_RANK = {"down": 0, "decompose": 0, "out": 1, "breadth": 1, "up": 2, "synthesize": 2}


def frontier_order(nodes: list[dict], key: str = "direction") -> list[dict]:
    """Stable-sort frontier nodes so decomposition(down) + breadth(out) expand before synthesis(up).
    Unknown/absent direction sorts as 'out' (1) — explored, but never ahead of a decomposition."""
    return sorted(nodes, key=lambda n: _DIR_RANK.get((n.get(key) or "out"), 1))


def require_context(parts: dict, required: list[str]) -> list[str]:
    """Context-sufficiency gate. Returns the list of MISSING required keys (empty = sufficient).
    A verb refuses on non-empty and names what's missing — no guessing on thin input."""
    return [k for k in required if not (parts.get(k) or "").strip()] if parts else list(required)
