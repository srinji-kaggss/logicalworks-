"""Tests for lgwks_chunking — canonical text chunking strategies.

Coverage:
- Each strategy's basic functionality (happy path).
- Edge cases: empty input, whitespace-only, single word, very long text.
- Boundary behavior: window size, overlap, sentence splitting.
- Factory returns correct class for each name.
- Determinism: same input → same output (no randomness).
- Configuration validation (negative/invalid params).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from lgwks_chunking import (
    ChunkingStrategy,
    SlidingWindowChunking,
    RegexChunking,
    SentenceChunking,
    get_chunker,
)


class TestSlidingWindowChunking:
    """Test sliding window chunker with overlap."""

    def test_basic_chunking_with_overlap(self):
        """Verify overlapping windows work correctly."""
        text = " ".join(["word"] * 100)
        chunker = SlidingWindowChunking(size=10, overlap=5)
        chunks = chunker.chunk(text)

        # First chunk: words 0-9
        assert chunks[0] == " ".join(["word"] * 10)
        # Second chunk: words 5-14 (step = 10 - 5 = 5)
        assert chunks[1] == " ".join(["word"] * 10)
        # Should have multiple chunks for 100 words with size 10 and step 5
        assert len(chunks) > 1

    def test_no_overlap(self):
        """Verify non-overlapping chunking (overlap=0)."""
        text = " ".join(["word"] * 10)
        chunker = SlidingWindowChunking(size=5, overlap=0)
        chunks = chunker.chunk(text)

        assert len(chunks) == 2
        assert chunks[0] == " ".join(["word"] * 5)
        assert chunks[1] == " ".join(["word"] * 5)

    def test_empty_input(self):
        """Empty or whitespace-only input returns empty list."""
        chunker = SlidingWindowChunking(size=10, overlap=5)

        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
        assert chunker.chunk("\n\t") == []

    def test_single_word(self):
        """Single word smaller than window size."""
        chunker = SlidingWindowChunking(size=10, overlap=5)
        chunks = chunker.chunk("hello")

        assert chunks == ["hello"]

    def test_exactly_window_size(self):
        """Text with exactly window size words."""
        text = " ".join(["word"] * 10)
        chunker = SlidingWindowChunking(size=10, overlap=5)
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_custom_word_regex(self):
        """Custom regex pattern for word splitting."""
        # Using comma as word separator
        text = "a,b,c,d,e,f,g,h,i,j,k,l,m"
        chunker = SlidingWindowChunking(size=3, overlap=1, word_regex=r"[a-z]")
        chunks = chunker.chunk(text)

        # Step = 3 - 1 = 2, so windows overlap by 1
        assert len(chunks) >= 2
        # Each chunk should have 3 "words" (letters)
        assert all(len(c.split(",")) <= 3 for c in chunks)

    def test_large_text(self):
        """Chunking on very large text."""
        text = " ".join(["word"] * 10000)
        chunker = SlidingWindowChunking(size=100, overlap=20)
        chunks = chunker.chunk(text)

        # Should have multiple chunks
        assert len(chunks) > 50
        # All chunks should be non-empty
        assert all(chunks)
        # All chunks should have ~100 words (except possibly the last)
        word_counts = [len(c.split()) for c in chunks]
        assert all(95 <= wc <= 100 for wc in word_counts[:-1])

    def test_invalid_size(self):
        """Size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="size must be >= 1"):
            SlidingWindowChunking(size=0, overlap=0)

        with pytest.raises(ValueError, match="size must be >= 1"):
            SlidingWindowChunking(size=-5, overlap=0)

    def test_invalid_overlap(self):
        """Negative overlap raises ValueError."""
        with pytest.raises(ValueError, match="overlap must be >= 0"):
            SlidingWindowChunking(size=10, overlap=-1)

    def test_overlap_gte_size(self):
        """Overlap >= size raises ValueError."""
        with pytest.raises(ValueError, match="overlap.*must be < size"):
            SlidingWindowChunking(size=10, overlap=10)

        with pytest.raises(ValueError, match="overlap.*must be < size"):
            SlidingWindowChunking(size=10, overlap=15)

    def test_determinism(self):
        """Same input always produces same output."""
        text = "The quick brown fox jumps over the lazy dog " * 5
        chunker = SlidingWindowChunking(size=20, overlap=5)

        result1 = chunker.chunk(text)
        result2 = chunker.chunk(text)

        assert result1 == result2

    def test_jarvis_compat(self):
        """Verify lgwks_jarvis.chunk_text semantics (size=450, overlap=70)."""
        text = " ".join(["word"] * 500)
        chunker = SlidingWindowChunking(size=450, overlap=70)
        chunks = chunker.chunk(text)

        # Should have overlapping windows
        assert len(chunks) > 1
        # Each chunk should be ~450 words
        for chunk in chunks[:-1]:
            assert 440 <= len(chunk.split()) <= 460

    def test_run_compat(self):
        """Verify lgwks_run._chunk semantics (size=400, overlap=0)."""
        text = " ".join(["word"] * 800)
        chunker = SlidingWindowChunking(size=400, overlap=0)
        chunks = chunker.chunk(text)

        assert len(chunks) == 2
        assert len(chunks[0].split()) == 400
        assert len(chunks[1].split()) == 400

    def test_substrate_text_compat(self):
        """Verify lgwks_substrate_text._chunk_text semantics (size=320, overlap=48)."""
        text = " ".join(["word"] * 400)
        chunker = SlidingWindowChunking(size=320, overlap=48)
        chunks = chunker.chunk(text)

        # Step = 320 - 48 = 272
        # Expect overlapping windows
        assert len(chunks) >= 2


class TestRegexChunking:
    """Test regex-based splitting."""

    def test_split_on_blank_lines(self):
        """Split on multiple blank lines."""
        text = "Para 1\n\nPara 2\n\nPara 3"
        chunker = RegexChunking(pattern=r"\n\n+")
        chunks = chunker.chunk(text)

        assert chunks == ["Para 1", "Para 2", "Para 3"]

    def test_split_on_newline(self):
        """Split on single newlines."""
        text = "Line 1\nLine 2\nLine 3"
        chunker = RegexChunking(pattern=r"\n")
        chunks = chunker.chunk(text)

        assert chunks == ["Line 1", "Line 2", "Line 3"]

    def test_split_on_comma(self):
        """Split on commas."""
        text = "a, b, c, d"
        chunker = RegexChunking(pattern=r",\s*")
        chunks = chunker.chunk(text)

        assert chunks == ["a", "b", "c", "d"]

    def test_no_strip(self):
        """Don't strip whitespace when strip=False."""
        text = "  Para 1  \n\n  Para 2  "
        chunker = RegexChunking(pattern=r"\n\n+", strip=False)
        chunks = chunker.chunk(text)

        assert chunks == ["  Para 1  ", "  Para 2  "]

    def test_empty_input(self):
        """Empty input returns empty list."""
        chunker = RegexChunking(pattern=r"\n\n+")

        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_no_matches(self):
        """Text with no pattern matches returns single chunk."""
        text = "Single paragraph with no splits"
        chunker = RegexChunking(pattern=r"\n\n+")
        chunks = chunker.chunk(text)

        assert chunks == [text]

    def test_determinism(self):
        """Same input always produces same output."""
        text = "Para 1\n\nPara 2\n\nPara 3\n\nPara 4"
        chunker = RegexChunking(pattern=r"\n\n+")

        result1 = chunker.chunk(text)
        result2 = chunker.chunk(text)

        assert result1 == result2


class TestSentenceChunking:
    """Test sentence-based splitting."""

    def test_basic_sentence_split(self):
        """Split on sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence."
        chunker = SentenceChunking()
        chunks = chunker.chunk(text)

        assert len(chunks) == 3
        assert chunks[0] == "First sentence."
        assert chunks[1] == "Second sentence."
        assert chunks[2] == "Third sentence."

    def test_question_and_exclamation(self):
        """Split on ? and ! boundaries."""
        text = "What is this? An exclamation! A statement."
        chunker = SentenceChunking()
        chunks = chunker.chunk(text)

        assert len(chunks) == 3
        assert chunks[0] == "What is this?"
        assert chunks[1] == "An exclamation!"
        assert chunks[2] == "A statement."

    def test_sentences_per_chunk(self):
        """Group multiple sentences per chunk."""
        text = "First. Second. Third. Fourth. Fifth."
        chunker = SentenceChunking(sentences_per_chunk=2)
        chunks = chunker.chunk(text)

        assert len(chunks) == 3
        assert chunks[0] == "First. Second."
        assert chunks[1] == "Third. Fourth."
        assert chunks[2] == "Fifth."

    def test_known_limitation_abbreviations_split(self):
        """KNOWN LIMITATION (documented): the naive stdlib punctuation splitter
        splits inside abbreviations like ``U.S.`` — abbreviation-aware
        segmentation needs a Punkt-style dictionary (nltk), which is deferred
        per the dependency doctrine. This test pins the actual behavior so the
        limitation is explicit, not a silent surprise."""
        text = "The U.S. is large. Another sentence."
        chunker = SentenceChunking()
        chunks = chunker.chunk(text)

        # Splits on every '.' run, including the ones in "U.S."
        assert chunks == ["The U.", "S.", "is large.", "Another sentence."]

    def test_empty_input(self):
        """Empty input returns empty list."""
        chunker = SentenceChunking()

        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_single_sentence(self):
        """Single sentence with period."""
        chunker = SentenceChunking()
        text = "Just one sentence."
        chunks = chunker.chunk(text)

        assert chunks == [text]

    def test_no_strip(self):
        """Don't strip whitespace when strip=False."""
        text = "  First.  \n  Second.  "
        chunker = SentenceChunking(strip=False)
        chunks = chunker.chunk(text)

        # Without strip, leading/trailing spaces are preserved
        assert all("  " in c or not c for c in chunks)

    def test_invalid_sentences_per_chunk(self):
        """sentences_per_chunk < 1 raises ValueError."""
        with pytest.raises(ValueError, match="sentences_per_chunk must be >= 1"):
            SentenceChunking(sentences_per_chunk=0)

        with pytest.raises(ValueError, match="sentences_per_chunk must be >= 1"):
            SentenceChunking(sentences_per_chunk=-1)

    def test_determinism(self):
        """Same input always produces same output."""
        text = "First. Second. Third. Fourth. Fifth."
        chunker = SentenceChunking(sentences_per_chunk=2)

        result1 = chunker.chunk(text)
        result2 = chunker.chunk(text)

        assert result1 == result2


class TestFactory:
    """Test get_chunker factory function."""

    def test_factory_sliding_window(self):
        """Factory creates SlidingWindowChunking."""
        chunker = get_chunker('sliding_window', size=100, overlap=10)
        assert isinstance(chunker, SlidingWindowChunking)
        assert chunker.size == 100
        assert chunker.overlap == 10

    def test_factory_regex(self):
        """Factory creates RegexChunking."""
        chunker = get_chunker('regex', pattern=r"\n\n+")
        assert isinstance(chunker, RegexChunking)
        assert chunker.pattern == r"\n\n+"

    def test_factory_sentence(self):
        """Factory creates SentenceChunking."""
        chunker = get_chunker('sentence', sentences_per_chunk=3)
        assert isinstance(chunker, SentenceChunking)
        assert chunker.sentences_per_chunk == 3

    def test_factory_default_params(self):
        """Factory works with default parameters."""
        chunker = get_chunker('sliding_window')
        assert isinstance(chunker, SlidingWindowChunking)
        assert chunker.size == 320
        assert chunker.overlap == 48

    def test_factory_unknown_strategy(self):
        """Unknown strategy name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            get_chunker('unknown_strategy')

    def test_factory_returns_strategy_instance(self):
        """Factory returns ChunkingStrategy subclass."""
        for name in ['sliding_window', 'regex', 'sentence']:
            chunker = get_chunker(name)
            assert isinstance(chunker, ChunkingStrategy)


class TestIntegration:
    """Integration tests across strategies."""

    def test_all_strategies_handle_empty_input(self):
        """All strategies return empty list for empty input."""
        strategies = [
            SlidingWindowChunking(),
            RegexChunking(),
            SentenceChunking(),
        ]

        for chunker in strategies:
            assert chunker.chunk("") == []
            assert chunker.chunk("   ") == []

    def test_all_strategies_deterministic(self):
        """All strategies are deterministic."""
        text = "The quick brown fox. Jumps over the lazy dog. Test text here."
        strategies = [
            SlidingWindowChunking(size=10, overlap=2),
            RegexChunking(pattern=r"\. "),
            SentenceChunking(sentences_per_chunk=1),
        ]

        for chunker in strategies:
            result1 = chunker.chunk(text)
            result2 = chunker.chunk(text)
            assert result1 == result2

    def test_all_strategies_produce_non_empty_chunks(self):
        """All strategies produce only non-empty chunks."""
        text = "Some test text. With multiple sentences. And various content here."
        strategies = [
            SlidingWindowChunking(),
            RegexChunking(),
            SentenceChunking(),
        ]

        for chunker in strategies:
            chunks = chunker.chunk(text)
            assert all(chunks)  # All chunks are truthy (non-empty)
            assert all(isinstance(c, str) for c in chunks)

    def test_different_strategies_different_results(self):
        """Different strategies produce different (but valid) chunking."""
        text = "First. Second. Third. Fourth. Fifth."

        sliding = SlidingWindowChunking(size=5, overlap=1)
        regex = RegexChunking(pattern=r"\. ")
        sentence = SentenceChunking()

        sliding_chunks = sliding.chunk(text)
        regex_chunks = regex.chunk(text)
        sentence_chunks = sentence.chunk(text)

        # They should produce different results
        assert sliding_chunks != regex_chunks or sliding_chunks != sentence_chunks

        # But all should be non-empty lists of strings
        assert all(isinstance(c, str) for chunks in [sliding_chunks, regex_chunks, sentence_chunks] for c in chunks)
