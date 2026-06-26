"""S3 (#338) — the `models` selector surface that the TUI projects.

The TUI holds NO catalog: it reads `lgwks models list` and writes back via
`models locality` / `models use`. These tests lock that Python contract.

Hermetic: SELECTION_PATH is redirected into tmp_path (the real choice is never
clobbered) and the cloud plane is monkeypatched (the network is never touched).
"""
from __future__ import annotations

import lgwks_model_mesh as mesh
import lgwks_model_port as mp


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(mp, "SELECTION_PATH", tmp_path / "model-selection.json")


# ── persistence + precedence ────────────────────────────────────────────────
def test_default_is_local_with_no_selection_file(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    monkeypatch.delenv("LGWKS_MODEL_LOCALITY", raising=False)
    assert mp.load_selection() == {}
    assert mp.active_locality() == mp.LOCAL  # private default, no file needed


def test_set_locality_persists_and_is_read_back(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    monkeypatch.delenv("LGWKS_MODEL_LOCALITY", raising=False)
    mp.set_locality(mp.CLOUD)
    assert (tmp_path / "model-selection.json").exists()
    assert mp.active_locality() == mp.CLOUD  # persisted choice wins over the default


def test_env_overrides_persisted_locality(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    mp.set_locality(mp.CLOUD)
    monkeypatch.setenv("LGWKS_MODEL_LOCALITY", "local")
    assert mp.active_locality() == mp.LOCAL  # env > persisted


def test_set_locality_rejects_unknown(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    try:
        mp.set_locality("mars")
        assert False, "must reject an unknown locality"
    except ValueError:
        pass


def test_corrupt_selection_file_recovers(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "model-selection.json").write_text("{not json")
    assert mp.load_selection() == {}  # never raises
    monkeypatch.delenv("LGWKS_MODEL_LOCALITY", raising=False)
    assert mp.active_locality() == mp.LOCAL


# ── use → resolve_model reads the persisted choice ───────────────────────────
def test_use_persists_cloud_ref_and_resolve_reads_it(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    monkeypatch.delenv("LGWKS_MODEL_LOCALITY", raising=False)
    monkeypatch.delenv("LGWKS_CLOUD_EMBED_MODEL", raising=False)
    import lgwks_models_dev as md
    card = {"ref": "acme/embed-1", "locality": "cloud", "context": 8192}
    monkeypatch.setattr(md, "resolve", lambda ref: card if ref == "acme/embed-1" else None)

    mp.set_model("embed", "acme/embed-1", locality=mp.CLOUD)
    sel = mp.resolve_model("embed")  # locality from persisted state, ref from persisted state
    assert sel is not None
    assert sel["locality"] == mp.CLOUD
    assert sel["runtime_id"] == "acme/embed-1"
    assert sel["card"] == card


def test_env_cloud_ref_overrides_persisted(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    import lgwks_models_dev as md
    monkeypatch.setattr(md, "resolve", lambda ref: {"ref": ref})
    mp.set_model("embed", "persisted/one", locality=mp.CLOUD)
    monkeypatch.setenv("LGWKS_CLOUD_EMBED_MODEL", "env/two")
    sel = mp.resolve_model("embed", locality=mp.CLOUD)
    assert sel["runtime_id"] == "env/two"  # env > persisted


# ── the unified catalog the TUI renders ──────────────────────────────────────
def test_catalog_has_both_planes_and_marks_cloud_opt_in(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    monkeypatch.delenv("LGWKS_MODEL_LOCALITY", raising=False)
    import lgwks_models_dev as md
    fake = {"schema": md.SCHEMA, "fetched_at": "x", "degraded": False,
            "providers": {"openai": {"id": "openai", "models": {"text-embedding-3-small": {}}}}}
    monkeypatch.setattr(md, "refresh", lambda **kw: fake)
    monkeypatch.setattr(md, "models", lambda provider=None: ["openai/text-embedding-3-small"])

    cat = mp.catalog()
    assert cat["schema"] == "lgwks.model.catalog.v1"
    assert cat["active_locality"] == mp.LOCAL and cat["default_locality"] == mp.LOCAL
    # local plane carries the law-pinned embed Eye with its hub runtime id
    embed = [r for r in cat["local"] if r["role"] == "embed"]
    assert embed and embed[0]["law_name"] == mesh.model_name_for_role("embed", trust_class="sensor")
    assert embed[0]["runtime_id"] == embed[0]["law_name"].split("/")[-1]
    # cloud plane is marked opt-in and lists providers
    assert cat["cloud"]["opt_in"] is True
    assert {"id": "openai", "models": 1} in cat["cloud"]["providers"]


def test_catalog_offline_degrades_without_crashing(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    import lgwks_models_dev as md
    def _boom(**kw):
        raise OSError("offline")
    monkeypatch.setattr(md, "refresh", _boom)
    cat = mp.catalog()  # must not raise — the local plane is unaffected
    assert cat["cloud"]["degraded"] is True
    assert any(r["role"] == "embed" for r in cat["local"])  # local still present


def test_catalog_provider_drilldown(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    import lgwks_models_dev as md
    monkeypatch.setattr(md, "refresh", lambda **kw: {"degraded": False, "providers": {}})
    monkeypatch.setattr(md, "models", lambda provider=None: [f"{provider}/m1", f"{provider}/m2"])
    cat = mp.catalog(provider="openai")
    assert cat["cloud"]["models"] == ["openai/m1", "openai/m2"]
