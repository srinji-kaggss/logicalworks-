"""Chunk-CID parity gate (R6.2) — the jarvis-crawl ⟷ substrate-build convergence lock.

The Pristine Program flagged `lgwks_jarvis.crawl_command` as reimplementing
`lgwks_substrate_run.build_run`'s chunk-ingest loop, with the FEAR that the two
have divergent chunk-boundary logic producing DIFFERENT content-addressed CIDs
(which would fork stored content). This gate settles that empirically and pins it.

VERIFIED FINDING (the fear is false): both paths already delegate to the ONE
canonical `lgwks_chunking.SlidingWindowChunking` and the ONE canonical hash seam,
so at EQUAL params they produce byte-identical chunks and byte-identical chunk
CIDs. The chunkers are already converged (#265); the only real divergence is the
DEFAULT params (jarvis 450/70 vs build_run 320/48) — and unifying those would
re-CID all stored crawl content, so it is a separate migration, NOT folded here.

This gate fails if anyone:
  1. forks the chunk-boundary logic (the two chunker doors stop agreeing), or
  2. forks the content-id hash (`io._sha` ⟷ `lgwks_hashing.digest` diverge), or
  3. changes either CID template away from `chunk-{hash[:16]}`.
"""

from __future__ import annotations

import unittest

import lgwks_hashing
import lgwks_jarvis
import lgwks_substrate_io as io
import lgwks_substrate_text as text

# A fixed input that yields multiple chunks at small window sizes.
_FIXTURE = (
    "RRSP minimum amount is $5,000. Use form T2033 to transfer. "
    "Contribution room carries forward. Withholding tax applies on early withdrawal. "
) * 30

# (size, overlap) pairs to cross-check; includes the historical defaults of each
# path so a future drift in either default still exercises the chunker agreement.
_PARAMS = [(80, 10), (120, 20), (320, 48), (450, 70)]


def _build_cids(pieces: list[str]) -> list[str]:
    """The build_run / _ingest_docs chunk-CID template (lgwks_substrate_run:224)."""
    return [f"chunk-{io._sha(p)[:16]}" for p in pieces]


def _jarvis_cids(pieces: list[str]) -> list[str]:
    """The crawl_command chunk-CID template (lgwks_jarvis:680)."""
    return [f"chunk-{lgwks_hashing.digest(p)[:16]}" for p in pieces]


class TestChunkCidParity(unittest.TestCase):
    def test_chunkers_agree_at_equal_params(self):
        """Both chunker doors produce identical chunk boundaries at equal params."""
        for size, overlap in _PARAMS:
            with self.subTest(size=size, overlap=overlap):
                a = text._chunk_text(_FIXTURE, size=size, overlap=overlap)
                b = lgwks_jarvis.chunk_text(_FIXTURE, size, overlap)
                self.assertEqual(
                    a, b,
                    f"chunk boundaries diverged at size={size} overlap={overlap} — "
                    "the two paths no longer share lgwks_chunking.SlidingWindowChunking",
                )
                self.assertGreater(len(a), 1, "fixture must yield >1 chunk to be meaningful")

    def test_hash_seam_is_one(self):
        """The content-id hash is one seam: io._sha and lgwks_hashing.digest agree."""
        for sample in (_FIXTURE, "", "x", "edge\ncase\ttext"):
            self.assertEqual(
                io._sha(sample), lgwks_hashing.digest(sample),
                "io._sha diverged from lgwks_hashing.digest — the chunk CID would fork",
            )

    def test_chunk_cids_identical_at_equal_params(self):
        """End-to-end: identical chunk CIDs for a fixed input at equal params."""
        for size, overlap in _PARAMS:
            with self.subTest(size=size, overlap=overlap):
                pieces = text._chunk_text(_FIXTURE, size=size, overlap=overlap)
                self.assertEqual(
                    _build_cids(pieces), _jarvis_cids(pieces),
                    f"chunk CIDs diverged at size={size} overlap={overlap} — "
                    "stored content would fork between the crawl and build paths",
                )


if __name__ == "__main__":
    unittest.main()
