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
    """The Tongue routes through the ONE model gateway (lgwks_model_port), not a
    network provider. Invariants preserved from the old openrouter-seam tests:
    (1) fail-closed when the model can't answer; (2) use the model when it does."""

    def test_tongue_fails_closed_when_model_defers(self):
        # no local model / agent handoff / deferral → no synchronous JSON → skeleton
        import lgwks_model_port
        with mock.patch.object(lgwks_model_port, "reason",
                               return_value={"ok": False, "mode": "deferred", "value": None}):
            self.assertIsNone(lgwks_tongue._generate("prompt", "{}"))

    def test_tongue_parses_local_proposal_json(self):
        # a local generative proposal (mesh-law model) is parsed as JSON
        import lgwks_model_port
        env = {"ok": True, "mode": "generative", "value": {"text": '{"ok": true}'}}
        with mock.patch.object(lgwks_model_port, "reason", return_value=env):
            self.assertEqual(lgwks_tongue._generate("prompt", "{}"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
