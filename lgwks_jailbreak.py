import re
import json

_JAILBREAK_RE = re.compile(
    r"\b(ignore previous|system prompt|you are now|developer mode|dan mode|bypass|override)\b", 
    re.I
)

def is_clean(prompt: str) -> bool:
    """Layer 1 Math Gate: strictly deterministic pattern check for LLM Injection."""
    if _JAILBREAK_RE.search(prompt):
        return False
    return True

def sanitize(prompt: str) -> str:
    """Aggressive sanitization before prompt reaches Layer 2/3."""
    # Remove control characters and potential escape sequences
    clean = re.sub(r"[\x00-\x1F\x7F]", "", prompt)
    return clean.strip()[:16000]

