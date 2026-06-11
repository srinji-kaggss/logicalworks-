"""lgwks_waste — waste ledger: the proof context-optimisation works (I11).

Measurement ONLY. Does NOT change the router or selection cut — it INFORMS the
next tuning (INGESTION-PLAN §I11 scope fence + PRD-04 INV: "non-generative,
waste-measured"). No model layer.

Authority: spec/second-harness/prd/PRD-04-context-economy.md §04-c
           spec/second-harness/INGESTION-PLAN.md §I11
           spec/second-harness/INGESTION-LAYER.md §8 (G-13)
Schema:    lgwks.waste.ledger.v1   (family: harness)
Issue:     I11

Formula (PRD-04 §04-c):
    used_within_n(item) = item cid cited or acted-on within WINDOW_TURNS turns
    waste_rate = 1 − ( Σ tokens of used items / Σ tokens of all injected items )
    0 = perfect, 1 = pure waste

Decisions:
    D1: WINDOW_TURNS = 3 is the pre-registered N — "cited within how many turns?"
        (PRD-04 open-Q line 93). Constant, never tuned under test.
        //why 3: conservative window; an item unused across three model turns is
        unlikely to contribute; avoids both false-positive and false-negative waste.
    D2: "cited/acted-on" detection = case-insensitive cid substring match against
        the first WINDOW_TURNS turns of transcript text. The window starts at turn 0
        (the session start) for all items — packs are injected at session start, not
        staggered. Deterministic and explainable.
    D3: transcript path is injected as an argument, env-pinnable via
        LGWKS_TRANSCRIPT_PATH — NEVER hardcoded.
    D4: the selection-cut threshold the ledger would recommend raising is the constant
        SUGGEST_CUT_THRESHOLD. I11 REPORTS it, does NOT act on it (scope fence).
    D5: ledger is persisted via lgwks_cognition (one byte-truth); full item list
        is preserved so per-item attribution is available after the session ends.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema identifier (auto-scanned by lgwks_schema._scan_schemas)
# ---------------------------------------------------------------------------

SCHEMA = "lgwks.waste.ledger.v1"

# Pre-registered knobs (D1, D4 — document, never fiddle under test).
WINDOW_TURNS: int = 3          # N: citation window in turns (PRD-04 open-Q, line 93)
SUGGEST_CUT_THRESHOLD: float = 0.50   # waste-rate above which cut should be raised (report only)

# Env override for transcript path (D3).
_TRANSCRIPT_ENV = "LGWKS_TRANSCRIPT_PATH"


# ---------------------------------------------------------------------------
# Detection helper
# ---------------------------------------------------------------------------

def _detect_use(cid: str, turns: list[str]) -> tuple[bool, int | None]:
    """Return (used, first_use_turn_index) where used = cid appears in a turn."""
    needle = cid.lower()
    for i, turn_text in enumerate(turns):
        if needle in turn_text.lower():
            return True, i
    return False, None


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def _load_transcript(path: str | Path) -> list[dict]:
    """Load a JSONL transcript. Returns list of parsed records; empty on missing."""
    p = Path(path)
    if not p.exists():
        return []
    records = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _extract_turn_texts(transcript: list[dict]) -> list[str]:
    """Extract string text from each transcript record.

    Handles both flat-string content and the Claude Code JSONL format where
    content is a list of {type, text} blocks.
    """
    texts = []
    for rec in transcript:
        if not isinstance(rec, dict):
            continue
        for key in ("content", "text", "message", "output", "input"):
            val = rec.get(key)
            if isinstance(val, str):
                texts.append(val)
            elif isinstance(val, list):
                for part in val:
                    if isinstance(part, str):
                        texts.append(part)
                    elif isinstance(part, dict):
                        # {type: "text", text: "..."} blocks (Claude Code format)
                        for k2 in ("text", "content"):
                            v2 = part.get(k2)
                            if isinstance(v2, str):
                                texts.append(v2)
    return texts


# ---------------------------------------------------------------------------
# Ledger builder
# ---------------------------------------------------------------------------

def build_ledger(
    packs: list[dict],
    transcript: list[dict] | str | Path,
    *,
    window_turns: int = WINDOW_TURNS,
) -> dict:
    """Build a lgwks.waste.ledger.v1 dict from lgwks.inbound.v1 packs and a transcript.

    packs:      list of lgwks.inbound.v1 dicts (from lgwks_inbound.build_pack).
    transcript: JSONL path (str/Path) or pre-parsed list[dict] of transcript records.
    window_turns: pre-registered N (D1); override only in tests.

    Returns the typed ledger dict — no free-text fields (D5 PRD-04 invariant).
    """
    # Resolve transcript
    if isinstance(transcript, (str, Path)):
        transcript_path = str(transcript)
        raw_records = _load_transcript(transcript_path)
    else:
        transcript_path = os.environ.get(_TRANSCRIPT_ENV, "<injected>")
        raw_records = list(transcript)

    turn_texts = _extract_turn_texts(raw_records)

    # The citation window is the same for all items: the first window_turns turns
    # of the session (D2). Packs are injected once at session start; there is no
    # per-item staggered injection turn.
    window = turn_texts[:window_turns]

    items: list[dict] = []
    for pack in packs:
        schema_val = pack.get("schema", "")
        if schema_val != "lgwks.inbound.v1":
            print(
                f"warning: skipping pack with unexpected schema {schema_val!r} "
                f"(expected 'lgwks.inbound.v1')",
                file=sys.stderr,
            )
            continue

        # Build the canonical cid → tokens mapping from a single pass.
        # depth_handles carry authoritative est_tokens; handles that lack a
        # depth_handle entry fall back to the even budget split.
        depth_map: dict[str, int] = {}
        for dh in pack.get("depth_handles", []):
            cid = dh.get("id", "")
            if cid:
                depth_map[cid] = dh.get("est_tokens", 0)

        # Collect all cids: union of handles + depth_handles (deduped via dict)
        n_handles = len(pack.get("handles", []))
        budget_per_handle = (
            pack.get("budget", {}).get("used_tokens", 0) // n_handles
            if n_handles > 0 else 0
        )

        seen: set[str] = set()
        all_cids: list[tuple[str, int]] = []
        for h in pack.get("handles", []):
            cid = h if isinstance(h, str) else str(h)
            if cid and cid not in seen:
                seen.add(cid)
                all_cids.append((cid, depth_map.get(cid, budget_per_handle)))
        for dh in pack.get("depth_handles", []):
            cid = dh.get("id", "")
            if cid and cid not in seen:
                seen.add(cid)
                all_cids.append((cid, dh.get("est_tokens", 0)))

        for cid, tok in all_cids:
            used, first_turn = _detect_use(cid, window)
            items.append({
                "cid": cid,
                "tokens": tok,
                "used_within_n": used,
                "first_use_turn": first_turn,
            })

    tokens_injected = sum(it["tokens"] for it in items)
    tokens_used = sum(it["tokens"] for it in items if it["used_within_n"])
    rate = _waste_rate_from_totals(tokens_injected, tokens_used)

    return {
        "schema": SCHEMA,
        "session_id": _session_id_from_transcript(raw_records),
        "window_turns": window_turns,
        "items": items,
        "totals": {
            "tokens_injected": tokens_injected,
            "tokens_used": tokens_used,
            "waste_rate": rate,
        },
    }


def _session_id_from_transcript(records: list[dict]) -> str:
    for rec in records:
        if isinstance(rec, dict):
            for key in ("session_id", "sessionId", "conversation_id"):
                val = rec.get(key)
                if isinstance(val, str) and val:
                    return val
    return "unknown"


def _waste_rate_from_totals(tokens_injected: int, tokens_used: int) -> float:
    """waste_rate = 1 − tokens_used / tokens_injected  ∈ [0, 1]."""
    if tokens_injected <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - tokens_used / tokens_injected))


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def waste_rate(ledger: dict) -> float:
    """Return the waste_rate from a ledger dict. 0 = perfect, 1 = pure waste."""
    return ledger.get("totals", {}).get("waste_rate", 0.0)


def worst_item(ledger: dict) -> dict | None:
    """Return the highest-token unused item (most attributable waste), or None."""
    unused = [it for it in ledger.get("items", []) if not it.get("used_within_n")]
    if not unused:
        return None
    return max(unused, key=lambda it: it.get("tokens", 0))


# ---------------------------------------------------------------------------
# Persistence via lgwks_cognition (D5)
# ---------------------------------------------------------------------------

def persist_ledger(ledger: dict, *, stream: str = "waste") -> dict:
    """Append the full ledger to the cognition log (one byte-truth — D5).

    The complete item list (including per-item cid and used_within_n) is persisted
    so high-waste injections remain attributable after the session ends (PRD-04 §04-c).
    """
    import lgwks_cognition

    log = lgwks_cognition.CognitionLog(stream)
    return log.append("note", {"ledger": ledger, "schema": SCHEMA})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    p = sub.add_parser("waste", help="waste ledger: proof context-optimisation works (I11)")
    sp = p.add_subparsers(dest="waste_cmd", required=True)

    report_p = sp.add_parser("report", help="compute waste ledger from packs + transcript")
    report_p.add_argument("packs", help="lgwks.inbound.v1 JSON file (single pack or array)")
    report_p.add_argument("--transcript", default=None, metavar="PATH",
                          help=f"JSONL transcript path (env: {_TRANSCRIPT_ENV})")
    report_p.add_argument("--window", type=int, default=WINDOW_TURNS, metavar="N",
                          help=f"citation window N (pre-registered: {WINDOW_TURNS})")
    report_p.add_argument("--persist", action="store_true",
                          help="persist ledger to cognition log (lgwks_cognition)")
    report_p.set_defaults(func=_cmd_report)

    info_p = sp.add_parser("info", help="show waste ledger schema and constants")
    info_p.set_defaults(func=_cmd_info)


def _cmd_report(args) -> int:
    transcript_path = getattr(args, "transcript", None) or os.environ.get(_TRANSCRIPT_ENV)
    if not transcript_path:
        print(
            f"error: provide --transcript PATH or set {_TRANSCRIPT_ENV}",
            file=sys.stderr,
        )
        return 1

    try:
        with open(args.packs, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot load packs file: {e}", file=sys.stderr)
        return 1

    packs = raw if isinstance(raw, list) else [raw]
    ledger = build_ledger(packs, transcript_path, window_turns=args.window)

    if getattr(args, "persist", False):
        persist_ledger(ledger)

    print(json.dumps(ledger, indent=2))

    rate = waste_rate(ledger)
    worst = worst_item(ledger)
    print(f"\n  waste_rate:  {rate:.3f}  (0=perfect, 1=pure waste)")
    if worst:
        print(f"  worst item:  cid={worst['cid']}  tokens={worst['tokens']}")
    if rate > SUGGEST_CUT_THRESHOLD:
        print(
            f"  NOTE: waste_rate {rate:.3f} > threshold {SUGGEST_CUT_THRESHOLD} "
            f"— consider raising the selection cut (REPORT ONLY; I11 scope fence)."
        )
    return 0


def _cmd_info(args) -> int:
    print(json.dumps({
        "schema": SCHEMA,
        "window_turns": WINDOW_TURNS,
        "suggest_cut_threshold": SUGGEST_CUT_THRESHOLD,
        "transcript_env": _TRANSCRIPT_ENV,
        "formula": "waste_rate = 1 − tokens_used / tokens_injected  ∈ [0,1]",
        "window_semantics": "search first window_turns turns from session start (D2)",
        "detection": "cid substring match against transcript within window (deterministic)",
        "scope_fence": "measurement only — I11 REPORTS threshold breach, does NOT act",
        "persist": "full ledger including per-item items[] persisted via lgwks_cognition (D5)",
    }, indent=2))
    return 0
