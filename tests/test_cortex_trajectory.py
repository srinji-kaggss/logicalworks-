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

    def test_content_recorded_verbatim_not_spell_corrected(self):
        # Ground-truth fidelity (#180): a near-primitive typo ("gxt" is Levenshtein-1
        # from "git") must be tokenized EXACTLY as typed — the tape records what
        # actually happened, not a "corrected" rewrite that desyncs state from
        # consequence. (The old _smart_correct path would have rewritten this.)
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            traj = tk.tokenize_trajectory({"content": "gxt statuz", "entities": []})
            beg, end = tk.vocab["[BEG]"], tk.vocab["[END]"]
            body = traj.tokens[traj.tokens.index(beg) + 1:traj.tokens.index(end)]
            self.assertEqual(bytes(body).decode("utf-8"), "gxt statuz")

    def test_truncation_is_recorded_not_silent(self):
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            short = tk.tokenize_trajectory({"content": "ok", "entities": []})
            self.assertFalse(short.metadata["content_truncated"])
            self.assertEqual(short.metadata["content_chars"], 2)
            big = tk.tokenize_trajectory({"content": "x" * 5000, "entities": []})
            self.assertTrue(big.metadata["content_truncated"])
            self.assertEqual(big.metadata["content_chars"], 5000)
            beg, end = tk.vocab["[BEG]"], tk.vocab["[END]"]
            body = big.tokens[big.tokens.index(beg) + 1:big.tokens.index(end)]
            self.assertEqual(len(body), atok._MAX_CONTENT_CHARS)

    def test_encode_modality_tolerates_bad_hash(self):
        # A malformed upstream hash must not crash the encoder (cortex would
        # swallow the exception into an empty token stream, silently dropping the
        # turn). Bad hash -> anchor token only.
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            self.assertEqual(tk.encode_modality("IMG", "zz"), [tk.vocab["[IMG]"]])
            self.assertEqual(tk.encode_modality("IMG", ""), [tk.vocab["[IMG]"]])
            good = tk.encode_modality("IMG", "deadbeefcafe")
            self.assertEqual(good[0], tk.vocab["[IMG]"])
            self.assertEqual(good[1:], [0xde, 0xad, 0xbe, 0xef])

    def test_smart_correct_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            # Same input -> same correction, regardless of set iteration order.
            self.assertEqual(tk._smart_correct("gxt"), tk._smart_correct("gxt"))
            self.assertEqual(tk._smart_correct("gxt"), "git")


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


class TestCortexIdempotencyAndAutonomousCapture(unittest.TestCase):
    """The daemon (not a hook) is the core capture path: it must be able to
    re-process a growing transcript without duplicating training turns."""

    def _write(self, path: Path, turns: list[dict]) -> None:
        import json
        path.write_text("\n".join(json.dumps(t) for t in turns) + "\n", encoding="utf-8")

    def test_reprocessing_is_idempotent(self):
        import lgwks_cortex
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "s.jsonl"
            self._write(transcript, [
                {"turn_id": "t1", "role": "user", "content": "map the repo"},
                {"turn_id": "t2", "role": "assistant", "content": "done"},
            ])
            cortex = lgwks_cortex.TranscriptCortex(root)
            first = cortex.process_transcript(transcript, "sess", n=0)
            self.assertEqual(len(first), 2)
            # Re-run on the same transcript: every turn already seen -> 0 new.
            again = cortex.process_transcript(transcript, "sess", n=0)
            self.assertEqual(len(again), 0)
            out = root / "store" / "cortex" / "sess.cortex.jsonl"
            self.assertEqual(sum(1 for _ in out.open()), 2)  # no duplicate lines

    def test_growing_transcript_appends_only_new_turns(self):
        import lgwks_cortex
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "s.jsonl"
            self._write(transcript, [{"turn_id": "t1", "role": "user", "content": "first"}])
            cortex = lgwks_cortex.TranscriptCortex(root)
            cortex.process_transcript(transcript, "sess", n=0)
            self._write(transcript, [
                {"turn_id": "t1", "role": "user", "content": "first"},
                {"turn_id": "t2", "role": "assistant", "content": "second"},
            ])
            new = cortex.process_transcript(transcript, "sess", n=0)
            self.assertEqual([t.turn_id for t in new], ["t2"])

    def test_daemon_autonomous_capture_and_subagent_refusal(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "live.jsonl"
            self._write(transcript, [{"turn_id": "t1", "role": "user", "content": "hello"}])
            d = lgwks_daemon.SessionDaemon(root)
            # Autonomous pass builds the trajectory, no hook involved.
            m1 = d._maybe_process_cortex(str(transcript), 0.0)
            self.assertGreater(m1, 0.0)
            self.assertTrue((root / "store" / "cortex" / "live.cortex.jsonl").exists())
            # Unchanged mtime -> skipped (watermark unchanged).
            self.assertEqual(d._maybe_process_cortex(str(transcript), m1), m1)
            # Subagent transcript -> refused (stale-session guard, #227 F3).
            self.assertEqual(d._maybe_process_cortex("/x/subagents/a.jsonl", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
