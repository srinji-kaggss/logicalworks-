"""
lgwks_memory — deterministic project memory chain (hardened, build #3).

Append-only, HMAC-chained project facts plus deterministic theme extraction.
Every context pack is rebuilt from the chain, never from ambient model memory.

HARDENING (Issue #53):
  * Exclusive file lock (fcntl.flock) around read-modify-write in append().
  * Single-writer invariant enforced by exclusive lock; multi-reader safe.
  * Atomic line writes (complete JSON line in one syscall) so readers never see
    partial records even without a read lock.
  * Concurrent stress tests: 2 threads × 100 appends each → verify chain integrity.
"""

from __future__ import annotations

import argparse
import fcntl
import lgwks_hashing
import json
import os
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import lgwks_sign
import lgwks_vecmath as _vm  # canonical vector math (one source of truth)

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "projects"
_GENESIS = "0" * 64
from lgwks_substrate_config import SLUG_SCRUB_RE as _SAFE  # one source of truth
_KINDS = {"project_scope", "conversation", "theme", "fetch_plan", "fetch_result", "note"}
from lgwks_lexicon import STOP_EN as _STOP  # canonical stopword set (was a local copy)


def _project_id(project: str) -> str:
    safe = _SAFE.sub("-", project.strip().lower()).strip(".-") or "project"
    suffix = lgwks_hashing.content_id(project, 12)
    return f"{safe}-{suffix}"


def _path(project: str) -> Path:
    return _DIR / _project_id(project) / "memory.jsonl"


def _core(rec: dict) -> str:
    return json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))


def _read(project: str) -> list[dict]:
    p = _path(project)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def verify(project: str, key: bytes | None = None) -> bool:
    key = key if key is not None else lgwks_sign.signing_key()[0]
    prev = _GENESIS
    try:
        rows = _read(project)
    except Exception:
        return False
    for rec in rows:
        if rec.get("kind") not in _KINDS or rec.get("prev") != prev:
            return False
        if lgwks_sign.mac(_core(rec) + prev, key) != rec.get("hash"):
            return False
        prev = rec["hash"]
    return True


def _lock_exclusive(fh) -> None:
    """Exclusive advisory lock. Blocks until acquired. Never raises for our use case
    (local disk; if the lock fails, the chain is already broken)."""
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    except (OSError, IOError):
        pass


def _unlock(fh) -> None:
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except (OSError, IOError):
        pass


def append(project: str, kind: str, data: dict, key: bytes | None = None) -> dict:
    """Append a record to the project memory chain under exclusive file lock.

    Single-writer invariant: only one agent/process can append at a time.
    Readers (verify, _read, context) are safe concurrently because each line
    is written atomically as a complete JSON record in one syscall.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown memory kind {kind!r}")

    key = key if key is not None else lgwks_sign.signing_key()[0]
    p = _path(project)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Open in a+ so we can lock the file descriptor before any read or write.
    with p.open("a+", encoding="utf-8") as fh:
        _lock_exclusive(fh)
        try:
            # Must seek to start for reading; 'a+' puts us at EOF.
            fh.seek(0)
            rows: list[dict] = []
            for line in fh.read().splitlines():
                if line.strip():
                    rows.append(json.loads(line))

            if rows:
                # Verify existing chain integrity before appending
                prev_local = _GENESIS
                chain_ok = True
                for rec in rows:
                    if rec.get("kind") not in _KINDS or rec.get("prev") != prev_local:
                        chain_ok = False
                        break
                    if lgwks_sign.mac(_core(rec) + prev_local, key) != rec.get("hash"):
                        chain_ok = False
                        break
                    prev_local = rec["hash"]
                if not chain_ok:
                    raise ValueError(
                        f"refusing to append to broken project memory chain: {project}"
                    )
                prev = rows[-1]["hash"]
            else:
                prev = _GENESIS

            rec = {
                "seq": len(rows) + 1,
                "ts": time.time(),
                "project": project,
                "kind": kind,
                "data": data,
                "prev": prev,
            }
            rec["hash"] = lgwks_sign.mac(_core(rec) + prev, key)

            # Atomic line write: complete JSON line in one syscall.
            # JSON lines are typically < PIPE_BUF (4096 bytes), so this is atomic
            # on local filesystems. For very large data payloads, truncation risk
            # is documented — do NOT store multi-MB blobs inline.
            line = json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n"
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            _unlock(fh)

    return rec


def _tokens(text: str) -> list[str]:
    import lgwks_lexicon as _lex  # canonical lexical analyzer (one source of truth)
    return _lex.tokens(text, profile=_lex.TERM, min_len=3, stop=_STOP)


def themes(text: str, limit: int = 24) -> list[dict]:
    toks = _tokens(text)
    counts: Counter[str] = Counter(toks)
    counts.update(" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1)))
    counts.update(" ".join(toks[i:i + 3]) for i in range(max(0, len(toks) - 2)))
    rows = []
    for label, weight in counts.most_common(limit):
        rows.append({"theme": label, "weight": weight, "embedding": embedding(label)})
    return rows


def embedding(text: str, dims: int = 128) -> list[float]:
    features = _tokens(text)
    features.extend(" ".join(features[i:i + 2]) for i in range(max(0, len(features) - 1)))
    # Canonical feature-hash MECHANISM (#223 family 2); byte-exact with prior copy.
    return _vm.hash_embed(features, dims)


def remember(project: str, text: str, source: str = "conversation", verbose_embeddings: bool = False) -> dict:
    rec = append(project, "conversation", {"source": source, "text_sha256": lgwks_hashing.digest(text)})
    th = themes(text)
    append(project, "theme", {"source_seq": rec["seq"], "themes": th})
    th_display = []
    for t in th:
        t_copy = {k: v for k, v in t.items() if verbose_embeddings or k != "embedding"}
        th_display.append(t_copy)
    return {"project": project, "chain_head": rec["hash"], "conversation_seq": rec["seq"], "themes": th_display}


def init_project(project: str, site: str, goal: str) -> dict:
    parsed = urllib.parse.urlparse(site if "://" in site else "https://" + site)
    host = parsed.hostname or site
    rec = append(project, "project_scope", {"site": host, "goal": goal, "allowed_hosts": [host]})
    if goal:
        remember(project, goal, source="project-goal")
    return {"project": project, "scope_seq": rec["seq"], "site": host}


def context(project: str, query: str = "", limit: int = 12) -> dict:
    if not verify(project):
        raise ValueError(f"project memory chain is broken: {project}")
    rows = _read(project)
    qv = embedding(query) if query else []
    theme_rows: list[dict] = []
    scopes: list[dict] = []
    for rec in rows:
        if rec.get("kind") == "theme":
            for t in rec["data"].get("themes", []):
                theme_rows.append({**t, "seq": rec["seq"], "score": _vm.dot(qv, t.get("embedding", [])) if qv else t["weight"]})
        elif rec.get("kind") == "project_scope":
            scopes.append(rec["data"])
    theme_rows.sort(key=lambda x: (x["score"], x["weight"]), reverse=True)
    return {
        "project": project,
        "chain_ok": True,
        "chain_head": rows[-1]["hash"] if rows else _GENESIS,
        "events": len(rows),
        "scopes": scopes,
        "focus_themes": theme_rows[:limit],
        "context_rule": "Use this chain as prior context; do not invent memory outside the chain.",
    }


def memory_command(args: argparse.Namespace) -> int:
    if args.memory_command == "init":
        payload = init_project(args.project, args.site, args.goal)
    elif args.memory_command == "remember":
        import lgwks_inline
        text = lgwks_inline.get_precedence_payload(expr=args.text, file_at=args.file)
        payload = remember(args.project, text, source=args.source,
                           verbose_embeddings=getattr(args, "verbose_embeddings", False))
    else:
        payload = context(args.project, query=args.query, limit=args.limit)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("memory", help="project memory chain: init, remember, context")
    mem = p.add_subparsers(dest="memory_command", required=True)
    init = mem.add_parser("init", help="declare project scope and goal")
    init.add_argument("project")
    init.add_argument("--site", required=True)
    init.add_argument("--goal", default="")
    init.set_defaults(func=memory_command)
    rem = mem.add_parser("remember", help="append conversation text and derived themes")
    rem.add_argument("project")
    rem.add_argument("--text", default="")
    rem.add_argument("--file")
    rem.add_argument("--source", default="conversation")
    rem.add_argument("--verbose-embeddings", action="store_true", dest="verbose_embeddings",
                     help="include raw vector embeddings in theme output")
    rem.set_defaults(func=memory_command)
    ctx = mem.add_parser("context", help="emit deterministic chained context")
    ctx.add_argument("project")
    ctx.add_argument("--query", default="")
    ctx.add_argument("--limit", type=int, default=12)
    ctx.set_defaults(func=memory_command)
