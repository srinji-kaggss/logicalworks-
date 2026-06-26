"""Tests for scripts/gen_okf.py — the OKF bundle generator/validator.

Locks the deterministic derivation (a human must be able to reconstruct every
frontmatter field from the rules) and the frontmatter round-trip. Pure-function
tests; no bundle mutation.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "gen_okf", Path(__file__).resolve().parent.parent / "scripts" / "gen_okf.py")
g = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(g)


def test_derive_type_is_deterministic_by_path():
    assert g.derive_type(Path("ADR-sast-001-x.md")) == "ADR"
    assert g.derive_type(Path("schemas/REGISTRY.md")) == "Schema"
    assert g.derive_type(Path("research/x.md")) == "Research"
    assert g.derive_type(Path("handoff/y.md")) == "Handoff"
    assert g.derive_type(Path("proofs/p.md")) == "Proof"
    assert g.derive_type(Path("ESCALATION-LADDER-LAW.md")) == "Law"
    assert g.derive_type(Path("seed-surface-spec.md")) == "Spec"
    assert g.derive_type(Path("some-plan.md")) == "Plan"
    assert g.derive_type(Path("archive/old.md")) == "Archive"
    assert g.derive_type(Path("random-note.md")) == "Reference"  # default


def test_frontmatter_roundtrip_preserves_keys():
    fm = {"type": "Concept", "title": "X", "description": "one line", "tags": "[a, b]"}
    text = g.emit_frontmatter(fm) + "# Body\n\nhello\n"
    parsed, body = g.split_frontmatter(text)
    assert parsed["type"] == "Concept"
    assert parsed["title"] == "X"
    assert body.startswith("# Body")


def test_split_frontmatter_absent_is_noop():
    parsed, body = g.split_frontmatter("# No frontmatter\n\ntext\n")
    assert parsed == {}
    assert body.startswith("# No frontmatter")


def test_derive_title_prefers_h1_then_filename():
    assert g.derive_title("# Real Title\n\nbody", "fallback-name") == "Real Title"
    assert g.derive_title("no heading here", "my-doc-name") == "My Doc Name"


def test_derive_description_skips_headings_lists_fences():
    body = "# Heading\n\n```\ncode\n```\n\n- bullet\n\nThis is the real first sentence. More."
    assert g.derive_description(body) == "This is the real first sentence."


def test_strip_inline_preserves_identifiers():
    # underscores in identifiers must survive (lgwks_pipeline.py, not lgwkspipeline.py)
    assert g._strip_inline("see `lgwks_model_port.py` here") == "see lgwks_model_port.py here"


def test_emit_orders_required_first():
    out = g.emit_frontmatter({"timestamp": "t", "type": "X", "title": "Y"})
    lines = [l for l in out.splitlines() if ":" in l]
    assert lines[0].startswith("type:")  # required field leads
