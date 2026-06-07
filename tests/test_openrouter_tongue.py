import importlib
import unittest
from unittest import mock

import lgwks_openrouter
import lgwks_tongue


class TestOpenRouterModelSelection(unittest.TestCase):
    def test_default_chain_uses_free_non_gemma_models(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            importlib.reload(lgwks_openrouter)
            models = lgwks_openrouter._models_to_try(None)

        self.assertEqual(models[0], "nvidia/nemotron-3-ultra-550b-a55b:free")
        self.assertIn("poolside/laguna-m.1:free", models)
        self.assertIn("moonshotai/kimi-k2.6:free", models)
        self.assertTrue(all("gemma" not in model.lower() for model in models))
        self.assertTrue(all(model.endswith(":free") for model in models))

    def test_explicit_model_is_used_alone(self):
        self.assertEqual(
            lgwks_openrouter._models_to_try("anthropic/claude-sonnet-4.5"),
            ["anthropic/claude-sonnet-4.5"],
        )


class TestTongueProviderSeam(unittest.TestCase):
    def test_tongue_fails_closed_without_openrouter(self):
        with mock.patch.object(lgwks_tongue.lgwks_openrouter, "is_configured", return_value=False):
            self.assertIsNone(lgwks_tongue._generate("prompt", "{}"))

    def test_tongue_uses_openrouter_when_configured(self):
        with mock.patch.object(lgwks_tongue.lgwks_openrouter, "is_configured", return_value=True), \
             mock.patch.object(lgwks_tongue.lgwks_openrouter, "generate_json", return_value={"ok": True}) as gen:
            self.assertEqual(lgwks_tongue._generate("prompt", "{}"), {"ok": True})
        gen.assert_called_once_with("prompt", "{}")


if __name__ == "__main__":
    unittest.main()
