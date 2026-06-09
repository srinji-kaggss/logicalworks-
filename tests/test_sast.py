"""Tests for lgwks_sast — CFG + flow-sensitive taint over Python.
Each test plants a known vuln (must catch) or clean code (must NOT flag)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lgwks_sast as sast


def _cwes(code):
    return {f["cwe"] for f in sast.analyze_source(code)}


class TestSqlInjection(unittest.TestCase):
    def test_fstring_sql_from_request_is_flagged(self):
        code = (
            "def view(request):\n"
            "    username = request.GET.get('username')\n"
            "    sql = f'SELECT * FROM users WHERE name={username}'\n"
            "    cursor.execute(sql)\n"
        )
        self.assertIn("CWE-89", _cwes(code))

    def test_parameterized_query_not_flagged(self):
        code = (
            "def view(request):\n"
            "    username = request.GET.get('username')\n"
            "    cursor.execute('SELECT * FROM users WHERE name=%s', [username])\n"
        )
        # the SQL string is a literal; the tainted value is a bound param, not interpolated
        self.assertNotIn("CWE-89", _cwes(code))

    def test_sanitized_input_not_flagged(self):
        code = (
            "def view(request):\n"
            "    raw = request.GET.get('id')\n"
            "    safe = int(raw)\n"
            "    cursor.execute(f'SELECT * FROM t WHERE id={safe}')\n"
        )
        self.assertNotIn("CWE-89", _cwes(code))


class TestOtherCwes(unittest.TestCase):
    def test_command_injection(self):
        code = ("def h(request):\n"
                "    cmd = request.GET.get('c')\n"
                "    os.system('ping ' + cmd)\n")
        self.assertIn("CWE-78", _cwes(code))

    def test_code_injection(self):
        code = ("def h(request):\n    eval(request.GET.get('x'))\n")
        self.assertIn("CWE-94", _cwes(code))

    def test_deserialization(self):
        code = ("def h(request):\n    pickle.loads(request.data)\n")
        self.assertIn("CWE-502", _cwes(code))

    def test_ssrf(self):
        code = ("def h(request):\n    url = request.GET.get('u')\n    requests.get(url)\n")
        self.assertIn("CWE-918", _cwes(code))

    def test_path_traversal(self):
        code = ("def h(request):\n    p = request.GET.get('f')\n    open(p).read()\n")
        self.assertIn("CWE-22", _cwes(code))


class TestNoFalsePositives(unittest.TestCase):
    def test_clean_code_silent(self):
        code = ("def add(a, b):\n    total = a + b\n    return total\n")
        self.assertEqual(sast.analyze_source(code), [])

    def test_literal_sink_silent(self):
        code = ("def h():\n    cursor.execute('SELECT 1')\n    os.system('ls')\n")
        self.assertEqual(sast.analyze_source(code), [])

    def test_parse_error_returns_empty(self):
        self.assertEqual(sast.analyze_source("def (("), [])


class TestControlFlow(unittest.TestCase):
    def test_taint_through_if_branch(self):
        code = ("def h(request):\n"
                "    x = request.GET.get('q')\n"
                "    if cond:\n"
                "        y = x\n"
                "        cursor.execute(f'... {y}')\n")
        self.assertIn("CWE-89", _cwes(code))

    def test_deterministic(self):
        code = ("def h(request):\n    eval(request.GET.get('x'))\n")
        self.assertEqual(sast.analyze_source(code), sast.analyze_source(code))


class TestCatalog(unittest.TestCase):
    def test_catalog_live_and_deferred(self):
        s = sast.catalog_status()
        self.assertIn("TAINT-001-SQL-INJECTION", s["live"])
        self.assertIn("MEM-002-USE-AFTER-FREE", s["deferred"])
        self.assertIn("CWE-89", s["cwe_classes_live"])
        self.assertEqual(s["total"], 12)


if __name__ == "__main__":
    unittest.main()
