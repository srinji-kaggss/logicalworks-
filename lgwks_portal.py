"""lgwks_portal — deterministic portal packets for coding-agent re-entry.

The portal surface is the first executable slice of the JEPA/packet architecture:

  raw context -> refined intent -> local graph ranking -> portal packet

No LLM is used here. The output is a typed artifact a coding agent can consume
instead of rereading a slop-heavy chat log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_graph


PORTAL_SCHEMA = "lgwks.portal.v1"
CODE_PACKET_SCHEMA = "lgwks.portal.code.v1"
EDGE_STATES = {"soft", "search", "hard", "rejected"}
TRANCHES = ("repo_code", "project_intent")


@dataclass(frozen=True)
class RelationCandidate:
    source: str
    target: str
    kind: str
    state: str
    score: float
    why: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "state": self.state,
            "score": self.score,
            "why": list(self.why),
        }


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_./-]{1,}", text)]


def _sha(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def _project_key(intent: str, repo: Path) -> str:
    return f"project:{_sha(str(repo.resolve()) + '|' + intent, 16)}"


def _portal_key(project_key: str, intent: str) -> str:
    return f"portal:{_sha(project_key + '|' + intent, 16)}"


def _portal_dir(repo: Path) -> Path:
    return repo / ".lgwks" / "portals"


def _portal_path(repo: Path, portal_key: str) -> Path:
    return _portal_dir(repo) / f"{portal_key.replace(':', '_')}.json"


def _read_context(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if getattr(args, "intent", ""):
        parts.append(args.intent.strip())
    for file_arg in getattr(args, "context_file", []) or []:
        p = Path(file_arg)
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    stdin_blob = getattr(args, "stdin_text", "")
    if stdin_blob:
        parts.append(stdin_blob)
    return "\n\n".join(p for p in parts if p.strip()).strip()


def _rank_candidates(graph: lgwks_graph.Graph, intent: str, limit: int = 8) -> list[dict[str, Any]]:
    toks = set(_tokenize(intent))
    pr = graph.pagerank() if graph.nodes else {}
    rows: list[dict[str, Any]] = []
    for node in graph.nodes.values():
        hay = " ".join(
            [node.id]
            + list(node.imports)
            + list(node.defines)
            + list(node.variables)
            + list(node.calls)
            + list(node.config_keys)
        ).lower()
        overlap = sorted(tok for tok in toks if tok in hay)
        if not overlap and toks:
            continue
        overlap_score = len(overlap) / max(1, len(toks)) if toks else 0.0
        centrality = pr.get(node.id, 0.0)
        score = round(overlap_score * 0.8 + min(0.2, centrality * 3.0), 4)
        why: list[str] = []
        if overlap:
            why.append("token_overlap")
        if centrality:
            why.append("graph_centrality")
        rows.append(
            {
                "path": node.id,
                "kind": node.kind,
                "score": score,
                "matched_tokens": overlap,
                "why": why,
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["path"]))
    return rows[:limit]


def _relation_candidates(intent: str, ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in ranked:
        rel = RelationCandidate(
            source="intent",
            target=row["path"],
            kind="relevance",
            state="search",
            score=row["score"],
            why=tuple(row["why"]) or ("token_overlap",),
        )
        out.append(rel.as_dict())
    return out


def _hard_edges(graph: lgwks_graph.Graph, ranked: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    selected = {r["path"] for r in ranked}
    edges: list[dict[str, Any]] = []
    for edge in graph.edges:
        if edge.source in selected or edge.target in selected:
            edges.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                    "state": "hard",
                    "weight": edge.weight,
                }
            )
        if len(edges) >= limit:
            break
    return edges


def build_portal(repo: Path, intent: str, *, refresh: bool = False) -> dict[str, Any]:
    repo = repo.resolve()
    graph = lgwks_graph.get_graph(repo, force_refresh=refresh)
    project_key = _project_key(intent, repo)
    portal_key = _portal_key(project_key, intent)
    ranked = _rank_candidates(graph, intent)
    packet = {
        "schema": PORTAL_SCHEMA,
        "key": portal_key,
        "project_key": project_key,
        "repo": str(repo),
        "intent": intent,
        "summary": (
            "Deterministic repo-grounded portal packet. Candidate files come from local graph "
            "structure plus intent-token overlap; relation candidates remain in search state "
            "until a typed support path is promoted."
        ),
        "tranches": list(TRANCHES),
        "graph": {
            "schema": graph.schema,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
        },
        "candidate_files": ranked,
        "relation_candidates": _relation_candidates(intent, ranked),
        "hard_edges": _hard_edges(graph, ranked),
    }
    _validate_portal_packet(packet)
    return packet


def _validate_portal_packet(packet: dict[str, Any]) -> None:
    required = {"schema", "key", "project_key", "repo", "intent", "tranches", "candidate_files", "relation_candidates", "hard_edges"}
    missing = required - set(packet)
    if missing:
        raise ValueError(f"portal packet missing keys: {sorted(missing)}")
    if packet["schema"] != PORTAL_SCHEMA:
        raise ValueError(f"unexpected portal schema: {packet['schema']!r}")
    for edge in packet.get("relation_candidates", []):
        if edge.get("state") not in EDGE_STATES:
            raise ValueError(f"invalid relation candidate state: {edge.get('state')!r}")
    for edge in packet.get("hard_edges", []):
        if edge.get("state") != "hard":
            raise ValueError("hard_edges must use state='hard'")


def _load_portal(repo: Path, key: str) -> dict[str, Any]:
    path = _portal_path(repo.resolve(), key)
    if not path.exists():
        raise FileNotFoundError(f"portal key not found: {key}")
    packet = json.loads(path.read_text(encoding="utf-8"))
    _validate_portal_packet(packet)
    return packet


def build_command(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    intent = _read_context(args)
    if not intent:
        print("error: portal build requires --intent, --context-file, or stdin", file=sys.stderr)
        return 1
    packet = build_portal(repo, intent, refresh=args.refresh)
    out = _portal_path(repo.resolve(), packet["key"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    return 0


def show_command(args: argparse.Namespace) -> int:
    packet = _load_portal(Path(args.repo), args.key)
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    return 0


def code_command(args: argparse.Namespace) -> int:
    packet = _load_portal(Path(args.repo), args.key)
    code_packet = {
        "schema": CODE_PACKET_SCHEMA,
        "key": packet["key"],
        "project_key": packet["project_key"],
        "repo": packet["repo"],
        "intent": packet["intent"],
        "summary": packet["summary"],
        "candidate_files": packet["candidate_files"][:6],
        "recommended_start": [row["path"] for row in packet["candidate_files"][:3]],
        "relation_candidates": packet["relation_candidates"][:6],
        "hard_edges": packet["hard_edges"][:12],
    }
    print(json.dumps(code_packet, indent=2, ensure_ascii=False))
    return 0


def add_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "portal",
        help="build deterministic repo-grounded portal packets for coding-agent re-entry",
    )
    ins = p.add_subparsers(dest="portal_command", required=True)

    build = ins.add_parser("build", help="compile intent/context into a stored portal packet")
    build.add_argument("--repo", default=".", help="path to repo or local folder (default: .)")
    build.add_argument("--intent", default="", help="inline operator intent")
    build.add_argument("--context-file", action="append", default=[], help="optional text/markdown context file")
    build.add_argument("--refresh", action="store_true", help="refresh the local graph cache before building")
    build.set_defaults(func=build_command)

    show = ins.add_parser("show", help="show a stored portal packet")
    show.add_argument("key", help="portal:<hash> key")
    show.add_argument("--repo", default=".", help="path to repo or local folder (default: .)")
    show.set_defaults(func=show_command)

    code = ins.add_parser("code", help="emit the compact AI-facing coding packet for a portal key")
    code.add_argument("key", help="portal:<hash> key")
    code.add_argument("--repo", default=".", help="path to repo or local folder (default: .)")
    code.set_defaults(func=code_command)
