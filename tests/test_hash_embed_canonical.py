"""#223 family 2 — deterministic feature-hash embedder convergence.

The signed-bucket blake2b mechanism was copy-pasted across 5 modules
(run/jarvis/project_artifacts/embed/memory). Each carried its own copy, so one
could rot independently — exactly how #29 happened (a sibling drifted to
np.random, turning gate confidence into noise). They now share ONE tested
mechanism, `lgwks_vecmath.hash_embed`, while each KEEPS its own feature extraction
(the part that legitimately differs: tokenizer, n-gram order, weighting, dims).

This test is the evidence the extraction changed no stored-vector bytes: every
caller is asserted against an inline copy of its pre-convergence body over an
adversarial battery (incl. a surrogate char that exercises jarvis's
errors="ignore"). It also pins the mechanism's own contract.

It complements `test_one_embedder.py` (which forbids RNG in embed paths): together
they make both "no RNG" AND "no silent re-derivation" machine-checked.
"""

from __future__ import annotations

import hashlib
import math
import re
import unittest

import lgwks_vecmath as vm
import lgwks_run as run
import lgwks_jarvis as jv
import lgwks_project_artifacts as pa
import lgwks_embed as emb
import lgwks_memory as mem
import lgwks_concept as concept


BATTERY = [
    "", "a", "the quick brown fox not good vs good", "v1.2.3 state-of-the-art",
    "café münchen \udce9 surrogate", "node_id edge weight " * 5,
    "one two three four five", "ALL CAPS lower", "a-b a.b a+b", "x" * 200,
]


# --- oracles: verbatim pre-convergence implementations ------------------------
def _old_run(text, dims=run.DIMS):
    vec = [0.0] * dims
    toks = re.findall(r"[a-z0-9]+", text.lower())
    features = list(toks)
    if len(toks) >= 2:
        features += [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)]
    if len(toks) >= 3:
        features += [" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)]
    for feat in features:
        d = hashlib.blake2b(feat.encode(), digest_size=8).digest()
        bucket = int.from_bytes(d[:4], "big") % dims
        sign = 1.0 if d[4] % 2 == 0 else -1.0
        w = 1.0
        if " " in feat:
            w = 1.5 if feat.count(" ") == 1 else 2.0
        vec[bucket] += sign * w
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / n, 6) for v in vec]


def _old_jv(text, dims=jv.DEFAULT_DIMS):
    toks = jv.tokens(text)
    features = toks[:]
    features += [" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1))]
    features += [" ".join(toks[i:i + 3]) for i in range(max(0, len(toks) - 2))]
    vec = [0.0] * dims
    for feat in features:
        d = hashlib.blake2b(feat.encode("utf-8", errors="ignore"), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / n, 6) for v in vec]


def _old_pa(text, dims=pa.EMBED_DIMS):
    features = pa._terms(text)
    features += [" ".join(features[i:i + 2]) for i in range(max(0, len(features) - 1))]
    vec = [0.0] * dims
    for feat in features:
        d = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    n = sum(v * v for v in vec) ** 0.5 or 1.0
    return [round(v / n, 6) for v in vec]


def _old_emb(text, dims=emb.DIMS):
    toks = emb._tokens(text)
    feats = toks[:]
    feats += [" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1))]
    vec = [0.0] * dims
    for feat in feats:
        d = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / n, 6) for v in vec]


def _old_mem(text, dims=128):
    features = mem._tokens(text)
    features += [" ".join(features[i:i + 2]) for i in range(max(0, len(features) - 1))]
    vec = [0.0] * dims
    for feat in features:
        d = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    n = sum(v * v for v in vec) ** 0.5 or 1.0
    return [round(v / n, 6) for v in vec]


def _old_concept_vector(c):
    """Pre-routing concept_vector: structured composite with the atom inlined."""
    vec = [0.0] * concept.CONCEPT_DIMS

    def add(text, weight=1.0, salt=""):
        for i, tok in enumerate(concept._tokenize(text)):
            pw = 1.0 / (1.0 + math.log1p(i))
            h = hashlib.blake2b(f"{salt}{tok}".encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % concept.CONCEPT_DIMS
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign * weight * pw

    add(c.label, 4.0, "label:")
    add(c.concept_type, 2.0, "type:")
    add(c.definition, 3.0, "def:")
    for a in c.aliases:
        add(a, 1.5, "alias:")
    for k, v in sorted(c.attributes.items()):
        add(f"{k}={v}", 2.5, "attr:")
    h = hashlib.blake2b(f"occ:{c.occurrences}".encode(), digest_size=8).digest()
    idx = int.from_bytes(h[:4], "big") % concept.CONCEPT_DIMS
    sign = 1.0 if h[4] % 2 == 0 else -1.0
    vec[idx] += sign * math.log1p(c.occurrences)
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / n, 6) for x in vec]


class TestEmbedderByteEquivalence(unittest.TestCase):
    def test_run_weighted_unchanged(self):
        for s in BATTERY:
            self.assertEqual(run._deterministic_embed(s), _old_run(s), repr(s))

    def test_jarvis_errors_ignore_unchanged(self):
        for s in BATTERY:
            self.assertEqual(jv.deterministic_embedding(s), _old_jv(s), repr(s))

    def test_project_artifacts_unchanged(self):
        for s in BATTERY:
            self.assertEqual(pa._embedding(s), _old_pa(s), repr(s))

    def test_embed_unchanged(self):
        for s in BATTERY:
            self.assertEqual(emb._embedding(s), _old_emb(s), repr(s))

    def test_memory_unchanged(self):
        for s in BATTERY:
            self.assertEqual(mem.embedding(s), _old_mem(s), repr(s))

    def test_concept_vector_unchanged(self):
        # The structured composite embedder shares only the bucket/sign ATOM; routing
        # it must not change the stored concept vector by a single byte.
        cases = [
            concept.Concept("x", "RRSP Transfer", "rrsp-transfer", "PLAN_TYPE",
                            definition="a registered savings plan rollover",
                            aliases=["RRSP", "retirement plan"],
                            attributes={"form": "T2033", "ver": "2024"}, occurrences=7),
            concept.Concept("y", "", "", "", definition="", aliases=[], attributes={},
                            occurrences=0),
            concept.Concept("z", "café", "cafe", "T", definition="münchen platz",
                            aliases=["a"], attributes={"k": "v"}, occurrences=1),
        ]
        for c in cases:
            self.assertEqual(concept.concept_vector(c), _old_concept_vector(c), c.concept_id)


class TestHashEmbedContract(unittest.TestCase):
    def test_deterministic_across_calls(self):
        self.assertEqual(vm.hash_embed(["a", "b", "a b"], 64),
                         vm.hash_embed(["a", "b", "a b"], 64))

    def test_unit_norm_for_nonempty(self):
        v = vm.hash_embed(["alpha", "beta", "alpha beta"], 128)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=5)

    def test_empty_features_is_zero_vector(self):
        self.assertEqual(vm.hash_embed([], 16), [0.0] * 16)

    def test_weighted_rescales_ngrams_relative_to_unigrams(self):
        # Need a unigram AND an n-gram in DIFFERENT buckets: weighting changes their
        # relative magnitude, which survives L2-normalisation. (A lone feature
        # normalises to the same unit spike regardless of weight.)
        feats = ["alpha", "beta", "alpha beta"]
        self.assertNotEqual(vm.hash_embed(feats, 64, weighted=True),
                            vm.hash_embed(feats, 64, weighted=False))

    def test_encode_errors_ignore_handles_surrogate(self):
        # strict would raise on a lone surrogate; ignore must not.
        out = vm.hash_embed(["x\udce9y"], 32, encode_errors="ignore")
        self.assertEqual(len(out), 32)

    def test_hash_bucket_atom_is_deterministic_and_in_range(self):
        b1, s1 = vm.hash_bucket("alpha", 64)
        b2, s2 = vm.hash_bucket("alpha", 64)
        self.assertEqual((b1, s1), (b2, s2))
        self.assertTrue(0 <= b1 < 64)
        self.assertIn(s1, (1.0, -1.0))

    def test_hash_embed_uses_the_atom(self):
        # A single feature lands exactly in its atom's bucket (unit spike there).
        bucket, sign = vm.hash_bucket("solo", 16)
        v = vm.hash_embed(["solo"], 16)
        self.assertEqual(v[bucket], round(sign, 6))


if __name__ == "__main__":
    unittest.main()
