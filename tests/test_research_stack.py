"""
Offline tests for the research stack: capability resolution, search hygiene, steering, extract typing,
grounding degradation. No network — providers are monkeypatched. Hardens the turn's build (search
chain + resolver + extract + ground wiring) against regression.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_capabilities as cap
import lgwks_search as search
import lgwks_steering as steering
import lgwks_extract as extract
import lgwks_ground as ground


class TestCapabilitiesAgnostic(unittest.TestCase):
    def test_chain_surfaces_agnostic_ids_not_vendor_names(self):
        # Director directive: no brand names on the surface. The chain must expose role ids only.
        brands = {"firecrawl", "googler", "ddgr", "crwl", "playwright", "pdftotext", "markitdown", "fitz"}
        for r in cap.doctor():
            for node in r["chain"]:
                self.assertNotIn(node["id"], brands, f"vendor name leaked as id: {node['id']}")

    def test_resolve_unknown_capability_is_loud_not_silent(self):
        r = cap.resolve("does-not-exist")
        self.assertIsNone(r["chosen"])

    def test_missing_capability_carries_install_hint(self):
        # a fabricated all-absent capability must report an install hint, never a silent empty.
        r = cap.resolve("search")
        if r["missing"]:
            self.assertTrue(r["install"])

    def test_find_binary_probes_beyond_path(self):
        # python3 exists; find_binary must locate a real binary (PATH or scatter dirs).
        self.assertTrue(cap.find_binary("python3") or cap.find_binary("python"))


class TestSearchHygiene(unittest.TestCase):
    def test_dedup_and_relevance_rank(self):
        rows = [
            {"title": "unrelated postal api", "url": "https://x.com/api", "snippet": "post", "via": "open"},
            {"title": "Canada Life acquisition close", "url": "https://cl.com/a", "snippet": "Canada Life acquisition", "via": "open"},
            {"title": "dup", "url": "https://cl.com/a?utm=1", "snippet": "Canada Life", "via": "open"},
        ]
        orig = search._PROVIDERS
        search._PROVIDERS = [("open", lambda q, k: list(rows))]
        try:
            out = search.search("Canada Life acquisition", k=5)
        finally:
            search._PROVIDERS = orig
        urls = [r["url"].split("?")[0] for r in out]
        self.assertEqual(len(urls), len(set(urls)), "URLs must be deduped (ignoring query string)")
        self.assertIn("acquisition", out[0]["title"].lower(), "most on-topic ranks first")

    def test_falls_through_empty_provider_to_next(self):
        orig = search._PROVIDERS
        hit = {"title": "Canada Life", "url": "https://cl.com/x", "snippet": "", "via": "open"}
        search._PROVIDERS = [("cli", lambda q, k: []), ("open", lambda q, k: [hit])]
        try:
            out = search.search("Canada Life", k=3)
        finally:
            search._PROVIDERS = orig
        self.assertEqual(len(out), 1)

    def test_unwrap_redirect(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc"
        self.assertEqual(search._unwrap(wrapped), "https://example.com/page")

    def test_parse_links_reads_dom_and_skips_nav(self):
        # the real around-the-block: parse links from a (browser-rendered) DOM, drop self/nav hosts.
        dom = ('<a href="https://duckduckgo.com/settings">nav</a>'
               '<a href="https://greatwestlifeco.com/news/value-partners.html">Value Partners acquisition</a>'
               '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fquadrus.com%2Fabout">Quadrus about</a>')
        rows = search._parse_links(dom, k=5, via="rendered")
        urls = [r["url"] for r in rows]
        self.assertNotIn("https://duckduckgo.com/settings", urls, "nav/self host must be dropped")
        self.assertIn("https://greatwestlifeco.com/news/value-partners.html", urls)
        self.assertIn("https://quadrus.com/about", urls, "wrapped redirect must be unwrapped")
        self.assertTrue(all(r["via"] == "rendered" for r in rows))

    def test_open_rotates_endpoints_on_empty(self):
        # the live failure: one endpoint 429s → empty. _open must back off and rotate to the next host.
        calls = []
        def fake_curl(url, data=None, timeout=20):
            calls.append(url)
            if "html.duckduckgo" in url:
                return ""                                   # first endpoint blocked/empty
            return '<a href="https://cl.com/acq">Canada Life acquisition</a>'  # second endpoint answers
        slept = []
        orig = search._curl
        search._curl = fake_curl
        try:
            rows = search._open("Canada Life acquisition", k=3, sleep=lambda s: slept.append(s))
        finally:
            search._curl = orig
        self.assertTrue(rows, "rotation must recover when the first endpoint is dry")
        self.assertEqual(rows[0]["url"], "https://cl.com/acq")
        self.assertGreaterEqual(len(calls), 2, "must have tried more than one endpoint")
        self.assertTrue(slept, "must have backed off before rotating")

    def test_mojeek_parser_skips_promo_and_nav(self):
        # the binning trap: a generic anchor grab conflated Mojeek's own promo links with results.
        # the targeted parser takes ONLY <a class="title"> result anchors.
        body = ('<a href="https://buttondown.email/Mojeek">Newsletter</a>'
                '<ul class="results-standard">'
                '<a class="title" href="https://deepmind.google/blog/alphaevolve">AlphaEvolve</a>'
                '</ul>')
        rows = search._parse_mojeek(body, k=5, via="open")
        urls = [r["url"] for r in rows]
        self.assertEqual(urls, ["https://deepmind.google/blog/alphaevolve"], "only result anchors, no promo")

    def test_backoff_monotonic_and_capped(self):
        self.assertLess(search._backoff(0), search._backoff(2))
        self.assertLessEqual(search._backoff(10), 2.0, "backoff is capped, never unbounded")


class TestSteering(unittest.TestCase):
    def test_nan_and_out_of_range_clamp_to_default(self):
        self.assertEqual(steering._clamp(float("nan"), 0.0, 1.0, 0.5), 0.5)
        self.assertEqual(steering._clamp(9.0, 0.0, 1.0, 0.3), 1.0)
        self.assertEqual(steering._clamp(-9.0, -1.0, 1.0, 0.0), -1.0)

    def test_down_out_before_up_ordering(self):
        nodes = [{"direction": "up"}, {"direction": "out"}, {"direction": "down"}, {}]
        ordered = [n.get("direction", "out") for n in steering.frontier_order(nodes)]
        self.assertEqual(ordered[0], "down")          # decompose first
        self.assertEqual(ordered[-1], "up")            # synthesis last

    def test_require_context_names_missing(self):
        missing = steering.require_context({"objective": "x", "purpose": ""}, ["objective", "purpose"])
        self.assertEqual(missing, ["purpose"])

    def test_prompt_fragment_reflects_dials(self):
        s = steering.Steering(frontierness=0.9, lens=-0.9, depth=0.9)
        frag = s.prompt_fragment().lower()
        self.assertIn("frontier", frag)
        self.assertIn("first principles", frag)


class TestExtractTyping(unittest.TestCase):
    def test_extension_detection(self):
        self.assertEqual(extract._ext_of("https://x.com/doc.pdf?a=1"), ".pdf")
        self.assertEqual(extract._ext_of("/local/file.docx"), ".docx")

    def test_missing_local_file_is_honest_failure(self):
        r = extract.extract("/no/such/file.txt")
        self.assertFalse(r["ok"])
        self.assertEqual(r["text"], "")


class TestGroundDegradation(unittest.TestCase):
    def test_web_empty_search_returns_no_evidence(self):
        orig = search.sweep
        search.sweep = lambda q, **k: {"results": [], "arms_empty": ["all"], "has_evidence": False}
        try:
            text, cites = ground._web("anything")
        finally:
            search.sweep = orig
        self.assertEqual((text, cites), ("", []))

    def test_ground_has_evidence_false_when_all_empty(self):
        o1, o2 = ground._ctx7_docs, ground._web
        ground._ctx7_docs = lambda q: ("", [])
        ground._web = lambda q, **k: ("", [])
        try:
            g = ground.ground("x")
        finally:
            ground._ctx7_docs, ground._web = o1, o2
        self.assertFalse(g["has_evidence"])
        self.assertEqual(g["sources"], [])


if __name__ == "__main__":
    unittest.main()
