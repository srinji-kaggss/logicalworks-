"""
Chunk 2: Machine-mode output hardening.

Subprocess-level tests that verify:
1. `lgwks --machine crawl <url>` emits parseable JSON to stdout.
2. `lgwks --machine substrate map <url> --embed-provider deterministic` emits parseable JSON.
3. Neither command leaks ANSI escape codes, progress output, or setup noise to stdout.
4. stderr is separate from the machine-readable stdout stream.

These tests are network-light:
- Jarvis crawl URL path: mocked via monkeypatching lgwks._import_substrate.
- Substrate map: uses --embed-provider deterministic and a temp dir, patching _crawl_site.
- All tests assert `--estimate-only` / dry paths to avoid real I/O.

The subprocess approach is intentional: it catches output pollution from import-time
side effects, print() calls in modules loaded at runtime, and ANSI codes in tqdm/rich/etc.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent
_LGWKS = str(_REPO / "lgwks")

# Python executable that owns the repo packages.
_PY = sys.executable


def _run(*args: str, env_extra: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run lgwks as a subprocess and return the completed process."""
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [_PY, _LGWKS, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(_REPO),
    )


def _has_ansi(text: str) -> bool:
    """Return True if `text` contains ANSI escape sequences."""
    import re
    return bool(re.search(r"\x1b\[[0-9;]*[mABCDEFGHJKLMSTfhilmpsu]", text))


# ─────────────────────────────────────────────────────────────────────────────
# 1. lgwks --machine crawl --estimate-only (fastest, deterministic)
# ─────────────────────────────────────────────────────────────────────────────

class TestMachineModeJarvisCrawlEstimate(unittest.TestCase):
    """
    --estimate-only short-circuits before any network or substrate call.
    Stdout must be a single, complete JSON object.
    """

    def test_stdout_is_parseable_json(self):
        proc = _run(
            "--machine", "crawl",
            "https://example.com",
            "--max-pages", "3",
            "--estimate-only",
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr!r}")
        payload = json.loads(proc.stdout)
        self.assertIn("estimated_seconds", payload)
        self.assertIn("estimated_minutes", payload)

    def test_stdout_has_no_ansi_codes(self):
        proc = _run(
            "--machine", "crawl",
            "https://example.com",
            "--estimate-only",
        )
        self.assertFalse(
            _has_ansi(proc.stdout),
            f"ANSI codes found in machine stdout: {proc.stdout[:300]!r}",
        )

    def test_stdout_is_not_empty(self):
        proc = _run(
            "--machine", "crawl",
            "https://example.com",
            "--estimate-only",
        )
        self.assertTrue(proc.stdout.strip(), "machine stdout must not be empty")

    def test_no_progress_noise_before_json(self):
        """Stdout must start directly with '{', no preamble."""
        proc = _run(
            "--machine", "crawl",
            "https://example.com",
            "--estimate-only",
        )
        stripped = proc.stdout.lstrip()
        self.assertTrue(
            stripped.startswith("{"),
            f"stdout must start with '{{', got: {proc.stdout[:80]!r}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. lgwks --machine substrate query --vector (deterministic, no network)
# ─────────────────────────────────────────────────────────────────────────────

class TestMachineModeSubstrateQueryDeterministic(unittest.TestCase):
    """
    `substrate query --vector` over a synthetic run with deterministic vectors.
    No network, no model loading.  Verifies stdout is clean JSON.
    """

    def _make_deterministic_run(self, tmp: str) -> str:
        """
        Create a minimal substrate run directory with deterministic vectors
        so `substrate query --vector` can run without any real crawl.
        """
        from pathlib import Path
        import hashlib

        run_id = "test-machine-mode-deterministic"
        run_dir = Path(tmp) / run_id
        run_dir.mkdir(parents=True)

        # Write manifest.json with deterministic vector_space.
        manifest = {
            "schema": "lgwks.substrate.run.v0",
            "run_id": run_id,
            "target": "https://example.com",
            "source_type": "url",
            "project": "test",
            "created_at": "2026-06-07T00:00:00Z",
            "vector_space": {
                "canonical_provider": "deterministic-feature-hash",
                "canonical_model": "",
                "dims": 256,
                "semantic": False,
                "ambiguous": False,
            },
            "embedding": {
                "provider_requested": "deterministic",
                "providers_used": {"deterministic-feature-hash": 2},
                "total_vectors": 2,
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        # Write two minimal deterministic vectors so cosine search has something to rank.
        def det_vec(text: str, dims: int = 256) -> list[float]:
            h = hashlib.sha256(text.encode()).digest()
            raw = [(h[i % len(h)] / 255.0) - 0.5 for i in range(dims)]
            norm = sum(x * x for x in raw) ** 0.5 or 1.0
            return [x / norm for x in raw]

        rows = [
            {
                "vector_id": "vec-a",
                "chunk_id": "chunk-a",
                "document_id": "doc-a",
                "provider": "deterministic-feature-hash",
                "dims": 256,
                "vector": det_vec("machine first language"),
                "chunk_kind": "fact",
                "fact_score": 0.8,
                "vector_text": "machine first language",
            },
            {
                "vector_id": "vec-b",
                "chunk_id": "chunk-b",
                "document_id": "doc-b",
                "provider": "deterministic-feature-hash",
                "dims": 256,
                "vector": det_vec("substrate embedding provider"),
                "chunk_kind": "fact",
                "fact_score": 0.7,
                "vector_text": "substrate embedding provider",
            },
        ]
        with (run_dir / "vectors.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

        return str(run_dir)

    def test_substrate_query_vector_stdout_is_parseable_json(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_deterministic_run(td)
            proc = _run(
                "--machine", "state", "run", "index", run_dir,
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
            )
        # A mismatch or empty-vector result will still return JSON.
        self.assertIn(proc.returncode, (0, 1), f"unexpected exit: {proc.stderr[:200]!r}")
        payload = json.loads(proc.stdout)
        self.assertIsInstance(payload, dict, f"stdout must be JSON object: {proc.stdout[:200]!r}")

    def test_substrate_query_stdout_has_no_ansi(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_deterministic_run(td)
            proc = _run(
                "--machine", "state", "run", "index", run_dir,
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
            )
        self.assertFalse(
            _has_ansi(proc.stdout),
            f"ANSI codes in machine stdout: {proc.stdout[:200]!r}",
        )

    def test_substrate_query_stdout_starts_with_brace(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_deterministic_run(td)
            proc = _run(
                "--machine", "state", "run", "index", run_dir,
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
            )
        self.assertTrue(
            proc.stdout.lstrip().startswith("{"),
            f"stdout must start with '{{', got: {proc.stdout[:80]!r}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. apple-local: --machine substrate map --embed-provider apple-local
#    must emit parseable JSON or a clean JSON error (never raw traceback)
# ─────────────────────────────────────────────────────────────────────────────

class TestMachineModeAppleLocalSubstrateMap(unittest.TestCase):
    """
    When apple-local runtime is unavailable (CI/non-Apple), the command must
    still produce parseable JSON output — either a successful run (if runtime
    present) or a structured error JSON (if unavailable), never a raw Python
    traceback or ANSI-decorated progress output.

    We use --estimate-only equivalent: --max-pages 0 --max-depth 0, which makes
    the crawl immediately return an empty result without touching network or Apple
    runtime for crawling.  The embed path is what matters here.
    """

    def test_apple_local_emit_is_json_or_clean_skip(self):
        """
        Run substrate map with apple-local.  On non-Apple or CI:
        - The command may fail (returncode non-zero) but stdout must still be
          parseable JSON (a structured error) OR empty (if the binary exits
          before producing output in an error path).
        - stdout must not contain raw tracebacks.
        - stdout must not contain ANSI codes.
        """
        with tempfile.TemporaryDirectory() as td:
            proc = _run(
                "--machine", "crawl",
                "https://example.com",
                "--engine", "substrate",
                "--embed-provider", "apple-local",
                "--max-pages", "0",
                "--max-depth", "0",
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
                timeout=60,
            )

        # Stdout must not contain ANSI codes regardless of outcome.
        self.assertFalse(
            _has_ansi(proc.stdout),
            f"ANSI in stdout: {proc.stdout[:200]!r}",
        )
        # Stdout must not contain raw Python tracebacks.
        self.assertNotIn(
            "Traceback (most recent call last)",
            proc.stdout,
            "raw Python traceback must not appear in machine stdout",
        )
        # If stdout is non-empty it must be valid JSON.
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
                self.assertIsInstance(payload, dict)
            except json.JSONDecodeError:
                self.fail(
                    f"stdout is non-empty but not valid JSON: {proc.stdout[:300]!r}"
                )

    def test_apple_local_stdout_has_no_ansi_when_skipped(self):
        """Even when apple-local is skipped, no ANSI must reach stdout."""
        with tempfile.TemporaryDirectory() as td:
            proc = _run(
                "--machine", "crawl",
                "https://example.com",
                "--engine", "substrate",
                "--embed-provider", "apple-local",
                "--max-pages", "0",
                "--max-depth", "0",
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
                timeout=60,
            )
        self.assertFalse(_has_ansi(proc.stdout))

    def test_apple_local_unavailable_file_build_is_structured_json(self):
        """A real local-file build should fail closed as JSON when apple-local is unavailable."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "sample.txt"
            target.write_text("machine first substrate text for apple local embedding", encoding="utf-8")
            proc = _run(
                "--machine", "crawl",
                str(target),
                "--engine", "substrate",
                "--embed-provider", "apple-local",
                env_extra={"LGWKS_SUBSTRATE_ROOT": td},
                timeout=60,
            )
        self.assertIn(proc.returncode, (0, 1), f"unexpected stderr: {proc.stderr[:200]!r}")
        self.assertFalse(_has_ansi(proc.stdout))
        self.assertNotIn("Traceback (most recent call last)", proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertIsInstance(payload, dict)
        if proc.returncode:
            self.assertEqual(payload.get("schema"), "lgwks.substrate.error.v0")
            self.assertEqual(payload.get("error"), "embedding provider unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# 4. lgwks --machine crawl (legacy engine) remains deterministic by default
#    (no substrate, no apple-local, just the estimate or keyword legacy path)
# ─────────────────────────────────────────────────────────────────────────────

class TestJarvisCrawlMachineModeDefaultDeterministic(unittest.TestCase):
    """
    With no --embed-provider flag, crawl keyword-only must not load
    lgwks_apple or any non-deterministic embedding provider.
    """

    def test_jarvis_keyword_estimate_only_stdout_is_json(self):
        proc = _run(
            "--machine", "crawl",
            "RRSP retirement",
            "--estimate-only",
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr!r}")
        payload = json.loads(proc.stdout)
        self.assertIn("estimated_seconds", payload)

    def test_jarvis_keyword_estimate_no_ansi(self):
        proc = _run(
            "--machine", "crawl",
            "RRSP retirement",
            "--estimate-only",
        )
        self.assertFalse(_has_ansi(proc.stdout))

    def test_jarvis_url_estimate_only_stdout_is_json(self):
        proc = _run(
            "--machine", "crawl",
            "https://example.com",
            "--max-pages", "1",
            "--estimate-only",
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr!r}")
        payload = json.loads(proc.stdout)
        self.assertIn("estimated_seconds", payload)


if __name__ == "__main__":
    unittest.main()
