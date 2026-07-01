"""Coverage import test for lgwks_site_profile."""

from __future__ import annotations

import unittest

import lgwks_site_profile


class TestLgwksSiteProfileCoverage(unittest.TestCase):
    """Minimal coverage test for lgwks_site_profile.load_profile."""

    def test_load_profile_missing_host_returns_default_dict(self) -> None:
        """load_profile must return a dict gracefully when no profile exists."""
        result = lgwks_site_profile.load_profile(
            "this-host-does-not-exist-12345.example.com"
        )
        self.assertIsInstance(result, dict)
        self.assertIn("host", result)
        self.assertIn("dom", result)
        self.assertIn("crawl", result)


if __name__ == "__main__":
    unittest.main()
