"""lgwks_chunking — canonical text chunking strategies.

PILLAR 2 BASEMENT: the final seam for text chunking (refs #261, #223).

Three divergent chunkers exist in the codebase today:
- lgwks_jarvis.chunk_text: size=450, overlap=70, word-windowed (uses \\S+)
- lgwks_run._chunk: size=400, overlap=0, word-windowed (uses split())
- lgwks_substrate_text._chunk_text: size=320, overlap=48, word-windowed (uses \\S+)

This module consolidates them behind a canonical ABC interface. Later PRs will
migrate the three callers onto these strategies without changing their semantics.
STRATEGY FAMILY: ported from crawl4ai (Apache-2.0, liftable).

Interface Design:
- ChunkingStrategy (ABC): def chunk(text: str) -> list[str]
- SlidingWindowChunking: word-window with configurable size/step
- RegexChunking: split on regex boundaries (e.g. newlines, sentences)
- SentenceChunking: split on sentence boundaries (stdlib regex; no nltk)
- Factory: get_chunker(name: str, **opts) -> ChunkingStrategy

All strategies are DETERMINISTIC (same input → same output, no randomness).
Dependencies: STDLIB ONLY (re, abc, typing). No nltk or third-party.

Deferred (crawl4ai strategies that require nltk, TextTiling, etc.):
- TopicChunking (nltk required) — will defer to a later slice
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import ClassVar


class ChunkingStrategy(ABC):
    """Abstract base class for text chunking strategies."""

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """Split text into chunks.

        Args:
            text: The input text to chunk.

        Returns:
            A list of non-empty text chunks. Empty input returns [].
        """
        ...


class SlidingWindowChunking(ChunkingStrategy):
    """Word-based sliding window chunking with configurable overlap.

    Splits text by words, using a window of fixed size and a step that
    determines overlap. Compatible with the three legacy chunkers once
    they instantiate it with their own parameters.

    Examples:
        >>> chunker = SlidingWindowChunking(size=450, overlap=70)
        >>> chunks = chunker.chunk("word " * 500)
        >>> len(chunks) > 1  # overlapping windows
        True
    """

    def __init__(self, size: int = 320, overlap: int = 48, word_regex: str = r"\S+"):
        """Initialize the sliding window chunker.

        Args:
            size: Window size in words.
            overlap: Number of words to overlap between consecutive windows.
            word_regex: Regex pattern to split words (default: \\S+).
        """
        if size < 1:
            raise ValueError(f"size must be >= 1, got {size}")
        if overlap < 0:
            raise ValueError(f"overlap must be >= 0, got {overlap}")
        if overlap >= size:
            raise ValueError(f"overlap ({overlap}) must be < size ({size})")

        self.size = size
        self.overlap = overlap
        self.word_regex = word_regex

    def chunk(self, text: str) -> list[str]:
        """Chunk text using sliding window over words."""
        if not text or not text.strip():
            return []

        words = re.findall(self.word_regex, text)
        if not words:
            return []

        chunks: list[str] = []
        step = max(1, self.size - self.overlap)

        for start in range(0, len(words), step):
            end = start + self.size
            chunk = " ".join(words[start:end])
            if chunk:
                chunks.append(chunk)

            # Stop if we've reached the end of the text
            if end >= len(words):
                break

        return chunks


class RegexChunking(ChunkingStrategy):
    """Split text on regex pattern boundaries.

    Useful for splitting on paragraphs, newlines, or custom delimiters.
    Keeps non-empty chunks and optionally strips whitespace.

    Examples:
        >>> chunker = RegexChunking(pattern=r"\n\n+")  # split on blank lines
        >>> chunks = chunker.chunk("Para 1\n\nPara 2\n\nPara 3")
        >>> len(chunks)
        3
    """

    def __init__(self, pattern: str = r"\n\n+", strip: bool = True):
        """Initialize the regex chunker.

        Args:
            pattern: Regex pattern for split boundaries.
            strip: Whether to strip whitespace from each chunk.
        """
        self.pattern = pattern
        self.strip = strip
        self._compiled_pattern = re.compile(pattern)

    def chunk(self, text: str) -> list[str]:
        """Chunk text by splitting on regex pattern."""
        if not text or not text.strip():
            return []

        parts = self._compiled_pattern.split(text)
        chunks = []

        for part in parts:
            chunk = part.strip() if self.strip else part
            if chunk:
                chunks.append(chunk)

        return chunks


class SentenceChunking(ChunkingStrategy):
    """Split text into sentences with optional windowing.

    Uses a regex-based sentence splitter (no nltk/NLTK dependency).
    Optionally groups sentences into windows for larger chunks.

    KNOWN LIMITATION: this is a naive punctuation splitter — it splits on every
    run of ``. ! ?``, so abbreviations ("U.S."), decimals ("3.14") and ellipses
    are split. Abbreviation-aware segmentation needs a Punkt-style dictionary
    (nltk), deferred per the dependency doctrine alongside TopicChunking.

    Examples:
        >>> chunker = SentenceChunking()
        >>> text = "First sentence. Second sentence. Third sentence."
        >>> chunks = chunker.chunk(text)
        >>> len(chunks)
        3

        >>> # With window grouping
        >>> chunker = SentenceChunking(sentences_per_chunk=2)
        >>> chunks = chunker.chunk(text)
        >>> len(chunks)
        2
    """

    # Regex to find sentence-ending punctuation (period, ?, !).
    # Matches the position right after such punctuation.
    _SENTENCE_END: ClassVar[re.Pattern] = re.compile(r'[.!?]+')

    def __init__(self, sentences_per_chunk: int = 1, strip: bool = True):
        """Initialize the sentence chunker.

        Args:
            sentences_per_chunk: Number of sentences to group per chunk (1 = one sentence per chunk).
            strip: Whether to strip whitespace from each chunk.
        """
        if sentences_per_chunk < 1:
            raise ValueError(f"sentences_per_chunk must be >= 1, got {sentences_per_chunk}")
        self.sentences_per_chunk = sentences_per_chunk
        self.strip = strip

    def chunk(self, text: str) -> list[str]:
        """Chunk text by sentences."""
        if not text or not text.strip():
            return []

        # Find all sentence-ending punctuation marks and use them to split sentences
        sentences = []
        current_start = 0

        for match in self._SENTENCE_END.finditer(text):
            # Extract from current_start to the end of the punctuation match
            end_pos = match.end()
            sentence = text[current_start:end_pos]

            if self.strip:
                sentence = sentence.strip()

            if sentence:
                sentences.append(sentence)

            # Start next sentence after this one
            current_start = end_pos

        # Handle any remaining text after the last sentence
        if current_start < len(text):
            remaining = text[current_start:]
            if self.strip:
                remaining = remaining.strip()
            if remaining:
                sentences.append(remaining)

        if not sentences:
            return []

        # Group sentences into chunks
        chunks = []
        for i in range(0, len(sentences), self.sentences_per_chunk):
            chunk = " ".join(sentences[i:i + self.sentences_per_chunk])
            if chunk:
                chunks.append(chunk)

        return chunks


def get_chunker(name: str, **opts) -> ChunkingStrategy:
    """Factory to instantiate a chunker by name.

    Args:
        name: Strategy name ('sliding_window', 'regex', 'sentence').
        **opts: Strategy-specific options (passed to __init__).

    Returns:
        An instantiated ChunkingStrategy.

    Raises:
        ValueError: If name is not recognized.

    Examples:
        >>> chunker = get_chunker('sliding_window', size=450, overlap=70)
        >>> isinstance(chunker, SlidingWindowChunking)
        True
    """
    strategies = {
        'sliding_window': SlidingWindowChunking,
        'regex': RegexChunking,
        'sentence': SentenceChunking,
    }

    if name not in strategies:
        raise ValueError(f"Unknown chunking strategy: {name}. Choose from {list(strategies.keys())}")

    return strategies[name](**opts)
