from __future__ import annotations

import argparse
import contextlib
import io
import json
import sqlite3
from pathlib import Path
from unittest import mock

import lgwks_do
import lgwks_research_memory
from lgwks_phase import PhaseResult


def _brain_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "create table chronicle (id integer primary key, repo text, type text, "
            "source_id text, dense_summary text, embedding blob, timestamp text)"
        )
        conn.execute(
            "insert into chronicle (repo, type, source_id, dense_summary) "
            "values (?, ?, ?, ?)",
            (
                "logicalworks-",
                "NOTE",
                "metacognition-001",
                "Metacognition research should route durable prior context before fresh web search.",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _research_args(**overrides) -> argparse.Namespace:
    base = {
        "query": "https://metacognition.example/research",
        "depth": 0,
        "model": "",
        "json": True,
        "brain_db": "",
        "recall_limit": 4,
        "no_brain_recall": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_unified_brain_recall_reads_cross_repo_context(tmp_path: Path):
    db = _brain_db(tmp_path / "brain.db")

    payload = lgwks_research_memory.recall("metacognition prior context", db_path=db, limit=3)

    assert payload["ok"] is True
    assert payload["hit_count"] == 1
    assert payload["matched_terms"] == ["context", "metacognition", "prior"]
    assert payload["missing_terms"] == []
    assert payload["hits"][0]["table"] == "chronicle"
    assert payload["hits"][0]["source"] == "logicalworks-:metacognition-001"
    assert payload["hits"][0]["matched_terms"] == ["metacognition", "prior", "context"]
    assert "durable prior context" in payload["hits"][0]["snippet"]


def test_codebase_brain_requires_explicit_db_configuration(monkeypatch):
    monkeypatch.delenv("LGWKS_AGENT_BRAIN_DB", raising=False)

    payload = lgwks_research_memory.recall("metacognition prior context")

    assert payload["ok"] is False
    assert payload["configured"] is False
    assert payload["db"] == ""
    assert "not configured" in payload["error"]
    assert "/Users/srinji/ingestion_results" not in json.dumps(payload)


def test_do_research_skips_unconfigured_codebase_brain(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LGWKS_AGENT_BRAIN_DB", raising=False)
    manifest = {
        "run_id": "ok-run",
        "artifacts": {"root": str(tmp_path / "run")},
        "counts": {"documents": 1, "chunks": 2, "facts": 0, "vectors": 0},
    }
    args = _research_args()

    with mock.patch("lgwks_do._run_aup_check", return_value=PhaseResult("aup:check", True, 0, message="allow")):
        with mock.patch("lgwks_substrate.build_run", return_value=manifest):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = lgwks_do._do_research(args)

    payload = json.loads(buf.getvalue())
    assert rc == 0
    phase = payload["phases"][1]
    assert phase["name"] == "brain:recall"
    assert phase["ok"] is True
    assert phase["exit_code"] == 0
    assert phase["artifact"]["configured"] is False
    assert "not configured" in phase["message"]


def test_do_research_attaches_brain_recall_phase(tmp_path: Path):
    db = _brain_db(tmp_path / "brain.db")
    manifest = {
        "run_id": "ok-run",
        "artifacts": {"root": str(tmp_path / "run")},
        "counts": {"documents": 1, "chunks": 2, "facts": 0, "vectors": 0},
    }
    args = _research_args(brain_db=str(db))

    with mock.patch("lgwks_do._run_aup_check", return_value=PhaseResult("aup:check", True, 0, message="allow")):
        with mock.patch("lgwks_substrate.build_run", return_value=manifest):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = lgwks_do._do_research(args)

    payload = json.loads(buf.getvalue())
    assert rc == 0
    assert payload["verdict"] == "pass"
    phase = payload["phases"][1]
    assert phase["name"] == "brain:recall"
    assert phase["artifact"]["hit_count"] == 1
    assert phase["artifact"]["hits"][0]["source"] == "logicalworks-:metacognition-001"


def test_do_research_fails_closed_on_empty_substrate(tmp_path: Path):
    manifest = {
        "run_id": "empty-run",
        "artifacts": {"root": str(tmp_path / "run")},
        "counts": {"documents": 0, "chunks": 0, "facts": 0, "vectors": 0},
    }
    args = _research_args(no_brain_recall=True)

    with mock.patch("lgwks_do._run_aup_check", return_value=PhaseResult("aup:check", True, 0, message="allow")):
        with mock.patch("lgwks_substrate.build_run", return_value=manifest):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = lgwks_do._do_research(args)

    payload = json.loads(buf.getvalue())
    phase = payload["phases"][-1]
    assert rc == 2
    assert payload["verdict"] == "degraded"
    assert phase["name"] == "substrate:research"
    assert phase["ok"] is False
    assert phase["exit_code"] == 2
    assert phase["message"] == "0 docs, 0 chunks"
