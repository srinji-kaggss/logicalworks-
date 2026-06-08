"""
Tests for U7: lgwks_bot_optimizer.
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lgwks_graph as gmod
import lgwks_bot_optimizer as optimizer
import lgwks_project_artifacts as artifacts


def _write(tmp: Path, name: str, src: str) -> str:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return name


class TestOptimizerBot(unittest.TestCase):

    def test_missing_graph_cache_emits_failure(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "a.py", "x = 1\n")
            findings = optimizer.run(tmp, graph=None)
            self.assertTrue(findings)
            self.assertEqual(findings[0]["kind"], "analyzer_failure")
            ok, errs = artifacts.validate_bot_record(findings[0])
            self.assertTrue(ok, f"invalid record: {errs}")

    def test_god_module_detected(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # Create a large file (over 500 lines)
            large_src = "class LargeClass:\n" + "".join(f"    def method_{i}(self): pass\n" for i in range(520))
            _write(tmp, "god.py", large_src)
            _write(tmp, "a.py", "import god\n")
            _write(tmp, "b.py", "import god\n")
            _write(tmp, "c.py", "import god\n")
            _write(tmp, "d.py", "import god\n")

            # Build graph with high in-degree to god.py and bridging to d.py
            graph = gmod.Graph()
            for n in ["god.py", "a.py", "b.py", "c.py", "d.py"]:
                graph.nodes[n] = gmod.Node(id=n, kind="file")
            graph.edges = [
                gmod.Edge("a.py", "god.py", "import"),
                gmod.Edge("b.py", "god.py", "import"),
                gmod.Edge("c.py", "god.py", "import"),
                gmod.Edge("god.py", "d.py", "import"),
            ]

            findings = optimizer.run(tmp, graph=graph)
            # Find god_module finding
            god_finds = [f for f in findings if f["kind"] == "god_module"]
            self.assertTrue(god_finds)
            self.assertEqual(god_finds[0]["target"]["id"], "god.py")
            
            # Check schema validation
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}")

    def test_split_candidate_detected(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # defines > 8 public symbols and line count > 350
            src = "\n".join(f"def func_{i}(): pass" for i in range(12)) + "\n" + "\n" * 360
            _write(tmp, "oversized.py", src)

            # disjoint clusters: build_* and validate_* and run_*
            cluster_src = """\
                def build_one(): pass
                def build_two(): pass
                def validate_one(): pass
                def validate_two(): pass
                def run_one(): pass
                def run_two(): pass
            """
            _write(tmp, "clustered.py", cluster_src)

            graph = gmod.Graph()
            graph.nodes["oversized.py"] = gmod.Node(id="oversized.py", kind="file")
            graph.nodes["clustered.py"] = gmod.Node(id="clustered.py", kind="file")

            findings = optimizer.run(tmp, graph=graph)
            split_finds = [f for f in findings if f["kind"] == "split_candidate"]
            self.assertTrue(len(split_finds) >= 2)
            targets = {f["target"]["id"] for f in split_finds}
            self.assertIn("oversized.py", targets)
            self.assertIn("clustered.py", targets)

            # Check schema validation
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}")

    def test_token_waste_duplicate_import(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # 5 files importing lgwks_project_artifacts directly
            for i in range(5):
                _write(tmp, f"f_{i}.py", "import lgwks_project_artifacts\n")

            graph = gmod.Graph()
            for i in range(5):
                nid = f"f_{i}.py"
                graph.nodes[nid] = gmod.Node(id=nid, kind="file", imports=("lgwks_project_artifacts",))
                graph.edges.append(gmod.Edge(nid, "lgwks_project_artifacts.py", "import"))

            findings = optimizer.run(tmp, graph=graph)
            import_finds = [f for f in findings if f["kind"] == "token_waste_duplicate_import"]
            self.assertTrue(import_finds)
            self.assertEqual(import_finds[0]["target"]["id"], "f_0.py")

            # Check schema validation
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}")

    def test_token_waste_reimplemented_utility_and_reuse_candidate(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # Re-implemented utility in different files
            _write(tmp, "a.py", "def my_cool_helper_function(): pass\n")
            _write(tmp, "b.py", "def my_cool_helper_function(): pass\n")
            _write(tmp, "c.py", "def my_cool_helper_function(): pass\n")

            graph = gmod.Graph()
            graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file", defines=("my_cool_helper_function",))
            graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file", defines=("my_cool_helper_function",))
            graph.nodes["c.py"] = gmod.Node(id="c.py", kind="file", defines=("my_cool_helper_function",))

            findings = optimizer.run(tmp, graph=graph)
            reimpl = [f for f in findings if f["kind"] == "token_waste_reimplemented_utility"]
            reuse = [f for f in findings if f["kind"] == "reuse_candidate"]
            self.assertTrue(reimpl)
            self.assertTrue(reuse)

            # Check schema validation
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}")

    def test_dead_parameter(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "a.py", "def my_func(a, b, c):\n    return a + b\n")

            graph = gmod.Graph()
            graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")

            findings = optimizer.run(tmp, graph=graph)
            dead_finds = [f for f in findings if f["kind"] == "dead_parameter"]
            self.assertTrue(dead_finds)
            self.assertEqual(dead_finds[0]["links"]["symbol"], "my_func")

            # Check schema validation
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}")

    def test_subset_mode(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "a.py", "def my_func(a, b, c):\n    return a + b\n")
            _write(tmp, "b.py", "def other_func(x, y, z):\n    return x + y\n")

            graph = gmod.Graph()
            graph.nodes["a.py"] = gmod.Node(id="a.py", kind="file")
            graph.nodes["b.py"] = gmod.Node(id="b.py", kind="file")

            findings = optimizer.run(tmp, changed_files=["a.py"], graph=graph)
            targets = {f["target"]["id"] for f in findings}
            self.assertIn("a.py", targets)
            self.assertNotIn("b.py", targets)


if __name__ == "__main__":
    unittest.main()
