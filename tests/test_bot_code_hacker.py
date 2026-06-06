"""
Tests for U5: lgwks_bot_code_hacker.

Acceptance:
  1. Valid lgwks.bot.record.v1 records emitted.
  2. Dangerous shell usage (os.system, subprocess shell=True, eval) detected.
  3. Secret / logging risks detected.
  4. Network imports in non-network modules flagged (architecture-wall check).
  5. Changed-file subset scanning works without full-repo scan.
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lgwks_bot_code_hacker as hacker
import lgwks_project_artifacts as artifacts


def _write(tmp: Path, name: str, src: str) -> str:
    p = tmp / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return name


class TestRecordValidity(unittest.TestCase):
    """All emitted records must pass the schema validator."""

    def test_every_finding_is_valid_schema(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "bad.py", """\
                import os
                os.system("rm -rf /")
            """)
            findings = hacker.run(tmp)
        self.assertTrue(findings, "expected at least one finding")
        for rec in findings:
            ok, errs = artifacts.validate_bot_record(rec)
            self.assertTrue(ok, f"invalid record: {errs}\n{rec}")


class TestH1DangerousShell(unittest.TestCase):
    """Acceptance 2: dangerous shell execution detected."""

    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_os_system_flagged(self):
        findings = self._scan("import os\nos.system('ls')\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("dangerous_shell_exec", kinds)

    def test_subprocess_shell_true_flagged_critical(self):
        findings = self._scan(
            "import subprocess\nsubprocess.run('ls', shell=True)\n"
        )
        exec_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
        self.assertTrue(exec_finds)
        self.assertTrue(any(f["severity"] == "critical" for f in exec_finds))

    def test_subprocess_string_cmd_flagged(self):
        findings = self._scan(
            "import subprocess\ncmd = 'ls '\nsubprocess.run(f'{cmd} -la', shell=False)\n"
        )
        # f-string (JoinedStr) arg — high severity
        exec_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
        self.assertTrue(exec_finds)

    def test_eval_dynamic_arg_flagged(self):
        findings = self._scan("x = input()\neval(x)\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("dangerous_shell_exec", kinds)

    def test_eval_constant_not_flagged(self):
        findings = self._scan("eval('1+1')\n")
        exec_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
        self.assertFalse(exec_finds, "constant eval should not be flagged")


class TestH2UnsafeFileMutation(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_shutil_rmtree_flagged(self):
        findings = self._scan("import shutil\nshutil.rmtree('/tmp/foo')\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("unsafe_file_mutation", kinds)

    def test_os_remove_flagged(self):
        findings = self._scan("import os\nos.remove('x.py')\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("unsafe_file_mutation", kinds)


class TestH4SecretExposure(unittest.TestCase):
    """Acceptance 3: secret / logging risks detected."""

    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_token_in_print_flagged(self):
        findings = self._scan("token = 'abc'\nprint(token)\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("secret_exposure_risk", kinds)

    def test_api_key_in_logging_flagged(self):
        findings = self._scan(
            "import logging\napi_key = 'x'\nlogging.info(api_key)\n"
        )
        kinds = [f["kind"] for f in findings]
        self.assertIn("secret_exposure_risk", kinds)

    def test_unrelated_print_not_flagged(self):
        findings = self._scan("print('hello world')\n")
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertFalse(secret_finds)


class TestH3NetworkEgress(unittest.TestCase):
    """Acceptance 4: network imports in non-network modules flagged."""

    def _scan(self, filename: str, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, filename, src)
            return hacker.run(tmp)

    def test_requests_import_in_deterministic_module_flagged(self):
        findings = self._scan("lgwks_cycle.py", "import requests\n")
        kinds = [f["kind"] for f in findings]
        self.assertIn("unbounded_network_egress", kinds)

    def test_requests_import_in_portal_module_allowed(self):
        # portal modules are explicitly expected to use the network
        findings = self._scan("lgwks_portal.py", "import requests\n")
        net_finds = [f for f in findings if f["kind"] == "unbounded_network_egress"]
        self.assertFalse(net_finds, "portal modules may use network imports")


class TestChangedFileSubset(unittest.TestCase):
    """Acceptance 5: changed-file subset scanning."""

    def test_only_changed_file_scanned(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "clean.py", "x = 1\n")
            _write(tmp, "dirty.py", "import os\nos.system('x')\n")
            # scan only clean.py
            findings = hacker.run(tmp, changed_files=["clean.py"])
            shell_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
            self.assertFalse(shell_finds, "dirty.py should not be scanned")

    def test_changed_file_subset_finds_issue(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "dirty.py", "import os\nos.system('x')\n")
            findings = hacker.run(tmp, changed_files=["dirty.py"])
            self.assertTrue(any(f["kind"] == "dangerous_shell_exec" for f in findings))


class TestParseErrorHandling(unittest.TestCase):
    def test_syntax_error_emits_failure_record(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "broken.py", "def foo(:\n    pass\n")
            findings = hacker.run(tmp)
        self.assertTrue(any(f["kind"] == "analyzer_failure" for f in findings))
        for rec in findings:
            ok, errs = artifacts.validate_bot_record(rec)
            self.assertTrue(ok, errs)
