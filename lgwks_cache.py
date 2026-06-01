"""
lgwks_cache — the UNTRUSTED-CACHE store (build #2, z2 evidence / z4 quarantine).

Everything fetched from the world is untrusted data. This store holds it content-addressed (sha256),
quarantined away from cognition + intent, and EXECUTABLE-NEVER: it only ever returns bytes/text to be
treated as data (callers wrap it as <UNTRUSTED_FINDINGS> before any model sees it; the store itself
never runs anything). Content-addressing gives free dedup + integrity: the same page fetched twice is
one entry, and a hash mismatch on read is tamper-evidence.

Boundary (T0): this store NEVER holds PII or AI thinking — those go to lgwks_vault / lgwks_cognition.
The three stores are separate dirs so a leak in one can't expose the others.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "untrusted"          # quarantine: its own dir, never mixed with cognition/intent
_INDEX = _DIR / "index.jsonl"


def _ensure() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _path_for(h: str) -> Path:
    return _DIR / h[:2] / h                    # sharded by hash prefix to keep dirs shallow


def put(url: str, kind: str, content) -> dict:
    """Store fetched world data. Returns {hash, url, kind, bytes, path}. Idempotent by content hash
    (re-storing identical content is a no-op write). Written 0600, no execute bit — data, never code."""
    _ensure()
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    h = _hash(raw)
    p = _path_for(h)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        os.chmod(p, 0o600)                      # owner read/write only; NOT executable
        with _INDEX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"hash": h, "url": url, "kind": kind, "bytes": len(raw)}, sort_keys=True) + "\n")
    return {"hash": h, "url": url, "kind": kind, "bytes": len(raw), "path": str(p)}


def has(h: str) -> bool:
    return _path_for(h).exists()


def get_bytes(h: str) -> bytes | None:
    """Return content by hash, or None. Verifies the hash on read — a mismatch is tamper-evidence."""
    p = _path_for(h)
    if not p.exists():
        return None
    raw = p.read_bytes()
    if _hash(raw) != h:                         # integrity: the file was altered out from under us
        return None
    return raw


def get_text(h: str) -> str | None:
    raw = get_bytes(h)
    return raw.decode("utf-8", "replace") if raw is not None else None


def entries() -> list[dict]:
    if not _INDEX.exists():
        return []
    out = []
    for line in _INDEX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def status() -> dict:
    e = entries()
    return {"store": "untrusted-cache", "dir": str(_DIR), "entries": len(e),
            "bytes": sum(x.get("bytes", 0) for x in e), "executable_never": True}
