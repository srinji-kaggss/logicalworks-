"""Tests for lgwks_schema — schema registry."""

import json
import unittest
from pathlib import Path

import lgwks_schema


class TestSchemaRegistry(unittest.TestCase):
    def test_registry_has_known_schemas(self):
        reg = lgwks_schema._REGISTRY
        self.assertIn("lgwks.spawn.v1", reg)
        self.assertIn("lgwks.manifest.v0", reg)
        self.assertIn("lgwks.do.run.v1", reg)

    def test_registry_entries_have_fields(self):
        reg = lgwks_schema._REGISTRY
        for name, entry in reg.items():
            self.assertIn("name", entry)
            self.assertEqual(entry["name"], name)

    def test_ls_json(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_schema._schema_ls_command(type("Args", (), {"json": True, "domain": None})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertEqual(data["schema"], "lgwks.schema.registry.v0")
            self.assertGreater(data["count"], 0)
            self.assertIsInstance(data["items"], list)
        finally:
            sys.stdout = old_stdout

    def test_ls_filter_domain(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_schema._schema_ls_command(type("Args", (), {"json": True, "domain": "lgwks.spawn"})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertGreater(data["count"], 0)
            for item in data["items"]:
                self.assertTrue(item["name"].startswith("lgwks.spawn"))
        finally:
            sys.stdout = old_stdout

    def test_show_known_schema(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_schema._schema_show_command(type("Args", (), {"name": "lgwks.spawn.v1", "json": True})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertTrue(data["ok"])
            self.assertEqual(data["schema"]["name"], "lgwks.spawn.v1")
        finally:
            sys.stdout = old_stdout

    def test_show_unknown_schema(self):
        import io, sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            rc = lgwks_schema._schema_show_command(type("Args", (), {"name": "lgwks.nonexistent.v99", "json": False})())
            self.assertEqual(rc, 1)
            err = sys.stderr.getvalue()
            self.assertIn("unknown schema", err)
        finally:
            sys.stderr = old_stderr

    def test_show_json_unknown(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_schema._schema_show_command(type("Args", (), {"name": "lgwks.nonexistent.v99", "json": True})())
            self.assertEqual(rc, 1)
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertFalse(data["ok"])
            self.assertIn("error", data)
        finally:
            sys.stdout = old_stdout

    def test_ls_tty_output(self):
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            rc = lgwks_schema._schema_ls_command(type("Args", (), {"json": False, "domain": None})())
            self.assertEqual(rc, 0)
            output = sys.stdout.getvalue()
            self.assertIn("schema(s) registered", output)
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
