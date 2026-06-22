"""#265 — the 3 legacy chunkers route onto canonical lgwks_chunking.

`run._chunk` (size=400, overlap=0, split()), `jarvis.chunk_text` (450/70, \\S+) and
`substrate_text._chunk_text` (320/48, \\S+) were three copies of one sliding-window
algorithm. They now all delegate to `lgwks_chunking.SlidingWindowChunking`, keeping
their own (size, overlap) presets.

Chunk boundaries are corpus-sensitive (they key stored vectors/graph rows), so this
proves the routing changed NO bytes: each function is asserted against an inline copy
of its pre-routing body over an adversarial battery (control/unicode whitespace,
empty, single word, >size, and the overlap>=size tolerance the wrappers preserve by
clamping instead of raising).
"""

from __future__ import annotations

import re
import unittest

import lgwks_run as run
import lgwks_jarvis as jv
import lgwks_substrate_text as st


def _old_run(text, size=400):
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)] or []


def _old_jv(text, size=450, overlap=70):
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunks = []
    step = max(1, size - overlap)
    for s in range(0, len(words), step):
        piece = " ".join(words[s:s + size])
        if piece:
            chunks.append(piece)
        if s + size >= len(words):
            break
    return chunks


def _old_st(text, size=320, overlap=48):
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step = max(1, size - overlap)
    out = []
    for s in range(0, len(words), step):
        out.append(" ".join(words[s:s + size]))
        if s + size >= len(words):
            break
    return out


BATTERY = [
    "", "   ", "one", "alpha beta gamma delta",
    " ".join(str(i) for i in range(1000)), "a\tb\nc  d", "x " * 500,
    "café " * 30 + "münchen", "\x1c\x1d sep \x1e\x1f text", "  pad  ",
]


class TestChunkersByteExact(unittest.TestCase):
    def test_run_default_and_sizes(self):
        for t in BATTERY:
            self.assertEqual(run._chunk(t), _old_run(t), repr(t))
            for sz in (400, 420, 100, 1, 1000):
                self.assertEqual(run._chunk(t, sz), _old_run(t, sz), (t, sz))

    def test_jarvis_default_and_presets(self):
        for t in BATTERY:
            self.assertEqual(jv.chunk_text(t), _old_jv(t), repr(t))
            for sz, ov in [(450, 70), (420, 70), (100, 20), (50, 49), (10, 0)]:
                self.assertEqual(jv.chunk_text(t, sz, ov), _old_jv(t, sz, ov), (t, sz, ov))

    def test_substrate_text_default_and_presets(self):
        for t in BATTERY:
            self.assertEqual(st._chunk_text(t), _old_st(t), repr(t))
            for sz, ov in [(320, 48), (420, 70), (100, 20), (50, 49)]:
                self.assertEqual(st._chunk_text(t, sz, ov), _old_st(t, sz, ov), (t, sz, ov))

    def test_overlap_ge_size_tolerated_not_raised(self):
        # The legacy step=max(1,size-overlap) tolerated overlap>=size; the wrappers
        # clamp to size-1 to reproduce it rather than hit the canonical's ValueError.
        self.assertEqual(jv.chunk_text("w " * 200, 100, 150), _old_jv("w " * 200, 100, 150))
        self.assertEqual(st._chunk_text("w " * 120, 50, 80), _old_st("w " * 120, 50, 80))


if __name__ == "__main__":
    unittest.main()
