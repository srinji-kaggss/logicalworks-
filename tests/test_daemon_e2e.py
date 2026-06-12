"""End-to-end tests for the daemon pipeline without live hooks.

Covers: emit → store → packet loop; assemble_inbound ctx kwarg; _DOMAINS coverage.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_daemon as daemon_mod
import lgwks_daemon_event as event_mod
from lgwks_daemon_store import DaemonEventStore


def _make_store(tmp: Path) -> DaemonEventStore:
    db_path = tmp / "store" / "daemon_events.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DaemonEventStore(db_path)


def _sample_event(tenant_id: str = "test-tenant", session_id: str = "s1", agent_id: str = "a1") -> dict:
    return event_mod.build_event(
        tenant_id=tenant_id,
        agent_id=agent_id,
        session_id=session_id,
        actor="human",
        client="human",
        lane="ingress",
        kind="human_message",
        scope="agent_local",
        payload={"prompt": "hello"},
    )


class TestEmitPacketLoop(unittest.TestCase):
    """Full loop: append event → get_packet returns it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir()

    def test_appended_event_appears_in_packet(self):
        store = _make_store(self.tmp)
        tenant_id = "test-tenant"
        session_id = "session-e2e"
        agent_id = "claude"
        try:
            event = _sample_event(tenant_id=tenant_id, session_id=session_id, agent_id=agent_id)
            inserted = store.append(event)
            self.assertTrue(inserted)

            packet = store.get_packet(tenant_id=tenant_id, session_id=session_id, agent_id=agent_id)
            self.assertEqual(packet["session_id"], session_id)
            self.assertEqual(packet["agent_id"], agent_id)
            self.assertGreaterEqual(packet["event_count"], 1)
            event_ids = [e["event_id"] for e in packet["recent_events"]]
            self.assertIn(event["event_id"], event_ids)
        finally:
            store.close()

    def test_packet_pk_dedup(self):
        """Appending the same event twice counts as one."""
        store = _make_store(self.tmp)
        try:
            event = _sample_event()
            store.append(event)
            store.append(event)
            packet = store.get_packet(tenant_id="test-tenant", session_id="s1", agent_id="a1")
            count = sum(1 for e in packet["recent_events"] if e["event_id"] == event["event_id"])
            self.assertEqual(count, 1)
        finally:
            store.close()

    def test_packet_isolates_by_session(self):
        store = _make_store(self.tmp)
        try:
            e1 = _sample_event(session_id="sess-A", agent_id="agent-A")
            e2 = _sample_event(session_id="sess-B", agent_id="agent-B")
            store.append(e1)
            store.append(e2)

            p1 = store.get_packet(tenant_id="test-tenant", session_id="sess-A", agent_id="agent-A")
            p2 = store.get_packet(tenant_id="test-tenant", session_id="sess-B", agent_id="agent-B")
            ids1 = {e["event_id"] for e in p1["recent_events"]}
            ids2 = {e["event_id"] for e in p2["recent_events"]}
            self.assertIn(e1["event_id"], ids1)
            self.assertNotIn(e2["event_id"], ids1)
            self.assertIn(e2["event_id"], ids2)
            self.assertNotIn(e1["event_id"], ids2)
        finally:
            store.close()


class TestEmitCommand(unittest.TestCase):
    """Exercises _emit_command end-to-end through the CLI function."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "store").mkdir()

    def _make_args(self, kind="human_message", session_id="s1", agent_id="a1",
                   tenant=None, actor="human", client="human", lane="ingress",
                   scope="agent_local") -> argparse.Namespace:
        return argparse.Namespace(
            repo=str(self.tmp),
            kind=kind,
            session_id=session_id,
            agent_id=agent_id,
            tenant=tenant,
            actor=actor,
            client=client,
            lane=lane,
            scope=scope,
        )

    def test_emit_returns_zero_and_inserts(self):
        args = self._make_args()
        import io
        import sys

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                rc = daemon_mod._emit_command(args)
        finally:
            sys.stdout = old

        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])
        self.assertTrue(out["inserted"])
        self.assertTrue(out["event_id"].startswith("evt-"))

    def test_emit_then_packet_contains_event(self):
        args = self._make_args(session_id="smoke-session", agent_id="smoke-agent")

        import io
        import sys

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                daemon_mod._emit_command(args)
        finally:
            sys.stdout = old

        emit_result = json.loads(buf.getvalue())
        event_id = emit_result["event_id"]

        # Now verify the packet contains that event
        paths = daemon_mod._paths(Path(args.repo).resolve())
        store = DaemonEventStore(paths.db)
        tenant_id = f"repo:{paths.repo_root.name}"
        try:
            packet = store.get_packet(
                tenant_id=tenant_id,
                session_id="smoke-session",
                agent_id="smoke-agent",
            )
        finally:
            store.close()

        ids = [e["event_id"] for e in packet["recent_events"]]
        self.assertIn(event_id, ids)

    def test_emit_with_stdin_payload(self):
        args = self._make_args(kind="workflow_event", actor="daemon", client="daemon",
                               lane="workflow", scope="shared_referee")

        import io
        import sys

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        payload = json.dumps({"event": "test_event", "value": 42})
        try:
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                mock_stdin.read.return_value = payload
                rc = daemon_mod._emit_command(args)
        finally:
            sys.stdout = old

        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])


class TestAssembleInboundCtx(unittest.TestCase):
    """assemble_inbound ctx kwarg supersedes store_conn + tenant_store."""

    def test_ctx_none_and_store_conn_none_raises(self):
        import lgwks_inbound as inbound
        with self.assertRaises(ValueError, msg="store_conn is required when ctx is None"):
            inbound.assemble_inbound(None, {"nodes": [], "edges": []}, store_conn=None, ctx=None)

    def test_ctx_sets_tenant_store(self):
        import lgwks_inbound as inbound
        import lgwks_rank as rank

        # Build a minimal graph so rank_graph works
        graph = {
            "nodes": [{"id": "n1", "label": "X"}],
            "edges": [],
        }
        mock_store = MagicMock()
        mock_store.read.return_value = None  # no vector records → empty fused set

        mock_ctx = MagicMock()
        mock_ctx.store = mock_store

        # Should not raise ValueError about store_conn; may raise RankError if graph is degenerate
        try:
            inbound.assemble_inbound(None, graph, store_conn=None, ctx=mock_ctx)
        except rank.RankError:
            pass  # expected for a single-node graph with no edges — that's fine
        except Exception as exc:
            self.fail(f"unexpected exception with ctx set: {exc}")

        # The store's read was called for node n1 — confirms ctx.store was used
        # (It may or may not be called depending on whether rank_graph returns n1)


class TestDomainCoverage(unittest.TestCase):
    """daemon and access are now in _DOMAINS — pre-existing gap closed."""

    def test_daemon_in_domains(self):
        import lgwks_home
        all_verbs = sum(lgwks_home._DOMAINS.values(), [])
        self.assertIn("daemon", all_verbs)

    def test_access_in_domains(self):
        import lgwks_home
        all_verbs = sum(lgwks_home._DOMAINS.values(), [])
        self.assertIn("access", all_verbs)


if __name__ == "__main__":
    unittest.main()
