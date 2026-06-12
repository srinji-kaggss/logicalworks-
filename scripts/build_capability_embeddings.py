#!/usr/bin/env python3
"""build_capability_embeddings — freeze the Qwen verb-embedding matrix (U6.2 #85).

Amortized intelligence: embed each capability's (verb + intent) text ONCE,
offline, via lgwks_embed_port.EmbedPort, and freeze the vectors. At runtime
lgwks_engine embeds only the prompt (one live Qwen call) and cosines it against
this frozen matrix — coverage C + match scores go from lexical token-overlap to
semantic similarity while staying within INV-7 (<1s) on a warm worker.

Requires the model present (store/models/Qwen3-VL-Embedding-8B*). Without it,
EmbedPort raises EmbedUnavailableError and this exits 2 — run `make
download-models` first. The runtime degrades to the lexical+demand floor when
this artifact is absent, so the engine never hard-depends on it.

The vectors are the Qwen *sensor* layer (exempt from the Calculator Test by
design — feedback_math_not_bert_scorer); the runtime cosine over them is pure
arithmetic (in-bounds).

Output (repo root):  .lgwks/capability_vectors.json   schema lgwks.capability_vectors.v1

Run from repo root:  python3 scripts/build_capability_embeddings.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / ".lgwks" / "capability_vectors.json"
_SCHEMA = "lgwks.capability_vectors.v1"


def main() -> int:
    sys.path.insert(0, str(_REPO))
    import lgwks_map

    result = lgwks_map.map_intent("", top=10_000)
    verbs = result.get("matches", [])
    if not verbs:
        loader = getattr(lgwks_map, "_load_verbs", None) or getattr(lgwks_map, "load_verbs", None)
        verbs = loader() if callable(loader) else []
    if not verbs:
        print("ERROR: no capability verbs found", file=sys.stderr)
        return 1

    try:
        import lgwks_embed_port as ep
        port = ep.EmbedPort()
    except Exception as exc:  # EmbedUnavailableError or import failure
        print(f"ERROR: embed port unavailable ({exc}). Run `make download-models`.",
              file=sys.stderr)
        return 2

    records: list[dict] = []
    try:
        for v in verbs:
            verb = v.get("verb", "")
            intent = v.get("intent", "")
            text = f"{verb} {intent}".strip()
            if not text:
                continue
            vec = port.embed_text(text)
            records.append({"verb": verb, "intent": intent, "vec": vec})
        space_id = port.space_id()
        dim = len(records[0]["vec"]) if records else 0
    finally:
        port.close()

    if not records:
        print("ERROR: no vectors produced", file=sys.stderr)
        return 1

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": _SCHEMA,
        "space_id": space_id,
        "dim": dim,
        "n_verbs": len(records),
        "verbs": records,
    }
    _OUT.write_text(json.dumps(payload) + "\n")
    print(f"wrote {_OUT.relative_to(_REPO)}  ({len(records)} verbs, dim {dim}, space {space_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
