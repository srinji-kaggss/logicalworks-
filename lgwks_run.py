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
import ipaddress
import json
import math
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import lgwks_sign
from axiom.cid import compute_cid as axiom_compute_cid

ROOT = Path(__file__).resolve().parent
DIMS = 256
MAX_BYTES = 3_000_000          # H4: hard response-body cap (both fetch paths)
MAX_REDIRECTS = 3
UNIVERSAL_SCHEMA = "lgwks.run_index.v0"
RUNS_DIR = Path(".lgwks") / "runs"

# Every gate that must have clicked before the crawler may run (ADR-001 §5 + L9).
GATES_REQUIRED = ("G1_intent", "G2_scope_lock", "G3_url_risk", "G4_auth", "G5_egress", "L9_conduct")


def compute_file_cid(path: Path) -> str:
    """Compute Axiom CID of a file's content."""
    return axiom_compute_cid(path.read_bytes())


def write_universal_index(
    root: Path,
    run_id: str,
    source: str,
    artifacts: list[dict[str, Any]],
    links: list[dict[str, str]] | None = None,
    repo: Path | None = None
) -> dict[str, Any]:
    """Write or update a universal run index.
    
    Ensures artifact paths are relative and safe.
    """
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    
    index = {
        "schema": UNIVERSAL_SCHEMA,
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo.resolve()) if repo else str(ROOT.resolve()),
        "source": source,
        "artifacts": artifacts,
        "links": links or [],
    }
    
    # Path safety check
    for art in artifacts:
        p = Path(art["path"])
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"unsafe artifact path: {art['path']}")

    index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    return index


def adopt_axiom_run(axiom_run_dir: Path, repo: Path | None = None) -> dict[str, Any]:
    """Link an Axiom run into the universal run spine."""
    axiom_run_dir = axiom_run_dir.resolve()
    if not axiom_run_dir.is_dir():
        raise ValueError(f"not a directory: {axiom_run_dir}")
    
    repo = (repo or ROOT).resolve()
    index_path = axiom_run_dir / "index.json"
    if not index_path.exists():
        raise ValueError(f"Axiom index.json not found in {axiom_run_dir}")
    
    axiom_index = json.loads(index_path.read_text(encoding="utf-8"))
    axiom_id = axiom_index.get("run_id", axiom_run_dir.name)
    run_id = f"run-{axiom_id.replace('axiom-', '')}"
    
    uni_root = repo / RUNS_DIR / run_id
    
    artifacts = []
    # 1. Add the Axiom run index itself
    if not index_path.is_relative_to(repo):
        raise ValueError(f"Axiom run index is outside the repository boundary: {index_path}")
        
    rel_axiom_index = index_path.relative_to(repo)
    artifacts.append({
        "kind": "axiom_run_index",
        "path": str(rel_axiom_index),
        "schema": axiom_index.get("schema"),
        "cid": compute_file_cid(index_path)
    })
    
    # 2. Add other artifacts from Axiom index
    for art in axiom_index.get("artifacts", []):
        kind = art.get("kind")
        p = Path(art.get("path", ""))
        full_p = (axiom_run_dir / p).resolve()
        
        if not full_p.exists():
            raise ValueError(f"artifact missing from Axiom run: {kind} at {p}")
            
        if not full_p.is_relative_to(repo):
            raise ValueError(f"artifact is outside the repository boundary: {kind} at {full_p}")
            
        rel_p = full_p.relative_to(repo)
        schema = art.get("schema")
        cid = compute_file_cid(full_p)
        
        # HARDEN: Unknown kinds must have a schema and CID
        known_axiom_kinds = {"capture", "emissions", "fabric_log", "narration", "narration_emissions", "narration_fabric_log"}
        if kind not in known_axiom_kinds and not schema:
            raise ValueError(f"unknown artifact kind {kind!r} missing schema in Axiom index")
            
        artifacts.append({
            "kind": f"axiom_{kind}",
            "path": str(rel_p),
            "schema": schema,
            "cid": cid
        })
    
    links = [
        {"from": f"axiom_{a['kind']}", "to": "axiom_run_index", "rel": "described_by"}
        for a in axiom_index.get("artifacts", [])
    ]
    
    return write_universal_index(uni_root, run_id, "axiom", artifacts, links, repo=repo)


def index_command(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.is_dir():
        index_path = path / "index.json"
    else:
        index_path = path
    
    if not index_path.exists():
        print(json.dumps({"ok": False, "error": f"not found: {index_path}"}), file=sys.stderr)
        return 1
        
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        print(json.dumps(index, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


def adopt_axiom_command(args: argparse.Namespace) -> int:
    try:
        res = adopt_axiom_run(Path(args.run_dir), repo=Path(args.repo) if args.repo else None)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("run", help="post-gate crawl execution spine and universal run management")
    p.add_argument("--dry", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--fail-gate", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=_run_compat_dispatch)
    sp = p.add_subparsers(dest="run_command")
    
    # post-gate crawl dispatch (legacy main logic)
    crawl = sp.add_parser("crawl", help="execute a post-gate crawl plan")
    crawl.add_argument("--dry", action="store_true", help="synthetic pages, no network (testable)")
    crawl.add_argument("--demo", action="store_true", help="run the offline CRM demo")
    crawl.add_argument("--fail-gate", action="store_true", help="demo with a RED gate (shows fail-closed)")
    crawl.set_defaults(func=_crawl_dispatch)

    idx = sp.add_parser("index", help="print a universal run index")
    idx.add_argument("path", help="run directory or index.json path")
    idx.add_argument("--json", action="store_true", help="structured output (default)")
    idx.set_defaults(func=index_command)
    
    adopt = sp.add_parser("adopt-axiom", help="link an Axiom run into the universal run spine")
    adopt.add_argument("run_dir", help="Axiom run directory")
    adopt.add_argument("--repo", help="optional repo root")
    adopt.add_argument("--json", action="store_true", help="structured output (default)")
    adopt.set_defaults(func=adopt_axiom_command)


def _run_compat_dispatch(args: argparse.Namespace) -> int:
    if getattr(args, "demo", False) or getattr(args, "fail_gate", False):
        return _crawl_dispatch(args)
    print("Use `lgwks run crawl --demo`, `lgwks run index <path>`, or `lgwks run adopt-axiom <dir>`.", file=sys.stderr)
    return 1


def _crawl_dispatch(args: argparse.Namespace) -> int:
    if not (args.demo or args.fail_gate):
        print("Use --demo or --fail-gate for now; manual crawl plans are not yet CLI-exposed.", file=sys.stderr)
        return 1
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
    print(f"  run log chain intact: {res.runlog_intact}  integrity={res.integrity_mode}  "
          f"gates_verified={res.gates_verified}")
    if res.integrity_mode == "unanchored":
        print("  note: unanchored signer — detects corruption only, NOT adversarial rewrite. "
              "Provision a key: security add-generic-password -U -s lgwks:signing-key -w")
    print(f"  pre-vector graph: {res.prevector_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgwks_run")
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] != "run":
        raw = ["run", *raw]
    add_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(raw)
    return args.func(args)


class ScopeError(Exception):
    """An attempt to touch a URL outside the frozen declared set (L6)."""


class GateError(Exception):
    """A required gate is missing or red. Fail-closed: the crawler does not run."""


@dataclass(frozen=True)
class GateVerdict:
    gate: str
    passed: bool
    detail: str = ""
    sig: str = ""        # C2: HMAC over f"{run_id}|{gate}|{int(passed)}" by the admission verifier


def sign_verdict(run_id: str, gate: str, passed: bool, key: bytes) -> str:
    return lgwks_sign.mac(f"{run_id}|{gate}|{int(passed)}", key)


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
    integrity_mode: str        # keyed-* (tamper-evident) or unanchored (corruption-only — honest)
    gates_verified: bool       # True only when verdict signatures were cryptographically checked


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fail-closed gate precondition.
# ─────────────────────────────────────────────────────────────────────────────
def assert_gates_clicked(plan: RunPlan, key: bytes, mode: str) -> bool:
    """Fail-closed. C2: when keyed, every verdict's signature must verify against this run_id; a
    forged/unsigned verdict is rejected. Returns whether verdicts were cryptographically verified."""
    by_gate = {v.gate: v for v in plan.verdicts}
    for gate in GATES_REQUIRED:
        v = by_gate.get(gate)
        if v is None:
            raise GateError(f"gate {gate} never evaluated — refusing to crawl (fail-closed)")
        if not v.passed:
            raise GateError(f"gate {gate} is RED: {v.detail} — refusing to crawl")
        if lgwks_sign.is_keyed(mode):
            if not lgwks_sign.verify(f"{plan.run_id}|{gate}|1", v.sig, key):
                raise GateError(f"gate {gate} verdict is unsigned/forged — refusing to crawl (C2)")
    if not plan.frozen_scope:
        raise GateError("frozen scope is empty — nothing was declared")
    return lgwks_sign.is_keyed(mode)


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

    def wait(self, host: str, clock=time.time, sleep=time.sleep, gap: float | None = None) -> None:
        effective_gap = max(0.0, self.gap if gap is None else gap)
        if effective_gap <= 0:
            return
        now = clock()
        due = self._last.get(host, 0.0) + effective_gap
        if now < due:
            sleep(due - now)
        self._last[host] = clock()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Provider seams (fetch, embed). Absent provider -> deterministic fallback, never a hard fail.
# ─────────────────────────────────────────────────────────────────────────────
def _scrub(text: str) -> str:
    # L-1: never let a full URL (possible query-string credential) reach a log line.
    return re.sub(r"https?://[^\s'\")]+", "<url>", text)[:300]


def host_is_blocked(host: str) -> bool:
    """C3/L-2: block loopback/private/link-local/metadata + DNS-rebinding. Resolve, then judge every IP."""
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return True
        if ip == ipaddress.ip_address("169.254.169.254"):  # cloud metadata (explicit; covered by link_local)
            return True
    return False


def _allowed_hop(url: str, frozen: tuple[str, ...]) -> bool:
    """A hop is allowed only if it is http(s), in the frozen declared set (L6), and not a blocked host."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):       # no file://, gopher://, etc.
        return False
    if url not in frozen:                        # scope is immutable — a redirect off-set is rejected
        return False
    return not host_is_blocked(p.netloc)


def fetch(url: str, dry: bool, synthetic: dict[str, str] | None, frozen: tuple[str, ...]) -> FetchResult:
    if dry:
        text = (synthetic or {}).get(url, "")
        return FetchResult(url, "ok" if text else "error", text=text,
                           error="" if text else "no synthetic page")
    import lgwks_auth_runtime
    import lgwks_search
    if not _allowed_hop(url, frozen):
        return FetchResult(url, "error", error="blocked: out-of-scope, non-http(s), or private/metadata host")
    # Manual redirect loop: redirects are NOT auto-followed; every hop is re-validated against the
    # frozen scope + IP denylist (C3 — defeats redirect SSRF / scope escape to 169.254.169.254 / localhost).
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        policy = lgwks_auth_runtime.auth_policy_for_url(current)
        if policy["active"] and not policy["usable"]:
            lgwks_auth_runtime.request_keyring(current, reason="active auth lock exists but keychain secret is missing")
            return FetchResult(url, "error", error="auth lock active but no usable keychain secret")
        try:
            from curl_cffi import requests as cffi  # type: ignore
            r = cffi.get(
                current,
                impersonate="chrome",
                timeout=20,
                allow_redirects=False,
                headers=policy["headers"] or None,
            )
            if r.status_code in (301, 302, 303, 307, 308):
                loc = urllib.parse.urljoin(current, r.headers.get("location", ""))
                if not _allowed_hop(loc, frozen):
                    return FetchResult(url, "error", error="redirect off declared scope — refused")
                current = loc
                continue
            if r.status_code in (401, 403):
                lgwks_auth_runtime.note_auth_failure(current, r.status_code)
                return FetchResult(url, "error", error=f"remote returned auth failure ({r.status_code})")
            body = r.text if len(r.content) <= MAX_BYTES else r.text[:MAX_BYTES]  # H4 byte cap
            ok, diag = lgwks_search.source_validity(body, current)
            if not ok:
                lgwks_auth_runtime.request_keyring(current, reason=diag or "auth/access wall detected")
                return FetchResult(url, "error", error=diag or "source validity rejected")
            return FetchResult(url, "ok", text=body)
        except ImportError:
            break
        except Exception as exc:
            return FetchResult(url, "error", error=_scrub(str(exc)))
    # stdlib fallback, redirects disabled via a no-follow opener.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):  # returning None disables auto-follow
            return None
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        policy = lgwks_auth_runtime.auth_policy_for_url(current)
        if policy["active"] and not policy["usable"]:
            lgwks_auth_runtime.request_keyring(current, reason="active auth lock exists but keychain secret is missing")
            return FetchResult(url, "error", error="auth lock active but no usable keychain secret")
        req_headers = {"User-Agent": "lgwks-jarvis-crawl/0.2 (+research)", **policy["headers"]}
        req = urllib.request.Request(current, headers=req_headers)
        try:
            with opener.open(req, timeout=20) as resp:
                body = resp.read(MAX_BYTES).decode("utf-8", errors="replace")
                ok, diag = lgwks_search.source_validity(body, current)
                if not ok:
                    lgwks_auth_runtime.request_keyring(current, reason=diag or "auth/access wall detected")
                    return FetchResult(url, "error", error=diag or "source validity rejected")
                return FetchResult(url, "ok", text=body)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                loc = urllib.parse.urljoin(current, exc.headers.get("Location", ""))
                if not _allowed_hop(loc, frozen):
                    return FetchResult(url, "error", error="redirect off declared scope — refused")
                current = loc
                continue
            if exc.code in (401, 403):
                lgwks_auth_runtime.note_auth_failure(current, exc.code)
            return FetchResult(url, "error", error=_scrub(str(exc)))
        except Exception as exc:
            return FetchResult(url, "error", error=_scrub(str(exc)))
    return FetchResult(url, "error", error="too many redirects")


def _deterministic_embed(text: str, dims: int = DIMS) -> list[float]:
    vec = [0.0] * dims
    toks = re.findall(r"[a-z0-9]+", text.lower())
    for tok in toks:
        d = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        vec[int.from_bytes(d[:4], "big") % dims] += 1.0 if d[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def embed(
    text: str,
    embed_on: bool,
    provider: str = "auto",
    *,
    model: str | None = None,
) -> tuple[list[float] | None, str, bool]:
    """Returns (vector, provider, is_semantic). is_semantic gates L2 edge labelling.
    provider 'auto'|'ollama' tries the real local Eye (qwen3-embedding via Ollama) → semantic vector.
    provider 'openrouter-vl' tries the remote multimodal Eye through OpenRouter.
    Falls back to deterministic feature-hash (NOT semantic)."""
    if not embed_on:
        return None, "none", False
    if provider in ("auto", "ollama"):
        import lgwks_ollama
        lgwks_ollama.ensure_eye_model()      # pull the local Eye on first use (no-op if present/down)
        vec = lgwks_ollama.embed_one(text)
        if vec is not None:
            return lgwks_ollama.slice_mrl(vec, DIMS), f"ollama:{lgwks_ollama.EYE_MODEL}", True
    if provider == "openrouter-vl":
        import lgwks_openrouter_embed
        chosen = model or lgwks_openrouter_embed.DEFAULT_MODEL
        vec = lgwks_openrouter_embed.embed_one(text, model=chosen)
        if vec is not None:
            return vec, f"openrouter:{chosen}", True
    if provider == "apple-local":
        import lgwks_apple
        chosen_model = model or lgwks_apple.DEFAULT_MODEL
        chosen_dims = lgwks_apple.DEFAULT_DIMS
        vec = lgwks_apple.embed_one(text, model_id=chosen_model, dims=chosen_dims)
        if vec is not None:
            return vec, lgwks_apple.provider_label(chosen_model), True
        # apple-local requested but runtime absent: fail closed by returning None
        # so the caller can emit a clear error rather than silently using deterministic.
        return None, "apple-local:unavailable", False
    # MLX path lands here in the migration (also semantic). Until a real provider answers:
    return _deterministic_embed(text), "deterministic-feature-hash", False


# ─────────────────────────────────────────────────────────────────────────────
# 6. Hash-chained, append-only run log (L5) — replayable; tamper breaks the chain.
# ─────────────────────────────────────────────────────────────────────────────
class RunLog:
    """Append-only, HMAC-chained (C1). With a keyed signer the chain is tamper-EVIDENT (a rewriter
    cannot recompute without the secret). Unanchored, it detects accidental corruption only — never
    claimed as more (the mode is reported)."""

    def __init__(self, run_id: str, path: Path | None, key: bytes | None = None):
        self.run_id = run_id
        self.path = path
        self.records: list[dict] = []
        self._prev = "0" * 64
        self._key = key if key is not None else lgwks_sign.signing_key()[0]

    def append(self, event: str, data: dict) -> None:
        rec = {"seq": len(self.records) + 1, "event": event, "run_id": self.run_id,
               "data": data, "prev_hash": self._prev}
        core = json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
        rec["hash"] = lgwks_sign.mac(core + self._prev, self._key)
        self._prev = rec["hash"]
        self.records.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def verify(self) -> bool:
        prev = "0" * 64
        for rec in self.records:
            core = json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
            if not lgwks_sign.verify(core + prev, rec["hash"], self._key):
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
    key, mode = lgwks_sign.signing_key()
    gates_verified = assert_gates_clicked(plan, key, mode)       # 1 — fail-closed + C2 verdict check
    out_dir = out_dir or (ROOT / "runs" / plan.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(plan.run_id, out_dir / "run.log.jsonl", key=key)
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
        import lgwks_auth_runtime
        auth_policy = lgwks_auth_runtime.auth_policy_for_url(url)
        rate.wait(_host(url), gap=max(plan.per_host_seconds, auth_policy["min_interval_seconds"]))  # 3 — politeness
        res = fetch(url, dry, synthetic, plan.frozen_scope)      # 4 — provider seam (scope-bound)
        fetched += 1
        # L-1 (hacker F9): never log a full URL — a query string can carry a credential. Log host+path only.
        safe_url = urllib.parse.urlparse(url)._replace(query="", fragment="").geturl()
        log.append("fetch", {"url": safe_url, "status": res.status, "error": res.error})
        if res.status != "ok" or not res.text.strip():
            continue
        doc_id = f"doc-{hashlib.sha256((url + res.text).encode()).hexdigest()[:12]}"
        docs.append({"id": doc_id, "url": url, "words": len(res.text.split())})
        embed_prov = "deterministic" if dry else "auto"   # dry == hermetic, no external calls
        for ci, chunk in enumerate(_chunk(res.text)):
            vec, embed_provider, semantic = embed(chunk, plan.embed, provider=embed_prov)  # 4
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
                     prevector_path=str(prevector), runlog_intact=log.verify(),
                     integrity_mode=mode, gates_verified=gates_verified)


def _demo_plan(all_pass: bool = True) -> tuple[RunPlan, dict[str, str]]:
    scope = ("https://example.org/crm-architecture", "https://example.org/crm-vs-cdp")
    synthetic = {
        scope[0]: "A CRM depends on identity and contact storage. Pipeline stages gate deal flow. "
                  "Lambda and cognito and github and jira connect as service nodes in the architecture.",
        scope[1]: "CRM versus CDP: the CRM controls contact records while the CDP controls events. "
                  "Benchmark against incumbents salesforce and hubspot for truth not marketing.",
    }
    # Sign verdicts as a legitimate admission verifier would (C2). Under a keyed signer these verify;
    # a caller fabricating verdicts without the key is rejected by assert_gates_clicked.
    key, _ = lgwks_sign.signing_key()
    verdicts = tuple(
        GateVerdict(g, all_pass, "" if all_pass else "demo-forced-red",
                    sig=sign_verdict("demo-crm", g, all_pass, key))
        for g in GATES_REQUIRED
    )
    plan = RunPlan(run_id="demo-crm", chain_label="mechanism",
                   frozen_scope=scope, keywords=("crm", "lambda", "cognito", "github", "jira", "cdp", "contact"),
                   max_pages=12, per_host_seconds=0.0, tier_floor="secondary", embed=True, verdicts=verdicts)
    return plan, synthetic


if __name__ == "__main__":
    raise SystemExit(main())
