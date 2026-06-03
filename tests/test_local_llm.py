from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

import lgwks_local_llm as llm


def test_available_true():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        assert llm.available() is True


def test_available_false():
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        assert llm.available() is False


def test_generate_success():
    mock_data = {
        "response": "Hello world from Qwen!",
        "eval_count": 5
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("lgwks_local_llm.available", return_value=True):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        res = llm.generate("Say hello", model="qwen2.5-coder:1.5b")
        assert res["ok"] is True
        assert res["text"] == "Hello world from Qwen!"
        assert res["tokens"] == 5
        assert res["model"] == "qwen2.5-coder:1.5b"


def test_generate_not_available():
    with patch("lgwks_local_llm.available", return_value=False):
        res = llm.generate("Say hello")
        assert res["ok"] is False
        assert "not available" in res["reason"]
