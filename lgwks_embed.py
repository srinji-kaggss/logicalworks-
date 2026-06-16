"""
lgwks_embed — deterministic local folder embedding vault.

Builds a project-level vector vault plus per-folder sub-vaults. It is local and
replayable: embeddings are deterministic feature hashes, cycles expand focus
keywords from discovered themes, and every record carries file/chunk provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VAULT_ROOT = ROOT / "store" / "vectors"
DIMS = 256
CHUNK_WORDS = 420
CHUNK_OVERLAP = 70
from lgwks_substrate_config import TEXT_EXT, SKIP_DIRS  # one source of truth (were local copies)
from lgwks_lexicon import STOP_EN as STOP  # canonical stopword set (was a local copy)
from lgwks_substrate_config import SLUG_SCRUB_RE as SAFE  # one source of truth
import lgwks_substrate_io as _io      # canonical file I/O (one source of truth)
import lgwks_substrate_text as _st    # canonical text chunking/scoring (one source of truth)
import lgwks_vecmath as _vm           # canonical vector math (one source of truth)


def _project_id(project: str) -> str:
    safe = SAFE.sub("-", project.strip().lower()).strip(".-") or "project"
    return f"{safe}-{hashlib.sha256(project.encode()).hexdigest()[:12]}"


def _folder_id(root: Path, folder: Path) -> str:
    rel = "." if folder == root else str(folder.relative_to(root))
    safe = SAFE.sub("-", rel.lower()).strip(".-") or "root"
    return f"{safe}-{hashlib.sha256(rel.encode()).hexdigest()[:12]}"


def _tokens(text: str) -> list[str]:
    # Canonical lexical analyzer (TERM profile keeps + - . ; one source of truth).
    import lgwks_lexicon as _lex
    return _lex.tokens(text, profile=_lex.TERM, min_len=3, stop=STOP)


def _embedding(text: str, dims: int = DIMS) -> list[float]:
    vec = [0.0] * dims
    toks = _tokens(text)
    feats = toks[:]
    feats.extend(" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1)))
    for feat in feats:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        vec[int.from_bytes(digest[:4], "big") % dims] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _files(root: Path, max_files: int) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if len(out) >= max_files:
            break
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if p.is_file() and p.suffix.lower() in TEXT_EXT and p.stat().st_size <= 2_000_000:
            out.append(p)
    return sorted(out)


from lgwks_substrate_io import _emit_jsonl as _write_jsonl  # one source of truth for JSONL write


def build_vault(root_path: str, project: str, keywords: list[str], cycles: int = 1,
                max_cycles: int = 12, max_files: int = 500, max_chars: int = 80_000) -> dict:
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"embed needs a directory: {root}")
    pid = _project_id(project)
    project_dir = VAULT_ROOT / pid
    files = _files(root, max_files)
    focus = [k.strip().lower() for k in keywords if k.strip()]
    if not focus:
        focus = [root.name.lower()]
    requested_cycles = cycles
    if cycles == 0:
        cycles = max_cycles
    cycles = max(1, min(cycles, max_cycles))

    all_records: list[dict] = []
    folder_records: dict[Path, list[dict]] = {}
    seen_focus: set[str] = set(focus)
    stable_at = None

    for cycle in range(1, cycles + 1):
        focus_vec = _embedding(" ".join(focus))
        cycle_terms: Counter[str] = Counter()
        for path in files:
            text = _io._read_text(path, max_chars)
            if not text:
                continue
            raw_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            for idx, chunk in enumerate(_st._chunk_text(text, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP)):
                vec = _embedding(chunk)
                score = round(_vm.dot(focus_vec, vec), 6)
                toks = _tokens(chunk)
                if score > 0:
                    cycle_terms.update(toks)
                    cycle_terms.update(" ".join(toks[i:i + 2]) for i in range(max(0, len(toks) - 1)))
                rec = {
                    "project": project,
                    "cycle": cycle,
                    "path": str(path),
                    "relpath": str(path.relative_to(root)),
                    "folder": str(path.parent.relative_to(root)) if path.parent != root else ".",
                    "chunk": idx,
                    "sha256": raw_hash,
                    "chunk_sha256": hashlib.sha256(chunk.encode("utf-8", errors="ignore")).hexdigest(),
                    "score": score,
                    "focus": focus,
                    "embedding_model": "deterministic-feature-hash-v1",
                    "is_semantic": False,
                    "dimensions": DIMS,
                    "embedding": vec,
                }
                all_records.append(rec)
                folder_records.setdefault(path.parent, []).append(rec)

        next_focus = [term for term, _ in cycle_terms.most_common(16) if term not in STOP]
        new_terms = [term for term in next_focus if term not in seen_focus][:8]
        if requested_cycles == 0 and not new_terms:
            stable_at = cycle
            break
        seen_focus.update(new_terms)
        focus = (focus + new_terms)[-24:]

    root_manifest = {
        "project": project,
        "project_id": pid,
        "root": str(root),
        "created_at": time.time(),
        "files": len(files),
        "records": len(all_records),
        "requested_cycles": requested_cycles,
        "cycles_run": stable_at or cycles,
        "stable_at": stable_at,
        "vault_type": "project-root",
        "subvaults": [],
    }
    for folder, rows in folder_records.items():
        fid = _folder_id(root, folder)
        subdir = project_dir / "folders" / fid
        _write_jsonl(subdir / "embeddings.jsonl", rows)
        manifest = {
            "project": project,
            "folder": str(folder),
            "folder_rel": str(folder.relative_to(root)) if folder != root else ".",
            "records": len(rows),
            "embedding_model": "deterministic-feature-hash-v1",
            "dimensions": DIMS,
        }
        (subdir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        root_manifest["subvaults"].append({"folder": manifest["folder_rel"], "path": str(subdir), "records": len(rows)})

    _write_jsonl(project_dir / "root" / "embeddings.jsonl", all_records)
    (project_dir / "root" / "manifest.json").write_text(json.dumps(root_manifest, indent=2, sort_keys=True), encoding="utf-8")

    try:
        import lgwks_memory
        lgwks_memory.append(project, "note", {
            "kind": "embedding-vault",
            "root": str(root),
            "vault": str(project_dir),
            "records": len(all_records),
            "cycles_run": root_manifest["cycles_run"],
        })
    except Exception:
        pass
    return {**root_manifest, "vault": str(project_dir), "manifest": str(project_dir / "root" / "manifest.json")}


def embed_command(args: argparse.Namespace) -> int:
    keywords = []
    for value in args.keywords or []:
        keywords.extend(re.split(r"[,;\n]+", value))
    payload = build_vault(args.path, args.project, keywords, cycles=args.cycles,
                          max_cycles=args.max_cycles, max_files=args.max_files,
                          max_chars=args.max_chars)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("embed", help="build deterministic vector vault from a local folder")
    p.add_argument("path")
    p.add_argument("--project", required=True)
    p.add_argument("--keywords", action="append", default=[])
    p.add_argument("--cycles", type=int, default=1, help="0 = repeat until stable, bounded by --max-cycles")
    p.add_argument("--max-cycles", type=int, default=12)
    p.add_argument("--max-files", type=int, default=500)
    p.add_argument("--max-chars", type=int, default=80_000)
    p.set_defaults(func=embed_command)
