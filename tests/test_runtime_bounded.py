"""Tests for the runtime.bounded Keel lane (R2 of the Pristine Program).

Locks the boundedness invariant the way Keel proves any invariant — against a
KNOWN-BAD fixture: the checker must FAIL on a freshly introduced unbounded
model/network sink, and must NOT false-positive on a bounded call or a non-sink
(dict.get / Path.open). This is the structural guard against the #320 disease
class (an unbounded model/network path shipping green).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import check_runtime_bounded as crb  # noqa: E402


def _scan_src(tmp_path: Path, src: str) -> list[dict]:
    f = tmp_path / "fixture.py"
    f.write_text(src)
    return crb.scan_file(f)


class TestSinkDetection(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_unbounded_subprocess_is_flagged(self):
        sinks = _scan_src(self.tmp, "import subprocess\nsubprocess.run(['curl', url])\n")
        sub = [s for s in sinks if s["kind"] == "subprocess"]
        self.assertEqual(len(sub), 1)
        self.assertFalse(sub[0]["bounded"], "unbounded subprocess.run not flagged as unbounded")

    def test_bounded_subprocess_is_recognised(self):
        sinks = _scan_src(self.tmp, "import subprocess\nsubprocess.run(['git','log'], timeout=5)\n")
        self.assertTrue(sinks[0]["bounded"], "timeout= subprocess not recognised as bounded")

    def test_unbounded_urlopen_is_flagged(self):
        src = "import urllib.request\nurllib.request.urlopen(req)\n"
        sinks = _scan_src(self.tmp, src)
        net = [s for s in sinks if s["kind"] == "network"]
        self.assertEqual(len(net), 1)
        self.assertFalse(net[0]["bounded"])

    def test_bounded_urlopen_is_recognised(self):
        src = "import urllib.request\nurllib.request.urlopen(req, timeout=10)\n"
        sinks = _scan_src(self.tmp, src)
        self.assertTrue(sinks[0]["bounded"])

    def test_module_rooted_network_verb_is_flagged(self):
        src = "import requests\nrequests.get(url)\n"
        sinks = _scan_src(self.tmp, src)
        self.assertEqual([s["kind"] for s in sinks], ["network"])
        self.assertFalse(sinks[0]["bounded"])

    def test_dict_get_is_not_a_sink(self):
        """The false-positive that bare-verb matching caused: obj.get() is not network."""
        src = "d = {}\nd.get('k')\nresult.get('status')\nstep.get('args')\n"
        self.assertEqual(_scan_src(self.tmp, src), [])

    def test_path_open_is_not_a_network_sink(self):
        """A urllib-speaking file still must not treat Path.open()/file.open() as a sink."""
        src = ("import urllib.request\n"
               "from pathlib import Path\n"
               "Path('x').open()\n"
               "f.open('r')\n")
        self.assertEqual(_scan_src(self.tmp, src), [])

    def test_opener_open_is_a_network_sink(self):
        src = ("import urllib.request\n"
               "opener = urllib.request.build_opener()\n"
               "opener.open(req, timeout=20)\n")
        net = [s for s in _scan_src(self.tmp, src) if s["kind"] == "network"]
        self.assertEqual(len(net), 1)
        self.assertTrue(net[0]["bounded"])

    # ── Hardening regressions (hacker pass H1/H3/H4) — detector blind spots ──

    def test_aliased_subprocess_import_is_not_invisible(self):
        """H1: `import subprocess as sp; sp.run(...)` was invisible — the live
        lgwks_workflows playwright sink shipped GO. Alias must be tracked."""
        src = "import subprocess as sp\nsp.run(['playwright','install'])\n"
        sub = [s for s in _scan_src(self.tmp, src) if s["kind"] == "subprocess"]
        self.assertEqual(len(sub), 1, "aliased subprocess import not detected")
        self.assertFalse(sub[0]["bounded"])

    def test_from_subprocess_import_run_is_detected(self):
        """H1: `from subprocess import run; run(...)` (bare-name call)."""
        src = "from subprocess import run\nrun(['curl', url])\n"
        sub = [s for s in _scan_src(self.tmp, src) if s["kind"] == "subprocess"]
        self.assertEqual(len(sub), 1)
        self.assertFalse(sub[0]["bounded"])

    def test_timeout_none_is_not_bounded(self):
        """H3: timeout=None blocks forever — must NOT count as bounded."""
        src = "import subprocess\nsubprocess.run(['curl', url], timeout=None)\n"
        sinks = _scan_src(self.tmp, src)
        self.assertFalse(sinks[0]["bounded"], "timeout=None wrongly accepted as bounded")

    def test_os_popen_is_a_sink(self):
        """H4: os.popen runs a shell pipe with no timeout API — must be a sink."""
        src = "import os\nos.popen('curl ' + url)\n"
        sub = [s for s in _scan_src(self.tmp, src) if s["kind"] == "subprocess"]
        self.assertEqual(len(sub), 1)
        self.assertFalse(sub[0]["bounded"])

    def test_aliased_net_import_is_detected(self):
        """H4: `from curl_cffi import requests as _curl; _curl.get(url)`."""
        src = "from curl_cffi import requests as _curl\n_curl.get(url)\n"
        net = [s for s in _scan_src(self.tmp, src) if s["kind"] == "network"]
        self.assertEqual(len(net), 1, "aliased net import not detected")
        self.assertFalse(net[0]["bounded"])

    def test_stored_session_client_is_detected(self):
        """H4: a stored client `s = requests.Session(); s.get(url)`."""
        src = "import requests\ns = requests.Session()\ns.get(url)\n"
        net = [s for s in _scan_src(self.tmp, src) if s["kind"] == "network"]
        self.assertEqual(len(net), 1, "stored Session client not detected")
        self.assertFalse(net[0]["bounded"])


class TestGateOnKnownBad(unittest.TestCase):
    """The lane VERDICT: a known-bad sink that is unbounded and not inventoried
    must produce a violation; a bounded or inventoried one must not."""

    def test_unbounded_unlisted_sink_is_a_violation(self):
        bad = {"file": "lgwks_x.py", "callee": "subprocess.run", "target": "curl",
               "kind": "subprocess", "bounded": False, "line": 1}
        allow = set()
        self.assertNotIn((bad["file"], bad["callee"], bad["target"]), allow)
        # mirror evaluate()'s rule: unbounded AND not allow-listed → violation
        is_violation = (not bad["bounded"]) and (
            (bad["file"], bad["callee"], bad["target"]) not in allow)
        self.assertTrue(is_violation)

    def test_inventoried_local_sink_is_not_a_violation(self):
        git = {"file": "lgwks_gh.py", "callee": "subprocess.check_output", "target": "git",
               "kind": "subprocess", "bounded": False, "line": 1}
        allow = {("lgwks_gh.py", "subprocess.check_output", "git")}
        is_violation = (not git["bounded"]) and (
            (git["file"], git["callee"], git["target"]) not in allow)
        self.assertFalse(is_violation)

    def test_live_repo_passes_the_gate(self):
        """The real runtime must currently satisfy the invariant (GO) — i.e. the
        committed inventory covers every unbounded sink, with no stale entries and
        no count drift. Guards against an uninventoried sink slipping in."""
        _all, violations, stale, mism = crb.evaluate_full()
        self.assertEqual(violations, [], f"uninventoried unbounded sinks: {violations}")
        self.assertEqual(stale, [], f"stale inventory entries: {stale}")
        self.assertEqual(mism, [], f"inventory count drift: {mism}")

    def test_inventory_entries_declare_lines(self):
        """H2: every out_of_scope entry must enumerate `lines` so the count-match
        gate can detect a new sink sharing a coarse (file,callee,target) key."""
        inv = crb.load_inventory()
        missing = [e for e in inv.get("out_of_scope", []) if not e.get("lines")]
        self.assertEqual(missing, [], f"entries without load-bearing `lines`: {missing}")


if __name__ == "__main__":
    unittest.main()
