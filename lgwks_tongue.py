"""
lgwks_tongue — the Tongue: gemma4 (Ollama) compiles hypotheses + the elimination question over the
intent, Issue #7. Fails closed to the deterministic skeleton.

Two corrections from the Director (2026-05-31):
- **Hn is NOT a fixed set.** H0 is the mandatory null (skeptical default). H1..Hn are COMPILED
  AUTONOMOUSLY — the model decides how many and what they are; do not pad to 3, do not bin distinct
  mechanisms together. Forcing a fixed lens count is the binning sin.
- **Build on existing breakthroughs.** Every hypothesis must name the prior breakthrough/framework it
  extends (`builds_on`). We stand on prior art; we do not reinvent. This is literature-grounded
  hypothesis generation (HypER-style), and it is how the instrument compounds on real work, not slop.

Truth-finding mandate: defend H0 until evidence falsifies it; a confirmed null is a valid result;
truth over interestingness. Anti-slop: forced format=json + strict schema; non-JSON = fallback.
"""

from __future__ import annotations

import lgwks_ollama
import lgwks_openrouter


def _generate(prompt: str, schema: str) -> dict | None:
    """Provider seam for generation. Cloud Tongue (OpenRouter) FIRST — the local 31B loses the
    interactive readiness race on 24GB and falls back every run. Local Ollama is the offline
    fallback; None → caller uses the deterministic skeleton. Vendor-agnostic: both honour the
    same (prompt, schema_hint) -> dict|None contract, so the Tongue never binds to one provider."""
    if lgwks_openrouter.is_configured():
        out = lgwks_openrouter.generate_json(prompt, schema)
        if out is not None:
            return out                       # cloud answered; do not double-spend the local model
    if lgwks_ollama.is_up():
        return lgwks_ollama.generate_json(prompt, schema)
    return None

SYSTEM = (
    "You are the Tongue of a research instrument, NOT a chatbot. You compile a bounded intent into "
    "falsifiable hypotheses. RULES: "
    "(1) H0 is the mandatory NULL — the skeptical 'no effect / artifact / baseline' that must be "
    "DISPROVEN by evidence. A confirmed null is a valid, good result. "
    "(2) Then compile AS MANY mechanism hypotheses H1..Hn as the intent genuinely warrants — decide "
    "the count yourself; do NOT pad to a fixed number and do NOT merge distinct mechanisms. "
    "(3) EVERY hypothesis must name the existing breakthrough/framework it builds on (builds_on) — we "
    "extend prior art, we do not reinvent. "
    "(4) Each hypothesis needs a concrete falsifier (what evidence would kill it). "
    "(5) Terse, specific, no hedging, no flattery, truth over interestingness."
)

# Variable-cardinality schema: H0 fixed role, H1..Hn autonomous. Shape validated; count is the model's.
HYP_SCHEMA = (
    '{"meant":"<1-line inferred true intent>",'
    '"hypotheses":[{"id":"H0","role":"null","claim":"","falsifier":"",'
    '"builds_on":["<prior breakthrough/framework>"],"keywords":["",""]},'
    '{"id":"H1","role":"mechanism","claim":"","falsifier":"","builds_on":[""],"keywords":[""]}'
    '/* ...H2..Hn as warranted... */],'
    '"question":"<one elimination question that maximally separates the hypotheses>"}'
)


def compile_hypotheses(objective: str, purpose: str) -> dict | None:
    """Autonomously compile H0 + H1..Hn (variable count), each grounded in prior art.
    Returns None on any failure → caller uses the deterministic skeleton (fail closed)."""
    prompt = (f"{SYSTEM}\n\nIntent: {objective!r}\nPurpose: {purpose!r}\n"
              f"Compile the hypotheses now.")
    out = _generate(prompt, HYP_SCHEMA)
    if not out or not isinstance(out.get("hypotheses"), list) or not out["hypotheses"]:
        return None
    # Validate the envelope (anti-slop): keep only well-shaped hypotheses; H0 must be present.
    clean = []
    for h in out["hypotheses"]:
        if isinstance(h, dict) and h.get("claim") and h.get("falsifier"):
            clean.append({
                "id": str(h.get("id", f"H{len(clean)}")),
                "role": "null" if str(h.get("id", "")).upper() == "H0" else (h.get("role") or "mechanism"),
                "claim": str(h["claim"]),
                "falsifier": str(h["falsifier"]),
                "builds_on": [str(x) for x in (h.get("builds_on") or []) if x][:4],
                "keywords": [str(k) for k in (h.get("keywords") or []) if k][:6],
            })
    if not any(h["role"] == "null" for h in clean):
        return None   # no null compiled → not trustworthy, fall back
    return {"meant": out.get("meant", ""), "hypotheses": clean, "question": out.get("question")}
