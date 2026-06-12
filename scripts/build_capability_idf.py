#!/usr/bin/env python3
"""build_capability_idf — freeze the I8 demand-weight table (stdlib only, no AI).

Engine invariant I8 (padding/verbosity-invariance) needs a per-token demand
weight so that padding a prompt with filler cannot dilute coverage C. The weight
is a smoothed IDF over the **capability vocabulary** — each capability's
(verb + intent) text is one document. A token mentioned by many capabilities
carries little discrimination (low weight); a token specific to few carries more.

Provenance (feedback_calculator_test): pure counting over human-authored
capability specs — no model, no internet, hand-derivable.
  df(t)  = # capabilities whose (verb|intent) text contains t
  idf(t) = log((N + 1) / (df(t) + 1)) + 1        # smoothed, always > 0
  N      = # capabilities with at least one content token

Output (repo root):  .lgwks/capability_idf.json   schema `lgwks.capability_idf.v1`

The runtime (lgwks_engine._load_demand_weights) prefers this frozen artifact but
recomputes the same table from the live verb catalog when it is absent — so this
script is an optimization + declared-provenance record, never a hard dependency.

Run from repo root:  python3 scripts/build_capability_idf.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / ".lgwks" / "capability_idf.json"
_SCHEMA = "lgwks.capability_idf.v1"


def main() -> int:
    sys.path.insert(0, str(_REPO))
    import lgwks_engine as eng  # reuse the SAME tokenizer + idf math as runtime
    import lgwks_map

    # Pull the full capability catalog (top large enough to cover all verbs).
    result = lgwks_map.map_intent("", top=10_000)
    verbs = result.get("matches", [])
    if not verbs:
        # map_intent only returns matches for a non-empty query; fall back to the
        # catalog loader if exposed, else bail loudly (no silent empty artifact).
        loader = getattr(lgwks_map, "_load_verbs", None) or getattr(lgwks_map, "load_verbs", None)
        verbs = loader() if callable(loader) else []
    if not verbs:
        print("ERROR: no capability verbs found — cannot build idf table", file=sys.stderr)
        return 1

    idf = eng._compute_capability_idf(verbs)
    if not idf:
        print("ERROR: idf table empty after tokenization", file=sys.stderr)
        return 1

    n_docs = sum(
        1 for v in verbs
        if set(eng._tokens(v.get("verb", ""))) | set(eng._tokens(v.get("intent", "")))
    )
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": _SCHEMA,
        "corpus": "capability_vocabulary (verb + intent text)",
        "n_documents": n_docs,
        "n_tokens": len(idf),
        "idf": dict(sorted(idf.items())),
    }
    _OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {_OUT.relative_to(_REPO)}  ({payload['n_tokens']} tokens, "
          f"{payload['n_documents']} docs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
