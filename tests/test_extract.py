"""Tests for lgwks_extract — auth-hardening, redirect safety, format extraction."""

from __future__ import annotations

import io
import unittest
import urllib.error
import urllib.request
from http.client import HTTPMessage

import lgwks_extract as extract


class MockFp:
    pass


def _make_request(url: str, headers: dict | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, headers=headers or {})


def _make_headers() -> HTTPMessage:
    return HTTPMessage(io.BytesIO(b""))


class TestSafeRedirectHandler(unittest.TestCase):
    """Issue #14: auth headers must NOT follow cross-host redirects."""

    def test_same_host_redirect_keeps_auth(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("https://example.com/page", {"Authorization": "Bearer abc123"})
        new = handler.redirect_request(req, MockFp(), 302, "Found", _make_headers(),
                                         "https://example.com/other")
        assert new is not None
        assert new.headers.get("Authorization") == "Bearer abc123"

    def test_cross_host_redirect_strips_auth(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("https://example.com/page", {"Authorization": "Bearer abc123", "Cookie": "session=xyz", "Accept": "text/html"})
        new = handler.redirect_request(req, MockFp(), 302, "Found", _make_headers(),
                                         "https://evil.com/steal")
        assert new is not None
        assert "Authorization" not in new.headers
        assert "Cookie" not in new.headers
        # benign headers should survive (Accept is not a credential header)
        assert "Accept" in new.headers

    def test_cross_host_redirect_strips_case_insensitive(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("https://example.com/page", {"authorization": "Bearer abc123", "COOKIE": "session=xyz"})
        new = handler.redirect_request(req, MockFp(), 302, "Found", _make_headers(),
                                         "https://evil.com/steal")
        assert new is not None
        assert "authorization" not in new.headers
        assert "COOKIE" not in new.headers

    def test_blocked_redirect_target_raises(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("https://example.com/page", {"Authorization": "Bearer abc123"})
        try:
            handler.redirect_request(req, MockFp(), 302, "Found", _make_headers(),
                                     "http://127.0.0.1/secret")
            raise AssertionError("Expected HTTPError for blocked redirect")
        except urllib.error.HTTPError as e:
            assert e.code == 302
            assert "blocked" in str(e.reason).lower()

    def test_scheme_change_same_host_keeps_auth(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("http://example.com/page", {"Authorization": "Bearer abc123"})
        new = handler.redirect_request(req, MockFp(), 301, "Moved", _make_headers(),
                                         "https://example.com/page")
        assert new is not None
        assert new.headers.get("Authorization") == "Bearer abc123"

    def test_port_change_same_host_keeps_auth(self):
        handler = extract._SafeRedirectHandler()
        req = _make_request("https://example.com:8080/page", {"Authorization": "Bearer abc123"})
        new = handler.redirect_request(req, MockFp(), 302, "Found", _make_headers(),
                                         "https://example.com:9090/page")
        assert new is not None
        assert new.headers.get("Authorization") == "Bearer abc123"


class TestRemoteAllowed(unittest.TestCase):
    def test_blocks_private_ips(self):
        assert not extract._remote_allowed("http://127.0.0.1/")
        assert not extract._remote_allowed("http://192.168.1.1/")
        assert not extract._remote_allowed("http://10.0.0.1/")

    def test_allows_public_hosts(self):
        assert extract._remote_allowed("https://example.com/")
        assert extract._remote_allowed("https://duckduckgo.com/")

    def test_blocks_localhost(self):
        assert not extract._remote_allowed("http://localhost/")
        assert not extract._remote_allowed("http://foo.localhost/")


class TestExtOf(unittest.TestCase):
    def test_url_paths(self):
        assert extract._ext_of("https://example.com/file.pdf") == ".pdf"
        assert extract._ext_of("https://example.com/path/doc.docx") == ".docx"

    def test_local_paths(self):
        assert extract._ext_of("/tmp/file.txt") == ".txt"
        assert extract._ext_of("/tmp/archive.tar.gz") == ".gz"
