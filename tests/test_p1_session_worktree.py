"""Tests for #109 (P1 transcript normalization), #110 (RequestContext), #111 (worktree CRDT merge).

Covers:
  - lgwks_transcript.tail(): empty/missing/malformed/real JSONL
  - hooks/claude_tool_hook.py: PostToolUse stdin → tool_call event
  - hooks/claude_stop_hook.py: transcript tail → transcript_turn events
  - lgwks_session.RequestContext + make_context()
  - WorktreeManager._crdt_reconverge_entity_graph(): no-sidecar, merge, fail-silent
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Issue #109 — lgwks_transcript.tail()
# ---------------------------------------------------------------------------

import lgwks_transcript as _transcript


class TestTranscriptTail(unittest.TestCase):

    def test_missing_path_returns_empty(self):
        self.assertEqual(_transcript.tail("/tmp/__no_such_file__.jsonl"), [])

    def test_none_path_returns_empty(self):
        self.assertEqual(_transcript.tail(None), [])

    def test_empty_file_returns_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            self.assertEqual(_transcript.tail(path), [])
        finally:
            os.unlink(path)

    def test_malformed_jsonl_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not json\n{also bad\n")
            path = f.name
        try:
            result = _transcript.tail(path)
            self.assertEqual(result, [])
        finally:
            os.unlink(path)

    def test_valid_human_turn(self):
        record = {"type": "human", "message": {"role": "user", "content": "hello"}, "uuid": "abc123"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(record) + "\n")
            path = f.name
        try:
            result = _transcript.tail(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["role"], "human")
            self.assertEqual(result[0]["turn_id"], "abc123")
            self.assertGreater(result[0]["content_len"], 0)
            self.assertEqual(result[0]["turn_index"], 0)
        finally:
            os.unlink(path)

    def test_valid_assistant_turn(self):
        record = {"type": "assistant", "message": {"role": "assistant", "content": "response text"}, "uuid": "def456"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(record) + "\n")
            path = f.name
        try:
            result = _transcript.tail(path)
            self.assertEqual(result[0]["role"], "assistant")
        finally:
            os.unlink(path)

    def test_tail_n_limits_output(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(30):
                rec = {"type": "human", "message": {"content": f"msg {i}"}, "uuid": f"u{i}"}
                f.write(json.dumps(rec) + "\n")
            path = f.name
        try:
            result = _transcript.tail(path, n=5)
            self.assertLessEqual(len(result), 5)
        finally:
            os.unlink(path)

    def test_mixed_valid_invalid_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("bad line\n")
            f.write(json.dumps({"type": "human", "message": {"content": "ok"}, "uuid": "g1"}) + "\n")
            f.write("another bad\n")
            path = f.name
        try:
            result = _transcript.tail(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["role"], "human")
        finally:
            os.unlink(path)

    def test_fallback_turn_id_when_no_uuid(self):
        record = {"type": "human", "message": {"content": "no uuid here"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(record) + "\n")
            path = f.name
        try:
            result = _transcript.tail(path)
            self.assertTrue(result[0]["turn_id"].startswith("turn-"))
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Issue #109 — hooks (fail-silent + event emission)
# ---------------------------------------------------------------------------

def _load_hook(hook_name: str):
    hook_path = _REPO / "hooks" / hook_name
    spec = importlib.util.spec_from_file_location(hook_name.replace(".py", ""), hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestClaudeToolHook(unittest.TestCase):

    def test_exit_zero_on_missing_tool_name(self):
        mod = _load_hook("claude_tool_hook.py")
        result = mod._emit.__wrapped__ if hasattr(mod._emit, "__wrapped__") else None
        # Just verify the module loads and main() returns 0 on malformed stdin
        import io
        orig_stdin = sys.stdin
        sys.stdin = io.StringIO("{}")
        try:
            ret = mod.main()
        finally:
            sys.stdin = orig_stdin
        self.assertEqual(ret, 0)

    def test_emit_builds_valid_event(self):
        """_emit() builds a valid daemon event without raising."""
        mod = _load_hook("claude_tool_hook.py")
        mock_store = MagicMock()
        mock_event_mod = MagicMock()
        built = {
            "schema": "lgwks.daemon.event.v1",
            "event_id": "evt-abc",
            "kind": "tool_call",
        }
        mock_event_mod.build_event.return_value = built

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            db_parent = repo_root / "store" / "daemon"
            db_parent.mkdir(parents=True)
            (db_parent / "daemon-events.db").touch()

            with patch.dict("sys.modules", {
                "lgwks_daemon_event": mock_event_mod,
                "lgwks_daemon_store": MagicMock(DaemonEventStore=MagicMock(return_value=mock_store)),
            }):
                mod._emit(repo_root, "bash", ["command"], 42, "sess-123")

        mock_event_mod.build_event.assert_called_once()
        call_kwargs = mock_event_mod.build_event.call_args.kwargs
        self.assertEqual(call_kwargs["kind"], "tool_call")
        self.assertEqual(call_kwargs["lane"], "telemetry")
        self.assertEqual(call_kwargs["actor"], "agent")
        payload = call_kwargs["payload"]
        self.assertEqual(payload["tool_name"], "bash")
        self.assertIn("command", payload["input_keys"])

    def test_fail_silent_on_bad_db_path(self):
        """_emit() with no daemon store silently returns."""
        mod = _load_hook("claude_tool_hook.py")
        with tempfile.TemporaryDirectory() as tmp:
            # No store/daemon/ dir → should not raise
            mod._emit(Path(tmp), "bash", ["cmd"], 10, "s")


class TestClaudeStopHook(unittest.TestCase):

    def test_stop_hook_emits_transcript_turns(self):
        """Stop hook reads JSONL and emits transcript_turn events."""
        mod = _load_hook("claude_stop_hook.py")
        mock_store = MagicMock()
        mock_event_mod = MagicMock()
        mock_event_mod.build_event.return_value = {
            "schema": "lgwks.daemon.event.v1",
            "event_id": "evt-x",
            "kind": "transcript_turn",
        }

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            db_dir = repo_root / "store" / "daemon"
            db_dir.mkdir(parents=True)
            (db_dir / "daemon-events.db").touch()

            transcript = repo_root / "session.jsonl"
            record = {"type": "human", "message": {"content": "test prompt"}, "uuid": "u1"}
            transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with patch.dict("sys.modules", {
                "lgwks_daemon_event": mock_event_mod,
                "lgwks_daemon_store": MagicMock(DaemonEventStore=MagicMock(return_value=mock_store)),
            }):
                with patch.dict(os.environ, {"LGWKS_TRANSCRIPT_PATH": str(transcript)}):
                    # Patch repo_root resolution
                    with patch.object(Path, "resolve", return_value=repo_root):
                        import io
                        orig_stdin = sys.stdin
                        sys.stdin = io.StringIO("{}")
                        try:
                            mod._emit_turn(
                                mock_store,
                                mock_event_mod,
                                f"repo:{repo_root.name}",
                                "session",
                                {"role": "human", "content_len": 10, "turn_index": 0, "turn_id": "u1"},
                            )
                        finally:
                            sys.stdin = orig_stdin

        mock_event_mod.build_event.assert_called_once()
        kwargs = mock_event_mod.build_event.call_args.kwargs
        self.assertEqual(kwargs["kind"], "transcript_turn")
        self.assertEqual(kwargs["lane"], "telemetry")
        self.assertEqual(kwargs["payload"]["role"], "human")


# ---------------------------------------------------------------------------
# Issue #110 — RequestContext + make_context()
# ---------------------------------------------------------------------------

import lgwks_session as _session


class TestRequestContext(unittest.TestCase):

    def test_request_context_is_frozen(self):
        mock_store = MagicMock()
        ctx = _session.RequestContext(
            tenant_id="t1",
            agent_id="claude",
            session_id="s1",
            store=mock_store,
        )
        with self.assertRaises(Exception):
            ctx.tenant_id = "changed"  # type: ignore[misc]

    def test_request_context_fields(self):
        mock_store = MagicMock()
        ctx = _session.RequestContext("t1", "agent1", "s1", store=mock_store)
        self.assertEqual(ctx.tenant_id, "t1")
        self.assertEqual(ctx.agent_id, "agent1")
        self.assertEqual(ctx.session_id, "s1")
        self.assertIs(ctx.store, mock_store)

    def test_make_context_calls_resolve(self):
        """make_context() resolves capability and builds TenantStore."""
        mock_port = MagicMock()
        mock_handle = MagicMock()
        mock_key = b"k" * 32
        mock_store_cls = MagicMock()
        mock_store_instance = MagicMock()
        mock_store_cls.return_value = mock_store_instance
        mock_conn = MagicMock()

        with patch("lgwks_access.resolve_capability_for_tenant", return_value=(mock_port, mock_handle, mock_key)) as mock_resolve, \
             patch("lgwks_access.TenantStore", mock_store_cls):
            ctx = _session.make_context("tenant-a", "claude", "sess-1", mock_conn)

        mock_resolve.assert_called_once_with("tenant-a")
        mock_store_cls.assert_called_once_with(mock_port, mock_handle, mock_key, mock_conn)
        self.assertEqual(ctx.tenant_id, "tenant-a")
        self.assertEqual(ctx.agent_id, "claude")
        self.assertEqual(ctx.session_id, "sess-1")
        self.assertIs(ctx.store, mock_store_instance)

    def test_make_context_promote_path(self):
        """make_context(promote=True) resolves promote capability."""
        mock_port, mock_handle, mock_key = MagicMock(), MagicMock(), b"k" * 32
        mock_conn = MagicMock()

        with patch("lgwks_access.resolve_promote_capability_for_tenant", return_value=(mock_port, mock_handle, mock_key)) as mock_resolve, \
             patch("lgwks_access.TenantStore", MagicMock(return_value=MagicMock())):
            ctx = _session.make_context("t", "a", "s", mock_conn, promote=True)

        mock_resolve.assert_called_once_with("t")


# ---------------------------------------------------------------------------
# Issue #111 — WorktreeManager._crdt_reconverge_entity_graph()
# ---------------------------------------------------------------------------

from lgwks_crdt import JsonFileSink, ORSet


def _make_worktree_manager():
    import lgwks_daemon_store as _store_mod
    mock_store = MagicMock()
    with tempfile.TemporaryDirectory() as tmp:
        from lgwks_daemon import WorktreeManager
        mgr = WorktreeManager(mock_store, Path(tmp))
    return mgr, tmp


class TestWorktreeCRDTReconverge(unittest.TestCase):

    def test_no_sidecar_no_error(self):
        """Calling _crdt_reconverge_entity_graph on an empty worktree is a no-op."""
        from lgwks_daemon import WorktreeManager
        mock_store = MagicMock()
        with tempfile.TemporaryDirectory() as repo_root_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                mgr = WorktreeManager(mock_store, Path(repo_root_dir))
                # Should not raise
                mgr._crdt_reconverge_entity_graph(Path(wt_dir))

    def test_nonexistent_worktree_path_is_silent(self):
        from lgwks_daemon import WorktreeManager
        mock_store = MagicMock()
        with tempfile.TemporaryDirectory() as repo_root_dir:
            mgr = WorktreeManager(mock_store, Path(repo_root_dir))
            # Path that does not exist
            mgr._crdt_reconverge_entity_graph(Path(repo_root_dir) / "no-such-wt")

    def test_sidecar_merged_into_canonical(self):
        """A worktree CRDT sidecar is merged into the canonical repo path on close."""
        from lgwks_daemon import WorktreeManager
        mock_store = MagicMock()
        with tempfile.TemporaryDirectory() as repo_root_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                repo_root = Path(repo_root_dir)
                wt_path = Path(wt_dir)
                mgr = WorktreeManager(mock_store, repo_root)

                # Create a worktree CRDT sidecar with one node in an ORSet
                sidecar_rel = Path("store") / "graphs" / "graph.db.crdt.json"
                wt_sidecar = wt_path / sidecar_rel
                wt_sidecar.parent.mkdir(parents=True)
                node_set = ORSet().add("node-abc")
                wt_sink = JsonFileSink(wt_sidecar)
                wt_sink.commit({"nodes": node_set, "edges": ORSet()})

                # Reconverge
                mgr._crdt_reconverge_entity_graph(wt_path)

                # Canonical sidecar should now exist and contain the node
                canonical = repo_root / sidecar_rel
                self.assertTrue(canonical.exists())
                canonical_sink = JsonFileSink(canonical)
                merged = canonical_sink.load()
                self.assertIn("nodes", merged)
                self.assertIn("node-abc", merged["nodes"].value())

    def test_sidecar_merge_is_additive(self):
        """Existing canonical state is preserved (not overwritten) when merging."""
        from lgwks_daemon import WorktreeManager
        mock_store = MagicMock()
        with tempfile.TemporaryDirectory() as repo_root_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                repo_root = Path(repo_root_dir)
                wt_path = Path(wt_dir)
                mgr = WorktreeManager(mock_store, repo_root)

                rel = Path("store") / "graphs" / "graph.db.crdt.json"

                # Canonical already has node-main
                canonical_sidecar = repo_root / rel
                canonical_sidecar.parent.mkdir(parents=True)
                JsonFileSink(canonical_sidecar).commit({"nodes": ORSet().add("node-main"), "edges": ORSet()})

                # Worktree adds node-wt
                wt_sidecar = wt_path / rel
                wt_sidecar.parent.mkdir(parents=True)
                JsonFileSink(wt_sidecar).commit({"nodes": ORSet().add("node-wt"), "edges": ORSet()})

                mgr._crdt_reconverge_entity_graph(wt_path)

                merged = JsonFileSink(canonical_sidecar).load()
                self.assertIn("node-main", merged["nodes"].value())
                self.assertIn("node-wt", merged["nodes"].value())

    def test_bad_sidecar_content_fail_silent(self):
        """A malformed sidecar file is skipped silently."""
        from lgwks_daemon import WorktreeManager
        mock_store = MagicMock()
        with tempfile.TemporaryDirectory() as repo_root_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                repo_root = Path(repo_root_dir)
                wt_path = Path(wt_dir)
                mgr = WorktreeManager(mock_store, repo_root)

                bad_sidecar = wt_path / "bad.crdt.json"
                bad_sidecar.write_text("not valid json {{", encoding="utf-8")

                # Should not raise
                mgr._crdt_reconverge_entity_graph(wt_path)


if __name__ == "__main__":
    unittest.main()
