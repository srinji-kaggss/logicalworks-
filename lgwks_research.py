"""
lgwks_research — autonomous deep-research loop (Issue #9, parent #7).

Given a seed intent + start node, the instrument STOPS asking questions and self-drives: round after
round of generate → crawl → reason(falsify+expand) → contrarian → save, building each round on the
prior rounds' distilled learnings, until it converges, the frontier goes dry, or the budget caps out.

BOUNDARY (T0, non-negotiable): autonomous PATH selection, not autonomous guardrails. Scope, budget,
and the function-set are frozen at launch (the human declares them once, then steps out). The loop
NEVER widens its own scope and NEVER fetches the open internet unattended — crawl defaults to
`estimate` (offline planning); `live` requires the signed, scope-frozen spine (lgwks_run).

Termination (Director, 2026-05-31): budget-capped convergence —
    stop = converged OR frontier_dry(K) OR budget_exhausted   (budget is the hard ceiling)

Each round is saved under runs/<run_id>/round-NNN/ and appended to a hash-chained ledger (L5): a
rewritten round breaks the chain. Cloud-Tongue tokens are metered against the budget; local/offline
steps are free. The rolling DIGEST (not raw text) is the cross-round memory — it keeps context within
the chosen model's window while the vector cache (live mode) holds the long-term store.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import lgwks_openrouter
import lgwks_sign
import lgwks_tongue

ROOT = Path(__file__).resolve().parent
DRY_LIMIT = 2          # consecutive frontier-dry rounds → converged-by-exhaustion
EIG_FLOOR = 0.15       # a frontier node below this expected-info-gain is not worth a round


@dataclass
class AutoConfig:
    objective: str
    purpose: str
    start: str                                   # the start node ("amazon", a URL, an entity)
    functions: tuple[str, ...] = ("generate", "falsify", "expand", "contrarian")
    max_rounds: int = 6
    token_budget: int = 120_000                  # hard ceiling on cloud-Tongue tokens
    crawl_mode: str = "estimate"                 # estimate (offline planning) | live (signed spine)
    max_pages: int = 8


@dataclass
class Budget:
    cap: int
    spent: int = 0
    def remaining(self) -> int: return max(0, self.cap - self.spent)
    def exhausted(self) -> bool: return self.spent >= self.cap
    def charge(self) -> None: self.spent += lgwks_openrouter.take_usage()


@dataclass
class RoundRecord:
    n: int
    hypotheses: list[dict]
    reason: dict
    contrarian: dict | None
    frontier_in: str
    crawl_note: str
    spent_after: int


@dataclass
class AutoResult:
    run_id: str
    rounds: int
    stop_reason: str
    surviving: list[str]
    spent: int
    out_dir: str
    ledger_intact: bool
    integrity_mode: str


def _run_id(cfg: AutoConfig) -> str:
    h = hashlib.sha256(f"{cfg.objective}|{cfg.start}".encode()).hexdigest()[:8]
    return f"auto-{h}"


def _crawl(cfg: AutoConfig, frontier: str) -> str:
    """The crawl step. estimate = offline planning note (no external fetch). live = the signed,
    scope-frozen spine (lgwks_run) — gated, never silent. Returns the findings text for Reason."""
    if cfg.crawl_mode == "estimate":
        return (f"[estimate mode — no document content fetched] frontier node: {frontier!r}. "
                f"Reason over the hypothesis space and prior learnings; propose what evidence at this "
                f"node would decide each surviving hypothesis.")
    # live mode is intentionally explicit: it must go through the gated, scope-frozen spine
    # (lgwks_run.execute_plan with signed verdicts). Wiring a per-round frozen URL set is the next
    # gated step (#9 Unit A.live) — until provisioned, live degrades to estimate, never silent crawl.
    return (f"[live mode requested for node {frontier!r}] live crawl must run through the signed "
            f"scope-frozen spine with an explicit frozen URL set — not yet provisioned; planning only.")


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def run_auto(cfg: AutoConfig, emit=print) -> AutoResult:
    """Drive the autonomous loop. `emit` is the progress sink (live viz hooks here — Unit C)."""
    run_id = _run_id(cfg)
    out_dir = ROOT / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    key, mode = lgwks_sign.signing_key()
    budget = Budget(cap=cfg.token_budget)
    ledger = out_dir / "rounds.ledger.jsonl"
    prev_hash = "genesis"
    digest = ""                       # rolling cross-round memory (distilled, not raw)
    frontier = cfg.start
    surviving: list[str] = []
    dry_streak = 0
    stop = "max_rounds"
    n = 0

    emit(f"  ◆ autonomous research · {cfg.objective!r} · start={cfg.start!r}")
    emit(f"    functions={','.join(cfg.functions)} · budget={cfg.token_budget} tok · "
         f"crawl={cfg.crawl_mode} · max_rounds={cfg.max_rounds}")

    with ledger.open("w") as lf:
        for n in range(1, cfg.max_rounds + 1):
            if budget.exhausted():
                stop = "budget_exhausted"; break
            emit(f"\n  ── round {n}/{cfg.max_rounds} · frontier={frontier!r} · "
                 f"spent={budget.spent}/{budget.cap} tok ──")

            # 1. GENERATE — autonomous Hn, building on the rolling digest.
            compiled = lgwks_tongue.compile_hypotheses(cfg.objective, cfg.purpose, context=digest)
            budget.charge()
            if not compiled:
                stop = "tongue_offline"; emit("    Tongue offline — stopping (fail closed)."); break
            hyps = compiled["hypotheses"]
            emit(f"    generate: {len(hyps)} hypotheses (H0 null + {len(hyps)-1} mechanism)")

            # 2. CRAWL — frontier node → findings (estimate planning or gated live).
            findings = _crawl(cfg, frontier)

            # 3. REASON — falsify + expand folded in: which falsifiers hit, who survives, next frontier.
            reason = lgwks_tongue.reason_over_findings(cfg.objective, hyps, findings, context=digest)
            budget.charge()
            if not reason:
                stop = "tongue_offline"; emit("    reason step offline — stopping."); break
            surviving = reason["surviving"] or [h["id"] for h in hyps]
            emit(f"    falsify: hit={reason['falsifiers_hit'] or '—'} · surviving={surviving}")
            top = sorted(reason["frontier"], key=lambda f: -f["eig"])
            emit(f"    expand: {len(top)} frontier candidates"
                 + (f" · top={top[0]['node']!r} (eig {top[0]['eig']:.2f})" if top else " · none"))

            # 4. CONTRARIAN (optional) — steelman the null / attack the leading H.
            contra = None
            if "contrarian" in cfg.functions and hyps:
                leading = next((h["claim"] for h in hyps if h.get("role") != "null"), hyps[0]["claim"])
                contra = lgwks_tongue.contrarian(cfg.objective, leading, context=digest)
                budget.charge()
                if contra:
                    emit(f"    contrarian: shifts_belief={contra['shifts_belief']} · {contra['attack'][:80]}")

            # 5. SAVE round artifacts.
            rdir = out_dir / f"round-{n:03d}"
            rdir.mkdir(exist_ok=True)
            (rdir / "hypotheses.json").write_text(_canon(compiled))
            (rdir / "reason.json").write_text(_canon(reason))
            (rdir / "think.md").write_text(
                f"# Round {n} — reasoning trace\n\n## frontier in\n{frontier}\n\n## think\n{reason['think']}\n"
                + (f"\n## contrarian\n{contra['attack']}\n" if contra else ""))
            if contra:
                (rdir / "contrarian.json").write_text(_canon(contra))
            (rdir / "digest.md").write_text(f"# Round {n} digest\n\n{reason['digest']}\n")

            # 6. Hash-chain the round (L5) — tamper breaks the chain.
            rec = {"n": n, "frontier_in": frontier, "hyp_count": len(hyps),
                   "falsifiers_hit": reason["falsifiers_hit"], "surviving": surviving,
                   "learnings": reason["learnings"], "digest": reason["digest"],
                   "converged": reason["converged"], "spent": budget.spent, "prev": prev_hash}
            rec["hash"] = lgwks_sign.mac(prev_hash + _canon(rec), key)
            prev_hash = rec["hash"]
            lf.write(_canon(rec) + "\n"); lf.flush()

            # 7. Carry forward + decide next frontier.
            digest = (digest + "\n" + reason["digest"]).strip()[-6000:]   # window-bounded rolling memory
            top_eig = top[0]["eig"] if top else 0.0
            if reason["converged"]:
                stop = "converged"; emit("\n  ✓ converged — hypotheses resolved."); break
            if not top or top_eig < EIG_FLOOR:
                dry_streak += 1
                if dry_streak >= DRY_LIMIT:
                    stop = "frontier_dry"; emit(f"\n  ✓ frontier dry for {DRY_LIMIT} rounds — stopping."); break
            else:
                dry_streak = 0
                frontier = top[0]["node"]

    intact = _verify_ledger(ledger, key)
    (out_dir / "result.json").write_text(_canon({
        "run_id": run_id, "rounds": n, "stop_reason": stop, "surviving": surviving,
        "spent": budget.spent, "integrity_mode": mode, "ledger_intact": intact,
        "objective": cfg.objective, "start": cfg.start}))
    emit(f"\n  ◆ done · {n} rounds · stop={stop} · surviving={surviving} · spent={budget.spent} tok")
    emit(f"  ↳ artifacts: {out_dir}  (ledger {'intact' if intact else 'BROKEN'} · {mode})")
    return AutoResult(run_id, n, stop, surviving, budget.spent, str(out_dir), intact, mode)


def _verify_ledger(ledger: Path, key: bytes) -> bool:
    if not ledger.exists():
        return False
    prev = "genesis"
    for line in ledger.read_text().splitlines():
        rec = json.loads(line)
        claimed = rec.pop("hash")
        if rec.get("prev") != prev or lgwks_sign.mac(prev + _canon(rec), key) != claimed:
            return False
        prev = claimed
    return True
