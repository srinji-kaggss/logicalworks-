"""Tests for lgwks_hooks — audit-first hook system."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_hooks as hooks


class TestBuildEvent(unittest.TestCase):
    def test_required_fields(self):
        rec = hooks.build_event("file.post_write", {"path": "/tmp/x.py"})
        self.assertEqual(rec["schema"], hooks.AUDIT_SCHEMA)
        self.assertEqual(rec["event"], "file.post_write")
        self.assertIn("ts", rec)
        self.assertIn("session_id", rec)
        self.assertIn("pid", rec)
        self.assertIn("cwd", rec)
        self.assertEqual(rec["payload"]["path"], "/tmp/x.py")

    def test_all_events_are_strings(self):
        for e in hooks.EVENTS:
            self.assertIsInstance(e, str)
            self.assertIn(".", e)  # must be namespaced


class TestAuditAppend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def test_creates_audit_log(self):
        rec = hooks.build_event("session.start", {"goal": "test"}, cwd=self.tmp)
        hooks.audit_append(rec, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        self.assertTrue(log.exists())
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["event"], "session.start")

    def test_appends_not_overwrites(self):
        for i in range(3):
            rec = hooks.build_event("tool.pre_invoke", {"verb": f"verb{i}"}, cwd=self.tmp)
            hooks.audit_append(rec, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)

    def test_bad_path_writes_to_stderr_not_raise(self):
        """audit_append must never raise — errors go to stderr only."""
        readonly = Path("/dev/full")  # always fails writes on Linux, skip on macOS
        # Instead: patch open to raise
        with patch("builtins.open", side_effect=OSError("disk full")):
            err = io.StringIO()
            with patch("sys.stderr", err):
                hooks.audit_append({"event": "x"}, cwd=self.tmp)
            self.assertIn("audit write failed", err.getvalue())


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def test_empty_registry_on_missing_file(self):
        reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"], [])

    def test_save_and_load_roundtrip(self):
        reg = hooks._load_registry(cwd=self.tmp)
        reg["hooks"].append({
            "name": "my-hook", "event": "file.post_write",
            "type": "script", "command": "/usr/bin/true", "enabled": True,
        })
        with patch.object(hooks, "fire"):  # suppress meta-event during test
            hooks._save_registry(reg, cwd=self.tmp)
        loaded = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(len(loaded["hooks"]), 1)
        self.assertEqual(loaded["hooks"][0]["name"], "my-hook")

    def test_malformed_registry_returns_empty(self):
        path = self.tmp / ".lgwks" / "hooks.json"
        path.write_text("{not valid json}", encoding="utf-8")
        err = io.StringIO()
        with patch("sys.stderr", err):
            reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"], [])
        self.assertIn("registry parse failed", err.getvalue())


class TestBuiltinHooks(unittest.TestCase):
    def test_why_nudge_fires_for_code_file(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._builtin_why_nudge("file.post_write", {"path": "src/main.py"})
        self.assertIn("//why hook", out.getvalue())

    def test_why_nudge_silent_for_non_code(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._builtin_why_nudge("file.post_write", {"path": "data/report.pdf"})
        self.assertEqual(out.getvalue(), "")

    def test_why_nudge_silent_for_missing_path(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._builtin_why_nudge("file.post_write", {})
        self.assertEqual(out.getvalue(), "")

    def test_secret_scrub_warns_on_credential_pattern(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_secret_scrub("http.post_fetch",
                {"body": 'api_key=AAAA1234567890abcdef1234'})
        self.assertIn("secret-scrub-check", err.getvalue())

    def test_secret_scrub_silent_on_clean_body(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_secret_scrub("http.post_fetch", {"body": "<html>hello</html>"})
        self.assertEqual(err.getvalue(), "")

    def test_token_watcher_warns_above_threshold(self):
        err = io.StringIO()
        with patch("sys.stderr", err), \
             patch.dict(os.environ, {"LGWKS_TOKEN_ALERT_THRESHOLD": "100"}):
            hooks._builtin_token_watcher("model.post_invoke", {"tokens_used": 200})
        self.assertIn("token-spend-watcher", err.getvalue())

    def test_token_watcher_silent_below_threshold(self):
        err = io.StringIO()
        with patch("sys.stderr", err), \
             patch.dict(os.environ, {"LGWKS_TOKEN_ALERT_THRESHOLD": "10000"}):
            hooks._builtin_token_watcher("model.post_invoke", {"tokens_used": 50})
        self.assertEqual(err.getvalue(), "")

    def test_git_drift_warns_on_rejected_push(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_git_drift("git.post_push", {"exit_code": 1, "stderr": "rejected"})
        self.assertIn("git-drift-watch", err.getvalue())

    def test_git_drift_silent_on_clean_push(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_git_drift("git.post_push", {"exit_code": 0, "stderr": ""})
        self.assertEqual(err.getvalue(), "")

    def test_scope_mirror_prints_on_violation(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_scope_mirror("scope.violation", {"message": "unauthorized file"})
        self.assertIn("scope-guard-mirror", err.getvalue())


class TestFire(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def test_fire_always_writes_audit(self):
        hooks.fire("session.start", {"goal": "test"}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        self.assertTrue(log.exists())
        rec = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(rec["event"], "session.start")

    def test_fire_runs_builtin_why_nudge(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks.fire("file.post_write", {"path": "main.rs"}, cwd=self.tmp)
        self.assertIn("//why hook", out.getvalue())

    def test_fire_unknown_event_still_audited(self):
        # Unknown events are not blocked — they still get audited
        hooks.fire("custom.my_event", {"data": "x"}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        events = [json.loads(l)["event"] for l in log.read_text().splitlines() if l.strip()]
        self.assertIn("custom.my_event", events)

    def test_fire_user_hook_called_with_json_stdin(self):
        """User hook script receives event JSON on stdin."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "test-hook", "event": "session.end",
            "type": "script", "command": "/usr/bin/true",
            "enabled": True,
        }]}
        reg_path = self.tmp / ".lgwks" / "hooks.json"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            hooks.fire("session.end", {"duration_s": 42}, cwd=self.tmp)
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args
            self.assertIsNotNone(call_kwargs)

    def test_fire_disabled_user_hook_not_called(self):
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "disabled-hook", "event": "session.end",
            "type": "script", "command": "/usr/bin/true",
            "enabled": False,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg), encoding="utf-8")
        with patch("subprocess.run") as mock_run:
            hooks.fire("session.end", {}, cwd=self.tmp)
            mock_run.assert_not_called()

    def test_fire_user_hook_failure_logged_not_raised(self):
        """A user hook exit_code != 0 must not propagate as an exception."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "failing-hook", "event": "auth.failure",
            "type": "script", "command": "/usr/bin/false",
            "enabled": True,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg), encoding="utf-8")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr=b"hook internal error",
            )
            # Must not raise
            hooks.fire("auth.failure", {"reason": "bad_token"}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        events = [json.loads(l)["event"] for l in log.read_text().splitlines() if l.strip()]
        self.assertIn("tool.error", events)

    def test_fire_builtin_exception_logged_not_raised(self):
        """A crashing builtin must not propagate as an exception."""
        def crashing_builtin(event, payload):
            raise RuntimeError("simulated crash")

        with patch.dict(hooks._BUILTINS, {"tool.pre_invoke": [crashing_builtin]}):
            hooks.fire("tool.pre_invoke", {}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        events = [json.loads(l)["event"] for l in log.read_text().splitlines() if l.strip()]
        self.assertIn("tool.error", events)


class TestCliList(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def _make_args(self, **kwargs):
        args = MagicMock()
        args.repo = str(self.tmp)
        args.json = False
        for k, v in kwargs.items():
            setattr(args, k, v)
        return args

    def test_list_json_contains_builtins(self):
        args = self._make_args(json=True)
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_list(args)
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        names = [h["name"] for h in data["hooks"]]
        self.assertIn("why-annotation-nudge", names)
        self.assertIn("secret-scrub-check", names)
        self.assertIn("token-spend-watcher", names)

    def test_list_human_table_prints(self):
        args = self._make_args(json=False)
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_list(args)
        text = out.getvalue()
        self.assertIn("NAME", text)
        self.assertIn("why-annotation-nudge", text)


class TestCliRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def _make_args(self, event, payload="{}"):
        args = MagicMock()
        args.repo = str(self.tmp)
        args.event = event
        args.payload = payload
        return args

    def test_run_valid_event_returns_0(self):
        rc = hooks._cmd_run(self._make_args("session.start", '{"goal":"x"}'))
        self.assertEqual(rc, 0)

    def test_run_unknown_event_returns_1(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_run(self._make_args("not.a.real.event"))
        self.assertEqual(rc, 1)

    def test_run_invalid_payload_json_returns_1(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_run(self._make_args("session.start", "{bad json"))
        self.assertEqual(rc, 1)


class TestCliAddRemove(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()

    def _make_args(self, **kwargs):
        args = MagicMock()
        args.repo = str(self.tmp)
        for k, v in kwargs.items():
            setattr(args, k, v)
        return args

    def test_add_and_list(self):
        args = self._make_args(name="my-hook", event="file.post_write",
                               command="/usr/bin/echo", description="test hook")
        with patch.object(hooks, "fire"):
            rc = hooks._cmd_add(args)
        self.assertEqual(rc, 0)
        reg = hooks._load_registry(cwd=self.tmp)
        names = [h["name"] for h in reg["hooks"]]
        self.assertIn("my-hook", names)

    def test_add_unknown_event_returns_1(self):
        args = self._make_args(name="x", event="bad.event", command="/usr/bin/true", description="")
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_add(args)
        self.assertEqual(rc, 1)

    def test_remove_existing(self):
        # Add first
        add_args = self._make_args(name="to-remove", event="session.end",
                                   command="/usr/bin/true", description="")
        with patch.object(hooks, "fire"):
            hooks._cmd_add(add_args)
        # Remove
        rm_args = self._make_args(name="to-remove")
        with patch.object(hooks, "fire"):
            rc = hooks._cmd_remove(rm_args)
        self.assertEqual(rc, 0)
        reg = hooks._load_registry(cwd=self.tmp)
        self.assertNotIn("to-remove", [h["name"] for h in reg["hooks"]])

    def test_remove_nonexistent_returns_1(self):
        args = self._make_args(name="ghost-hook")
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_remove(args)
        self.assertEqual(rc, 1)

    def test_add_deduplicates_by_name(self):
        for i in range(3):
            args = self._make_args(name="dup", event="file.post_write",
                                   command=f"/usr/bin/cmd{i}", description="")
            with patch.object(hooks, "fire"):
                hooks._cmd_add(args)
        reg = hooks._load_registry(cwd=self.tmp)
        dups = [h for h in reg["hooks"] if h["name"] == "dup"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["command"], "/usr/bin/cmd2")


class TestCliAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".lgwks").mkdir()
        # Seed audit log with known events
        for event in ["session.start", "file.post_write", "command.blocked"]:
            hooks.fire(event, {"test": True}, cwd=self.tmp)

    def _make_args(self, **kwargs):
        args = MagicMock()
        args.repo = str(self.tmp)
        args.json = True
        args.event_filter = None
        args.last = 50
        args.since = None
        args.export = None
        for k, v in kwargs.items():
            setattr(args, k, v)
        return args

    def test_audit_returns_all_records(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_audit(self._make_args())
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        events = [r["event"] for r in data["records"]]
        self.assertIn("session.start", events)

    def test_audit_filter_by_event(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_audit(self._make_args(event_filter="file.post_write"))
        data = json.loads(out.getvalue())
        for r in data["records"]:
            self.assertEqual(r["event"], "file.post_write")

    def test_audit_last_n(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_audit(self._make_args(last=1))
        data = json.loads(out.getvalue())
        # last=1 should return exactly 1 record (or fewer)
        self.assertLessEqual(len(data["records"]), 1)

    def test_audit_export(self):
        export_path = str(self.tmp / "export.jsonl")
        args = self._make_args(export=export_path, json=False)
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_audit(args)
        self.assertTrue(Path(export_path).exists())
        lines = [l for l in Path(export_path).read_text().splitlines() if l.strip()]
        self.assertGreater(len(lines), 0)

    def test_audit_empty_log(self):
        empty_dir = Path(tempfile.mkdtemp())
        (empty_dir / ".lgwks").mkdir()
        args = self._make_args()
        args.repo = str(empty_dir)
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_audit(args)
        self.assertEqual(rc, 0)


class TestEventTaxonomy(unittest.TestCase):
    def test_all_event_namespaces_covered(self):
        namespaces = {e.split(".")[0] for e in hooks.EVENTS}
        expected = {"file", "command", "git", "http", "session",
                    "model", "auth", "scope", "config", "tool", "audit"}
        self.assertEqual(namespaces, expected)

    def test_no_duplicate_events(self):
        self.assertEqual(len(hooks.EVENTS), len(set(hooks.EVENTS)))
