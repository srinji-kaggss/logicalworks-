from lgwks_fabric_projection import ProjectionResult


def test_projection_result_ok_true_when_no_error():
    result = ProjectionResult(name="vector", applied=True, written=5, error=None)
    assert result.ok is True
    assert result.written == 5


def test_projection_result_ok_false_when_error_set():
    result = ProjectionResult(name="vector", applied=False, error="write failed")
    assert result.ok is False
    assert result.applied is False
