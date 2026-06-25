"""S1 (#336) — lgwks_models_dev: cloud-plane catalog client.

All tests are hermetic: the network is never touched (we monkeypatch
`_fetch_remote`) and the real `.lgwks/models-dev.json` cache is never clobbered
(we redirect `CACHE_PATH` into tmp_path).
"""
from __future__ import annotations

import json

import lgwks_models_dev as m

_FAKE = {
    "schema": m.SCHEMA,
    "source": m.API_URL,
    "fetched_at": "2026-06-25T00:00:00+00:00",
    "providers": {
        "anthropic": {"id": "anthropic", "models": {
            "claude-x": {"name": "Claude X", "family": "claude",
                         "limit": {"context": 200000, "output": 8192},
                         "modalities": {"input": ["text", "image"], "output": ["text"]},
                         "reasoning": False, "tool_call": True, "open_weights": False,
                         "cost": {"input": 3, "output": 15}}}},
        "agg": {"id": "agg", "models": {"xai/grok": {"name": "Grok via agg"}}},  # namespaced id
    },
}


def _redirect_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_PATH", tmp_path / "models-dev.json")


def test_refresh_writes_cache(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(m, "_fetch_remote", lambda timeout: _FAKE)
    snap = m.refresh(force=True)
    assert snap["providers"]["anthropic"]["models"]["claude-x"]["name"] == "Claude X"
    assert (tmp_path / "models-dev.json").exists()  # atomic write landed


def test_offline_cache_hit_skips_network(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    # seed a FRESH cache, then make any fetch explode — refresh must not call it
    (tmp_path / "models-dev.json").write_text(json.dumps({**_FAKE, "fetched_at": m.datetime.now(m.timezone.utc).isoformat()}))
    def _boom(timeout):  # noqa: ANN001
        raise AssertionError("network must not be touched on a fresh cache")
    monkeypatch.setattr(m, "_fetch_remote", _boom)
    snap = m.refresh()
    assert snap["providers"]["anthropic"]["models"]["claude-x"]


def test_degrade_when_fetch_fails_and_no_cache(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    def _fail(timeout):  # noqa: ANN001
        raise m.urllib.error.URLError("offline")
    monkeypatch.setattr(m, "_fetch_remote", _fail)
    snap = m.refresh(force=True)  # never raises
    assert snap["degraded"] is True and snap["providers"] == {}


def test_resolve_hit_and_normalized_card(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    (tmp_path / "models-dev.json").write_text(json.dumps(_FAKE))
    card = m.resolve("anthropic/claude-x")
    assert card is not None
    assert card["ref"] == "anthropic/claude-x"
    assert card["locality"] == "cloud"
    assert card["context"] == 200000
    assert card["tool_call"] is True
    assert card["input_modalities"] == ["text", "image"]


def test_resolve_namespaced_model_id(monkeypatch, tmp_path):
    """Aggregator model ids contain '/': split only on the first separator."""
    _redirect_cache(monkeypatch, tmp_path)
    (tmp_path / "models-dev.json").write_text(json.dumps(_FAKE))
    card = m.resolve("agg/xai/grok")
    assert card is not None and card["model"] == "xai/grok"


def test_resolve_miss_returns_none(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    (tmp_path / "models-dev.json").write_text(json.dumps(_FAKE))
    assert m.resolve("nope/nope") is None
    assert m.resolve("malformed-no-slash") is None
    assert m.resolve("") is None


def test_malformed_cache_recovers(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    (tmp_path / "models-dev.json").write_text("{not valid json")
    assert m._load_cache() == {}  # corrupt → empty, never raises


def test_providers_and_models_listing(monkeypatch, tmp_path):
    _redirect_cache(monkeypatch, tmp_path)
    (tmp_path / "models-dev.json").write_text(json.dumps(_FAKE))
    assert m.providers() == ["agg", "anthropic"]
    assert m.models("anthropic") == ["anthropic/claude-x"]
