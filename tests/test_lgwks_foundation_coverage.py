import sys

from lgwks_foundation import available


def test_available_returns_expected_shape():
    result = available()
    
    assert set(result.keys()) == {"foundation_models", "natural_language", "platform"}
    assert isinstance(result["foundation_models"], bool)
    assert isinstance(result["natural_language"], bool)
    assert result["platform"] == sys.platform
