"""Real regression tests for lgwks_redact.scrub() — credential value redaction."""

from __future__ import annotations

import lgwks_redact


def test_scrub_redacts_api_key():
    """A string containing an api_key credential must have the value redacted."""
    input_str = 'api_key="sk-abc12345678"'
    result = lgwks_redact.scrub(input_str)
    assert "[REDACTED]" in result, (
        f"Expected [REDACTED] in output but got: {result!r}"
    )


def test_scrub_passes_plain_text_unchanged():
    """A plain string with no secrets must pass through unchanged."""
    input_str = "hello world, nothing to see here"
    result = lgwks_redact.scrub(input_str)
    assert result == input_str, (
        f"Expected unchanged output but got: {result!r}"
    )
