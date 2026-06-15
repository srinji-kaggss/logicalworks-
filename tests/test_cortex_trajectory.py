"""Tests for the training-data path: ANT byte-level tokenization + cortex
trajectory emission onto the State Fabric.

ANT (lgwks_tokenizer) must produce a clean integer stream, and the Transcript
Cortex must persist that stream as a tokenized artifact through the gate (so the
Causal Tape + TokenIndex become the replayable training corpus) instead of
discarding it.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_storage
import lgwks_tokenizer as atok


class TestAetheriusTokenizerByteLevel(unittest.TestCase):
    def _tok(self, root: Path) -> atok.AetheriusTokenizer:
        return atok.AetheriusTokenizer(root)

    def test_content_is_byte_level_not_codepoint(self):
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            # An em-dash (codepoint 8212) must NOT appear as token 8212 (which
            # would collide with the entity range); it must decompose to UTF-8
            # bytes, all in 0-255.
            traj = tk.tokenize_trajectory({"content": "a—b", "entities": []})
            beg, end = tk.vocab["[BEG]"], tk.vocab["[END]"]
            content_tokens = traj.tokens[traj.tokens.index(beg) + 1:traj.tokens.index(end)]
            self.assertTrue(all(0 <= t <= 255 for t in content_tokens))
            self.assertNotIn(8212, content_tokens)
            self.assertEqual(bytes(content_tokens).decode("utf-8"), "a—b")

    def test_entity_tokens_use_full_hash_no_modulo(self):
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            traj = tk.tokenize_trajectory({"content": "", "entities": ["lgwks_storage.py"]})
            ent = [t for t in traj.tokens if t >= atok.ENTITY_TOKEN_BASE]
            self.assertEqual(len(ent), 1)
            # Deterministic + in the disjoint entity range.
            self.assertGreaterEqual(ent[0], atok.ENTITY_TOKEN_BASE)
            traj2 = tk.tokenize_trajectory({"content": "", "entities": ["lgwks_storage.py"]})
            self.assertEqual(traj.tokens, traj2.tokens)


class TestCortexTrajectoryEmission(unittest.TestCase):
    def test_turns_persist_as_tokenized_artifacts(self):
        import json

        import lgwks_cortex

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Minimal transcript: two assistant turns with content + an entity.
            transcript = root / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    json.dumps(t)
                    for t in [
                        {"turn_id": "t1", "role": "assistant", "content": "edit lgwks_storage.py now"},
                        {"turn_id": "t2", "role": "user", "content": "run the tests"},
                    ]
                ),
                encoding="utf-8",
            )

            gate = lgwks_storage.StorageGate(root / "fabric", tenant_id="session-x")
            try:
                cortex = lgwks_cortex.TranscriptCortex(root)
                turns = cortex.process_transcript(transcript, "session-x", gate=gate)
                self.assertEqual(len(turns), 2)

                # Each turn left a tokenized artifact in the TokenIndex under the
                # Aetherius tokenizer — i.e. the trajectory tokens persisted.
                aet = gate.tokenizers.default_aetherius_id()
                # The first turn mentions an entity + content, so it must have tokens.
                postings = []
                for q in range(256, 512):  # core/control tokens always present ([TRN],[BEG],[END])
                    postings.extend(gate.token_index.query_token(aet, q))
                self.assertTrue(postings, "expected ANT control tokens indexed for trajectories")
            finally:
                gate.close()


if __name__ == "__main__":
    unittest.main()
