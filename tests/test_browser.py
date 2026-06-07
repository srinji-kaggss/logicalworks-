"""Tests for lgwks_browser — auth-hardening, route scoping."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lgwks_browser as browser


class MockRoute:
    def __init__(self):
        self.continued_headers: dict[str, str] | None = None
        self.continued = False

    def continue_(self, headers: dict[str, str] | None = None):
        self.continued_headers = headers
        self.continued = True


class MockRequest:
    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {"User-Agent": "Mozilla/5.0"}


class TestRouteHandler(unittest.TestCase):
    """Issue #14: auth headers must ONLY be sent to the lock host, never to cross-origin
    subresources or redirect destinations."""

    def test_injects_auth_for_lock_host(self):
        handler = browser._route_handler("example.com", {"Authorization": "Bearer abc123"})
        route = MockRoute()
        req = MockRequest("https://example.com/api/data")
        handler(route, req)
        assert route.continued
        assert route.continued_headers is not None
        assert route.continued_headers.get("Authorization") == "Bearer abc123"
        assert route.continued_headers.get("User-Agent") == "Mozilla/5.0"

    def test_strips_auth_for_cross_origin_subresource(self):
        handler = browser._route_handler("example.com", {"Authorization": "Bearer abc123"})
        route = MockRoute()
        req = MockRequest("https://tracker.evil.com/pixel.js")
        handler(route, req)
        assert route.continued
        # route.continue_() was called without headers arg → no override, existing headers unchanged
        assert route.continued_headers is None

    def test_strips_auth_for_different_host_same_tld(self):
        handler = browser._route_handler("api.example.com", {"Authorization": "Bearer abc123"})
        route = MockRoute()
        req = MockRequest("https://cdn.example.com/asset.css")
        handler(route, req)
        assert route.continued
        assert route.continued_headers is None

    def test_case_insensitive_host_match(self):
        handler = browser._route_handler("Example.COM", {"Authorization": "Bearer abc123"})
        route = MockRoute()
        req = MockRequest("https://example.com/page")
        handler(route, req)
        assert route.continued
        assert route.continued_headers.get("Authorization") == "Bearer abc123"

    def test_empty_auth_host_match_continues_with_existing_headers(self):
        """When auth_headers is empty and host matches, handler continues with existing headers."""
        handler = browser._route_handler("example.com", {})
        route = MockRoute()
        req = MockRequest("https://example.com/page")
        handler(route, req)
        assert route.continued
        assert route.continued_headers is not None
        assert "User-Agent" in route.continued_headers
        assert "Authorization" not in route.continued_headers


class TestRemoteAllowed(unittest.TestCase):
    def test_blocks_private(self):
        assert not browser._remote_allowed("http://127.0.0.1/")
        assert not browser._remote_allowed("http://192.168.1.1/")

    def test_allows_public(self):
        assert browser._remote_allowed("https://example.com/")


class TestSessionForUrl(unittest.TestCase):
    def test_returns_none_for_unknown_host(self):
        assert browser._session_for_url("https://unknown.example.com/") is None

    def test_returns_none_for_invalid_url(self):
        assert browser._session_for_url("not-a-url") is None

    def test_cross_domain_cookie_match(self):
        """If session was saved on auth.example.com but cookies are scoped to .example.com,
        portal.example.com should find the session."""
        with tempfile.TemporaryDirectory() as td:
            session_dir = Path(td)
            auth_session = session_dir / "auth-example-com.json"
            auth_session.write_text(
                json.dumps({
                    "cookies": [
                        {
                            "name": "session",
                            "value": "abc123",
                            "domain": ".example.com",
                            "path": "/",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            old = browser._SESSION_DIR
            try:
                browser._SESSION_DIR = session_dir
                result = browser._session_for_url("https://portal.example.com/dashboard")
                assert result == auth_session, f"expected {auth_session}, got {result}"
            finally:
                browser._SESSION_DIR = old

    def test_cross_domain_exact_subdomain_match(self):
        """Cookie domain without leading dot also works."""
        with tempfile.TemporaryDirectory() as td:
            session_dir = Path(td)
            auth_session = session_dir / "login-example-com.json"
            auth_session.write_text(
                json.dumps({
                    "cookies": [
                        {
                            "name": "token",
                            "value": "xyz",
                            "domain": "example.com",
                            "path": "/",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            old = browser._SESSION_DIR
            try:
                browser._SESSION_DIR = session_dir
                result = browser._session_for_url("https://app.example.com/")
                assert result == auth_session
            finally:
                browser._SESSION_DIR = old

    def test_cross_domain_no_match_for_wrong_domain(self):
        """A session for evil.com must NOT match example.com."""
        with tempfile.TemporaryDirectory() as td:
            session_dir = Path(td)
            (session_dir / "evil-com.json").write_text(
                json.dumps({
                    "cookies": [{"name": "s", "value": "v", "domain": "evil.com", "path": "/"}]
                }),
                encoding="utf-8",
            )
            old = browser._SESSION_DIR
            try:
                browser._SESSION_DIR = session_dir
                assert browser._session_for_url("https://example.com/") is None
            finally:
                browser._SESSION_DIR = old

    def test_returns_path_for_existing_session(self):
        with tempfile.TemporaryDirectory() as td:
            session_dir = Path(td)
            # _session_for_url preserves dots in the host, so the file name includes them.
            session_file = session_dir / "portal.fundserv.com.json"
            session_file.write_text('{"cookies": []}', encoding="utf-8")
            with mock.patch.object(browser, "_SESSION_DIR", session_dir):
                result = browser._session_for_url("https://portal.fundserv.com/login")
                self.assertIsNotNone(result)
                self.assertEqual(result, session_dir / "portal.fundserv.com.json")


class TestClickCandidateRanking(unittest.TestCase):
    def test_content_tile_ranks_above_chrome_by_structure(self):
        content_tile = {
            "text": "Any Product Area",
            "text_len": 16,
            "href": "",
            "tag": "button",
            "role": "",
            "area": 80_000,
            "y": 280,
            "depth": 8,
            "in_main": True,
            "in_article": False,
            "in_chrome": False,
            "in_dialog": False,
        }
        chrome_link = {
            "text": "Any Footer Link",
            "text_len": 15,
            "href": "https://example.com/footer",
            "tag": "a",
            "role": "",
            "area": 2_000,
            "y": 780,
            "depth": 8,
            "in_main": False,
            "in_article": False,
            "in_chrome": True,
            "in_dialog": False,
        }
        modal_button = {
            **content_tile,
            "in_main": False,
            "in_dialog": True,
        }

        self.assertGreater(browser._click_candidate_score(content_tile), browser._click_candidate_score(chrome_link))
        self.assertGreater(browser._click_candidate_score(content_tile), browser._click_candidate_score(modal_button))


if __name__ == "__main__":
    unittest.main()
