"""
Tests for U5 build #2: lgwks_bot_code_hacker — fraud-engine-grade static analyzer.

Covers:
  1. Layer 1 surface detection (H1-H4, backward compatible with build #1)
  2. Layer 2 taint analysis (secret source → sink flow)
  3. Layer 3 composite risk scoring (severity derived from confidence + context)
  4. Layer 4 baseline suppression (FP tracking, auto-suppress after 2 dismissals)
  5. Layer 5 SARIF export (valid SARIF 2.1.0 schema)
"""

from __future__ import annotations

import json
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
    """Acceptance: dangerous shell execution detected."""

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


class TestH4TaintAnalysis(unittest.TestCase):
    """Layer 2: secret source → sink flow detection."""

    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_secret_in_print_with_taint_flow(self):
        findings = self._scan("token = 'abc'\nprint(token)\n")
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertTrue(secret_finds)
        # Should report taint flow with source line
        self.assertTrue(any("taint flow" in f["summary"] for f in secret_finds))

    def test_secret_in_fstring_logging(self):
        src = """\
            import logging
            api_key = 'secret123'
            logging.info(f"key={api_key}")
        """
        findings = self._scan(src)
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertTrue(secret_finds)
        self.assertTrue(any("api_key" in f["summary"] for f in secret_finds))

    def test_unrelated_print_not_flagged(self):
        findings = self._scan("print('hello world')\n")
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertFalse(secret_finds)

    def test_env_var_read_taint_tracked(self):
        src = """\
            import os
            api_key = os.environ.get("API_KEY")
            print(api_key)
        """
        findings = self._scan(src)
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertTrue(secret_finds)
        self.assertTrue(any("env_var" in f["summary"] for f in secret_finds))

    def test_non_secret_var_not_flagged(self):
        """A variable with an innocent name (not matching _SECRET_RE) that
        was never assigned a secret value should not be flagged."""
        src = """\
            greeting = "hello"
            print(greeting)
        """
        findings = self._scan(src)
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertFalse(secret_finds, "innocent variable should not be flagged")

    def test_secret_named_var_always_tracked(self):
        """A variable named 'token' is always tracked as a potential secret
        source because the name itself is a strong signal — but the report
        shows it was tracked by name (secret_var), not inferred."""
        src = """\
            token = "csrf-token-123"
            print(token)
        """
        findings = self._scan(src)
        secret_finds = [f for f in findings if f["kind"] == "secret_exposure_risk"]
        self.assertTrue(secret_finds)
        self.assertTrue(any("secret_var" in f["summary"] for f in secret_finds))


class TestH3NetworkEgress(unittest.TestCase):
    """Acceptance: network imports in non-network modules flagged."""

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
        findings = self._scan("lgwks_portal.py", "import requests\n")
        net_finds = [f for f in findings if f["kind"] == "unbounded_network_egress"]
        self.assertFalse(net_finds, "portal modules may use network imports")


class TestChangedFileSubset(unittest.TestCase):
    """Acceptance: changed-file subset scanning."""

    def test_only_changed_file_scanned(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "clean.py", "x = 1\n")
            _write(tmp, "dirty.py", "import os\nos.system('x')\n")
            findings = hacker.run(tmp, changed_files=["clean.py"])
            shell_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
            self.assertFalse(shell_finds, "dirty.py should not be scanned")

    def test_changed_file_subset_finds_issue(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "dirty.py", "import os\nos.system('x')\n")
            findings = hacker.run(tmp, changed_files=["dirty.py"])
            self.assertTrue(any(f["kind"] == "dangerous_shell_exec" for f in findings))


class TestBaselineSuppression(unittest.TestCase):
    """Layer 4: false-positive suppression via historical baseline."""

    def test_suppressed_after_two_dismissals(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "secret.py", "token = 'x'\nprint(token)\n")
            baseline = tmp / "baseline.json"

            # First run: finding appears
            f1 = hacker.run(tmp, baseline_path=baseline)
            self.assertTrue(any(f["kind"] == "secret_exposure_risk" for f in f1))

            # Manually mark as dismissed twice (simulate user feedback)
            data = json.loads(baseline.read_text())
            for item in data["findings"]:
                item["dismiss_count"] = 2
            baseline.write_text(json.dumps(data), encoding="utf-8")

            # Third run: suppressed
            f3 = hacker.run(tmp, baseline_path=baseline)
            secret_finds = [f for f in f3 if f["kind"] == "secret_exposure_risk"]
            self.assertFalse(secret_finds, "should be suppressed after 2 dismissals")

    def test_new_finding_not_suppressed(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "secret.py", "token = 'x'\nprint(token)\n")
            baseline = tmp / "baseline.json"
            f1 = hacker.run(tmp, baseline_path=baseline)
            self.assertTrue(any(f["kind"] == "secret_exposure_risk" for f in f1))


class TestSARIFExport(unittest.TestCase):
    """Layer 5: SARIF 2.1.0 output validation."""

    def test_sarif_file_created(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "bad.py", "import os\nos.system('rm')\n")
            findings = hacker.run(tmp, emit_sarif=True)
            sarif_path = tmp / ".lgwks" / "code-hacker.sarif"
            self.assertTrue(sarif_path.exists())
            data = json.loads(sarif_path.read_text())
            self.assertEqual(data["version"], "2.1.0")
            self.assertIn("runs", data)
            self.assertTrue(len(data["runs"][0]["results"]) > 0)

    def test_sarif_result_has_required_fields(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "bad.py", "import os\nos.system('rm')\n")
            hacker.run(tmp, emit_sarif=True)
            sarif_path = tmp / ".lgwks" / "code-hacker.sarif"
            data = json.loads(sarif_path.read_text())
            result = data["runs"][0]["results"][0]
            self.assertIn("ruleId", result)
            self.assertIn("level", result)
            self.assertIn("message", result)
            self.assertIn("locations", result)
            self.assertIn("physicalLocation", result["locations"][0])

    def test_analyzer_failure_excluded_from_sarif(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "broken.py", "def foo(:\n    pass\n")
            hacker.run(tmp, emit_sarif=True)
            sarif_path = tmp / ".lgwks" / "code-hacker.sarif"
            data = json.loads(sarif_path.read_text())
            for result in data["runs"][0]["results"]:
                self.assertNotEqual(result.get("ruleId"), "analyzer_failure")


class TestCompositeRiskScoring(unittest.TestCase):
    """Layer 3: risk scores map to correct severity tiers."""

    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_shell_true_is_critical(self):
        findings = self._scan("import subprocess\nsubprocess.run('ls', shell=True)\n")
        exec_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
        self.assertTrue(any(f["severity"] == "critical" for f in exec_finds))
        self.assertTrue(all(f["confidence"] >= 0.9 for f in exec_finds))

    def test_network_import_is_medium(self):
        findings = self._scan("import requests\n")
        net_finds = [f for f in findings if f["kind"] == "unbounded_network_egress"]
        self.assertTrue(any(f["severity"] == "medium" for f in net_finds))


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


class TestFingerprintStability(unittest.TestCase):
    """Findings must have stable fingerprints for baseline tracking."""

    def test_same_code_same_fingerprint(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "bad.py", "import os\nos.system('x')\n")
            f1 = hacker.run(tmp)
            f2 = hacker.run(tmp)
        fp1 = hacker._finding_fingerprint(f1[0])
        fp2 = hacker._finding_fingerprint(f2[0])
        self.assertEqual(fp1, fp2)

    def test_different_line_different_fingerprint(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "bad.py", "\n\nimport os\nos.system('x')\n")
            f1 = hacker.run(tmp)
            _write(tmp, "bad.py", "import os\nos.system('x')\n")
            f2 = hacker.run(tmp)
        fp1 = hacker._finding_fingerprint(f1[0])
        fp2 = hacker._finding_fingerprint(f2[0])
        self.assertNotEqual(fp1, fp2)


class TestH5SsrfRisk(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_unvalidated_httpx_get_flagged(self):
        src = "import httpx\nurl = input()\nhttpx.get(url)\n"
        findings = self._scan(src)
        self.assertTrue(any(f["kind"] == "ssrf_risk" for f in findings))

    def test_validated_httpx_get_not_flagged(self):
        # Even a weak validation heuristic should reduce risk or suppress the finding
        src = """\
            import httpx
            from lgwks_browser import _remote_allowed
            url = input()
            if _remote_allowed(url):
                httpx.get(url)
        """
        findings = self._scan(src)
        ssrf_finds = [f for f in findings if f["kind"] == "ssrf_risk"]
        self.assertFalse(ssrf_finds, "validated request should not be flagged as high risk")


class TestH6PathTraversal(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_unsafe_read_text_flagged(self):
        src = "from pathlib import Path\np = Path(input())\ncontent = p.read_text()\n"
        findings = self._scan(src)
        self.assertTrue(any(f["kind"] == "path_traversal_risk" for f in findings))

    def test_safe_read_text_not_flagged(self):
        src = """\
            from pathlib import Path
            root = Path("/tmp/safe")
            p = Path(input())
            if p.resolve().is_relative_to(root.resolve()):
                content = p.read_text()
        """
        findings = self._scan(src)
        path_finds = [f for f in findings if f["kind"] == "path_traversal_risk"]
        self.assertFalse(path_finds, "boundary-checked path should not be flagged")


class TestH7SqlInjection(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_dynamic_sql_execute_flagged(self):
        src = "import sqlite3\nconn = sqlite3.connect(':memory:')\ntable = input()\nconn.execute(f'SELECT * FROM {table}')\n"
        findings = self._scan(src)
        self.assertTrue(any(f["kind"] == "sql_injection_risk" for f in findings))

    def test_parameterized_sql_not_flagged(self):
        src = "import sqlite3\nconn = sqlite3.connect(':memory:')\nval = input()\nconn.execute('SELECT * FROM users WHERE id = ?', (val,))\n"
        findings = self._scan(src)
        sqli_finds = [f for f in findings if f["kind"] == "sql_injection_risk"]
        self.assertFalse(sqli_finds, "parameterized SQL should not be flagged")


class TestH1AdvancedCommandInjection(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_subprocess_run_list_with_tainted_string_not_flagged_if_clean(self):
        # This is safe because it's a list, even if tainted, shell won't interpret it
        src = "import subprocess\ncmd = input()\nsubprocess.run(['ls', cmd])\n"
        findings = self._scan(src)
        exec_finds = [f for f in findings if f["kind"] == "dangerous_shell_exec"]
        self.assertFalse(exec_finds)

    def test_os_popen_tainted_flagged(self):
        src = "import os\ncmd = input()\nos.popen(f'ls {cmd}')\n"
        findings = self._scan(src)
        self.assertTrue(any(f["kind"] == "dangerous_shell_exec" for f in findings))


class TestH8FileUploadRisk(unittest.TestCase):
    def _scan(self, src: str) -> list[dict]:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "target.py", src)
            return hacker.run(tmp)

    def test_unvalidated_file_write_flagged(self):
        src = "from pathlib import Path\nname = input()\nPath(name).write_text('content')\n"
        findings = self._scan(src)
        self.assertTrue(any(f["kind"] == "file_storage_risk" for f in findings))


if __name__ == "__main__":
    unittest.main()
