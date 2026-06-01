"""
lgwks_tongue — the Tongue: gemma4 (Ollama) turns the deterministic chain skeleton into good
hypotheses + elimination questions, Issue #7. Fails closed to the deterministic skeleton.

Truth-finding mandate (Director): the bot defends H0 (the null) until evidence falsifies it, and
proves H0, H1, or Hn by truth regardless of which is more interesting. The system prompt enforces
this — the Tongue must state a defensible NULL and is told a boring confirmed null is a valid result.

Anti-slop: every call is forced-JSON with a strict schema; non-JSON = fallback, never trusted prose.
"""

from __future__ import annotations

import lgwks_ollama

SYSTEM = (
    "You are the Tongue of a research instrument, NOT a chatbot. You compile a bounded intent into "
    "falsifiable hypotheses. Rules: (1) State H0 as the skeptical NULL (no effect / artifact / "
    "baseline) that must be DISPROVEN by evidence — a confirmed null is a valid, good result. "
    "(2) H1..Hn are mechanism hypotheses, each with a concrete falsifier. (3) Be terse, specific, "
    "no hedging, no flattery. (4) Truth over interestingness — never bias toward the spicy answer."
)

HYP_SCHEMA = (
    '{"meant":"<1-line inferred true intent>",'
    '"H0":{"claim":"<null>","falsifier":"<what evidence would kill it>"},'
    '"H1":{"claim":"","falsifier":""},'
    '"Hn":{"claim":"","falsifier":""}}'
)

CHAIN_SCHEMA = (
    '{"question":"<one elimination question, max EIG>",'
    '"chains":[{"label":"mechanism|control|evidence","hypothesis":"","null":"",'
    '"helpful_answer":"<what picking this commits to>","keywords":["",""]}]}'
)


def hypotheses(objective: str, purpose: str) -> dict | None:
    """Generate H0/H1/Hn for the intent. None if Ollama is down (caller uses its own H0 default)."""
    if not lgwks_ollama.is_up():
        return None
    prompt = f"{SYSTEM}\n\nIntent: {objective!r}\nPurpose: {purpose!r}\nGenerate the hypotheses."
    return lgwks_ollama.generate_json(prompt, HYP_SCHEMA)


def enrich_chains(objective: str, purpose: str, lens_labels: list[str]) -> dict | None:
    """Turn the deterministic lens skeleton into good hypothesis/null/answer text + the question.
    Returns None on any failure → caller keeps the deterministic chains unchanged (fail closed)."""
    if not lgwks_ollama.is_up():
        return None
    prompt = (f"{SYSTEM}\n\nIntent: {objective!r}\nPurpose: {purpose!r}\n"
              f"Produce one causal chain per lens {lens_labels}. Each chain needs a hypothesis, its "
              f"NULL (falsifier), a one-line helpful_answer, and 2-4 keywords. Then ONE elimination "
              f"question that maximally separates the chains.")
    return lgwks_ollama.generate_json(prompt, CHAIN_SCHEMA)
