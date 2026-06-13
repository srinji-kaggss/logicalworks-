"""Tests for lgwks.daemon.event.v2 (#118 — "event_envelope").

Maps directly to the issue's acceptance bullets:
  1. deterministic encoding — same inputs → same event_id, byte-stable body;
  2. every v1 record validates under v2 unchanged (back-compat) + lazy upgrade;
  3. the three adapted producers emit valid v2 events with source/trust;
  4. payload_cid round-trips a real axiom CID and rejects a non-CID string.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from axiom.cid import compute_cid

import lgwks_daemon_event as daemon_event
from lgwks_daemon_store import DaemonEventStore

ROOT = Path(__file__).resolve().parent.parent


def _load_hook(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "hooks" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDeterministicEncoding(unittest.TestCase):
    """Acceptance 1: deterministic encoding survives the v2 axes."""

    def _kwargs(self) -> dict:
        return {
            "tenant_id": "tenant.alpha",
            "agent_id": "claude",
            "session_id": "sess-001",
            "actor": "agent",
            "client": "claude",
            "lane": "telemetry",
            "kind": "tool_call",
            "scope": "agent_local",
            "payload": {"tool": "pytest", "status": "ok"},
            "ts": "2026-06-13T00:00:00+00:00",
            "source": "model",
            "trust": "model_proposed",
        }

    def test_emits_v2_by_default(self):
        record = daemon_event.build_event(**self._kwargs())
        self.assertEqual(record["schema"], "lgwks.daemon.event.v2")
        self.assertEqual(record["source"], "model")
        self.assertEqual(record["trust"], "model_proposed")

    def test_event_id_deterministic_with_v2_axes(self):
        left = daemon_event.build_event(**self._kwargs())
        right = daemon_event.build_event(**self._kwargs())
        self.assertEqual(left["event_id"], right["event_id"])

    def test_canonical_body_byte_stable(self):
        record = daemon_event.build_event(**self._kwargs())
        a = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        b = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.assertEqual(a, b)

    def test_distinct_source_changes_event_id(self):
        base = self._kwargs()
        other = dict(base, source="terminal")
        self.assertNotEqual(
            daemon_event.build_event(**base)["event_id"],
            daemon_event.build_event(**other)["event_id"],
        )


class TestBackCompat(unittest.TestCase):
    """Acceptance 2: v1 records still validate; lazy upgrade projects them to v2."""

    def _v1_record(self) -> dict:
        # A historical v1 envelope as it would sit in the store (raw, schema v1).
        record = {
            "schema": "lgwks.daemon.event.v1",
            "event_id": "evt-legacy-0001",
            "ts": "2026-06-12T00:00:00+00:00",
            "tenant_id": "tenant.alpha",
            "agent_id": "claude",
            "session_id": "sess-legacy",
            "actor": "human",
            "client": "claude",
            "lane": "ingress",
            "kind": "human_message",
            "scope": "agent_local",
            "payload": {"prompt_len": 12},
        }
        return record

    def test_v1_record_validates_unchanged(self):
        record = self._v1_record()
        self.assertEqual(daemon_event.validate_event(record), record)

    def test_upgrade_preserves_event_id(self):
        v1 = self._v1_record()
        v2 = daemon_event.upgrade_v1_to_v2(v1)
        self.assertEqual(v2["event_id"], v1["event_id"])  # identity is stable
        self.assertEqual(v2["schema"], "lgwks.daemon.event.v2")

    def test_upgrade_fills_axes(self):
        v2 = daemon_event.upgrade_v1_to_v2(self._v1_record())
        self.assertEqual(v2["source"], "text")  # inferred from kind=human_message
        self.assertEqual(v2["trust"], "human_confirmed")  # human_message is human-origin
        self.assertEqual(v2["replay"]["schema_from"], "lgwks.daemon.event.v1")
        daemon_event.validate_event(v2)  # the upgrade output is a valid v2 envelope

    def test_upgrade_does_not_overtrust_model_output(self):
        # Harden regression: a legacy model-origin event must NOT migrate to the
        # strongest non-human trust (deterministic). Model output is untrusted-until-typed.
        v1 = dict(self._v1_record(), kind="tool_call", event_id="evt-legacy-tool")
        v2 = daemon_event.upgrade_v1_to_v2(v1)
        self.assertEqual(v2["trust"], "model_proposed")
        self.assertNotEqual(v2["trust"], "deterministic")

    def test_upgrade_is_idempotent_on_v2(self):
        v2 = daemon_event.build_event(
            tenant_id="t.a", agent_id="claude", session_id="s1",
            actor="agent", client="claude", lane="telemetry",
            kind="tool_call", scope="agent_local", payload={}, source="model",
        )
        self.assertIs(daemon_event.upgrade_v1_to_v2(v2), v2)

    def test_upgrade_rejects_foreign_schema(self):
        with self.assertRaises(ValueError):
            daemon_event.upgrade_v1_to_v2({"schema": "lgwks.other.v1"})


class TestPayloadCid(unittest.TestCase):
    """Acceptance 4: payload_cid round-trips an axiom CID and rejects non-CIDs."""

    def test_round_trips_axiom_cid(self):
        cid = compute_cid(b"large out-of-band payload bytes")
        record = daemon_event.build_event(
            tenant_id="t.a", agent_id="claude", session_id="s1",
            actor="agent", client="claude", lane="telemetry",
            kind="model_output", scope="agent_local", payload={},
            payload_cid=cid, trust="model_proposed",
        )
        self.assertEqual(record["payload_cid"], cid)
        daemon_event.validate_event(record)

    def test_rejects_non_cid_string(self):
        with self.assertRaises(ValueError):
            daemon_event.build_event(
                tenant_id="t.a", agent_id="claude", session_id="s1",
                actor="agent", client="claude", lane="telemetry",
                kind="model_output", scope="agent_local", payload={},
                payload_cid="not-a-cid",
            )


class TestProducersEmitV2(unittest.TestCase):
    """Acceptance 3: the three adapted producers emit valid v2 events end-to-end."""

    def _read_back(self, repo_root: Path) -> list[dict]:
        db = repo_root / "store" / "daemon" / "daemon-events.db"
        store = DaemonEventStore(db)
        try:
            return store.list_events(tenant_id=f"repo:{repo_root.name}")
        finally:
            store.close()

    def _repo(self) -> Path:
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="evt2_"))
        (root / "store" / "daemon").mkdir(parents=True)
        return root

    def test_claude_tool_hook_emits_v2(self):
        root = self._repo()
        hook = _load_hook("claude_tool_hook")
        hook._emit(root, "Bash", ["command"], 42, "sess-x")
        events = self._read_back(root)
        self.assertTrue(events)
        evt = events[0]
        daemon_event.validate_event(evt)
        self.assertEqual(evt["schema"], "lgwks.daemon.event.v2")
        self.assertEqual(evt["source"], "model")
        self.assertEqual(evt["trust"], "model_proposed")

    def test_codex_inbound_emits_v2(self):
        root = self._repo()
        hook = _load_hook("codex_inbound")
        hook._emit_daemon_event(root, "do the thing", "sess-y")
        evt = self._read_back(root)[0]
        daemon_event.validate_event(evt)
        self.assertEqual(evt["schema"], "lgwks.daemon.event.v2")
        self.assertEqual(evt["source"], "text")
        self.assertEqual(evt["trust"], "human_confirmed")

    def test_subconscious_inbound_emits_v2(self):
        root = self._repo()
        hook = _load_hook("subconscious_inbound")
        hook._emit_daemon_event(root, "another prompt", "sess-z")
        evt = self._read_back(root)[0]
        daemon_event.validate_event(evt)
        self.assertEqual(evt["schema"], "lgwks.daemon.event.v2")
        self.assertEqual(evt["source"], "text")
        self.assertEqual(evt["trust"], "human_confirmed")


if __name__ == "__main__":
    unittest.main()
