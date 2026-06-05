from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import lgwks_openrouter_embed


class _Resp:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class OpenRouterEmbedTests(unittest.TestCase):
    def test_embed_one_parses_vector(self):
        with patch("lgwks_keyvault.get_secret", return_value=("test-key", "env")):
            with patch("urllib.request.urlopen", return_value=_Resp({"data": [{"embedding": [0.1, -0.2, 0.3]}]})):
                vec = lgwks_openrouter_embed.embed_one("hello", model="nvidia/llama-nemotron-embed-vl-1b-v2:free")
        self.assertEqual(vec, [0.1, -0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
