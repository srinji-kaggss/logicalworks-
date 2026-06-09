"""Tests for lgwks_codebase — semantic codebase database."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_codebase as cb


class TestCodebaseParsing(unittest.TestCase):
    def _make_repo(self, files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        for name, content in files.items():
            path = d / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return d

    def test_parse_python_function(self):
        repo = self._make_repo({
            "foo.py": "def hello(name: str) -> str:\n    '''Say hello.'''\n    return f'Hello {name}'\n"
        })
        entities, _ = cb.scan_codebase(repo)
        funcs = [e for e in entities if e.kind == "function"]
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "hello")
        self.assertEqual(funcs[0].signature, "def hello(name: str) -> str")
        self.assertEqual(funcs[0].docstring, "Say hello.")

    def test_parse_python_class(self):
        repo = self._make_repo({
            "bar.py": "class Foo:\n    '''A foo.'''\n    def bar(self):\n        pass\n"
        })
        entities, _ = cb.scan_codebase(repo)
        classes = [e for e in entities if e.kind == "class"]
        methods = [e for e in entities if e.kind == "method"]
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].name, "Foo")
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0].name, "bar")
        self.assertEqual(methods[0].parent, "Foo")

    def test_parse_python_module(self):
        repo = self._make_repo({
            "baz.py": "x = 1\n"
        })
        entities, _ = cb.scan_codebase(repo)
        modules = [e for e in entities if e.kind == "module"]
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].name, "baz")

    def test_parse_markdown(self):
        repo = self._make_repo({
            "readme.md": "# Title\n\nSome text.\n\n## Section\n\nMore text.\n"
        })
        entities, _ = cb.scan_codebase(repo)
        docs = [e for e in entities if e.kind == "doc"]
        self.assertGreaterEqual(len(docs), 1)
        names = [d.name for d in docs]
        self.assertIn("Title", names)

    def test_parse_config(self):
        repo = self._make_repo({
            "config.json": '{"key": "value"}\n'
        })
        entities, _ = cb.scan_codebase(repo)
        configs = [e for e in entities if e.kind == "config"]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "config.json")

    def test_skip_dirs(self):
        repo = self._make_repo({
            "__pycache__/cached.pyc": "bad",
            "good.py": "x = 1\n"
        })
        entities, _ = cb.scan_codebase(repo)
        self.assertTrue(all("__pycache__" not in e.file for e in entities))

    def test_relations_imports(self):
        repo = self._make_repo({
            "a.py": "import os\nimport json\n\ndef f():\n    pass\n"
        })
        entities, relations = cb.scan_codebase(repo)
        imports = [r for r in relations if r.kind == "imports"]
        self.assertGreaterEqual(len(imports), 1)
        targets = {r.target for r in imports}
        self.assertIn("os", targets)

    def test_relations_calls(self):
        repo = self._make_repo({
            "b.py": "def helper():\n    pass\n\ndef main():\n    helper()\n"
        })
        entities, relations = cb.scan_codebase(repo)
        calls = [r for r in relations if r.kind == "calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].target, [e for e in entities if e.name == "helper"][0].id)


class TestCodebaseIndex(unittest.TestCase):
    def test_build_index_creates_files(self):
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "test.py").write_text("def foo(): pass\n", encoding="utf-8")

        # Temporarily override DB_DIR
        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            meta = cb.build_index(d)
            self.assertTrue((cb.DB_DIR / "entities.jsonl").exists())
            self.assertTrue((cb.DB_DIR / "relations.jsonl").exists())
            self.assertTrue((cb.DB_DIR / "index.json").exists())
            self.assertEqual(meta.schema, cb._SCHEMA)
            self.assertGreater(meta.entity_count, 0)
        finally:
            cb.DB_DIR = orig_db


class TestCodebaseSearch(unittest.TestCase):
    def test_search_finds_function(self):
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "api.py").write_text("def get_user(user_id: int) -> dict:\n    '''Fetch user.'''\n    pass\n", encoding="utf-8")

        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            cb.build_index(d)
            results = cb.search("fetch user", top_k=5)
            self.assertGreater(len(results), 0)
            names = {r["name"] for r in results}
            self.assertIn("get_user", names)
        finally:
            cb.DB_DIR = orig_db

    def test_search_kind_filter(self):
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "x.py").write_text("class Foo:\n    pass\n\ndef bar():\n    pass\n", encoding="utf-8")

        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            cb.build_index(d)
            results = cb.search("foo", top_k=5, kind_filter="class")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["kind"], "class")
        finally:
            cb.DB_DIR = orig_db


class TestCodebaseStatus(unittest.TestCase):
    def test_status_not_indexed(self):
        orig_db = cb.DB_DIR
        cb.DB_DIR = Path(tempfile.mkdtemp(prefix="lgwks-cb-status-"))
        try:
            st = cb.status()
            self.assertFalse(st.get("indexed", True))
        finally:
            cb.DB_DIR = orig_db

    def test_status_indexed(self):
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "x.py").write_text("def f(): pass\n", encoding="utf-8")

        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            cb.build_index(d)
            st = cb.status()
            self.assertTrue(st.get("indexed", False) or "entity_count" in st)
            self.assertEqual(st["schema"], cb._SCHEMA)
        finally:
            cb.DB_DIR = orig_db


class TestCodebaseCLI(unittest.TestCase):
    def test_cli_index_json(self):
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "x.py").write_text("def f(): pass\n", encoding="utf-8")

        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            rc = cb._codebase_index_command(type("Args", (), {"json": True})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertEqual(data["schema"], cb._SCHEMA)
        finally:
            sys.stdout = old_stdout
            cb.DB_DIR = orig_db

    def test_cli_search_json(self):
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        d = Path(tempfile.mkdtemp(prefix="lgwks-cb-test-"))
        (d / "x.py").write_text("def helper():\n    '''Help me.'''\n    pass\n", encoding="utf-8")

        orig_db = cb.DB_DIR
        cb.DB_DIR = d / "cbdb"
        try:
            cb.build_index(d)
            rc = cb._codebase_search_command(type("Args", ()
                , {"query": "help", "json": True, "top_k": 5, "kind": None})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertIn("results", data)
        finally:
            sys.stdout = old_stdout
            cb.DB_DIR = orig_db


if __name__ == "__main__":
    unittest.main()
