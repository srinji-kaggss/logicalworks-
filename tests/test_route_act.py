from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import lgwks_route


def _engine(pathway: str) -> dict:
    return {
        "schema": "lgwks.engine.schema.v1",
        "pathways": [pathway],
        "insights": {
            "selections": [{"verb": pathway, "intent": "selected", "score": 1.0}],
            "scores": {"confidence_P": 1.0},
        },
        "meta": {"risk": {"verdict": "proceed"}},
    }


def test_route_act_executes_codebase_search_in_one_call(monkeypatch, tmp_path: Path):
    import lgwks_codebase
    import lgwks_engine

    built: list[Path | None] = []
    searched: list[tuple[str, int]] = []

    monkeypatch.setattr(lgwks_engine, "run_engine", lambda intent, repo=None, top=5: _engine("codebase search"))
    monkeypatch.setattr(lgwks_codebase, "status", lambda: {"schema": "lgwks.codebase.v0", "indexed": False})
    monkeypatch.setattr(lgwks_codebase, "index_stale", lambda repo=None: False)
    monkeypatch.setattr(lgwks_codebase, "build_index", lambda repo=None: built.append(repo) or SimpleNamespace(
        schema="lgwks.codebase.v0",
        file_count=1,
        entity_count=2,
        relation_count=3,
    ))
    monkeypatch.setattr(lgwks_codebase, "search", lambda query, top_k=5, kind_filter=None: searched.append((query, top_k)) or [
        {"file": "lgwks_route.py", "name": "act_intent", "kind": "function", "line": 1}
    ])

    result = lgwks_route.act_intent("find the codebase orchestrator entrypoint", repo=tmp_path, top=7)

    assert result["schema"] == "lgwks.route.act.v1"
    assert result["ok"] is True
    assert result["executed"] is True
    assert result["action"]["verb"] == "codebase search"
    assert [p["name"] for p in result["phases"]] == ["route:engine", "codebase:index", "codebase:search"]
    assert built == [tmp_path]
    assert searched == [("find the codebase orchestrator entrypoint", 7)]
    assert result["result"]["results"][0]["file"] == "lgwks_route.py"


def test_route_act_rebuilds_stale_codebase_index(monkeypatch, tmp_path: Path):
    import lgwks_codebase
    import lgwks_engine

    built: list[Path | None] = []

    monkeypatch.setattr(lgwks_engine, "run_engine", lambda intent, repo=None, top=5: _engine("codebase search"))
    monkeypatch.setattr(lgwks_codebase, "status", lambda: {"schema": "lgwks.codebase.v0", "entity_count": 10})
    monkeypatch.setattr(lgwks_codebase, "index_stale", lambda repo=None: True)
    monkeypatch.setattr(lgwks_codebase, "build_index", lambda repo=None: built.append(repo) or SimpleNamespace(
        schema="lgwks.codebase.v0",
        file_count=1,
        entity_count=2,
        relation_count=3,
    ))
    monkeypatch.setattr(lgwks_codebase, "search", lambda query, top_k=5, kind_filter=None: [])

    result = lgwks_route.act_intent("find new route act code", repo=tmp_path)

    assert result["ok"] is True
    assert [p["name"] for p in result["phases"]] == ["route:engine", "codebase:index", "codebase:search"]
    assert built == [tmp_path]


def test_route_act_blocks_mutating_natural_language(monkeypatch):
    import lgwks_engine

    monkeypatch.setattr(lgwks_engine, "run_engine", lambda intent, repo=None, top=5: _engine("do ship"))

    result = lgwks_route.act_intent("delete generated files and push the fix", execute=True)

    assert result["ok"] is False
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["action"]["kind"] == "blocked_mutation"
    assert "requires an explicit typed workflow" in result["block_reason"]


def test_route_act_compiles_research_url_to_existing_research_spine(monkeypatch):
    import lgwks_engine

    monkeypatch.setattr(lgwks_engine, "run_engine", lambda intent, repo=None, top=5: _engine("do research"))

    result = lgwks_route.act_intent("research https://example.com and recall prior evidence", execute=False)

    assert result["ok"] is True
    assert result["executed"] is False
    assert result["action"]["verb"] == "do research"
    assert result["action"]["kind"] == "research"
    assert result["action"]["target"] == "https://example.com"
