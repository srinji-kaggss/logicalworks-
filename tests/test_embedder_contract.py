"""#152 — the shared Embedder contract for single-text providers.

`lgwks_apple.embed_one` and `lgwks_openrouter_embed.embed_one` were two parallel
provider functions with the same return contract but no explicit shared interface.
The contract is now named (`lgwks_model_port.Embedder`) and the providers bind to it
statically (under TYPE_CHECKING). This test pins the RUNTIME half of the contract,
which static typing can't prove:

  1. callable with a single `text` arg,
  2. returns list[float] | None,
  3. NEVER raises — returns None when the provider is unavailable/suppressed (so
     callers fail closed without try/except).
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

import lgwks_apple as apple
import lgwks_openrouter_embed as ore
from lgwks_model_port import Embedder


class TestEmbedderProtocol(unittest.TestCase):
    def test_both_providers_are_recognised_as_embedders(self):
        # runtime_checkable structural check (documents the contract surface).
        self.assertIsInstance(apple.embed_one, Embedder)
        self.assertIsInstance(ore.embed_one, Embedder)


class TestUnavailableReturnsNoneNeverRaises(unittest.TestCase):
    def test_apple_unavailable_returns_none(self):
        # No MLX runtime in CI → is_available() False → None, no exception.
        with mock.patch.object(apple, "is_available", return_value=False):
            self.assertIsNone(apple.embed_one("hello"))

    def test_openrouter_suppressed_returns_none(self):
        with mock.patch("lgwks_model_port.models_suppressed", return_value=True):
            self.assertIsNone(ore.embed_one("hello"))

    def test_openrouter_no_key_returns_none(self):
        with mock.patch("lgwks_model_port.models_suppressed", return_value=False), \
             mock.patch.object(ore.lgwks_keyvault, "get_secret", return_value=(None, None)):
            self.assertIsNone(ore.embed_one("hello"))


class TestSuccessPathReturnsListOfFloats(unittest.TestCase):
    def test_openrouter_success_returns_list_float(self):
        payload = json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]}).encode("utf-8")

        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return payload

        with mock.patch("lgwks_model_port.models_suppressed", return_value=False), \
             mock.patch.object(ore.lgwks_keyvault, "get_secret", return_value=("sk-test", None)), \
             mock.patch.object(ore.urllib.request, "urlopen", return_value=_Resp()):
            vec = ore.embed_one("hello")
        assert vec is not None
        self.assertEqual(vec, [0.1, 0.2, 0.3])
        self.assertTrue(all(isinstance(x, float) for x in vec))

    def test_openrouter_malformed_response_returns_none_not_raises(self):
        payload = json.dumps({"unexpected": "shape"}).encode("utf-8")

        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return payload

        with mock.patch("lgwks_model_port.models_suppressed", return_value=False), \
             mock.patch.object(ore.lgwks_keyvault, "get_secret", return_value=("sk-test", None)), \
             mock.patch.object(ore.urllib.request, "urlopen", return_value=_Resp()):
            self.assertIsNone(ore.embed_one("hello"))


if __name__ == "__main__":
    unittest.main()
