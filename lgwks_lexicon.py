"""lgwks_lexicon — the one canonical LEXICAL analyzer (word / identifier tokenisation).

This is the plain lexical layer used by lexical search, feature-hashing, and keyword
overlap. It is a DIFFERENT concept from:
  - lgwks_tokenizer        — ANT, the neural *trajectory* byte-BPE tokenizer (token IDs);
  - lgwks_tokenizer_registry — analyzer *identity* registry.
Those stay distinct. This module owns lexical word-splitting, which had drifted into
nine near-identical `_tokens`/`_tokenize` copies and seven duplicated stopword lists,
each SLIGHTLY different (regex, min-length, stopword set, even list-vs-set return).
"Slightly different" is the bug — the recall silently diverged. One mechanism, named
profiles, named curated stopword sets; callers select policy, never re-derive it.

The word regex itself is already the single source of truth in lgwks_substrate_config
(WORD_RE); this reuses it rather than minting a second copy.
"""

from __future__ import annotations

import re

from lgwks_substrate_config import WORD_RE

# ── Profiles: the character class that defines "a token" in a domain ──────────
# WORD — plain words/numbers (engine/map/query/concept). The canonical shared regex.
WORD = WORD_RE                                            # [a-z0-9]+
# TERM — English terms that keep + - . (versions, hyphenates) — embed/memory.
TERM = re.compile(r"[a-z][a-z0-9_+\-.]*")
# CODE — code identifiers / paths that keep _ . / - — jepa/portal.
CODE = re.compile(r"[a-z][a-z0-9_./-]*")

# ── Curated stopword sets: defined ONCE here (were duplicated, slightly different) ──
# STOP_CLI — command-surface noise (engine/map): English glue + lgwks verb chrome.
STOP_CLI = frozenset(
    "the a an of to for and or with in on it this that is are be run get show "
    "lgwks create make build do use via from into your you my our please can "
    "how what when where why which will should would could".split()
)
# STOP_EN — generic English function words (union of the embed + memory lists).
STOP_EN = frozenset(
    "a an and are as at be by for from has have i if in is it its me my no not of "
    "on or our that the this to was we with you your".split()
)


def tokens(
    text: object,
    *,
    profile: re.Pattern[str] = WORD,
    min_len: int = 1,
    stop: frozenset[str] = frozenset(),
    unique: bool = False,
) -> list[str] | set[str]:
    """Lexically tokenise `text`. ONE mechanism, explicit policy.

    profile  : which token regex (WORD / TERM / CODE).
    min_len  : drop tokens shorter than this (post-match length filter).
    stop     : a curated stopword set to remove (e.g. STOP_CLI / STOP_EN).
    unique   : return a set instead of an order-preserving list.

    Always lowercases first (every prior copy did). Non-str input is coerced
    (mirrors the defensive `_tokens` copies that accepted object).
    """
    s = text if isinstance(text, str) else ("" if text is None else str(text))
    out = [t for t in profile.findall(s.lower()) if len(t) >= min_len and t not in stop]
    return set(out) if unique else out
