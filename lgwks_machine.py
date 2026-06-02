"""
lgwks_machine — the Tier-E MACHINE (build #3, z1). The intent/goal engine — NOT AI. It scores and
shapes intent; it does not speak.

This ships the HARNESS + a deterministic COLD-START refiner, honestly — not a faked neural net. The
flywheel (SPEC-lgwks-experience §1) is: cold-start = rules refine intent and LOG every refinement to
the cognition-log; that log becomes the corpus the neural Machine distils from. The neural upgrade is a
documented next step (microsoft/unixcoder-base, apache-2.0, → ForSequenceClassification head →
MPS fine-tune → CoreML/ANE), NOT something we pretend exists.

What the harness does today:
  • classify_intent  — heuristic intent class (the discriminative job, cold-start)
  • detect_gaps      — which required slots are unfilled for that class (slot-filling, cold-start)
  • specificity      — is this worth spending tokens on? (the learned gate, cold-start = heuristic)
  • refine           — the whole pass: class·entities·gaps·specificity·abstain + log an intent_commit
  • snapshot/freeze/promote — champion/challenger governance, content-addressed (ready for safetensors)
  • calibration      — Brier tracking; promotion is gated on it (the inflection / freeze trigger)

Membrane (z1 wall): when intent is too thin the Machine ABSTAINS and bounces to the human — it never
guesses intent. The abstain threshold is tunable by the steering Depth dial.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "machine"

# Cold-start intent classes: keyword signatures → class. Replaced by the distilled classifier later.
_CLASSES: dict[str, list[str]] = {
    "investment": ["invest", "acquire", "valuation", "stock", "revenue", "buy", "portfolio", "due diligence"],
    "code_review": ["review", "code quality", "refactor", "pr ", "pull request", "lint", "smell"],
    "debug": ["bug", "error", "crash", "fails", "broken", "stack trace", "regression", "why does"],
    "comparison": ["vs", "versus", "compare", "better than", "difference between", "or "],
    "build": ["build", "implement", "create", "design", "spec", "add a", "make a"],
    "explain": ["what is", "how does", "explain", "understand", "meaning of"],
}
# What each class MUST have to be answerable. A missing slot is a gap → a leading question.
_REQUIRED: dict[str, dict[str, list[str]]] = {
    "investment": {"timeframe": ["year", "month", "horizon", "term", "quarter", "2025", "2026"],
                   "decision": ["should", "whether", "buy", "sell", "hold", "allocate"]},
    "code_review": {"target": ["file", ".py", ".ts", ".rs", "repo", "function", "module", "/"],
                    "concern": ["security", "performance", "correctness", "style", "bug", "quality"]},
    "debug": {"symptom": ["error", "fails", "crash", "wrong", "unexpected", "exception"],
              "repro": ["when", "after", "steps", "reproduce", "happens"]},
    "comparison": {"axis": ["on", "for", "by", "in terms of", "cost", "speed", "quality"]},
    "build": {"goal": ["so that", "to ", "goal", "need", "want"],
              "constraints": ["must", "without", "only", "constraint", "limit", "budget"]},
    "explain": {"purpose": ["because", "for", "so", "to ", "trying"]},
}
_VAGUE = {"stuff", "things", "everything", "all", "something", "etc", "whatever", "good", "best", "nice"}


def classify_intent(text: str) -> tuple[str, float]:
    """Best-matching class + a crude confidence (share of the signal it captured). 'unknown' if no signal."""
    low = text.lower()
    scores = {c: sum(1 for kw in kws if kw in low) for c, kws in _CLASSES.items()}
    best = max(scores, key=lambda c: scores[c])
    total = sum(scores.values())
    if scores[best] == 0:
        return "unknown", 0.0
    return best, round(scores[best] / total, 2)


def detect_gaps(text: str, cls: str) -> list[str]:
    """Required slots for the class not evidenced in the text — slot-filling, cold-start."""
    low = text.lower()
    req = _REQUIRED.get(cls, {})
    return [slot for slot, sig in req.items() if not any(s in low for s in sig)]


def specificity(text: str) -> float:
    """Is this worth tokens? 0..1 from length, concrete entities/numbers, minus vague-word penalty.
    The learned gate, cold-start = transparent heuristic (and a clean training label later)."""
    toks = re.findall(r"[A-Za-z0-9.+/_-]+", text)
    if not toks:
        return 0.0
    n = len(toks)
    has_entity = bool(re.search(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*", text)) or bool(re.search(r"\d", text))
    vague = sum(1 for t in toks if t.lower() in _VAGUE)
    score = min(1.0, n / 14.0) * 0.6 + (0.3 if has_entity else 0.0) - min(0.4, vague * 0.15)
    return round(max(0.0, min(1.0, score + 0.1)), 2)


def _entities(text: str) -> list[str]:
    """Cold-start NER: capitalised multi-word spans + quoted terms. Distilled NER replaces it."""
    caps = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", text)
    quoted = re.findall(r'"([^"]+)"', text)
    seen, out = set(), []
    for e in quoted + caps:
        if e.lower() not in seen and len(e) > 1:
            seen.add(e.lower()); out.append(e)
    return out[:8]


def _questions(gaps: list[str]) -> list[str]:
    """Leading questions (one decision each) for the missing slots — the refinement prompts."""
    phrasing = {
        "timeframe": "over what time horizon?", "decision": "what's the decision — buy, hold, or avoid?",
        "target": "which file, function, or repo?", "concern": "concerned about correctness, security, or performance?",
        "symptom": "what exactly goes wrong (the observed symptom)?", "repro": "when does it happen — the steps to reproduce?",
        "axis": "compare them on what axis (cost, speed, quality)?", "goal": "what outcome should this achieve?",
        "constraints": "any hard constraints (must/without/only)?", "purpose": "what's the why behind it?",
    }
    return [phrasing.get(g, f"please specify: {g}") for g in gaps]


def refine(intent: str, actor: str = "human", depth: float = 0.5, log: bool = True) -> dict:
    """The full cold-start pass. Returns a RefinedIntent. ABSTAINS (bounces to human) when intent is too
    thin for the steering Depth — never guesses. Logs an intent_commit to the cognition-log (the corpus).

    actor=='agent' auto-injects quality/slop intent-keywords (SPEC §6 agent-trigger augmentation)."""
    cls, conf = classify_intent(intent)
    spec = specificity(intent)
    threshold = 0.35 + 0.35 * max(0.0, min(1.0, depth))   # deeper stance demands more specificity
    # //why: unbin classifier-failure from user-vagueness (#29). Two distinct paths:
    #   - low specificity → legitimate abstain (user was vague)
    #   - high specificity + unknown class → classifier_coverage_gap, proceed (model limitation, not user fault)
    coverage_gap = False
    if cls == "unknown":
        if spec >= threshold:
            gaps: list[str] = []
            abstain = False
            coverage_gap = True
        else:
            gaps = ["intent_class"]
            abstain = True
    else:
        gaps = detect_gaps(intent, cls)
        abstain = spec < threshold or bool(gaps)
    augmented = intent
    if actor == "agent":   # steer agent-issued queries toward known failure modes (z1 augmentation)
        augmented = f"{intent} [quality:verify-claims, avoid-slop, cite-sources]"
    refined = {
        "intent": intent, "augmented": augmented, "actor": actor,
        "intent_class": cls, "class_confidence": conf,
        "entities": _entities(intent), "gaps": gaps, "specificity": spec,
        "threshold": round(threshold, 2), "abstain": abstain,
        "questions": _questions(gaps) if abstain else [],
        "classifier_coverage_gap": coverage_gap,
    }
    if log:
        _log_commit(refined)
        if coverage_gap:
            _log_coverage_gap(intent, spec, threshold)
    return refined


def _log_coverage_gap(intent: str, spec: float, threshold: float) -> None:
    """Log a classifier_coverage_gap as a #27 training signal."""
    try:
        import lgwks_cognition
        lgwks_cognition.CognitionLog("intent").append("classifier_coverage_gap", {
            "prompt": intent, "specificity": spec, "threshold": threshold,
            "why": "high-specificity intent classified as unknown; signal for ml-001/#27 training",
        })
    except Exception:
        pass


def _log_commit(refined: dict) -> None:
    """Append the refinement to the cognition-log — this IS the Machine's training corpus (fail-soft)."""
    try:
        import lgwks_cognition
        lgwks_cognition.CognitionLog("intent").append("intent_commit", {
            "prompt": refined["intent"], "class": refined["intent_class"],
            "gaps": refined["gaps"], "specificity": refined["specificity"],
            "abstained": refined["abstain"],
            "why": "cold-start heuristic refine; corpus seed for distillation",
        })
    except Exception:
        pass


# ── champion/challenger governance (content-addressed; ready for safetensors weights) ───────────────

def refine_command(args) -> int:
    """AI-facing verb: `lgwks refine "<intent>" [--agent] [--json]` → the RefinedIntent. Machine-first
    (JSON default). An agent reads gaps+questions and either fills them or proceeds if not abstaining."""
    import json as _json
    r = refine(args.intent, actor=("agent" if getattr(args, "agent", False) else "human"),
               depth=getattr(args, "depth", 0.5))
    if getattr(args, "json", True) and not getattr(args, "render", False):
        print(_json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    print(f"class={r['intent_class']} ({r['class_confidence']}) · specificity={r['specificity']}/{r['threshold']}")
    print(f"entities: {', '.join(r['entities']) or '—'}")
    print(f"gaps: {', '.join(r['gaps']) or 'none'}")
    if r["abstain"]:
        print("ABSTAIN — bounce to human. ask:")
        for q in r["questions"]:
            print(f"  · {q}")
    return 0


def _state_hash(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(state: dict) -> dict:
    """Content-address the Machine's state (today: refiner config; later: a safetensors weights ref).
    The hash IS the turn-back id. Stored under store/machine/snapshots/."""
    _DIR.mkdir(parents=True, exist_ok=True)
    h = _state_hash(state)
    (_DIR / "snapshots").mkdir(exist_ok=True)
    (_DIR / "snapshots" / f"{h}.json").write_text(json.dumps(state, sort_keys=True, indent=2))
    return {"hash": h, "frozen": _frozen() == h}


def freeze(h: str) -> dict:
    """Pin a snapshot as the turn-back point — the drift oracle + fallback champion."""
    _DIR.mkdir(parents=True, exist_ok=True)
    (_DIR / "frozen").write_text(h)
    return {"frozen": h}


def _frozen() -> str | None:
    p = _DIR / "frozen"
    return p.read_text().strip() if p.exists() else None


def _brier(records: list[dict]) -> float:
    """Mean squared error of calibrated predictions vs outcomes (0=perfect). The inflection metric."""
    pairs = [(r["p"], r["outcome"]) for r in records if "p" in r and "outcome" in r]
    if not pairs:
        return 0.0
    return round(sum((p - o) ** 2 for p, o in pairs) / len(pairs), 4)


def promote(challenger: dict, champion: dict | None, *, epsilon: float = 0.02) -> dict:
    """Champion/challenger gate: a challenger is promoted only if its calibration is NOT worse than the
    champion's (within epsilon). This is the freeze-on-drift discipline — capability never trades away
    calibration. Returns the decision; the human/orchestrator still confirms a real weights swap."""
    cb = _brier(challenger.get("calibration", []))
    pb = _brier(champion.get("calibration", [])) if champion else 1.0
    ok = cb <= pb + epsilon
    return {"promote": ok, "challenger_brier": cb, "champion_brier": pb,
            "reason": "calibration held" if ok else "challenger calibration regressed — frozen kept"}
