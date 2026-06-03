"""Tests for scope-creep-guard.py PreToolUse hook."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import scope-creep-guard main
import importlib.util

spec = importlib.util.spec_from_file_location("guard", os.path.expanduser("~/.claude/hooks/scope-creep-guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class TestScopeCreepGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.scope_dir = self.tmp / ".lgwks"
        self.scope_dir.mkdir(parents=True, exist_ok=True)
        self.scope_file = self.scope_dir / "active-scope.json"
        # Mock git repo directory structure
        (self.tmp / ".git").mkdir()

    def test_no_scope_file_allows_all(self):
        if self.scope_file.exists():
            self.scope_file.unlink()

        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "random.py")},
            "cwd": str(self.tmp)
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(event))):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 0)

    def test_allowed_file_exits_0(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp / "allowed.py")
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "allowed.py")},
            "cwd": str(self.tmp)
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(event))):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 0)

    def test_unallowed_file_exits_2(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp / "allowed.py")
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "creep.py")},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("SCOPE CREEP DETECTED", err.getvalue())

    def test_case_insensitivity_macos(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp / "allowed.py")
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # Casing mismatch input (e.g. capital A)
        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "Allowed.py")},
            "cwd": str(self.tmp)
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(event))):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 0)

    def test_tool_specific_keys(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp / "allowed.py")
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # grep_search tool with SearchPath outside allowed list
        event = {
            "tool_name": "grep_search",
            "tool_input": {"SearchPath": str(self.tmp / "restricted.py")},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("unauthorized file", err.getvalue())

    def test_cwd_subdirectory_resolution(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp / "allowed.py")
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # Run from a subdirectory CWD, checking that it resolves root active-scope.json
        sub_dir = self.tmp / "tests"
        sub_dir.mkdir(exist_ok=True)
        
        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "creep.py")},
            "cwd": str(sub_dir)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)

    def test_policy_file_bootstrap_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [
                str(self.tmp)
            ],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # Even if parent dir is allowed, editing active-scope.json itself is blocked
        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.scope_file)},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("Blocked modification of security configuration", err.getvalue())

    def test_command_chaining_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [],
            "allowed_commands": [
                "git"
            ]
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status && rm -rf /"},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("metacharacter", err.getvalue())

    def test_command_substitution_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [],
            "allowed_commands": [
                "git"
            ]
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status --abbrev=$(id)"},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("substitution is blocked", err.getvalue())

    def test_unspaced_semicolon_chaining_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [],
            "allowed_commands": ["git"]
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status;rm -rf /"},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("metacharacter ';'", err.getvalue())

    def test_newline_chaining_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [],
            "allowed_commands": ["git"]
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status\nrm -rf /"},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("metacharacter newline", err.getvalue())

    def test_loose_prefix_command_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [],
            "allowed_commands": ["git"]
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # allowed is "git", run command is "gitbuddy status"
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "gitbuddy status"},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("unauthorized command", err.getvalue())

    def test_nested_list_of_paths_block(self):
        scope_data = {
            "active": True,
            "allowed_files": [str(self.tmp / "allowed.py")],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        # Tool input uses a list of paths under a key containing "path"
        event = {
            "tool_name": "MultiWrite",
            "tool_input": {"paths": [str(self.tmp / "allowed.py"), str(self.tmp / "restricted.py")]},
            "cwd": str(self.tmp)
        }
        
        err = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), \
             patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("unauthorized file", err.getvalue())

    def test_fallback_project_root_without_git(self):
        # Remove git dir to test fallback to .lgwks discovery
        (self.tmp / ".git").rmdir()
        
        scope_data = {
            "active": True,
            "allowed_files": [str(self.tmp / "allowed.py")],
            "allowed_commands": []
        }
        self.scope_file.write_text(json.dumps(scope_data), encoding="utf-8")

        sub_dir = self.tmp / "tests"
        sub_dir.mkdir(exist_ok=True)
        
        event = {
            "tool_name": "Edit",
            "tool_input": {"path": str(self.tmp / "allowed.py")},
            "cwd": str(sub_dir)
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(event))):
            with self.assertRaises(SystemExit) as cm:
                guard.main()
            self.assertEqual(cm.exception.code, 0)
