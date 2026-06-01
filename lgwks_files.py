"""
lgwks_files — the `extract` and `convert` verbs: the read-anything port made into CLI surface.

A coding AI's most repeated grunt task is "turn this file/URL into text I can reason over" — a PDF spec,
a docx requirement, an xlsx of numbers, a JS-walled page. lgwks_extract already does the work (pdf →
office → html with browser escalation, honest failure). These verbs expose it machine-first:

  lgwks extract <target> [--json] [--max-chars N]     → text (or {source,kind,ok,text})
  lgwks convert <source> --to md|txt|json [--out f]   → materialise the extraction as an artifact

Both are read-only and cost no tokens. Default output is the text itself (pipe-friendly); --json gives
the structured envelope. Failure is loud and structured (ok:false), never a silent empty.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _extract(target: str, max_chars: int) -> dict:
    import lgwks_extract
    return lgwks_extract.extract(target, max_chars=max_chars)


def extract_command(args) -> int:
    doc = _extract(args.target, getattr(args, "max_chars", 8000))
    if getattr(args, "json", False):
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if doc["ok"] else 1
    if not doc["ok"]:
        print(f"extract: could not read {args.target!r} (kind={doc['kind']})", file=sys.stderr)
        return 1
    print(doc["text"])
    return 0


def convert_command(args) -> int:
    """Any source → text/markdown/json. The extraction IS the conversion (everything lands as text);
    --to json wraps it with provenance, md/txt emit the body. Honest scope: this normalises TO text
    formats, it does not re-render INTO binary formats (no txt→docx) — that would be a different tool."""
    doc = _extract(args.source, getattr(args, "max_chars", 20000))
    if not doc["ok"]:
        print(f"convert: could not read {args.source!r} (kind={doc['kind']})", file=sys.stderr)
        return 1
    to = getattr(args, "to", "txt")
    if to == "json":
        payload = json.dumps({"source": doc["source"], "kind": doc["kind"], "text": doc["text"]},
                             ensure_ascii=False, indent=2)
    elif to == "md":
        payload = f"# {doc['source']}\n\n_(extracted from {doc['kind']})_\n\n{doc['text']}\n"
    else:  # txt
        payload = doc["text"]
    out = getattr(args, "out", None)
    if out:
        Path(out).write_text(payload, encoding="utf-8")
        print(f"convert: wrote {out} ({len(payload)} chars, from {doc['kind']})", file=sys.stderr)
    else:
        print(payload)
    return 0
