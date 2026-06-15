import unittest
import os
import yaml
from pathlib import Path
import lgwks_config

class TestConfig(unittest.TestCase):
    def setUp(self):
        # Clear singleton
        lgwks_config._CONFIG = None
        # Mock paths
        self.test_home = Path("test_home_config.yaml")
        self.test_project = Path("test_project_config.yaml")
        lgwks_config.HOME_CONFIG = self.test_home
        lgwks_config.PROJECT_CONFIG = self.test_project

    def tearDown(self):
        if self.test_home.exists(): self.test_home.unlink()
        if self.test_project.exists(): self.test_project.unlink()
        for k in lgwks_config.ENV_MAP:
            if k in os.environ: del os.environ[k]

    def test_defaults(self):
        cfg = lgwks_config.get_config()
        self.assertEqual(cfg["pipeline"]["recall_k"], 2000)
        self.assertEqual(cfg["_provenance"]["pipeline.recall_k"], "default")

    def test_yaml_override(self):
        self.test_project.write_text(yaml.dump({
            "pipeline": {"recall_k": 1234}
        }))
        cfg = lgwks_config.get_config()
        self.assertEqual(cfg["pipeline"]["recall_k"], 1234)
        self.assertEqual(cfg["_provenance"]["pipeline.recall_k"], str(self.test_project))

    def test_env_override(self):
        os.environ["LGWKS_RECALL_K"] = "9999"
        cfg = lgwks_config.get_config()
        self.assertEqual(cfg["pipeline"]["recall_k"], 9999)
        self.assertEqual(cfg["_provenance"]["pipeline.recall_k"], "env:LGWKS_RECALL_K")

    def test_precedence(self):
        self.test_home.write_text(yaml.dump({"pipeline": {"recall_k": 1}}))
        self.test_project.write_text(yaml.dump({"pipeline": {"recall_k": 2}}))
        os.environ["LGWKS_RECALL_K"] = "3"
        
        cfg = lgwks_config.get_config()
        self.assertEqual(cfg["pipeline"]["recall_k"], 3)
        
        # Now remove env
        lgwks_config._CONFIG = None
        del os.environ["LGWKS_RECALL_K"]
        cfg = lgwks_config.get_config()
        self.assertEqual(cfg["pipeline"]["recall_k"], 2) # project > home

if __name__ == "__main__":
    unittest.main()
