#!/usr/bin/env python3
"""Decontamination membrane: strip codepoint classes that carry hidden payloads
and have no legitimate prose function. Reports a payload-likelihood score.
This is redesign #1's first primitive: untrusted text is sanitized BEFORE it
reaches any reasoning context."""
import sys, unicodedata

def classify(cp: str) -> str | None:
    o = ord(cp)
    if 0xE0000 <= o <= 0xE007F: return "TAG"            # Unicode tag chars (stego)
    if 0xE000 <= o <= 0xF8FF or 0xF0000 <= o <= 0xFFFFD or 0x100000 <= o <= 0x10FFFD: return "PUA"
    if o in (0x200B,0x200C,0x200D,0xFEFF,0x2060): return "ZWSP"   # zero-width
    if 0x202A <= o <= 0x202E or 0x2066 <= o <= 0x2069: return "BIDI"
    if unicodedata.category(cp) == "Mn": return "COMBINING"        # zalgo if dense
    return None

def sanitize(text: str):
    kept, stripped = [], {}
    combining = 0
    for ch in text:
        k = classify(ch)
        if k is None:
            kept.append(ch); 
        else:
            stripped[k] = stripped.get(k,0)+1
            if k == "COMBINING": combining += 1
    clean = "".join(kept)
    # keep combining marks that are sparse (legit accents); only flag if dense
    n = max(1, len(text))
    payload_ratio = sum(v for k,v in stripped.items() if k!="COMBINING")/n + (combining/n if combining/n>0.05 else 0)
    return clean, stripped, payload_ratio

if __name__ == "__main__":
    raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    clean, stripped, ratio = sanitize(raw)
    verdict = "PAYLOAD-LIKE (quarantine, do not expand inline)" if ratio > 0.02 else "document (safe to read)"
    sys.stderr.write(f"[membrane] {sys.argv[1].split('/')[-1]}: stripped={stripped} payload_ratio={ratio:.4f} -> {verdict}\n")
    if ratio > 0.02 and "--force" not in sys.argv:
        sys.exit(3)   # refuse to emit a payload-like file's body
    sys.stdout.write(clean)
