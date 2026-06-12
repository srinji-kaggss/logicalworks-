"""Tests for lgwks_daemon_event — normalized daemon event contract."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

import lgwks_daemon_event as daemon_event


class TestBuildEvent(unittest.TestCase):
    def test_required_fields_present(self):
        record = daemon_event.build_event(
            tenant_id="tenant.alpha",
            agent_id="claude",
            session_id="sess-001",
            actor="human",
            client="claude",
            lane="ingress",
            kind="human_message",
            scope="agent_local",
            payload={"message_cid": "cid-123"},
        )
        for field in (
            "schema", "event_id", "ts", "tenant_id", "agent_id", "session_id",
            "actor", "client", "lane", "kind", "scope", "payload",
        ):
            self.assertIn(field, record)
        self.assertEqual(record["schema"], daemon_event.SCHEMA)

    def test_event_id_is_deterministic_without_override(self):
        kwargs = {
            "tenant_id": "tenant.alpha",
            "agent_id": "codex",
            "session_id": "sess-002",
            "actor": "agent",
            "client": "codex",
            "lane": "telemetry",
            "kind": "tool_call",
            "scope": "agent_local",
            "payload": {"tool": "pytest", "status": "ok"},
            "ts": "2026-06-12T00:00:00+00:00",
        }
        left = daemon_event.build_event(**kwargs)
        right = daemon_event.build_event(**kwargs)
        self.assertEqual(left["event_id"], right["event_id"])

    def test_shared_referee_event_supported(self):
        record = daemon_event.build_event(
            tenant_id="tenant.alpha",
            agent_id="daemon.referee",
            session_id="sess-ref-01",
            actor="daemon",
            client="daemon",
            lane="control",
            kind="workflow_event",
            scope="shared_referee",
            payload={"decision": "serialize_git_write"},
            refs={"worktree": "wt-1", "agent_session": "sess-003"},
        )
        self.assertEqual(record["scope"], "shared_referee")
        self.assertEqual(record["refs"]["worktree"], "wt-1")


class TestValidateEvent(unittest.TestCase):
    def _record(self) -> dict:
        return daemon_event.build_event(
            tenant_id="tenant.alpha",
            agent_id="gemini",
            session_id="sess-003",
            actor="agent",
            client="gemini",
            lane="workflow",
            kind="workflow_event",
            scope="agent_local",
            payload={"workflow": "research.run"},
        )

    def test_invalid_identifier_rejected(self):
        with self.assertRaises(ValueError):
            daemon_event.build_event(
                tenant_id="tenant alpha",
                agent_id="gemini",
                session_id="sess-003",
                actor="agent",
                client="gemini",
                lane="workflow",
                kind="workflow_event",
                scope="agent_local",
                payload={"workflow": "research.run"},
            )

    def test_non_dict_payload_rejected(self):
        record = self._record()
        record["payload"] = ["bad"]
        with self.assertRaises(ValueError):
            daemon_event.validate_event(record)

    def test_invalid_ts_rejected(self):
        record = self._record()
        record["ts"] = "not-a-timestamp"
        with self.assertRaises(ValueError):
            daemon_event.validate_event(record)

    def test_non_serializable_payload_rejected(self):
        record = self._record()
        record["payload"] = {"bad": {1, 2, 3}}
        with self.assertRaises(ValueError):
            daemon_event.validate_event(record)


class TestCli(unittest.TestCase):
    def test_build_command_json(self):
        args = type(
            "Args",
            (),
            {
                "tenant_id": "tenant.alpha",
                "agent_id": "claude",
                "session_id": "sess-004",
                "actor": "human",
                "client": "claude",
                "lane": "ingress",
                "kind": "human_message",
                "scope": "agent_local",
                "payload": "{\"message_cid\":\"cid-1\"}",
                "refs": None,
                "causal_parent_id": None,
                "event_id": None,
            },
        )()
        with patch("sys.stdout", new_callable=io.StringIO) as buf:
            rc = daemon_event._build_command(args)
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["schema"], daemon_event.SCHEMA)

    def test_validate_command_reads_stdin(self):
        record = self._record()
        with patch("sys.stdin", io.StringIO(json.dumps(record))), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as buf:
            rc = daemon_event._validate_command(type("Args", (), {})())
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["ok"])

    def _record(self) -> dict:
        return daemon_event.build_event(
            tenant_id="tenant.alpha",
            agent_id="claude",
            session_id="sess-005",
            actor="agent",
            client="claude",
            lane="telemetry",
            kind="transcript_turn",
            scope="agent_local",
            payload={"turn_index": 12},
        )
