"""Coverage tests for lgwks_coreml.

The module is documented as a graceful no-op when coremltools or the model
file is absent, which is the expected case in this environment.
"""

from __future__ import annotations

import unittest

import lgwks_coreml


class TestLgwksCoremlCoverage(unittest.TestCase):
    def test_classify_page_returns_dict_without_raising(self) -> None:
        result = lgwks_coreml.classify_page("some sample page text")
        self.assertIsInstance(result, dict)

    def test_model_info_returns_dict(self) -> None:
        result = lgwks_coreml.model_info()
        self.assertIsInstance(result, dict)
