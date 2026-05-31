#!/usr/bin/env python3
"""
lgwks_run — the post-gate execution spine (Issue #7, ADR-001).

This is the moment after the form, the intent map, and all five DiD gates plus the conduct review
have clicked GREEN. The plan is frozen; the crawler must now run. This module is the trust-boundary
wrapper around the crawl mechanics — it is NOT the crawl algorithm (that is `lgwks jarvis crawl`).
Its job is to make "all gates passed -> fetch the declared set -> honest artifacts" unviolable:

  1. fail-closed gate precondition  — every required verdict must be present AND passed (L1/L6/L9).
  2. frozen-scope enforcement       — the crawler can ONLY touch the declared URL set; it can never
                                      grow (L6/L7). A URL not in the frozen set is dropped, logged.
  3. per-host politeness            — honor the granted/declared rate (G5).
  4. provider seams                 — fetch (curl_cffi -> urllib) and embed (mlx -> deterministic);
                                      absent provider falls back, never fails the run.
  5. post-crawl constitution checks — L2 (label <= evidence), L3 (uncertainty from information),
                                      L4 (no falsifier/tier -> quarantine).
  6. hash-chained run log           — every step appended + chained (L5); the run is replayable.

Runnable offline today: `--dry` uses synthetic pages (no network) so the spine is testable end-to-end.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIGNER = "local-unanchored"  # hardening target: Secure Enclave (ADR-064); linkage still detects rewrite
DIMS = 256

# Every gate that must have clicked before the crawler may run (ADR-001 §5 + L9).
GATES_REQUIRED = ("G1_intent", "G2_scope_lock", "G3_url_risk", "G4_auth", "G5_egress", "L9_conduct")


class GateError(Exception):
    """A required gate is missing or red. Fail-closed: the crawler does not run."""


class ScopeError(Exception):
    """An attempt to touch a URL outside the frozen declared set (L6)."""


@dataclass(frozen=True)
class GateVerdict:
    gate: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class RunPlan:
    run_id: str
    chain_label: str
    frozen_scope: tuple[str, ...]      # the declared URL set — immutable (L6)
    keywords: tuple[str, ...]
    max_pages: int
    per_host_seconds: float            # min seconds between fetches to one host (G5/auth grant)
    tier_floor: str
    embed: bool                        # default-on; False -> the Eye never loads
    verdicts: tuple[GateVerdict, ...]


@dataclass
class FetchResult:
    url: str
    status: str
    text: str = ""
    error: str = ""


@dataclass
class RunResult:
    run_id: str
    fetched: int
    documents: int
    nodes: int
    edges: int
    quarantined: int
    coverage: float
    uncertainty: float
    embed_provider: str
    prevector_path: str
    runlog_intact: bool


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fail-closed gate precondition.
# ─────────────────────────────────────────────────────────────────────────────
def assert_gates_clicked(plan: RunPlan) -> None:
    by_gate = {v.gate: v for v in plan.verdicts}
    for gate in GATES_REQUIRED:
        v = by_gate.get(gate)
        if v is None:
            raise GateError(f"gate {gate} never evaluated — refusing to crawl (fail-closed)")
        if not v.passed:
            raise GateError(f"gate {gate} is RED: {v.detail} — refusing to crawl")
    if not plan.frozen_scope:
        raise GateError("frozen scope is empty — nothing was declared")


# ─────────────────────────────────────────────────────────────────────────────
# 2/3. Frozen scope + per-host politeness.
# ─────────────────────────────────────────────────────────────────────────────
def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def _in_scope(url: str, frozen: tuple[str, ...]) -> bool:
    return url in frozen


class HostRate:
    def __init__(self, per_host_seconds: float):
        self.gap = max(0.0, per_host_seconds)
        self._last: dict[str, float] = {}

    def wait(self, host: str, clock=time.time, sleep=time.sleep) -> None:
        if self.gap <= 0:
            return
        now = clock()
        due = self._last.get(host, 0.0) + self.gap
        if now < due:
            sleep(due - now)
        self._last[host] = clock()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Provider seams (fetch, embed). Absent provider -> deterministic fallback, never a hard fail.
# ─────────────────────────────────────────────────────────────────────────────
def fetch(url: str, dry: bool, synthetic: dict[str, str] | None) -> FetchResult:
    if dry:
        text = (synthetic or {}).get(url, "")
        return FetchResult(url, "ok" if text else "error", text=text,
                           error="" if text else "no synthetic page")
    # Tier 1 stealth if available; else stdlib. (curl_cffi gives a real Chrome TLS/JA4 fingerprint.)
    try:
        from curl_cffi import requests as cffi  # type: ignore
        r = cffi.get(url, impersonate="chrome", timeout=20)
        return FetchResult(url, "ok", text=r.text)
    except ImportError:
        pass
    except Exception as exc:  # fetch failure is recorded, never hidden
        return FetchResult(url, "error", error=str(exc))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lgwks-jarvis-crawl/0.2 (+research)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return FetchResult(url, "ok", text=resp.read(2_000_000).decode("utf-8", errors="replace"))
    except Exception as exc:
        return FetchResult(url, "error", error=str(exc))


def _deterministic_embed(text: str, dims: int = DIMS) -> list[float]:
    vec = [0.0] * dims
    toks = re.findall(r"[a-z0-9]+", text.lower())
    for tok in toks:
        d = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def embed(text: str, embed_on: bool) -> tuple[list[float] | None, str, bool]:
    """Returns (vector, provider, is_semantic). is_semantic gates L2 edge labelling."""
    if not embed_on:
        return None, "none", False
    if importlib.util.find_spec("mlx_embeddings") is not None:
        # The real Eye (Qwen3-Embedding via MLX) wires in here during the migration and returns a
        # SEMANTIC vector (is_semantic=True -> L2 lets edges be labelled semantic_similarity). Until
        # that wiring lands we fall through to the deterministic provider, which is NOT semantic.
        pass
    return _deterministic_embed(text), "deterministic-feature-hash", False


# ─────────────────────────────────────────────────────────────────────────────
# 6. Hash-chained, append-only run log (L5) — replayable; tamper breaks the chain.
# ─────────────────────────────────────────────────────────────────────────────
class RunLog:
    def __init__(self, run_id: str, path: Path | None):
        self.run_id = run_id
        self.path = path
        self.records: list[dict] = []
        self._prev = "0" * 64

    def append(self, event: str, data: dict) -> None:
        rec = {"seq": len(self.records) + 1, "event": event, "run_id": self.run_id,
               "data": data, "prev_hash": self._prev}
        core = json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
        rec["hash"] = hashlib.sha256((core + self._prev + SIGNER).encode()).hexdigest()
        self._prev = rec["hash"]
        self.records.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def verify(self) -> bool:
        prev = "0" * 64
        for rec in self.records:
            core = json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
            if rec["hash"] != hashlib.sha256((core + prev + SIGNER).encode()).hexdigest():
                return False
            prev = rec["hash"]
        return True


def _chunk(text: str, size: int = 400) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)] or []


# ─────────────────────────────────────────────────────────────────────────────
# The spine.
# ─────────────────────────────────────────────────────────────────────────────
def execute_plan(plan: RunPlan, dry: bool = False, synthetic: dict[str, str] | None = None,
                 out_dir: Path | None = None, rate: HostRate | None = None) -> RunResult:
    assert_gates_clicked(plan)                                   # 1 — fail-closed
    out_dir = out_dir or (ROOT / "runs" / plan.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(plan.run_id, out_dir / "run.log.jsonl")
    rate = rate or HostRate(plan.per_host_seconds)
    log.append("run_start", {"chain": plan.chain_label, "scope_size": len(plan.frozen_scope),
                             "gates": [v.gate for v in plan.verdicts if v.passed]})

    docs: list[dict] = []
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    embeddings: list[dict] = []          # the objective vector cache (persisted below)
    fetched = 0
    embed_provider = "none"

    for url in plan.frozen_scope:                                # 2 — only the declared set; never grows
        if not _in_scope(url, plan.frozen_scope):
            log.append("scope_drop", {"url": url}); continue
        if fetched >= plan.max_pages:
            log.append("budget_stop", {"max_pages": plan.max_pages}); break
        rate.wait(_host(url))                                    # 3 — politeness
        res = fetch(url, dry, synthetic)                         # 4 — provider seam
        fetched += 1
        log.append("fetch", {"url": url, "status": res.status, "error": res.error})
        if res.status != "ok" or not res.text.strip():
            continue
        doc_id = f"doc-{hashlib.sha256((url + res.text).encode()).hexdigest()[:12]}"
        docs.append({"id": doc_id, "url": url, "words": len(res.text.split())})
        for ci, chunk in enumerate(_chunk(res.text)):
            vec, embed_provider, semantic = embed(chunk, plan.embed)  # 4
            if vec is not None:           # persist to the vector cache, stamped with provider/dim
                embeddings.append({"id": f"{doc_id}-c{ci}", "doc": doc_id, "dim": len(vec),
                                   "provider": embed_provider, "semantic": semantic, "vector": vec})
            for term in {t for t in re.findall(r"[a-z][a-z0-9]{3,}", chunk.lower()) if t in plan.keywords}:
                nid = f"term-{term}"
                nodes.setdefault(nid, {"id": nid, "label": term, "weight": 0.0,
                                       "falsifier": None, "tier": plan.tier_floor})
                nodes[nid]["weight"] += 1.0
                # L2: an edge is 'semantic' only if a real semantic vector backed it; else lexical.
                edges.append({"from": doc_id, "to": nid,
                              "kind": "semantic_similarity" if semantic else "lexical_cooccurrence"})

    # 5 — post-crawl constitution checks.
    coverage = round(len(docs) / max(1, plan.max_pages), 4)
    # L3: uncertainty from information (evidence breadth + node support), not page-count alone.
    supported = sum(1 for n in nodes.values() if n["weight"] >= 2)
    info = min(1.0, supported / max(1, len(plan.keywords)))
    uncertainty = round(1.0 - 0.5 * coverage - 0.5 * info, 4)
    log.append("L3_uncertainty", {"coverage": coverage, "information": round(info, 4), "uncertainty": uncertainty})
    # L4: a node with no falsifier and only the floor tier is not promotable -> quarantine.
    quarantine = [n for n in nodes.values() if n["falsifier"] is None]
    if quarantine:
        (out_dir / "quarantine.jsonl").write_text(
            "\n".join(json.dumps(n, sort_keys=True) for n in quarantine) + "\n", encoding="utf-8")
        log.append("L4_quarantine", {"count": len(quarantine), "reason": "no falsifier/tier — human review"})

    # 6 — pre-vector export (graph-schema/2-shaped; splice-and-dice / canvas viz).
    prevector = out_dir / "prevector.graph.json"
    prevector.write_text(json.dumps({
        "$schema": "graph-schema/2", "run_id": plan.run_id, "embed_provider": embed_provider,
        "nodes": list(nodes.values()), "edges": edges,
        "math": {"coverage": coverage, "uncertainty": uncertainty},
    }, indent=2, sort_keys=True), encoding="utf-8")
    if embeddings:                          # the objective vector cache (default-on; empty if --no-embed)
        (out_dir / "embeddings.jsonl").write_text(
            "\n".join(json.dumps(e, sort_keys=True) for e in embeddings) + "\n", encoding="utf-8")
        log.append("vector_cache", {"count": len(embeddings), "provider": embed_provider})
    log.append("run_end", {"documents": len(docs), "nodes": len(nodes), "edges": len(edges)})

    return RunResult(run_id=plan.run_id, fetched=fetched, documents=len(docs), nodes=len(nodes),
                     edges=len(edges), quarantined=len(quarantine), coverage=coverage,
                     uncertainty=uncertainty, embed_provider=embed_provider,
                     prevector_path=str(prevector), runlog_intact=log.verify())


def _demo_plan(all_pass: bool = True) -> tuple[RunPlan, dict[str, str]]:
    scope = ("https://example.org/crm-architecture", "https://example.org/crm-vs-cdp")
    synthetic = {
        scope[0]: "A CRM depends on identity and contact storage. Pipeline stages gate deal flow. "
                  "Lambda and cognito and github and jira connect as service nodes in the architecture.",
        scope[1]: "CRM versus CDP: the CRM controls contact records while the CDP controls events. "
                  "Benchmark against incumbents salesforce and hubspot for truth not marketing.",
    }
    verdicts = tuple(GateVerdict(g, all_pass, "" if all_pass else "demo-forced-red") for g in GATES_REQUIRED)
    plan = RunPlan(run_id="demo-crm", chain_label="mechanism",
                   frozen_scope=scope, keywords=("crm", "lambda", "cognito", "github", "jira", "cdp", "contact"),
                   max_pages=12, per_host_seconds=0.0, tier_floor="secondary", embed=True, verdicts=verdicts)
    return plan, synthetic


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lgwks_run", description="post-gate crawl execution spine")
    p.add_argument("--dry", action="store_true", help="synthetic pages, no network (testable)")
    p.add_argument("--demo", action="store_true", help="run the offline CRM demo")
    p.add_argument("--fail-gate", action="store_true", help="demo with a RED gate (shows fail-closed)")
    args = p.parse_args(argv)
    if not (args.demo or args.fail_gate):
        p.print_help(); return 1
    plan, synthetic = _demo_plan(all_pass=not args.fail_gate)
    out = ROOT / "runs" / plan.run_id
    try:
        res = execute_plan(plan, dry=True, synthetic=synthetic, out_dir=out)
    except GateError as exc:
        print(f"  REFUSED (fail-closed): {exc}")
        return 3
    print(f"  run {res.run_id}: fetched={res.fetched} docs={res.documents} nodes={res.nodes} "
          f"edges={res.edges} quarantined={res.quarantined}")
    print(f"  embed={res.embed_provider}  coverage={res.coverage}  uncertainty={res.uncertainty}")
    print(f"  run log chain intact: {res.runlog_intact}")
    print(f"  pre-vector graph: {res.prevector_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
