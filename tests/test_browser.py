"""Tests for lgwks_browser — auth-hardening, route scoping."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
