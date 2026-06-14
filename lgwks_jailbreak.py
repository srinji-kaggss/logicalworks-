"""lgwks_jailbreak — entrypoint injection-risk sensor + abstention verdict.

The entrypoint is the #1 prod attack surface (cf. the Chipotle/"Pepper 1" case:
a generative bot with authority + no gate → "ignore the rules" → free coding
agent). The structural cure is NOT a smarter model — it is to make the entrypoint
POWERLESS: a graded risk signal feeds the deterministic abstention gate, and the
worst a successful injection can do is mistranslate, never act.

Two layers, do not conflate (the recurring sensor-vs-engine line):
  - The risk ENGINE here is DETERMINISTIC and calculator-derivable: weighted
    signal detectors → bounded score → verdict. No model, no magic constants
    that aren't named below.
  - Injection detection over RAW natural language is a learned SENSOR problem
    (obfuscated/multilingual attacks evade regex). `_ml_injection_score` is the
    seam for that sensor; it degrades gracefully to the deterministic floor when
    no model is present — the exact pattern `lgwks_embed_port` uses (mlx →
    transformers → floor) and honoring the LGWKS_NO_MODELS kill-switch.

Verdicts map to the attenuation ladder (graceful degradation, not a hard wall):
  proceed → attenuate (sanitize + downgrade trust) → confirm (abstain to human)
  → block. Each non-proceed verdict carries a SYSTEM-GENERATED (templated, NOT
  LLM-narrated) transparency receipt, so the human sees danger they did not —
  whether it came from an attacker, their own ambiguity, or tech debt.

`is_clean`/`sanitize` are preserved verbatim for back-compat; `injection_risk`
and `assess` are the new graded surface the U6 engine now calls.
"""

import os
import re

# ── Back-compat surface (unchanged; external callers may still use these) ──────
_JAILBREAK_RE = re.compile(
    r"\b(ignore previous|system prompt|you are now|developer mode|dan mode|bypass|override)\b",
    re.I,
)


def is_clean(prompt: str) -> bool:
    """Layer 1 Math Gate: strictly deterministic pattern check for LLM Injection."""
    if _JAILBREAK_RE.search(prompt):
        return False
    return True


def sanitize(prompt: str) -> str:
    """Aggressive sanitization before prompt reaches Layer 2/3."""
    clean = re.sub(r"[\x00-\x1F\x7F]", "", prompt)
    return clean.strip()[:16000]


# ── Graded injection-risk signals ─────────────────────────────────────────────
# Each detector targets an INSTRUCTION TO THE MODEL TO CHANGE BEHAVIOUR, never a
# topic. "check for SQL injection" is a task, not an attack, and matches nothing
# here. `override_bypass` is scoped to safety/gate words so legit dev language
# ("bypass the cache", "override the config") does not false-positive — the bare
# back-compat regex above is intentionally looser.
_SIGNALS: tuple[tuple[str, float, re.Pattern], ...] = (
    ("instruction_override", 0.6, re.compile(
        r"\b(ignore|disregard|forget)\b[^.]{0,40}\b(previous|prior|above|earlier|all|your)\b"
        r"[^.]{0,30}\b(instruction|prompt|rule|context|direction|guideline)s?\b", re.I)),
    ("system_prompt_probe", 0.5, re.compile(
        r"\b(reveal|print|repeat|show|leak|output)\b[^.]{0,30}\b(system prompt|your "
        r"(instructions|rules|prompt)|initial prompt)", re.I)),
    ("role_reassignment", 0.5, re.compile(
        r"\b(you are now|from now on you (are|will)|act as (an? )?(unrestricted|dan|jailbroken|evil)"
        r"|pretend (to be|you are)|dan mode|developer mode|jailbreak mode)\b", re.I)),
    ("delimiter_injection", 0.5, re.compile(
        r"(<\|im_(start|end)\|>|\[/?INST\]|<<SYS>>|###\s*(system|instruction)|^\s*system:)", re.I | re.M)),
    ("override_bypass", 0.4, re.compile(
        r"\b(override|bypass|disable|turn off|ignore)\b[^.]{0,25}\b(safety|guard|guardrail|"
        r"filter|gate|moderation|restriction|policy|policies|rule|safeguard|protection)s?\b", re.I)),
)
# Long base64-ish blob (a classic payload-smuggling tell), scored as obfuscation.
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
# Zero-width / bidi-override codepoints — payload-smuggling tells. Defined by
# ordinal (no invisible chars in source): ZWSP/ZWNJ/ZWJ + bidi overrides + isolates.
_OBFUSCATION_ORDS = (
    frozenset({0x200B, 0x200C, 0x200D})
    | frozenset(range(0x202A, 0x202F))   # LRE..RLO bidi embeds/overrides
    | frozenset(range(0x2066, 0x206A))   # LRI/RLI/FSI/PDI isolates
)

# Abstention thresholds. HEURISTIC, pending labelled calibration (mirrors HAD's
# _TAU). Named here so the verdict is fully reconstructable (calculator test).
_T_BLOCK = 0.80      # strong attack → never run
_T_CONFIRM = 0.45    # suspicious → abstain to human
_T_ATTENUATE = 0.20  # mild → sanitize, proceed with downgraded trust


def _ml_injection_score(prompt: str):
    """ML sensor seam (graceful degradation; mirrors lgwks_embed_port).

    Returns a learned injection probability in [0, 1], or None when no model is
    present → caller falls back to the deterministic floor below.

    EASY-FIX-LATER (the model swap): plug Llama-Prompt-Guard-2-86M (multilingual,
    on-device — teacher/baseline) OR a tiny injection head/centroid on the OWNED
    Qwen3-Embedding here, scoring `prompt`. Must honor LGWKS_NO_MODELS and
    fail-closed-to-floor on any error (never block the conscious channel — INV-6).
    """
    if os.environ.get("LGWKS_NO_MODELS"):
        return None
    _ = prompt  # seam input for the future Prompt-Guard / embedding head
    return None  # no injection sensor wired yet — deterministic floor governs


def _has_obfuscation(prompt: str) -> bool:
    return any(ord(ch) in _OBFUSCATION_ORDS for ch in prompt) or bool(_BASE64_BLOB.search(prompt))


def injection_risk(prompt: str) -> dict:
    """Graded injection risk for `prompt`.

    Returns {score in [0,1], signals: [name...], mode}. Deterministic floor is
    always computed; if the ML sensor is present its score raises the verdict
    (defense-in-depth — either layer can flag).
    """
    if not prompt or not isinstance(prompt, str):
        return {"score": 0.0, "signals": [], "mode": "deterministic"}
    fired: list = []
    total = 0.0
    for name, weight, pat in _SIGNALS:
        if pat.search(prompt):
            fired.append(name)
            total += weight
    if _has_obfuscation(prompt):
        fired.append("obfuscation")
        total += 0.3
    det = min(1.0, round(total, 3))

    ml = _ml_injection_score(prompt)
    if ml is None:
        return {"score": det, "signals": fired, "mode": "deterministic"}
    score = max(det, round(float(ml), 3))
    return {"score": score, "signals": fired, "mode": "ml+deterministic"}


def _receipt(verdict: str, signals: list) -> str:
    """System-generated (templated, NOT LLM) transparency receipt for the user."""
    sig = ", ".join(signals) if signals else "elevated risk"
    if verdict == "block":
        return f"Held: input matched injection signals [{sig}] — not run. (system)"
    if verdict == "confirm":
        return f"Flagged [{sig}] — needs your confirmation before any action. (system)"
    if verdict == "attenuate":
        return f"Noticed [{sig}] — sanitized the input and proceeded with reduced trust. (system)"
    return ""


def assess(prompt: str) -> dict:
    """The abstention decision over the injection risk.

    Returns {verdict, injection_risk, signals, receipt}. `verdict` is one rung of
    the attenuation ladder: proceed | attenuate | confirm | block. Deterministic
    given the same prompt (no time, no randomness) — safe for the engine's T2.
    """
    r = injection_risk(prompt)
    score, signals = r["score"], r["signals"]
    if score >= _T_BLOCK:
        verdict = "block"
    elif score >= _T_CONFIRM:
        verdict = "confirm"
    elif score >= _T_ATTENUATE:
        verdict = "attenuate"
    else:
        verdict = "proceed"
    return {
        "verdict": verdict,
        "injection_risk": score,
        "signals": signals,
        "receipt": _receipt(verdict, signals),
    }
