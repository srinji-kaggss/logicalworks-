"""
lgwks_context — graduated-resolution (LOD) context pack for the next spawn (#9 harness layer).

A fresh spawn should NOT re-read every round at full fidelity — that burns the window on stale
detail. Instead it reads context at decaying resolution, recent = sharp, old = a single line. The
Director's tiers (2026-05-31):

    TIER 0  last  5 round JSONs   — symlinked RAW (full fidelity, machine-read)
    TIER 1  last  3 think logs    — verbatim
    TIER 2  last 10 rounds        — COMPACT (one digest line each)
    TIER 3  last 20 rounds        — ULTRA-COMPACT (one headline line each)

This is the rolling-digest idea generalised into levels of detail. Everything is optimised for an AI
reader; the STATE MATRIX is the math-for-AI / auditable-for-humans surface — a dense table the model
reads as state and a human audits as a grid. Source of truth = the hash-chained round ledger
(rounds.ledger.jsonl) + each round's think.md. Pure read/derive; writes only the CONTEXT pack.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TIER_RAW, TIER_FULL, TIER_COMPACT, TIER_ULTRA = 5, 3, 10, 20


def _rounds(run_dir: Path) -> list[dict]:
    ledger = run_dir / "rounds.ledger.jsonl"
    if not ledger.exists():
        return []
    return [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]


def _headline(r: dict) -> str:
    """ULTRA: one line — round, survivor count, falsifiers hit, first learning."""
    learn = (r.get("learnings") or ["—"])[0]
    return (f"R{r['n']:03d} surv={len(r.get('surviving', []))} hit={r.get('falsifiers_hit') or '—'} "
            f"| {learn[:70]}")


def _compact(r: dict) -> str:
    """COMPACT: round + frontier + clipped digest."""
    dig = " ".join((r.get("digest") or "").split())[:200]
    return f"R{r['n']:03d} [{r.get('frontier_in','?')}] {dig}"


def _agenda_block(run_dir: Path, rounds: list[dict]) -> str:
    """Render guide→agenda coverage (#9 co-processor) so a polling coding agent sees, live, which of
    its plan's questions have been researched. Coverage is DERIVED from the ledger (a node is covered
    once a round consumed it as frontier_in) — true even mid-run, before result.json exists."""
    ap = run_dir / "agenda.json"
    if not ap.exists():
        return ""
    try:
        data = json.loads(ap.read_text())
    except Exception:
        return ""
    items = data.get("agenda") or []
    if not items:
        return ""
    done = {r.get("frontier_in") for r in rounds}
    # node → guide verdict (supported/contradicted/unverified) from the round that researched it.
    verdict_by_node = {r.get("frontier_in"): (r.get("guide_verdict") or {}).get("verdict")
                       for r in rounds if r.get("guide_verdict")}
    covered = sum(1 for a in items if a.get("node") in done)
    nodes = {a.get("node") for a in items}
    tally = {v: sum(1 for node, vv in verdict_by_node.items() if vv == v and node in nodes)
             for v in ("supported", "contradicted", "unverified")}
    mark = {"contradicted": "✗", "supported": "✓", "unverified": "?"}
    # aggregate-first (product review): the headline tally before the per-question detail.
    head = (f"\n## RESEARCH AGENDA — {covered}/{len(items)} covered  ·  "
            f"{tally['supported']} supported · {tally['contradicted']} CONTRADICTED · "
            f"{tally['unverified']} unverified"
            + (f"\n   plan: {data['summary']}" if data.get("summary") else ""))
    lines = []
    for a in items:
        node = a.get("node", "")
        flag = mark.get(verdict_by_node.get(node) or "", "✓" if node in done else " ")
        lines.append(f"  [{flag}] {a.get('id','?')} {node!r} — {(a.get('question') or '')[:88]}")
    return "\n".join([head, *lines])


def _state_matrix(rounds: list[dict]) -> str:
    """Dense state table — machine reads it as state, human audits it as a grid."""
    head = "  n | surv | hit | converged | spent"
    rows = [f"  {r['n']:>3} | {len(r.get('surviving',[])):>4} | {len(r.get('falsifiers_hit',[])):>3} "
            f"| {str(r.get('converged',False)):>9} | {r.get('spent',0):>6}" for r in rounds]
    return "\n".join([head, "  " + "-" * 38, *rows])


def assemble(run_dir: Path) -> str:
    """Build the CONTEXT.md text (does not write it). Empty string if no rounds."""
    rounds = _rounds(run_dir)
    if not rounds:
        return ""
    rounds.sort(key=lambda r: r["n"])
    recent = list(reversed(rounds))                      # newest first for the decay tiers
    result_p = run_dir / "result.json"
    res = json.loads(result_p.read_text()) if result_p.exists() else {}

    parts = [f"# SPAWN CONTEXT — {run_dir.name}",
             f"objective={res.get('objective','?')!r} start={res.get('start','?')!r} "
             f"stop={res.get('stop_reason','?')} surviving={res.get('surviving',[])} "
             f"integrity={res.get('integrity_mode','?')} ledger_intact={res.get('ledger_intact','?')}",
             _agenda_block(run_dir, rounds),
             "\n## STATE MATRIX (math-for-AI / human-auditable)", _state_matrix(rounds),
             f"\n## TIER 0 — last {TIER_RAW} round JSONs (RAW, symlinked under ./CONTEXT/raw/)"]
    parts += [f"  raw/{run_dir.name}-R{r['n']:03d}.reason.json" for r in recent[:TIER_RAW]]

    parts.append(f"\n## TIER 1 — last {TIER_FULL} think logs (VERBATIM)")
    for r in recent[:TIER_FULL]:
        tm = run_dir / f"round-{r['n']:03d}" / "think.md"
        parts.append(tm.read_text().strip() if tm.exists() else f"(R{r['n']:03d} think.md missing)")

    parts.append(f"\n## TIER 2 — last {TIER_COMPACT} rounds (COMPACT)")
    parts += [_compact(r) for r in recent[:TIER_COMPACT]]

    parts.append(f"\n## TIER 3 — last {TIER_ULTRA} rounds (ULTRA-COMPACT)")
    parts += [_headline(r) for r in recent[:TIER_ULTRA]]
    return "\n".join(parts) + "\n"


def write_pack(run_dir: Path) -> Path | None:
    """Write ./CONTEXT/{CONTEXT.md, raw/*.reason.json symlinks}. Returns the CONTEXT.md path."""
    rounds = _rounds(run_dir)
    if not rounds:
        return None
    rounds.sort(key=lambda r: r["n"])
    cdir = run_dir / "CONTEXT"
    raw = cdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for r in list(reversed(rounds))[:TIER_RAW]:
        src = run_dir / f"round-{r['n']:03d}" / "reason.json"
        link = raw / f"{run_dir.name}-R{r['n']:03d}.reason.json"
        if link.is_symlink() or link.exists():
            link.unlink()
        if src.exists():
            os.symlink(os.path.relpath(src, raw), link)   # relative symlink → portable across moves
    out = cdir / "CONTEXT.md"
    out.write_text(assemble(run_dir))
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: lgwks_context.py <run_dir>", file=sys.stderr)
        return 2
    out = write_pack(Path(args[0]))
    if not out:
        print("no rounds found (no rounds.ledger.jsonl)", file=sys.stderr)
        return 1
    print(f"  context pack: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
