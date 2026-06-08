"""
Tests for U8: lgwks_bot_stress.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import lgwks_bot_stress as stress
import lgwks_project_artifacts as artifacts


class TestStressBot(unittest.TestCase):

    def test_run_stress_scenarios_emits_valid_records(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            # Run the stress bot
            findings = stress.run(tmp, store_path=str(tmp))
            
            # Verify we get some findings (we expect at least missing_lock, cascade_failure, etc. to trigger)
            self.assertTrue(findings)
            
            # Check validator
            for f in findings:
                ok, errs = artifacts.validate_bot_record(f)
                self.assertTrue(ok, f"invalid record: {errs}\n{f}")
                
            # Verify presence of specific kinds
            kinds = {f["kind"] for f in findings}
            self.assertTrue(kinds.intersection({"write_collision", "read_during_write", "missing_lock", "recovery_gap", "cascade_failure"}))


if __name__ == "__main__":
    unittest.main()
