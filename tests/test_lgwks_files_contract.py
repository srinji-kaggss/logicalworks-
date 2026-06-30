"""Contract-pinning tests for lgwks_files path-safety defaults (see module docstring note:
'absolute_local_paths_are_allowed_by_default_for_extract_convert'). These tests PIN current
behavior — they do not assert it is desirable; flipping the default needs separate sign-off."""

import argparse
import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import lgwks_files


def _real_parser_args(verb: str, target: str) -> argparse.Namespace:
    """Build args the same way the real CLI does: lgwks_files.add_parser() registers
    `extract`/`convert` on a real argparse subparser, so this exercises the actual
    --allow-absolute default (True), not a hand-typed stand-in for it."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    lgwks_files.add_parser(sub)
    argv = [verb, target]
    return parser.parse_args(argv)


class TestLgwksFilesContract(unittest.TestCase):
    def test_extract_allow_absolute_by_default(self):
        """extract_command, given the real parser's default args, allows an absolute path
        through _is_safe_path (CLI --allow-absolute default=True overrides the function's
        own allow_absolute=False default)."""
        target = "/absolute/path/does/not/exist" if os.name != "nt" else "C:\\absolute\\path\\does\\not\\exist"
        args = _real_parser_args("extract", target)
        self.assertTrue(getattr(args, "allow_absolute"), "parser default for --allow-absolute changed")

        stderr_output = io.StringIO()
        with redirect_stderr(stderr_output):
            lgwks_files.extract_command(args)

        # The path doesn't exist so extraction itself fails downstream — that's fine and
        # expected. What we pin is that the safety gate did NOT block it as "outside repo".
        error_output = stderr_output.getvalue()
        self.assertNotIn(
            "blocked path", error_output,
            f"Absolute path was blocked despite the CLI's effective allow_absolute=True default. Got: {error_output}",
        )

    def test_is_safe_path_default_param_is_restrictive(self):
        """The function's OWN default (no caller override) is allow_absolute=False — i.e.
        the mismatch is real: _is_safe_path is safety-oriented by default, callers opt out."""
        repo_root = Path(lgwks_files.__file__).resolve().parent
        self.assertFalse(lgwks_files._is_safe_path("/absolute/path", repo_root))


if __name__ == "__main__":
    unittest.main()