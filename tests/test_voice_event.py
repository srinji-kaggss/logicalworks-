"""Tests for lgwks.voice.event.v1 (#123 — speech ingress, never a gate bypass).

Maps to the issue's acceptance bullets:
  1. the schema supports streaming AND file-based ASR outputs;
  2. a voice event adapts into the #118 daemon envelope (source:speech);
  3. normalized text keeps a pointer to the raw transcript (raw is never lost).
"""

from __future__ import annotations

import unittest

from axiom.cid import verify_cid

import lgwks_daemon_event as de
import lgwks_voice_event as ve


class TestStreamingAndFile(unittest.TestCase):
    """Acceptance 1: streaming and file ASR fixtures both validate."""

    def test_streaming_interim_and_final(self):
        interim = ve.build_voice_event(
            raw_text="refactor the dae",
            audio_source={"kind": "stream", "sample_rate": 16000, "codec": "pcm16"},
            transcript_span={"start_ms": 0, "end_ms": 800},
            confidence=0.6, final=False,
        )
        final = ve.build_voice_event(
            raw_text="refactor the daemon query surface",
            audio_source={"kind": "stream", "sample_rate": 16000, "codec": "pcm16"},
            transcript_span={"start_ms": 0, "end_ms": 2400},
            confidence=0.95, final=True,
        )
        self.assertFalse(interim["final"])
        self.assertTrue(final["final"])

    def test_file_source(self):
        evt = ve.build_voice_event(
            raw_text="open the handoff doc",
            audio_source={"kind": "file", "path": "/tmp/clip.wav", "codec": "wav"},
        )
        self.assertEqual(evt["audio_source"]["kind"], "file")
        ve.validate_voice_event(evt)

    def test_bad_audio_kind_rejected(self):
        with self.assertRaises(ValueError):
            ve.build_voice_event(raw_text="x", audio_source={"kind": "telepathy"})

    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            ve.build_voice_event(raw_text="x", audio_source={"kind": "mic"}, confidence=2.0)


class TestAdaptsToDaemonEvent(unittest.TestCase):
    """Acceptance 2: voice event lowers into a valid #118 v2 envelope."""

    def test_lowers_to_speech_untrusted_event(self):
        voice = ve.build_voice_event(
            raw_text="ship it to prod now",
            audio_source={"kind": "mic"},
            confidence=0.9,
        )
        event = ve.to_daemon_event(
            voice, tenant_id="repo:demo", agent_id="claude", session_id="s1",
        )
        # The event must validate under the #118 v2 contract.
        de.validate_event(event)
        self.assertEqual(event["source"], "speech")
        self.assertEqual(event["trust"], "untrusted")  # voice can never arrive pre-trusted
        self.assertEqual(event["kind"], "transcript_turn")
        self.assertEqual(event["actor"], "human")
        # provenance points back to the raw transcript; raw is referenced by CID.
        self.assertEqual(event["provenance"]["derived_from"], [voice["raw_ref"]])
        self.assertTrue(event["payload_cid"].startswith("b2b256:"))


class TestRawPointerHolds(unittest.TestCase):
    """Acceptance 3: normalized text keeps a verifiable pointer to raw; raw is immutable."""

    def test_raw_ref_resolves_to_raw_text(self):
        raw = "their, was, weird ASR output"
        cleaned = "There was weird ASR output."
        voice = ve.build_voice_event(
            raw_text=raw, normalized_text=cleaned, audio_source={"kind": "mic"},
        )
        # normalized differs from raw, but raw is preserved verbatim...
        self.assertEqual(voice["raw_text"], raw)
        self.assertEqual(voice["normalized_text"], cleaned)
        self.assertTrue(voice["cleanup_provenance"]["changed"])
        # ...and raw_ref resolves to the EXACT raw transcript bytes.
        cid = voice["raw_ref"][len("raw:"):]
        self.assertTrue(verify_cid(raw.encode("utf-8"), cid))

    def test_passthrough_when_no_cleanup(self):
        voice = ve.build_voice_event(raw_text="already clean.", audio_source={"kind": "mic"})
        self.assertEqual(voice["normalized_text"], voice["raw_text"])
        self.assertFalse(voice["cleanup_provenance"]["changed"])
        self.assertEqual(voice["cleanup_provenance"]["method"], "passthrough")
        self.assertIsNone(voice["cleanup_provenance"]["model"])  # ASR/cleanup model is an open slot

    def test_tampered_raw_ref_rejected(self):
        voice = ve.build_voice_event(raw_text="genuine", audio_source={"kind": "mic"})
        voice["raw_text"] = "tampered after the fact"  # break raw integrity
        with self.assertRaises(ValueError):
            ve.validate_voice_event(voice)


if __name__ == "__main__":
    unittest.main()
