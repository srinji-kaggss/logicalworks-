"""lgwks_monitor — context upkeep and change detection.

Track how sources change over time by storing content-addressed snapshots
and computing diffs. Supports "check back in 8 hours" workflows for:
  · Google Scholar indexing progress
  · Twitter/X thread updates
  · Reddit post comment growth
  · Generic web page changes

All snapshots live in the untrusted cache (lgwks_cache) with a lightweight
monitor index that records (url, hash, timestamp, kind).
"""

from __future__ import annotations

import difflib
import json
import time
import urllib.parse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_MONITOR_DIR = _ROOT / "store" / "monitor"
_INDEX = _MONITOR_DIR / "index.jsonl"


def _ensure() -> None:
    _MONITOR_DIR.mkdir(parents=True, exist_ok=True)


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> float:
    return time.time()


def _normalize(text: str) -> list[str]:
    """Split text into comparable lines, stripping whitespace and collapsing empties."""
    return [ln for ln in (l.strip() for l in text.splitlines()) if ln]


def _read_index(url: str | None = None) -> list[dict]:
    """Read monitor index entries, optionally filtered by URL."""
    if not _INDEX.exists():
        return []
    out = []
    for line in _INDEX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if url is None or rec.get("url") == url:
                out.append(rec)
        except json.JSONDecodeError:
            continue
    return out


def _append_index(rec: dict) -> None:
    _ensure()
    with _INDEX.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


# ── Public API ──────────────────────────────────────────────────────────────


def snapshot(url: str, *, force: bool = False) -> dict:
    """Fetch a URL, extract text, store a snapshot, and record the timestamp.
    Returns {url, hash, timestamp, kind, bytes, changed, previous_hash, text}.
    If the content hash matches the most recent snapshot, changed=False."""
    import lgwks_extract
    import lgwks_cache

    doc = lgwks_extract.extract(url, max_chars=20000)
    if not doc.get("ok"):
        return {"url": url, "hash": "", "timestamp": _now(), "kind": doc.get("kind", "unknown"),
                "changed": False, "previous_hash": "", "text": "", "error": "extraction failed"}

    text = doc["text"]
    h = _hash(text)

    # Store in content-addressed cache
    cache_rec = lgwks_cache.put(url, doc.get("kind", "html"), text)

    # Find previous snapshot for this URL
    previous = _read_index(url)
    prev_hash = previous[-1]["hash"] if previous else ""
    changed = h != prev_hash

    rec = {
        "url": url,
        "hash": h,
        "timestamp": _now(),
        "kind": doc.get("kind", "html"),
        "bytes": cache_rec.get("bytes", 0),
        "previous_hash": prev_hash,
    }
    _append_index(rec)

    return {
        "url": url,
        "hash": h,
        "timestamp": rec["timestamp"],
        "kind": rec["kind"],
        "changed": changed,
        "previous_hash": prev_hash,
        "text": text,
    }


def diff(url: str, *, hours: float = 8.0, min_lines: int = 3) -> dict:
    """Compare the current content of `url` against the snapshot taken ~`hours` ago.
    Returns {url, changed, added_lines, removed_lines, percent_changed, last_check,
            current_hash, previous_hash, current_text, previous_text}.
    If no previous snapshot exists within the window, returns changed=False with a note."""
    cutoff = _now() - (hours * 3600)
    entries = _read_index(url)
    # Find the most recent snapshot before cutoff
    prior = None
    for e in reversed(entries):
        if e["timestamp"] <= cutoff:
            prior = e
            break
    if prior is None:
        return {
            "url": url, "changed": False, "added_lines": [], "removed_lines": [],
            "percent_changed": 0.0, "last_check": None,
            "current_hash": "", "previous_hash": "",
            "note": f"no snapshot older than {hours}h found",
        }

    current = snapshot(url)
    if not current.get("hash"):
        return {
            "url": url, "changed": False, "added_lines": [], "removed_lines": [],
            "percent_changed": 0.0, "last_check": prior["timestamp"],
            "current_hash": "", "previous_hash": prior["hash"],
            "note": "current extraction failed",
        }

    import lgwks_cache
    prev_text = lgwks_cache.get_text(prior["hash"]) or ""
    curr_text = current["text"]
    prev_lines = _normalize(prev_text)
    curr_lines = _normalize(curr_text)

    added = [ln for ln in curr_lines if ln not in prev_lines]
    removed = [ln for ln in prev_lines if ln not in curr_lines]
    total_lines = len(set(prev_lines) | set(curr_lines))
    pct = ((len(added) + len(removed)) / max(total_lines, 1)) * 100
    # Suppress noise: if fewer than min_lines changed, treat as unchanged
    significant = (len(added) + len(removed)) >= min_lines

    return {
        "url": url,
        "changed": significant and current["hash"] != prior["hash"],
        "added_lines": added[:50],      # cap to avoid bloat
        "removed_lines": removed[:50],
        "percent_changed": round(pct, 2),
        "last_check": prior["timestamp"],
        "current_hash": current["hash"],
        "previous_hash": prior["hash"],
        "current_text": curr_text,
        "previous_text": prev_text,
    }


def check(urls: list[str], *, hours: float = 8.0) -> dict:
    """Run snapshot+diff for a list of URLs. Returns a summary report:
    {checked, changed, unchanged, failures, details[]}."""
    details = []
    changed = 0
    unchanged = 0
    failures = 0
    for url in urls:
        d = diff(url, hours=hours)
        if d.get("note"):
            failures += 1
        elif d["changed"]:
            changed += 1
        else:
            unchanged += 1
        details.append(d)
    return {
        "checked": len(urls),
        "changed": changed,
        "unchanged": unchanged,
        "failures": failures,
        "hours": hours,
        "timestamp": _now(),
        "details": details,
    }


def history(url: str, limit: int = 10) -> list[dict]:
    """Return the last `limit` snapshots for a URL, newest first."""
    entries = _read_index(url)
    return sorted(entries, key=lambda e: e["timestamp"], reverse=True)[:limit]


def status() -> dict:
    """Overall monitor status: total URLs tracked, last snapshot time, store size."""
    all_entries = _read_index()
    if not all_entries:
        return {"tracked_urls": 0, "total_snapshots": 0, "last_snapshot": None, "dir": str(_MONITOR_DIR)}
    urls = {e["url"] for e in all_entries}
    last = max(e["timestamp"] for e in all_entries)
    return {
        "tracked_urls": len(urls),
        "total_snapshots": len(all_entries),
        "last_snapshot": last,
        "dir": str(_MONITOR_DIR),
    }
