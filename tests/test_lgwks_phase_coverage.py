"""
Test coverage for lgwks_phase module.
"""

from lgwks_phase import PhaseResult, verdict_from_phases

def test_all_passing_phases():
    # Create a list of PhaseResult instances with exit_code 0 (passing)
    phases = [
        PhaseResult(name="phase1", ok=True, exit_code=0),
        PhaseResult(name="phase2", ok=True, exit_code=0),
        PhaseResult(name="phase3", ok=True, exit_code=0)
    ]
    # Assert that verdict_from_phases returns "pass"
    assert verdict_from_phases(phases) == "pass"

def test_one_failing_phase():
    # Create a list of PhaseResult instances with at least one failing phase (exit_code 1, 2, 3, or 4)
    phases = [
        PhaseResult(name="phase1", ok=True, exit_code=0),
        PhaseResult(name="phase2", ok=False, exit_code=1),  # Using exit_code 1 for 'danger'
        PhaseResult(name="phase3", ok=True, exit_code=0)
    ]
    # Assert that verdict_from_phases returns "danger" (or "deny", "degraded", "error" based on worst exit code)
    assert verdict_from_phases(phases) == "danger"
