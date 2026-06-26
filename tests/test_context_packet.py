"""Tests for lgwks.context.packet.v1 (#122 — the shared subconscious briefing).

Promotes lgwks.daemon.packet.v0 → v1. Maps to the issue's acceptance bullets:
  1. schema exists and is registered (and validates);
  2. at least one adapter can consume the packet shape;
  3. packet generation is deterministic under fixed store state.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lgwks_daemon_event as de
from lgwks_daemon_store import (
    DaemonEventStore,
    PACKET_SCHEMA,
    CONTEXT_PACKET_SECTIONS,
    validate_context_packet,
)

TENANT = "repo:demo"


def _store() -> tuple[DaemonEventStore, Path]:
    db = Path(tempfile.mkdtemp(prefix="pkt_")) / "daemon-events.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return DaemonEventStore(db), db


def _append(store, *, kind="human_message", source="text", trust="human_confirmed", ts, payload=None):
    store.append(de.build_event(
        tenant_id=TENANT, agent_id="claude", session_id="s1",
        actor="human", client="claude", lane="ingress",
        kind=kind, scope="agent_local", payload=payload or {"prompt_head": "hello"},
        source=source, trust=trust, ts=ts,
    ))


class TestContextPacket(unittest.TestCase):
    def setUp(self):
        self.store, self.db = _store()
        _append(self.store, ts="2026-06-13T10:00:00+00:00")

    def tearDown(self):
        self.store.close()

    def test_schema_is_v1(self):
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        self.assertEqual(pkt["schema"], "lgwks.context.packet.v1")
        self.assertEqual(pkt["schema"], PACKET_SCHEMA)

    def test_locked_section_set_always_present(self):
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        for section in CONTEXT_PACKET_SECTIONS:
            self.assertIn(section, pkt, f"missing locked section {section}")
        validate_context_packet(pkt)  # passes even though several sections are empty

    def test_v0_core_preserved(self):
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        self.assertEqual(pkt["event_count"], 1)
        self.assertEqual(len(pkt["recent_events"]), 1)
        self.assertIn("queue", pkt)

    def test_provenance_watermark(self):
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        newest = pkt["recent_events"][0]["event_id"]
        self.assertEqual(pkt["provenance"]["watermark_event_id"], newest)

    def test_known_failures_derived(self):
        _append(self.store, kind="terminal_output", source="terminal", trust="deterministic",
                ts="2026-06-13T10:05:00+00:00", payload={"test_failed": True})
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        self.assertTrue(pkt["known_failures"])
        self.assertTrue(all("event_id" in f for f in pkt["known_failures"]))

    def test_active_task_matches_watermark(self):
        # Harden: active_task.head must equal provenance.watermark_event_id, even
        # with two events sharing a timestamp (deterministic, not append-order).
        _append(self.store, kind="tool_call", source="model", trust="model_proposed",
                ts="2026-06-13T10:00:00+00:00", payload={"k": 1})  # equal ts to setUp event
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        self.assertEqual(pkt["active_task"]["head_event_id"], pkt["provenance"]["watermark_event_id"])
        self.assertEqual(pkt["active_task"]["head_event_id"], pkt["recent_events"][0]["event_id"])

    def test_provider_cannot_mutate_packet(self):
        # Harden: a provider that mutates the events list must not corrupt the packet.
        def evil(t, s, ev):
            ev.clear()
            return [{"cid": "b2b256:xx"}]
        pkt = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude",
                                    retrieval_provider=evil)
        self.assertEqual(pkt["event_count"], 1)  # not zeroed by the provider
        self.assertEqual(len(pkt["recent_events"]), 1)

    def test_deterministic_under_fixed_state(self):
        p1 = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        p2 = self.store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        self.assertEqual(p1, p2)

    def test_providers_fill_dependent_sections(self):
        # #124 retrieval + #120 allowed_capabilities are provider-fed; default empty.
        pkt = self.store.get_packet(
            tenant_id=TENANT, session_id="s1", agent_id="claude",
            retrieval_provider=lambda t, s, ev: [{"cid": "b2b256:ab", "score": 1.0}],
            capability_provider=lambda t, a: ["review", "codebase index"],
        )
        self.assertEqual(pkt["retrieval"], [{"cid": "b2b256:ab", "score": 1.0}])
        self.assertEqual(pkt["allowed_capabilities"], ["review", "codebase index"])
        validate_context_packet(pkt)


class TestAdapterConsumes(unittest.TestCase):
    """Acceptance 2: an adapter consumes the v1 packet shape end-to-end."""

    def test_codex_style_adapter_reads_all_sections(self):
        store, _ = _store()
        try:
            _append(store, ts="2026-06-13T10:00:00+00:00")
            pkt = store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
        finally:
            store.close()

        # A minimal agent adapter: validate, then read every locked section into a
        # briefing. The same shape serves a human cockpit and any agent adapter.
        def adapter_consume(packet: dict) -> dict:
            validate_context_packet(packet)
            return {
                "task": packet["active_task"],
                "events": packet["event_count"],
                "hits": len(packet["retrieval"]),
                "failures": len(packet["known_failures"]),
                "capabilities": list(packet["allowed_capabilities"]),
                "watermark": packet["provenance"]["watermark_event_id"],
            }

        briefing = adapter_consume(pkt)
        self.assertEqual(briefing["events"], 1)
        self.assertIsNotNone(briefing["watermark"])


class TestPulseAffordanceHardening(unittest.TestCase):
    """The packet next_steps is a PULSE affordance set: each step carries speech-act
    modes, policy-derived approval, execution semantics, and — PULSE P5 — a
    machine-readable repair (next legal move) when blocked. Locks the #pulse-okf
    hardening so it cannot silently regress to a bare 'preconditions_met' bool."""

    def test_next_steps_is_a_locked_packet_section(self):
        self.assertIn("next_steps", CONTEXT_PACKET_SECTIONS)

    def test_approval_derives_from_policy_not_effect_class_alone(self):
        from lgwks_daemon_store import next_steps
        by = {s["kind"]: s for s in next_steps([])}
        # high-risk escape hatch force-gates; low-risk reversible network op is open;
        # medium-risk write needs one approval — proves approval reads policy+semantics.
        self.assertEqual(by["custom"]["approval"], "force")
        self.assertEqual(by["research_run"]["approval"], "none")
        self.assertEqual(by["workflow"]["approval"], "once")

    def test_p5_blocked_affordance_emits_next_legal_move(self):
        from lgwks_daemon_store import next_steps
        # index_run is blocked with no run to index — it must point to research_run,
        # not dead-end. (PULSE P5: every failure yields the next legal move.)
        by = {s["kind"]: s for s in next_steps([])}
        self.assertFalse(by["index_run"]["preconditions_met"])
        self.assertIn("has_unindexed_run", by["index_run"]["blocked_by"])
        self.assertTrue(any("research_run" in r for r in by["index_run"]["repair"]))

    def test_p5_repair_follows_state_affordance_graph(self):
        from lgwks_daemon_store import next_steps
        # With a worktree open, worktree_open blocks and its repair is worktree_close.
        ev = [{"kind": "worktree_open", "payload": {"kind": "worktree_open"}}]
        by = {s["kind"]: s for s in next_steps(ev)}
        self.assertFalse(by["worktree_open"]["preconditions_met"])
        self.assertTrue(any("worktree_close" in r for r in by["worktree_open"]["repair"]))

    def test_affordance_carries_speech_act_and_semantics(self):
        from lgwks_daemon_store import next_steps
        step = next(s for s in next_steps([]) if s["kind"] == "research_run")
        self.assertIn(step["mode"], ("ask", "do"))
        for key in ("side_effect", "reversible", "idempotent", "retry_safe"):
            self.assertIn(key, step["semantics"])


class TestTelemetryIsRealNotFabricated(unittest.TestCase):
    """The flight-display metrics must be REAL, calculator-reconstructable values —
    no payload-size proxies, no magic constants, no fabricated defaults (#323 harden)."""

    def test_entropy_history_is_real_shannon_over_kinds(self):
        from lgwks_daemon_store import _compute_entropy_history
        # All one kind → zero entropy at every point.
        same = [{"kind": "ping"} for _ in range(8)]
        self.assertTrue(all(v == 0 for v in _compute_entropy_history(same)))
        # A balanced mix of distinct kinds → high entropy in the trailing window.
        mixed = [{"kind": f"k{i % 4}"} for i in range(20)]
        self.assertGreaterEqual(max(_compute_entropy_history(mixed)), 90)
        # Empty → a single honest zero, never a crash.
        self.assertEqual(_compute_entropy_history([]), [0])

    def test_tps_is_real_and_honest_zero_when_unknown(self):
        from lgwks_daemon_store import _compute_tps
        evs = [{"ts": f"2026-06-26T00:00:{s:02d}Z"} for s in range(0, 10)]  # 10 ev / 9s
        self.assertAlmostEqual(_compute_tps(evs), round(10 / 9, 1))
        self.assertEqual(_compute_tps([{"ts": "2026-06-26T00:00:00Z"}]), 0.0)  # <2 → 0
        self.assertEqual(_compute_tps([{}, {}]), 0.0)  # no timestamps → honest 0, not 1.0

    def test_telemetry_has_no_fabricated_latency(self):
        from lgwks_daemon_store import _compute_telemetry
        evs = [{"event_id": "e2", "kind": "tool_call", "ts": "2026-06-26T00:00:01Z",
                "payload": {"a": 1}},
               {"event_id": "e1", "kind": "human_message", "ts": "2026-06-26T00:00:00Z",
                "payload": {"b": 2}}]  # newest-first
        rows = _compute_telemetry(evs)
        self.assertTrue(rows)
        for r in rows:
            self.assertNotIn("latency_ms", r)               # the fabricated metric is gone
            self.assertIsInstance(r["payload_bytes"], int)  # real serialized size
            self.assertIn("gap_ms", r)                      # real inter-event timing (or None)

    def test_steering_dials_not_hardcoded_fakes(self):
        store, _ = _store()
        try:
            _append(store, ts="2026-06-26T00:00:00+00:00")
            pkt = store.get_packet(tenant_id=TENANT, session_id="s1", agent_id="claude")
            # No fabricated Safety/Creativity/Accuracy constants; honest empty until
            # wired to a real steering signal.
            self.assertEqual(pkt["steering_dials"], [])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
