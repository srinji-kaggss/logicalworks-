"""Tests for lgwks_lfm2_extract — strict schema fill via LFM2-Extract.

All tests run without a live model — they use monkeypatching to isolate the
subprocess call. The safety invariant is: non-conformant output is never returned.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lgwks_lfm2_extract as lfm


STRICT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["title", "summary", "entities", "topics"],
    "additionalProperties": False,
    "properties": {
        "title":    {"type": "string", "maxLength": 256},
        "summary":  {"type": "string", "maxLength": 1024},
        "entities": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "topics":   {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "language": {"type": "string", "maxLength": 10},
    },
}

VALID_FILL = {
    "title": "Example Page",
    "summary": "This is a test page about widgets.",
    "entities": ["Acme Corp", "Widget 3000"],
    "topics": ["manufacturing", "widgets"],
    "language": "en",
}

PAGE_DICT = {
    "title": "Example Page",
    "url": "https://example.com/page",
    "text": "This is a test page about widgets from Acme Corp. Widget 3000 is their flagship.",
    "markdown": "",
}


def test_fill_schema_stdlib_fallback_when_llama_cli_absent():
    """No llama-cli binary → stdlib fill, never None."""
    with patch("shutil.which", return_value=None):
        result = lfm.fill_schema(PAGE_DICT, STRICT_SCHEMA)
    assert result is not None
    assert result["source"] == "stdlib"
    assert result["title"] == PAGE_DICT["title"]
    assert isinstance(result["summary"], str)
    assert isinstance(result["entities"], list)
    assert isinstance(result["topics"], list)


def test_fill_schema_stdlib_fallback_when_model_missing(tmp_path):
    """Model file not found → stdlib fill, never None."""
    with patch("shutil.which", return_value="/usr/local/bin/llama-cli"):
        result = lfm.fill_schema(PAGE_DICT, STRICT_SCHEMA, model_path=str(tmp_path / "nonexistent.gguf"))
    assert result is not None
    assert result["source"] == "stdlib"


def test_fill_schema_raises_on_invalid_json_output():
    """Non-JSON stdout → SchemaFillError, not silently swallowed."""
    mock_proc = MagicMock()
    mock_proc.stdout = "not json at all"

    with patch("shutil.which", return_value="/usr/local/bin/llama-cli"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run", return_value=mock_proc):
        with pytest.raises(lfm.SchemaFillError, match="not valid JSON"):
            lfm.fill_schema(PAGE_DICT, STRICT_SCHEMA, model_path="/fake/model.gguf")


def test_fill_schema_raises_on_schema_validation_failure():
    """Valid JSON but missing required fields → SchemaFillError."""
    bad_output = json.dumps({"bad_key": "wrong"})
    mock_proc = MagicMock()
    mock_proc.stdout = bad_output

    with patch("shutil.which", return_value="/usr/local/bin/llama-cli"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run", return_value=mock_proc):
        with pytest.raises(lfm.SchemaFillError):
            lfm.fill_schema(PAGE_DICT, STRICT_SCHEMA, model_path="/fake/model.gguf")


def test_fill_schema_happy_path():
    """Valid fill → returned as dict tagged source=lfm2."""
    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps(VALID_FILL)

    with patch("shutil.which", return_value="/usr/local/bin/llama-cli"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run", return_value=mock_proc):
        result = lfm.fill_schema(PAGE_DICT, STRICT_SCHEMA, model_path="/fake/model.gguf")

    assert result is not None
    for key in ("title", "summary", "entities", "topics"):
        assert key in result
    assert result["title"] == "Example Page"
    assert result["source"] == "lfm2"


def test_find_lfm2_model_returns_none_when_dir_absent(tmp_path):
    result = lfm.find_lfm2_model(str(tmp_path / "no_such_dir"))
    assert result is None


def test_find_lfm2_model_returns_none_when_no_match(tmp_path):
    (tmp_path / "unrelated.gguf").write_text("fake")
    result = lfm.find_lfm2_model(str(tmp_path))
    assert result is None


def test_find_lfm2_model_finds_match(tmp_path):
    model = tmp_path / "LFM2-1.2B-Extract.gguf"
    model.write_text("fake model bytes")
    result = lfm.find_lfm2_model(str(tmp_path))
    assert result == str(model)
