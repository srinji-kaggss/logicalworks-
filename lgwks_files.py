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


def _extract(target: str, max_chars: int, page_range: tuple[int, int] | None = None) -> dict:
    import lgwks_extract
    return lgwks_extract.extract(target, max_chars=max_chars, page_range=page_range)


def _parse_page_range(s: str | None) -> tuple[int, int] | None:
    """Parse a 'M-N' (or 'M') page spec into a 1-indexed (first,last) range. None if absent/invalid."""
    if not s:
        return None
    try:
        if "-" in s:
            a, b = s.split("-", 1)
            rng = (int(a), int(b))
        else:
            n = int(s)
            rng = (n, n)
        return rng if rng[0] >= 1 and rng[1] >= rng[0] else None
    except Exception:
        return None


def _truncation_notice(doc: dict, target: str) -> str:
    """A visible marker for the non-JSON path so a human/agent piping the text can SEE
    that the extract is a slice, not the whole, and how to continue. Experience fix for
    'stopped midway and captured noise' — never let truncation be silent."""
    if not doc.get("truncated"):
        return ""
    bits = [f"showed {doc.get('chars', len(doc.get('text', '')))} chars"]
    total = doc.get("total_pages")
    if doc.get("pages"):
        bits.append(f"pages {doc['pages']}" + (f" of {total}" if total is not None else ""))
    elif total is not None:
        bits.append(f"of {total} pages")
    cont = f"continue: lgwks extract {target!r}"
    if total is not None:
        # suggest the next unread page onward. If a range was read, continue after its
        # last page; else (char-cap mid-stream) suggest paginating from page 2.
        try:
            last_read = int(doc["pages"].split("\u2013")[1]) if doc.get("pages") else 1
        except Exception:
            last_read = 1
        nxt = last_read + 1
        if nxt <= total:
            cont += f" --pages {nxt}-{total}"
    return f"[\u2026 truncated: {', '.join(bits)} \u2014 {cont}]"


def _is_safe_path(target: str, repo_root: Path, allow_absolute: bool = False) -> bool:
    """Check if path is safe to read/write."""
    if not target: return False
    # 1. Block URLs - let lgwks_extract handle them if it wants, 
    # but we only validate local files here.
    if target.startswith(("http://", "https://", "ftp://")):
        return True
    
    p = Path(target)
    # 2. Absolute path check
    if p.is_absolute():
        return allow_absolute

    # 3. Traversal check (..)
    try:
        resolved = (repo_root / p).resolve()
        if not str(resolved).startswith(str(repo_root.resolve())):
            return False
    except Exception:
        return False
        
    return True


def extract_command(args) -> int:
    repo_root = Path(__file__).resolve().parent
    if not _is_safe_path(args.target, repo_root, getattr(args, "allow_absolute", True)):
        print(f"error: blocked path (outside repo): {args.target}", file=sys.stderr)
        return 1

    doc = _extract(args.target, getattr(args, "max_chars", 8000),
                   _parse_page_range(getattr(args, "pages", None)))
    if getattr(args, "json", False):
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if doc["ok"] else 1
    if not doc["ok"]:
        print(f"extract: could not read {args.target!r} (kind={doc['kind']})", file=sys.stderr)
        return 1
    print(doc["text"])
    # Experience fix: never let truncation be silent. Marker to stderr so piped stdout
    # (the text) stays clean, but a human/agent still sees it's a slice + how to continue.
    notice = _truncation_notice(doc, args.target)
    if notice:
        print(notice, file=sys.stderr)
    return 0


def convert_command(args) -> int:
    """Any source → text/markdown/json. The extraction IS the conversion (everything lands as text);
    --to json wraps it with provenance, md/txt emit the body. Honest scope: this normalises TO text
    formats, it does not re-render INTO binary formats (no txt→docx) — that would be a different tool."""
    repo_root = Path(__file__).resolve().parent
    source = getattr(args, "source", "")
    if not _is_safe_path(source, repo_root, getattr(args, "allow_absolute", True)):
        print(f"error: blocked path (outside repo): {source}", file=sys.stderr)
        return 1
    
    if getattr(args, "out", None) and args.out != "-":
        if not _is_safe_path(args.out, repo_root, getattr(args, "allow_absolute", True)):
            print(f"error: blocked output path (outside repo): {args.out}", file=sys.stderr)
            return 1

    doc = _extract(source, getattr(args, "max_chars", 20000),
                   _parse_page_range(getattr(args, "pages", None)))
    if not doc["ok"]:
        print(f"convert: could not read {source!r} (kind={doc['kind']})", file=sys.stderr)
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
    if out and out != "-":
        Path(out).write_text(payload, encoding="utf-8")
        print(f"convert: wrote {out} ({len(payload)} chars, from {doc['kind']})", file=sys.stderr)
    else:
        print(payload)
    return 0


def add_parser(sub) -> None:
    extract = sub.add_parser("extract", help="read any supported file or URL into text")
    extract.add_argument("target", help="file path or URL")
    extract.add_argument("--json", action="store_true", help="structured extraction envelope")
    extract.add_argument("--max-chars", type=int, default=8000, help="maximum extracted characters")
    extract.add_argument("--pages", default=None, help="PDF page range to read, e.g. 4-12 or 7 (resume a truncated extract)")
    extract.add_argument("--allow-absolute", action="store_true", default=True,
                         help="allow absolute local paths")
    extract.set_defaults(func=extract_command)

    convert = sub.add_parser("convert", help="convert any supported source to txt, md, or json")
    convert.add_argument("source", help="file path or URL")
    convert.add_argument("--to", choices=["txt", "md", "json"], default="txt")
    convert.add_argument("--out", default="-", help="output file, or - for stdout")
    convert.add_argument("--max-chars", type=int, default=20000, help="maximum extracted characters")
    convert.add_argument("--pages", default=None, help="PDF page range to read, e.g. 4-12 (resume a truncated extract)")
    convert.add_argument("--allow-absolute", action="store_true", default=True,
                         help="allow absolute local paths")
    convert.set_defaults(func=convert_command)
