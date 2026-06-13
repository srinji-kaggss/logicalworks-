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


if __name__ == "__main__":
    unittest.main()
