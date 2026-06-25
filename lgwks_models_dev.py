"""lgwks_models_dev — the CLOUD plane of the model layer (epic #335 / S1 #336).

The model layer has ONE port (`lgwks_model_port`) over a **locality axis**:

  • LOCAL  = `lgwks_model_mesh` (MESH_LAW) + `lgwks_model_hub` — on-device MLX,
             privacy-first, the DEFAULT.
  • CLOUD  = THIS module — used ONLY when the user opts into a cloud brain.
  • AETHERIUS = the future end-of-ingestion model (deferred; slot only).

This is a faithful, stdlib-only Python translation of OpenCode's Go models.dev
integration: fetch the open catalog (`https://models.dev/api.json`), cache it
offline-first, and resolve a `providerID/modelID` reference into a normalized
model card whose SHAPE mirrors `lgwks_model_hub._MODEL_CATALOG` — so LOCAL and
CLOUD are one card shape, not two divergent ones.

Design contract:
  • Zero new runtime dependencies — stdlib `urllib` + `json` only.
  • Offline-first — a missing network serves the cache; a missing/corrupt cache
    degrades to an empty catalog and NEVER raises (the local plane is unaffected).
  • Bounded egress — exactly one GET with a hard timeout (no crawl, no retry storm).
  • Privacy — performs NO inference and sends NO user data; fetches only the
    public catalog JSON.

`lgwks_model_port` (S2 #337) is the ONE selector that picks LOCAL vs CLOUD; the
Rust TUI (S3 #338) surfaces this catalog via the daemon. This module is the data
layer only — it makes no selection and runs no model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lgwks_substrate_config as _cfg  # canonical repo root — one source of truth

SCHEMA = "lgwks.models_dev.v1"
API_URL = "https://models.dev/api.json"
CACHE_PATH = _cfg.ROOT / ".lgwks" / "models-dev.json"
DEFAULT_TTL_S = 86_400  # a day; the catalog changes slowly
DEFAULT_TIMEOUT_S = 15.0
# Provenance over assertion: the catalog is the open models.dev dataset. Its
# license lives in the upstream repo; we record the source and the fetch time on
# every snapshot rather than hard-code a license claim we have not verified.
SOURCE = "models.dev"


# --------------------------------------------------------------------------- #
# cache IO (atomic) — NOTE: the repo has ~5 divergent json writers (#150 C-14);
# this stays a private local writer using the correct tmp+os.replace atomic
# pattern until that family converges onto one canonical `lgwks_substrate_io`
# helper. Do not promote this to a 6th public copy.
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic rename — a concurrent reader sees old-or-new, never a partial


def _load_cache() -> dict[str, Any]:
    """The cached snapshot, or {} when absent/corrupt (never raises)."""
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_age_s(snapshot: dict[str, Any]) -> float | None:
    stamp = snapshot.get("fetched_at")
    if not stamp:
        return None
    try:
        fetched = datetime.fromisoformat(stamp)
        return (datetime.now(timezone.utc) - fetched).total_seconds()
    except (ValueError, TypeError):
        return None


def _fetch_remote(timeout: float) -> dict[str, Any]:
    """One bounded GET of the public catalog. Raises on any network/parse failure."""
    req = urllib.request.Request(API_URL, headers={"User-Agent": "lgwks-models-dev/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed trusted host)
        raw = resp.read()
    providers = json.loads(raw)
    if not isinstance(providers, dict):
        raise ValueError("models.dev api.json did not parse to a provider map")
    return {
        "schema": SCHEMA,
        "source": API_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers,
    }


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def refresh(*, force: bool = False, ttl_s: int = DEFAULT_TTL_S,
            timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Return a catalog snapshot, refreshing from models.dev when stale.

    Offline-first: if the cache is fresh (age < ttl_s) and not `force`, return it
    without touching the network. Otherwise attempt one bounded GET; on ANY
    failure fall back to the existing cache (stale is better than dead), and if
    there is no cache return an empty-but-valid snapshot. Never raises.
    """
    cached = _load_cache()
    if not force and cached.get("providers"):
        age = _cache_age_s(cached)
        if age is not None and age < ttl_s:
            return cached
    try:
        fresh = _fetch_remote(timeout)
        _atomic_write_json(CACHE_PATH, fresh)
        return fresh
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        if cached.get("providers"):
            return cached  # degrade to stale cache — the cloud plane is best-effort
        return {"schema": SCHEMA, "source": API_URL, "fetched_at": None,
                "providers": {}, "degraded": True}


def _catalog() -> dict[str, Any]:
    """The provider->meta map from cache (or a refresh if no cache exists yet)."""
    snap = _load_cache()
    if not snap.get("providers"):
        snap = refresh()
    return snap.get("providers", {})


def _card(provider_id: str, model_id: str, m: dict[str, Any], fetched_at: str | None) -> dict[str, Any]:
    """Normalize a models.dev model entry into the one cross-plane card shape.

    Mirrors the *role* of `lgwks_model_hub._MODEL_CATALOG` (a catalog card) while
    carrying cloud-specific access metadata. `locality="cloud"` is the axis tag the
    port reads.
    """
    limit = m.get("limit") or {}
    modalities = m.get("modalities") or {}
    return {
        "ref": f"{provider_id}/{model_id}",
        "provider": provider_id,
        "model": model_id,
        "name": m.get("name") or model_id,
        "locality": "cloud",
        "family": m.get("family"),
        "context": limit.get("context"),
        "max_output": limit.get("output"),
        "input_modalities": list(modalities.get("input", [])),
        "output_modalities": list(modalities.get("output", [])),
        "reasoning": bool(m.get("reasoning")),
        "tool_call": bool(m.get("tool_call")),
        "open_weights": bool(m.get("open_weights")),
        "cost": m.get("cost") or {},
        "knowledge": m.get("knowledge"),
        "source": SOURCE,
        "fetched_at": fetched_at,
    }


def resolve(ref: str) -> dict[str, Any] | None:
    """Resolve a `providerID/modelID` reference to a normalized card, or None.

    The model id may itself contain '/' (aggregator providers re-expose namespaced
    ids), so we split only on the FIRST '/'. Unknown refs return None — never raise.
    """
    if not ref or "/" not in ref:
        return None
    provider_id, model_id = ref.split("/", 1)
    snap = _load_cache() or refresh()
    provider = (snap.get("providers") or {}).get(provider_id)
    if not isinstance(provider, dict):
        return None
    model = (provider.get("models") or {}).get(model_id)
    if not isinstance(model, dict):
        return None
    return _card(provider_id, model_id, model, snap.get("fetched_at"))


def providers() -> list[str]:
    """Sorted provider ids in the catalog (for the selector / TUI)."""
    return sorted(_catalog().keys())


def models(provider: str | None = None) -> list[str]:
    """Sorted `providerID/modelID` refs, optionally filtered to one provider."""
    cat = _catalog()
    out: list[str] = []
    for pid, pmeta in cat.items():
        if provider is not None and pid != provider:
            continue
        for mid in (pmeta.get("models") or {}):
            out.append(f"{pid}/{mid}")
    return sorted(out)


# --------------------------------------------------------------------------- #
# CLI (standalone + dispatcher) — read-only over the catalog
# --------------------------------------------------------------------------- #
def add_parser(sub: Any) -> None:
    p = sub.add_parser("models-dev", help="cloud-plane model catalog (models.dev)")
    s = p.add_subparsers(dest="action", required=True)
    r = s.add_parser("refresh", help="fetch/refresh the catalog snapshot")
    r.add_argument("--force", action="store_true", help="ignore TTL and re-fetch")
    lp = s.add_parser("list", help="list providers, or models for --provider")
    lp.add_argument("--provider", default=None)
    rp = s.add_parser("resolve", help="resolve providerID/modelID to a card")
    rp.add_argument("ref")
    p.set_defaults(_run=_run)


def _run(args: argparse.Namespace) -> int:
    if args.action == "refresh":
        snap = refresh(force=getattr(args, "force", False))
        n = sum(len(p.get("models") or {}) for p in snap.get("providers", {}).values())
        print(json.dumps({"source": snap.get("source"), "fetched_at": snap.get("fetched_at"),
                          "providers": len(snap.get("providers", {})), "models": n,
                          "degraded": snap.get("degraded", False)}, indent=2))
        return 0
    if args.action == "list":
        items = models(args.provider) if args.provider else providers()
        print(json.dumps(items, indent=2))
        return 0
    if args.action == "resolve":
        card = resolve(args.ref)
        if card is None:
            print(json.dumps({"error": "not found", "ref": args.ref}))
            return 1
        print(json.dumps(card, indent=2))
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgwks models-dev")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add_parser(sub)
    # add_parser registers under "models-dev"; for standalone, accept the action directly
    args = parser.parse_args(["models-dev", *(argv if argv is not None else sys.argv[1:])])
    return args._run(args)


if __name__ == "__main__":
    raise SystemExit(main())
