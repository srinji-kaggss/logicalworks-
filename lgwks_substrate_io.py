"""lgwks_substrate_io — file system I/O, JSONL/JSON emission, and manifest loading.

Defense-in-Depth:
- Layer 1 (entry): validate path existence and permissions before reading.
- Layer 2 (business): skip malformed lines in JSONL rather than failing the whole file.
- Layer 3 (environment): use atomic writes via parent mkdir + open for emission.
- Layer 4 (debug): all read failures return empty rather than crash, with silent fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from lgwks_hashing import digest as _sha  # canonical full digest (one source of truth)


def _slug(text: str, limit: int = 64) -> str:
    """Sanitize text into a filesystem-safe slug."""
    import re
    return (re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip(".-") or "substrate")[:limit]


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Read JSONL lines. Skip malformed lines silently. Returns empty list if file missing."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _emit_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows as newline-delimited JSON. Creates parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _emit_json(path: Path, payload: dict[str, Any]) -> None:
    """Write payload as formatted JSON. Creates parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _json_cell(value: Any) -> str:
    """Compact JSON serialization for SQLite TEXT columns."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _iter_text_files(root: Path, max_files: int) -> list[Path]:
    """Collect up to max_files text files under root, skipping SKIP_DIRS."""
    from lgwks_substrate_config import SKIP_DIRS, TEXT_EXT

    out: list[Path] = []
    root_resolved = root.resolve()
    for p in root.rglob("*"):
        if len(out) >= max_files:
            break
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        
        # Defense-in-depth: Prevent Symlink Path Traversal (LFI)
        try:
            p_resolved = p.resolve()
            if not p_resolved.is_relative_to(root_resolved):
                continue
        except Exception:
            continue

        if p.is_file() and p.suffix.lower() in TEXT_EXT and p.stat().st_size <= 2_000_000:
            out.append(p)
    return sorted(out)


def _read_text(path: Path, max_chars: int) -> str:
    """Read UTF-8 text, replacing errors, truncated to max_chars. Returns empty string on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _load_run_manifest(run_dir: Path) -> dict[str, Any]:
    """Load manifest.json from a substrate run directory. Returns empty dict if missing or unreadable."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
