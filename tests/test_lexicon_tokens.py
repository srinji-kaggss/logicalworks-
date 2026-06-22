"""#223 family 3 — tokenizer convergence onto lgwks_lexicon.

PR #220 routed engine/route/map/embed/portal/memory/jepa (and pipeline via embed)
to the canonical lexical analyzer. The residual core-surface re-implementation was
`lgwks_jarvis.tokens` (own regex + own STOPWORDS). It now delegates to
`lgwks_lexicon.tokens(profile=TERM, min_len=2, stop=<jarvis STOPWORDS>)`.

This test is the evidence the routing changed no bytes: `jarvis.tokens` is asserted
against an inline copy of its pre-convergence body over an adversarial battery. It
also pins the canonical's `unique` overload (list vs set).
"""

from __future__ import annotations

import re
import unittest

import lgwks_lexicon as lex
import lgwks_jarvis as jarvis


def _old_jarvis_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_+\-.]{1,}", text.lower())
            if t not in jarvis.STOPWORDS]


BATTERY = [
    "", "a", "ab", "a b c", "1ab", "v1.2.3", "foo_bar-baz.qux",
    "The quick brown fox and the lazy dog", "https://example.com/path",
    "a-b a.b a+b", "...", "café münchen", "state-of-the-art ML+AI v2.0",
    "node_id edge-weight w.x.y", "if in into is it its", "a1 b2 c3 d",
    "tab\tnewline\ndone", "a.. ..b ++c", "x" * 5, "UPPER lower MixED",
]


class TestJarvisTokensUnchanged(unittest.TestCase):
    def test_byte_exact_vs_pre_convergence(self):
        for s in BATTERY:
            self.assertEqual(jarvis.tokens(s), _old_jarvis_tokens(s), repr(s))


class TestLexiconOverload(unittest.TestCase):
    def test_unique_false_is_ordered_list_with_dups(self):
        out = lex.tokens("ab ab cd", profile=lex.WORD, min_len=2)
        self.assertEqual(out, ["ab", "ab", "cd"])

    def test_unique_true_is_set(self):
        out = lex.tokens("ab ab cd", profile=lex.WORD, min_len=2, unique=True)
        self.assertEqual(out, {"ab", "cd"})

    def test_term_profile_keeps_punctuation_word_profile_does_not(self):
        self.assertEqual(lex.tokens("v1.2-x", profile=lex.TERM, min_len=2), ["v1.2-x"])
        self.assertEqual(lex.tokens("v1.2-x", profile=lex.WORD, min_len=1), ["v1", "2", "x"])


if __name__ == "__main__":
    unittest.main()
