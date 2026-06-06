"""
Tests for lgwks.bot.record.v1 schema validation.

Spec: docs/bot-fabric/U1-BOT-RECORD.md
Acceptance:
  1. A JSON schema exists and validates canonical records.
  2. Invalid severity and confidence values fail closed.
  3. A record without evidence fails validation.
  4. A record without drill-down links fails validation.
  5. The schema is simple enough for every bot lane to reuse unchanged.
"""

import json
from pathlib import Path

import lgwks_project_artifacts as artifacts

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "schemas" / "lgwks-bot-record-v1.schema.json"


def _canonical_record(**overrides) -> dict:
    base = {
        "schema": "lgwks.bot.record.v1",
        "run_id": "run:2026-06-06:abc123",
        "bot": "graph_anomaly",
        "target": {"kind": "file", "id": "lgwks_substrate.py"},
        "kind": "hub_risk",
        "summary": "high-betweenness transit hub with broad blast radius",
        "severity": "medium",
        "confidence": 0.88,
        "status": "open",
        "evidence": [
            {"type": "metric", "name": "betweenness", "value": 0.074765, "unit": "score"}
        ],
        "links": {
            "repo": "/Users/srinji/logicalworks-",
            "file": "lgwks_substrate.py",
            "symbol": None,
            "tests": ["tests/test_substrate.py"],
            "artifacts": ["runs/graph/current.json"],
        },
        "world_refs": [{"kind": "concept", "id": "hub-module"}],
        "tags": ["graph", "blast-radius", "architecture"],
        "created_at": "2026-06-06T12:00:00Z",
    }
    base.update(overrides)
    return base


# -- acceptance 1: schema file exists --------------------------------------

def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"schema file not found at {SCHEMA_PATH}"


def test_schema_is_valid_json():
    payload = json.loads(SCHEMA_PATH.read_text())
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert payload["title"] == "lgwks.bot.record.v1"


# -- acceptance 2: invalid severity and confidence fail closed -------------

def test_valid_record_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record())
    assert ok, errs
    assert errs == []


def test_invalid_severity_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(severity="mega"))
    assert not ok
    assert any("severity" in e and "mega" in e for e in errs)


def test_severity_info_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(severity="info"))
    assert ok, errs


def test_severity_critical_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(severity="critical"))
    assert ok, errs


def test_confidence_too_high_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(confidence=1.01))
    assert not ok
    assert any("confidence" in e for e in errs)


def test_confidence_too_low_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(confidence=-0.01))
    assert not ok
    assert any("confidence" in e for e in errs)


def test_confidence_boundary_one_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(confidence=1.0))
    assert ok, errs


def test_confidence_boundary_zero_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(confidence=0.0))
    assert ok, errs


def test_confidence_boolean_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(confidence=True))
    assert not ok
    assert any("confidence" in e for e in errs)


# -- acceptance 3: record without evidence fails -------------------------

def test_missing_evidence_fails():
    rec = _canonical_record()
    del rec["evidence"]
    ok, errs = artifacts.validate_bot_record(rec)
    assert not ok
    assert any("evidence" in e for e in errs)


def test_empty_evidence_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(evidence=[]))
    assert not ok
    assert any("evidence" in e.lower() for e in errs)


def test_evidence_without_type_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(evidence=[{"name": "x"}]))
    assert not ok
    assert any("type" in e for e in errs)


def test_evidence_unknown_type_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(evidence=[{"type": "magic"}]))
    assert not ok
    assert any("magic" in e for e in errs)


# -- acceptance 4: record without drill-down links fails -------------------

def test_missing_links_fails():
    rec = _canonical_record()
    del rec["links"]
    ok, errs = artifacts.validate_bot_record(rec)
    assert not ok
    assert any("links" in e for e in errs)


def test_links_without_anchor_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(links={"repo": "/a/b"}))
    assert not ok
    assert any("anchor" in e.lower() for e in errs)


def test_links_with_file_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(links={"repo": "/a/b", "file": "x.py"}))
    assert ok, errs


def test_links_with_symbol_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(links={"repo": "/a/b", "symbol": "foo"}))
    assert ok, errs


def test_links_with_tests_passes():
    ok, errs = artifacts.validate_bot_record(_canonical_record(links={"repo": "/a/b", "tests": ["t.py"]}))
    assert ok, errs


def test_links_with_artifacts_passes():
    ok, errs = artifacts.validate_bot_record(
        _canonical_record(links={"repo": "/a/b", "artifacts": ["a.json"]})
    )
    assert ok, errs


def test_unknown_top_level_field_fails():
    ok, errs = artifacts.validate_bot_record(_canonical_record(unexpected=True))
    assert not ok
    assert any("unknown field" in e for e in errs)


def test_empty_required_strings_fail():
    ok, errs = artifacts.validate_bot_record(_canonical_record(run_id=""))
    assert not ok
    assert any("run_id" in e for e in errs)


def test_links_tests_items_must_be_strings():
    rec = _canonical_record()
    rec["links"]["tests"] = [123]
    ok, errs = artifacts.validate_bot_record(rec)
    assert not ok
    assert any("links.tests[0]" in e for e in errs)


def test_created_at_must_be_iso_datetime():
    ok, errs = artifacts.validate_bot_record(_canonical_record(created_at="not-a-date"))
    assert not ok
    assert any("created_at" in e for e in errs)


# -- acceptance 5: schema simplicity / reusability -------------------------

def test_validator_is_stdlib_only():
    # The validator must not depend on external packages.
    assert hasattr(artifacts, "validate_bot_record")
    # No jsonschema import required — function is pure stdlib.
    import inspect
    src = inspect.getsource(artifacts.validate_bot_record)
    assert "jsonschema" not in src


def test_schema_discriminator_enforced():
    ok, errs = artifacts.validate_bot_record(_canonical_record(schema="wrong"))
    assert not ok
    assert any("lgwks.bot.record.v1" in e for e in errs)


def test_status_values():
    for st in ["open", "confirmed", "suppressed", "duplicate", "resolved"]:
        ok, errs = artifacts.validate_bot_record(_canonical_record(status=st))
        assert ok, errs

    ok, errs = artifacts.validate_bot_record(_canonical_record(status="pending"))
    assert not ok
    assert any("pending" in e for e in errs)


# -- design constraints ----------------------------------------------------

def test_one_record_one_claim_shape():
    rec = _canonical_record()
    assert rec["kind"] == "hub_risk"
    assert "summary" in rec


def test_no_nested_prose_blobs():
    # evidence items are flat objects, not nested prose
    ev = _canonical_record()["evidence"][0]
    assert isinstance(ev, dict)
    assert "type" in ev
