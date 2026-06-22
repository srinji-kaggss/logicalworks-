"""#223 foundation-bypass — lgwks_clock is the one source for time formatting.

~19 raw `datetime.now()` / `time.strftime()` sites across 9 modules were routed to
canonical lgwks_clock functions. These tests pin the new primitives' contracts and
prove the UTC formatters are byte-identical to the inline expressions they replaced
(determinism checked against a fixed gmtime, so no second-boundary flake).
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from unittest import mock

import lgwks_clock as clock

# A fixed UTC instant for deterministic format checks.
_FIXED = time.struct_time((2026, 6, 14, 12, 5, 9, 6, 165, 0))


class TestFormats(unittest.TestCase):
    def test_now_iso_is_plus0000_second_precision(self):
        s = clock.now_iso()
        self.assertTrue(s.endswith("+00:00"), s)
        # parses and round-trips to an aware UTC datetime
        self.assertEqual(datetime.fromisoformat(s).tzinfo, timezone.utc)

    def test_now_aware_is_utc_aware(self):
        self.assertEqual(clock.now_aware().tzinfo, timezone.utc)

    def test_stamp_compact_shape(self):
        self.assertRegex(clock.stamp_compact(), r"^\d{8}-\d{6}$")

    def test_date_compact_shape(self):
        self.assertRegex(clock.date_compact(), r"^\d{8}$")

    def test_now_human_shape(self):
        self.assertRegex(clock.now_human(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$")


class TestByteIdenticalToReplacedExpressions(unittest.TestCase):
    """Each UTC formatter == the exact inline expression it replaced, under a fixed
    gmtime (so the assertion can't flake across a second tick)."""

    def test_stamp_compact_matches_inline(self):
        with mock.patch.object(clock.time, "gmtime", return_value=_FIXED):
            self.assertEqual(clock.stamp_compact(), time.strftime("%Y%m%d-%H%M%S", _FIXED))

    def test_date_compact_matches_inline(self):
        with mock.patch.object(clock.time, "gmtime", return_value=_FIXED):
            self.assertEqual(clock.date_compact(), time.strftime("%Y%m%d", _FIXED))

    def test_now_human_matches_inline(self):
        with mock.patch.object(clock.time, "gmtime", return_value=_FIXED):
            self.assertEqual(clock.now_human(), time.strftime("%Y-%m-%d %H:%M:%S UTC", _FIXED))


if __name__ == "__main__":
    unittest.main()
