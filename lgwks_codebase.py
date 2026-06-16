"""
lgwks_codebase — semantic codebase database for AI-native code understanding.

Builds a structured, searchable, versioned representation of the codebase:
  - Entities: functions, classes, modules, docstrings, type signatures
  - Relationships: imports, calls, inheritance, file→module mappings
  - Embeddings: deterministic hash-based vectors for semantic search
  - Graph: adjacency lists for impact analysis and navigation

Storage is plain JSONL + flat vectors — no SQLite, no pickle, no blob.
Everything is deterministic, reproducible, and human-auditable.

Schema: lgwks.codebase.v0
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import struct
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import lgwks_embed
import lgwks_vecmath  # canonical vector math (one source of truth)

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "store" / "codebase"
DB_DIR.mkdir(parents=True, exist_ok=True)

_SCHEMA = "lgwks.codebase.v0"

# File extensions we index
CODE_EXTS = {
    ".py", ".js", ".mjs", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".sh", ".swift", ".kt", ".kts", ".scala", ".lua", ".pl", ".pm",
    ".sql", ".r", ".dart", ".zig", ".clj", ".cljs", ".hs", ".ex", ".exs", ".erl",
}
DOC_EXTS = {".md", ".rst", ".txt"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".dockerfile"}
ALL_INDEX_EXTS = CODE_EXTS | DOC_EXTS | CONFIG_EXTS

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".venv-models", "venv", "target",
               ".next", "dist", "build", "store", "docs", ".claude", ".config",
               ".build/checkouts", ".build/artifacts"}
SKIP_FILES = {"*.pyc", "*.so", "*.dylib", "*.egg-info", "*.bin", "*.lock"}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeEntity:
    id: str
    kind: str       # function | class | module | method | doc | config | struct | trait | enum | entity
    name: str
    file: str
    line_start: int
    line_end: int
    text: str       # source text or doc content
    signature: str = ""   # for functions: def foo(a: int) -> str
    docstring: str = ""
    parent: str = ""    # for methods: parent class id
    module: str = ""    # python module path
    hash: str = ""      # content hash for change detection
    embedding: list[float] = field(default_factory=list)


@dataclass
class Relation:
    kind: str       # calls | imports | inherits | defines | contains
    source: str     # entity id
    target: str     # entity id or file path
    confidence: float = 1.0


@dataclass
class CodebaseIndex:
    schema: str = _SCHEMA
    created_at: float = 0.0
    git_sha: str = ""
    file_count: int = 0
    entity_count: int = 0
    relation_count: int = 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

from lgwks_hashing import content_id as _content_hash  # canonical content-id (one source of truth)


def _rel_path(path: Path, root: Path) -> str:
    """Return path relative to root, or just the filename if outside root."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _entity_id(file: Path, kind: str, name: str, line: int) -> str:
    base = f"{file}:{kind}:{name}:{line}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _parse_python(file: Path, root: Path) -> list[CodeEntity]:
    """Parse a Python file into entities (functions, classes, methods)."""
    try:
        source = file.read_text(encoding="utf-8")
    except Exception:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    entities: list[CodeEntity] = []
    module_path = _rel_path(file, root)[:-3].replace("/", ".").replace("\\", ".")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            if kind == "function" and any(
                isinstance(p, ast.FunctionDef) for p in ast.walk(node) if p != node
            ):
                # Simple heuristic: if it contains other functions, might be a method
                # but we'll let parent tracking handle that
                pass

            line_start = node.lineno
            line_end = node.end_lineno if hasattr(node, "end_lineno") else node.lineno
            text = "\n".join(lines[line_start - 1:line_end])

            # Signature extraction
            signature = ""
            if kind == "function" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                for arg in node.args.args:
                    arg_str = arg.arg
                    if arg.annotation and isinstance(arg.annotation, ast.Name):
                        arg_str += f": {arg.annotation.id}"
                    args.append(arg_str)
                if node.returns and isinstance(node.returns, ast.Name):
                    signature = f"def {name}({', '.join(args)}) -> {node.returns.id}"
                else:
                    signature = f"def {name}({', '.join(args)})"

            # Docstring
            docstring = ast.get_docstring(node) or ""

            # Parent tracking
            parent = ""
            for child in ast.walk(tree):
                if isinstance(child, ast.ClassDef):
                    for item in child.body:
                        if item is node:
                            parent = child.name
                            kind = "method"
                            break

            entity = CodeEntity(
                id=_entity_id(file, kind, name, line_start),
                kind=kind,
                name=name,
                file=_rel_path(file, root),
                line_start=line_start,
                line_end=line_end,
                text=text,
                signature=signature,
                docstring=docstring,
                parent=parent,
                module=module_path,
                hash=_content_hash(text),
            )
            entities.append(entity)

    # Add module-level entity
    module_entity = CodeEntity(
        id=_entity_id(file, "module", file.stem, 1),
        kind="module",
        name=file.stem,
        file=_rel_path(file, root),
        line_start=1,
        line_end=len(lines),
        text=source[:2000],  # truncated
        module=module_path,
        hash=_content_hash(source),
    )
    entities.append(module_entity)

    return entities


def _parse_rust(file: Path, root: Path) -> list[CodeEntity]:
    """Parse a Rust file into entities (structs, enums, functions, traits)."""
    try:
        source = file.read_text(encoding="utf-8")
    except Exception:
        return []

    lines = source.splitlines()
    entities: list[CodeEntity] = []

    # Simple regex-based parsing for Rust
    patterns = [
        (r'pub\s+struct\s+([a-zA-Z0-9_]+)', "struct"),
        (r'pub\s+enum\s+([a-zA-Z0-9_]+)', "enum"),
        (r'pub\s+fn\s+([a-zA-Z0-9_]+)', "function"),
        (r'pub\s+trait\s+([a-zA-Z0-9_]+)', "trait"),
        (r'impl(?:\s+<[^>]+>)?\s+([a-zA-Z0-9_]+)', "impl"),
    ]

    for i, line in enumerate(lines, 1):
        for pattern, kind in patterns:
            match = re.search(pattern, line)
            if match:
                name = match.group(1)
                # Find doc comments above
                doc_lines = []
                for k in range(i - 2, -1, -1):
                    if lines[k].strip().startswith("///") or lines[k].strip().startswith("//!"):
                        doc_lines.insert(0, lines[k].strip().lstrip("/! "))
                    else:
                        break
                
                entity = CodeEntity(
                    id=_entity_id(file, kind, name, i),
                    kind=kind,
                    name=name,
                    file=_rel_path(file, root),
                    line_start=i,
                    line_end=i + 5,  # heuristic
                    text=line.strip(),
                    docstring="\n".join(doc_lines),
                    hash=_content_hash(line),
                )
                entities.append(entity)

    # Module entity
    module_entity = CodeEntity(
        id=_entity_id(file, "module", file.stem, 1),
        kind="module",
        name=file.stem,
        file=_rel_path(file, root),
        line_start=1,
        line_end=len(lines),
        text=source[:2000],
        hash=_content_hash(source),
    )
    entities.append(module_entity)
    return entities


def _parse_doc(file: Path, root: Path) -> list[CodeEntity]:
    """Parse a markdown/text file into chunk entities."""
    try:
        text = file.read_text(encoding="utf-8")
    except Exception:
        return []

    # Split by headers for chunking
    chunks: list[tuple[str, int, int]] = []
    lines = text.splitlines()
    current_chunk: list[str] = []
    current_start = 1

    for i, line in enumerate(lines, 1):
        if line.startswith("#") and current_chunk:
            chunks.append(("\n".join(current_chunk), current_start, i - 1))
            current_chunk = [line]
            current_start = i
        else:
            current_chunk.append(line)

    if current_chunk:
        chunks.append(("\n".join(current_chunk), current_start, len(lines)))

    entities: list[CodeEntity] = []
    for j, (chunk_text, start, end) in enumerate(chunks):
        # Extract header as name
        header_match = re.search(r'^#+\s*(.+)', chunk_text, re.MULTILINE)
        name = header_match.group(1)[:50] if header_match else f"chunk-{j}"

        entity = CodeEntity(
            id=_entity_id(file, "doc", name, start),
            kind="doc",
            name=name,
            file=_rel_path(file, root),
            line_start=start,
            line_end=end,
            text=chunk_text[:2000],
            hash=_content_hash(chunk_text),
        )
        entities.append(entity)

    return entities


def _parse_config(file: Path, root: Path) -> list[CodeEntity]:
    """Parse a config file into a single entity."""
    try:
        text = file.read_text(encoding="utf-8")
    except Exception:
        return []

    entity = CodeEntity(
        id=_entity_id(file, "config", file.name, 1),
        kind="config",
        name=file.name,
        file=_rel_path(file, root),
        line_start=1,
        line_end=len(text.splitlines()),
        text=text[:2000],
        hash=_content_hash(text),
    )
    return [entity]


def _extract_relations(entities: list[CodeEntity]) -> list[Relation]:
    """Extract import/call/inherits relations from entities."""
    relations: list[Relation] = []
    entity_map = {e.name: e for e in entities}

    for e in entities:
        # Extract imports from all entity kinds (module-level imports are in module text)
        for match in re.finditer(r'(?:from\s+(\S+)\s+import|import\s+(\S+))', e.text):
            module = match.group(1) or match.group(2)
            if module:
                relations.append(Relation(
                    kind="imports",
                    source=e.id,
                    target=module,
                    confidence=1.0,
                ))

        if e.kind in ("function", "method"):
            # Extract calls (simple regex)
            for match in re.finditer(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', e.text):
                called = match.group(1)
                if called in entity_map and called != e.name:
                    relations.append(Relation(
                        kind="calls",
                        source=e.id,
                        target=entity_map[called].id,
                        confidence=0.8,
                    ))

        if e.kind == "class":
            # Extract inheritance
            for match in re.finditer(r'class\s+\w+\s*\(([^)]+)\)', e.text):
                bases = match.group(1).split(",")
                for base in bases:
                    base = base.strip()
                    if base in entity_map:
                        relations.append(Relation(
                            kind="inherits",
                            source=e.id,
                            target=entity_map[base].id,
                            confidence=1.0,
                        ))

        # Module contains entities
        if e.kind == "module":
            for child in entities:
                if child.file == e.file and child.id != e.id:
                    relations.append(Relation(
                        kind="contains",
                        source=e.id,
                        target=child.id,
                        confidence=1.0,
                    ))

    return relations


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _should_index(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.suffix not in ALL_INDEX_EXTS:
        return False
    return True


def _parse_generic_code(file: Path, root: Path) -> list[CodeEntity]:
    """Generic regex-based parser for most programming languages."""
    try:
        source = file.read_text(encoding="utf-8")
    except Exception:
        return []

    lines = source.splitlines()
    entities: list[CodeEntity] = []

    # Common patterns across many languages
    patterns = [
        (r'\b(?:class|struct|interface|trait|enum)\s+([a-zA-Z0-9_]+)', "entity"),
        (r'\b(?:fn|func|function|def|sub)\s+([a-zA-Z0-9_]+)', "function"),
        (r'\b(?:task|workflow|contract|module)\s+([a-zA-Z0-9_]+)', "module"),
    ]

    for i, line in enumerate(lines, 1):
        for pattern, kind in patterns:
            match = re.search(pattern, line)
            if match:
                name = match.group(1)
                # Heuristic: skip keywords or common noise
                if name in ("main", "self", "this", "pub", "private", "protected"):
                    continue

                entity = CodeEntity(
                    id=_entity_id(file, kind, name, i),
                    kind=kind,
                    name=name,
                    file=_rel_path(file, root),
                    line_start=i,
                    line_end=i + 10,  # heuristic chunk
                    text=line.strip(),
                    hash=_content_hash(line),
                )
                entities.append(entity)

    # Add module-level entity
    module_entity = CodeEntity(
        id=_entity_id(file, "module", file.stem, 1),
        kind="module",
        name=file.stem,
        file=_rel_path(file, root),
        line_start=1,
        line_end=len(lines),
        text=source[:2000],
        hash=_content_hash(source),
    )
    entities.append(module_entity)
    return entities


def scan_codebase(root: Path | None = None) -> tuple[list[CodeEntity], list[Relation]]:
    """Scan the codebase using git-provenance to avoid indexing slop."""
    is_default_root = root is None
    root = root or ROOT
    all_entities: list[CodeEntity] = []
    all_relations: list[Relation] = []

    # Identify roots to scan
    roots = [root]
    kernel_path = Path("/Users/srinji/logic-os-kernel")
    if is_default_root and kernel_path.exists():
        roots.append(kernel_path)

    for r in roots:
        try:
            # U1 provenance: only index what is tracked by git
            cmd = ["git", "ls-files"]
            files = subprocess.check_output(cmd, cwd=str(r), text=True).splitlines()
        except Exception:
            # Fallback to rglob if not a git repo, but still honor SKIP_DIRS
            files = [str(p.relative_to(r)) for p in r.rglob("*") if p.is_file()]

        for rel_path in files:
            path = r / rel_path
            if not _should_index(path):
                continue

            if path.suffix == ".py":
                entities = _parse_python(path, r)
            elif path.suffix == ".rs":
                entities = _parse_rust(path, r)
            elif path.suffix in DOC_EXTS:
                entities = _parse_doc(path, r)
            elif path.suffix in CONFIG_EXTS:
                entities = _parse_config(path, r)
            elif path.suffix in CODE_EXTS:
                entities = _parse_generic_code(path, r)
            else:
                continue

            relations = _extract_relations(entities)
            all_entities.extend(entities)
            all_relations.extend(relations)

    return all_entities, all_relations


def build_index(root: Path | None = None) -> CodebaseIndex:
    """Build the full codebase index with embeddings."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    entities, relations = scan_codebase(root)

    # Compute embeddings
    for e in entities:
        text_for_embed = f"{e.name} {e.signature} {e.docstring} {e.text[:500]}"
        e.embedding = lgwks_embed._embedding(text_for_embed, dims=256)

    # Write entities
    entities_file = DB_DIR / "entities.jsonl"
    with open(entities_file, "w", encoding="utf-8") as fh:
        for e in entities:
            fh.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

    # Write relations
    relations_file = DB_DIR / "relations.jsonl"
    with open(relations_file, "w", encoding="utf-8") as fh:
        for r in relations:
            fh.write(json.dumps({"kind": r.kind, "source": r.source, "target": r.target,
                                "confidence": r.confidence}, ensure_ascii=False) + "\n")

    # Write vectors (flat binary for fast similarity)
    vectors_file = DB_DIR / "vectors.bin"
    with open(vectors_file, "wb") as fh:
        for e in entities:
            fh.write(struct.pack(f"<{len(e.embedding)}f", *e.embedding))

    # Write index metadata
    import subprocess
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        git_sha = "unknown"

    meta = CodebaseIndex(
        schema=_SCHEMA,
        created_at=time.time(),
        git_sha=git_sha,
        file_count=len({e.file for e in entities}),
        entity_count=len(entities),
        relation_count=len(relations),
    )

    meta_file = DB_DIR / "index.json"
    meta_file.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")

    return meta


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def load_entities() -> list[CodeEntity]:
    """Load entities from the database."""
    entities_file = DB_DIR / "entities.jsonl"
    if not entities_file.exists():
        return []

    entities: list[CodeEntity] = []
    with open(entities_file, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                data = json.loads(line)
                entities.append(CodeEntity(**data))
    return entities


def spine(entity_id: str, depth: int = 3) -> list[dict[str, Any]]:
    """
    Extract the 'Logical Spine' (causal path) starting from an entity.
    Bridges the gap with logic-path trackers (Greptile/Serena).
    """
    entities = {e.id: e for e in load_entities()}
    relations = load_relations()
    
    path = []
    current_id = entity_id
    
    for _ in range(depth):
        if current_id not in entities:
            break
        
        e = entities[current_id]
        # Find outbound relations
        rel_links = [r for r in relations if r.source == current_id]
        
        path.append({
            "id": e.id,
            "kind": e.kind,
            "name": e.name,
            "file": e.file,
            "line": e.line_start,
            "calls": [{"id": r.target, "kind": r.kind} for r in rel_links if r.kind == "calls"]
        })
        
        # Follow the first 'calls' relation for the next link in the spine
        next_call = next((r for r in rel_links if r.kind == "calls" and r.target in entities), None)
        if next_call:
            current_id = next_call.target
        else:
            break
            
    return path


def search(query: str, top_k: int = 5, kind_filter: str | None = None) -> list[dict[str, Any]]:
    """Semantic search over the codebase."""
    query_vec = lgwks_embed._embedding(query, dims=256)
    entities = load_entities()

    results: list[tuple[float, CodeEntity]] = []
    for e in entities:
        if kind_filter and e.kind != kind_filter:
            continue
        if not e.embedding:
            continue
        score = lgwks_vecmath.dot(query_vec, e.embedding)
        results.append((score, e))

    results.sort(key=lambda x: -x[0])
    out: list[dict[str, Any]] = []
    for score, e in results[:top_k]:
        out.append({
            "score": round(score, 4),
            "id": e.id,
            "kind": e.kind,
            "name": e.name,
            "file": e.file,
            "line": e.line_start,
            "signature": e.signature,
            "docstring": e.docstring[:200] if e.docstring else "",
        })
    return out


def status() -> dict[str, Any]:
    """Return the current index status."""
    meta_file = DB_DIR / "index.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    return {"schema": _SCHEMA, "indexed": False, "note": "run 'lgwks codebase index' first"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    cb = sub.add_parser("codebase", help="semantic codebase database for AI-native code understanding")
    cb_sub = cb.add_subparsers(dest="codebase_command", required=True)

    index = cb_sub.add_parser("index", help="(re)build the codebase index")
    index.add_argument("--json", action="store_true", help="structured output")
    index.set_defaults(func=_codebase_index_command)

    search_p = cb_sub.add_parser("search", help="semantic search over the codebase")
    search_p.add_argument("query", help="search query")
    search_p.add_argument("--top-k", type=int, default=5, help="number of results")
    search_p.add_argument("--kind", choices=["function", "class", "method", "module", "doc", "config"],
                          help="filter by entity kind")
    search_p.add_argument("--json", action="store_true", help="structured output")
    search_p.set_defaults(func=_codebase_search_command)

    spine_p = cb_sub.add_parser("spine", help="extract logical execution path from an entity")
    spine_p.add_argument("entity_id", help="starting entity id")
    spine_p.add_argument("--depth", type=int, default=3, help="max path depth")
    spine_p.add_argument("--json", action="store_true", help="structured output")
    spine_p.set_defaults(func=_codebase_spine_command)

    status_p = cb_sub.add_parser("status", help="show index status")
    status_p.add_argument("--json", action="store_true", help="structured output")
    status_p.set_defaults(func=_codebase_status_command)


def _codebase_index_command(args: argparse.Namespace) -> int:
    meta = build_index()
    if getattr(args, "json", False):
        print(json.dumps(asdict(meta), indent=2))
    else:
        print(f"  indexed {meta.entity_count} entities from {meta.file_count} files")
        print(f"    {meta.relation_count} relations extracted")
        print(f"    schema: {meta.schema}")
        print(f"    git:    {meta.git_sha[:8] if meta.git_sha else 'unknown'}")
    return 0


def _codebase_spine_command(args: argparse.Namespace) -> int:
    path = spine(args.entity_id, depth=args.depth)
    if args.json:
        print(json.dumps(path, indent=2))
    else:
        for i, step in enumerate(path):
            indent = "  " * i
            print(f"{indent}➔ {step['name']} ({step['kind']}) in {step['file']}:{step['line']}")
    return 0


def _codebase_search_command(args: argparse.Namespace) -> int:
    results = search(args.query, top_k=getattr(args, "top_k", 5),
                     kind_filter=getattr(args, "kind", None))
    if getattr(args, "json", False):
        print(json.dumps({"query": args.query, "results": results}, indent=2))
    else:
        print(f"  {len(results)} result(s) for: {args.query}")
        for r in results:
            sig = f" | {r['signature']}" if r['signature'] else ""
            doc = f" | {r['docstring'][:60]}..." if r['docstring'] else ""
            print(f"    {r['score']:.4f} {r['kind']:<10} {r['name']:<30} {r['file']}:{r['line']}{sig}{doc}")
    return 0


def _codebase_status_command(args: argparse.Namespace) -> int:
    st = status()
    if getattr(args, "json", False):
        print(json.dumps(st, indent=2))
    else:
        if st.get("indexed", True):
            print(f"  codebase index: {st.get('entity_count', 0)} entities, {st.get('relation_count', 0)} relations")
            print(f"    schema:   {st.get('schema', 'unknown')}")
            print(f"    git:      {st.get('git_sha', 'unknown')[:8]}")
            print(f"    created:  {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.get('created_at', 0)))}")
        else:
            print(f"  codebase: not indexed — run 'lgwks codebase index'")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="lgwks_codebase")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="build the codebase index")
    index.add_argument("--json", action="store_true")
    index.set_defaults(func=lambda a: _codebase_index_command(a))

    search_p = sub.add_parser("search", help="semantic search")
    search_p.add_argument("query")
    search_p.add_argument("--top-k", type=int, default=5)
    search_p.add_argument("--kind", choices=["function", "class", "method", "module", "doc", "config"])
    search_p.add_argument("--json", action="store_true")
    search_p.set_defaults(func=lambda a: _codebase_search_command(a))

    status_p = sub.add_parser("status", help="index status")
    status_p.add_argument("--json", action="store_true")
    status_p.set_defaults(func=lambda a: _codebase_status_command(a))

    parsed = parser.parse_args(args)
    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
