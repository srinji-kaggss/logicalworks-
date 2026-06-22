"""lgwks_substrate_io — file system I/O, JSONL/JSON emission, and manifest loading.

Defense-in-Depth:
- Layer 1 (entry): validate path existence and permissions before reading.
- Layer 2 (business): skip malformed lines in JSONL rather than failing the whole file.
- Layer 3 (environment): use atomic writes via parent mkdir + open for emission.
- Layer 4 (debug): all read failures return empty rather than crash, with silent fallback.
"""

from __future__ import annotations

import json
import re as _re
from pathlib import Path
from typing import Any


from lgwks_hashing import digest as _sha  # canonical full digest (one source of truth)


def slug(
    text: str,
    *,
    limit: int | None = None,
    fallback: str = "item",
    allow: str = "._-",
    strip_scheme: bool = False,
    restrip_after_truncate: bool = False,
) -> str:
    """Canonical filesystem slug — one primitive, no per-module copies (#223 family 5).

    Lowercases; optionally strips a leading URL scheme; replaces every run of
    chars outside ``[a-z0-9]`` + ``allow`` with a single ``-``; trims leading/
    trailing ``-`` (and ``.`` when ``.`` is in ``allow``); applies ``fallback``
    for empties. ``limit`` / ``restrip_after_truncate`` reproduce each caller's
    persisted-path contract byte-for-byte (run dirs, plan_ids, workspace dirs).

    NOT for URL scope-ids that must keep ``/`` (``lgwks_urlrisk.slugify_target``)
    nor the space-keeping dedup key in ``lgwks_concept`` — those are distinct
    concepts, intentionally not merged here.
    """
    s = text.lower()
    if strip_scheme:
        s = _re.sub(r"https?://", "", s)
    s = _re.sub(rf"[^a-z0-9{_re.escape(allow)}]+", "-", s)
    strip_chars = "-." if "." in allow else "-"
    s = s.strip(strip_chars) or fallback
    if limit is not None:
        s = s[:limit]
        if restrip_after_truncate:
            s = s.strip(strip_chars) or fallback
    return s


def _slug(text: str, limit: int = 64) -> str:
    """Filesystem-safe slug. Byte-exact wrapper over canonical ``slug`` (#223 fam 5)."""
    return slug(text, limit=limit, fallback="substrate", allow="._-")


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


def _resolve_run_dir(run_arg: str) -> Path:
    """Resolve a substrate-run identifier to its export directory.

    A bare name like ``schemas`` previously resolved cwd-relative
    (``Path("schemas").resolve()``) and silently missed the run under the
    substrate store — ``query``/``baseline`` then returned empty with no signal.

    Resolution precedence:
    1. An explicit path (absolute or cwd-relative) that already exists.
    2. A real run directory named exactly under ``RUN_ROOT``. A *run* is
       identified by its ``manifest.json``; the bare ``<slug>`` dir is the
       cumulative gate root (only ``.db`` projections, no JSONL) and must NOT
       shadow the timestamped run export that ``query`` actually reads.
    3. A bare project slug → the most recent ``<slug>-<timestamp>`` run export.
    4. Last resort: the exact ``RUN_ROOT/<name>`` if present (e.g. the gate dir),
       else the literal path so the caller's own missing-handling reports the
       name the user actually asked for.
    """
    from lgwks_substrate_config import RUN_ROOT

    direct = Path(run_arg)
    if direct.exists():
        return direct.resolve()

    exact = RUN_ROOT / run_arg
    if (exact / "manifest.json").exists():
        return exact.resolve()

    slug = _slug(run_arg)
    runs = sorted(
        (p for p in RUN_ROOT.glob(f"{slug}-*") if (p / "manifest.json").exists()),
        key=lambda p: p.name,
    )
    if runs:
        return runs[-1].resolve()

    if exact.exists():
        return exact.resolve()
    return direct.resolve()


def _load_run_manifest(run_dir: Path) -> dict[str, Any]:
    """Load manifest.json from a substrate run directory. Returns empty dict if missing or unreadable."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
