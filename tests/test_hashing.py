"""Contract tests for lgwks_hashing — the single source of truth for content hashing.

These lock the canonical primitives against drift (the C-10 cid-consistency bug: the
same sha256 primitive had been copy-pasted ~15× with divergent truncation / error modes).
Each test states a property a human can re-derive with a calculator + hashlib docs.
"""

import hashlib
import json

import lgwks_hashing as H


# A string that exercises UTF-8: accents, an em dash, an emoji, path-ish chars.
SAMPLE = "Hello, wörld — déjà vu 🚀 / path.to_thing-1"


def test_content_id_is_truncated_sha256_hex():
    full = hashlib.sha256(SAMPLE.encode("utf-8", errors="ignore")).hexdigest()
    assert H.content_id(SAMPLE, 16) == full[:16]
    assert H.content_id(SAMPLE, 12) == full[:12]
    assert H.content_id(SAMPLE, 20) == full[:20]


def test_content_id_default_width_is_16():
    assert len(H.content_id(SAMPLE)) == 16
    assert H.content_id(SAMPLE) == H.content_id(SAMPLE, 16)


def test_digest_is_full_64_hex():
    d = H.digest(SAMPLE)
    assert len(d) == 64
    assert d == hashlib.sha256(SAMPLE.encode("utf-8", errors="ignore")).hexdigest()


def test_digest_bytes_matches_sha256_of_bytes():
    raw = b"\x00\x01raw\xffbytes"
    assert H.digest_bytes(raw) == hashlib.sha256(raw).hexdigest()
    assert len(H.digest_bytes(raw)) == 64


def test_canonical_id_is_order_independent():
    a = {"b": 2, "a": [1, 2, {"z": 9, "y": 8}]}
    b = {"a": [1, 2, {"y": 8, "z": 9}], "b": 2}  # same data, keys reordered
    assert H.canonical_id(a) == H.canonical_id(b)
    expected = hashlib.sha256(
        json.dumps(a, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert H.canonical_id(a) == expected


def test_blake_id_is_blake2b_hex():
    assert H.blake_id(SAMPLE, 16) == hashlib.blake2b(
        SAMPLE.encode("utf-8", errors="ignore"), digest_size=16
    ).hexdigest()
    # digest_size bytes -> 2x hex chars
    assert len(H.blake_id(SAMPLE, 16)) == 32
    assert len(H.blake_id(SAMPLE, 8)) == 16


def test_digest_file_streams_same_as_in_memory(tmp_path):
    p = tmp_path / "blob.bin"
    payload = (SAMPLE * 5000).encode("utf-8")  # > one 64KiB read buffer
    p.write_bytes(payload)
    assert H.digest_file(p) == hashlib.sha256(payload).hexdigest()


def test_error_mode_is_lossy_total_not_raising():
    # A lone surrogate is not encodable as strict UTF-8; the canonical content id
    # must never raise on it (errors="ignore" makes hashing total).
    nasty = "ok\ud800tail"
    cid = H.content_id(nasty)  # must not raise
    assert cid == hashlib.sha256(nasty.encode("utf-8", errors="ignore")).hexdigest()[:16]


def test_determinism():
    assert H.content_id(SAMPLE) == H.content_id(SAMPLE)
    assert H.digest(SAMPLE) == H.digest(SAMPLE)
    assert H.canonical_id({"k": 1}) == H.canonical_id({"k": 1})


def test_migrated_aliases_resolve_to_canonical():
    # The whole point: every module's local hash name now IS the canonical primitive.
    import lgwks_axiom
    import lgwks_substrate_io
    import lgwks_cache
    import lgwks_geoexpr
    import lgwks_concept

    assert lgwks_axiom._sha is H.content_id
    assert lgwks_substrate_io._sha is H.digest
    assert lgwks_cache._hash is H.digest_bytes
    assert lgwks_geoexpr._sha is H.canonical_id
    assert lgwks_concept._hash is H.blake_id
