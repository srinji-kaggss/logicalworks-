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

    def test_distinct_entities_get_distinct_token_ids(self):
        # #293 acceptance: injectivity. A token collision = a false posting in the
        # TokenIndex (an entity query returns the wrong artifact). Map a corpus of
        # distinct entities and assert no two share an id. 4000 names sits far below
        # the 56-bit birthday point (~2^28), so this is a hard guarantee, not luck —
        # at the old 4-byte width the same corpus already risked a collision.
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            names = [f"entity_{i}_{i*7 % 13}.py" for i in range(4000)]
            ids = []
            for name in names:
                traj = tk.tokenize_trajectory({"content": "", "entities": [name]})
                ent = [t for t in traj.tokens if t >= atok.ENTITY_TOKEN_BASE]
                self.assertEqual(len(ent), 1)
                ids.append(ent[0])
            self.assertEqual(len(set(ids)), len(names), "distinct entities collided on a token id")

    def test_entity_token_stays_within_integer_column_ceiling(self):
        # The TokenIndex.token column is a SQLite signed INTEGER (max 2^63-1).
        # Guards the ENTITY_HASH_BYTES width: an 8-byte hash would overflow it.
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            ceiling = 2 ** 63 - 1
            for name in ("a", "z" * 200, "lgwks_storage.py", "—unicode—name—"):
                traj = tk.tokenize_trajectory({"content": "", "entities": [name]})
                ent = [t for t in traj.tokens if t >= atok.ENTITY_TOKEN_BASE]
                self.assertTrue(all(t <= ceiling for t in ent), f"entity token overflows INTEGER: {name}")

    def test_byte_roundtrip_for_all_content_under_256(self):
        # #293 acceptance: round-trip byte fidelity for content < 256. Every byte
        # value 0..255 that survives UTF-8 round-trips through the content tokens.
        with tempfile.TemporaryDirectory() as td:
            tk = self._tok(Path(td))
            text = "".join(chr(c) for c in range(1, 128)) + "café—naïve—Ω"
            traj = tk.tokenize_trajectory({"content": text, "entities": []})
            beg, end = tk.vocab["[BEG]"], tk.vocab["[END]"]
            body = traj.tokens[traj.tokens.index(beg) + 1:traj.tokens.index(end)]
            self.assertTrue(all(0 <= t <= 255 for t in body))
            self.assertEqual(bytes(body).decode("utf-8"), text)

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


class TestTranscriptSelfDiscovery(unittest.TestCase):
    """The daemon must find the live session on its own — no hook, no correct
    env binding. This is the fix for the zero-capture failure: a daemon pinned
    at startup to a dead subagent transcript tailed a corpse forever."""

    def _mk_projects(self, td: Path):
        """A fake ~/.claude/projects layout: top-level transcripts + a subagent
        transcript nested under <session>/subagents/ (which must be ignored)."""
        import json
        import os
        proj_a = td / "projects" / "-Users-x-repo"
        proj_b = td / "projects" / "-Users-x"
        (proj_a / "old-sess" / "subagents").mkdir(parents=True)
        proj_b.mkdir(parents=True)
        line = json.dumps({"turn_id": "t1", "role": "user", "content": "hi"}) + "\n"
        old = proj_a / "old.jsonl"; old.write_text(line)
        fresh = proj_b / "fresh.jsonl"; fresh.write_text(line)
        sub = proj_a / "old-sess" / "subagents" / "agent-1.jsonl"; sub.write_text(line)
        # Deterministic mtimes (no wall-clock dependence): old is ancient,
        # fresh + subagent sit at t=2000.
        os.utime(old, (1000, 1000))
        os.utime(fresh, (2000, 2000))
        os.utime(sub, (2000, 2000))
        return td / "projects", fresh, sub

    def test_picks_freshest_nonsubagent_transcript(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            projects, fresh, _sub = self._mk_projects(Path(td))
            got = lgwks_daemon.discover_live_transcript(
                projects, now=2000.0, max_age_s=3600.0
            )
            self.assertEqual(got, str(fresh))

    def test_subagent_transcripts_are_never_discovered(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            projects, _fresh, sub = self._mk_projects(Path(td))
            got = lgwks_daemon.discover_live_transcript(
                projects, now=2000.0, max_age_s=3600.0
            )
            self.assertNotEqual(got, str(sub))
            self.assertNotIn("/subagents/", got or "")

    def test_idle_sessions_beyond_window_are_not_live(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            projects, _fresh, _sub = self._mk_projects(Path(td))
            # window so tight even "fresh" (now=2000) is excluded
            got = lgwks_daemon.discover_live_transcript(
                projects, now=1_000_000.0, max_age_s=10.0
            )
            self.assertIsNone(got)

    def test_resolver_drops_dead_binding_and_discovers(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            projects, fresh, _sub = self._mk_projects(Path(td))
            import os
            os.environ["LGWKS_CLAUDE_PROJECTS_DIR"] = str(projects)
            try:
                d = lgwks_daemon.SessionDaemon(Path(td))
                # bound to a dead subagent transcript -> must fall through
                target = d._resolve_capture_target(
                    "/p/x/subagents/agent.jsonl", now=2000.0
                )
                self.assertEqual(target, str(fresh))
            finally:
                os.environ.pop("LGWKS_CLAUDE_PROJECTS_DIR", None)

    def test_resolver_honours_a_live_explicit_pin(self):
        import lgwks_daemon
        import time
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pinned = root / "pinned.jsonl"
            pinned.write_text("{}\n")
            d = lgwks_daemon.SessionDaemon(root)
            # a real, fresh, non-subagent pin wins over discovery
            target = d._resolve_capture_target(str(pinned), now=time.time())
            self.assertEqual(target, str(pinned))


class TestCortexBoundedDrain(unittest.TestCase):
    """#247: a long backlog must not be tokenized in one synchronous pass that
    blocks the daemon loop (and SIGTERM). `limit` bounds new turns per call and
    idempotency drains the rest across calls."""

    def _write(self, path: Path, n: int) -> None:
        import json
        path.write_text(
            "\n".join(json.dumps({"turn_id": f"t{i}", "role": "user", "content": f"turn {i}"})
                      for i in range(n)) + "\n",
            encoding="utf-8",
        )

    def test_limit_bounds_new_turns_and_idempotency_drains_remainder(self):
        import lgwks_cortex
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "s.jsonl"
            self._write(transcript, 5)
            cortex = lgwks_cortex.TranscriptCortex(root)
            out = root / "store" / "cortex" / "sess.cortex.jsonl"

            first = cortex.process_transcript(transcript, "sess", n=0, limit=2)
            self.assertEqual([t.turn_id for t in first], ["t0", "t1"])
            self.assertEqual(sum(1 for _ in out.open()), 2)

            second = cortex.process_transcript(transcript, "sess", n=0, limit=2)
            self.assertEqual([t.turn_id for t in second], ["t2", "t3"])

            third = cortex.process_transcript(transcript, "sess", n=0, limit=2)
            self.assertEqual([t.turn_id for t in third], ["t4"])  # < cap -> drained
            self.assertEqual(sum(1 for _ in out.open()), 5)  # all 5, no dupes

    def test_daemon_holds_watermark_until_backlog_drained(self):
        import lgwks_daemon
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "live.jsonl"
            self._write(transcript, 5)
            d = lgwks_daemon.SessionDaemon(root)
            out = root / "store" / "cortex" / "live.cortex.jsonl"

            orig = lgwks_daemon.CORTEX_MAX_TURNS_PER_TICK
            lgwks_daemon.CORTEX_MAX_TURNS_PER_TICK = 2
            try:
                # Tick 1: cap hit -> watermark HELD at 0.0 so next tick resumes.
                wm = d._maybe_process_cortex(str(transcript), 0.0)
                self.assertEqual(wm, 0.0)
                self.assertEqual(sum(1 for _ in out.open()), 2)
                # Tick 2: still capped, still held.
                wm = d._maybe_process_cortex(str(transcript), wm)
                self.assertEqual(wm, 0.0)
                self.assertEqual(sum(1 for _ in out.open()), 4)
                # Tick 3: backlog drained (< cap) -> watermark ADVANCES to mtime.
                wm = d._maybe_process_cortex(str(transcript), wm)
                self.assertGreater(wm, 0.0)
                self.assertEqual(sum(1 for _ in out.open()), 5)
                # Tick 4: unchanged file -> skipped (steady state).
                self.assertEqual(d._maybe_process_cortex(str(transcript), wm), wm)
            finally:
                lgwks_daemon.CORTEX_MAX_TURNS_PER_TICK = orig


class TestCortexDropObservability(unittest.TestCase):
    """A pipeline whose PRODUCT is the data must never drop a trajectory
    silently. Emit failures are COUNTED (and logged), not swallowed."""

    class _FailGate:
        class _Tok:
            def default_aetherius_id(self):
                return "aet:test"
        tokenizers = _Tok()

        def ingest_artifact(self, _artifact):
            raise RuntimeError("simulated tape append failure")

        def close(self):
            pass

    def test_emit_failures_are_counted_not_swallowed(self):
        import io
        import json
        from contextlib import redirect_stderr

        import lgwks_cortex
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            transcript = root / "s.jsonl"
            transcript.write_text(
                "\n".join(json.dumps(t) for t in [
                    {"turn_id": "t1", "role": "user", "content": "a"},
                    {"turn_id": "t2", "role": "assistant", "content": "b"},
                ]) + "\n",
                encoding="utf-8",
            )
            cortex = lgwks_cortex.TranscriptCortex(root)
            buf = io.StringIO()
            with redirect_stderr(buf):
                turns = cortex.process_transcript(
                    transcript, "sess", gate=self._FailGate()
                )
            # Processing still completes (best-effort), but every drop is visible.
            self.assertEqual(len(turns), 2)
            self.assertEqual(cortex.emit_failures, 2)
            self.assertEqual(cortex.emit_ok, 0)
            err = buf.getvalue()
            self.assertIn("trajectory_emit_failed", err)
            self.assertIn("lgwks.cortex.drop.v1", err)


if __name__ == "__main__":
    unittest.main()
