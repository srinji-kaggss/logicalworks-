"""lgwks_jepa — first executable multi-view JEPA package surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import lgwks_capture
import lgwks_model_hub
import lgwks_portal

ROOT = Path(__file__).resolve().parent
JEPA_ROOT = ROOT / "store" / "jepa"
JEPA_SCHEMA = "lgwks.jepa.v1"

_STOP = {
    "the", "and", "that", "with", "from", "this", "into", "your", "have", "just", "need", "what", "when",
    "where", "which", "about", "like", "onto", "also", "then", "than", "them", "they", "their", "there",
    "were", "been", "being", "will", "would", "could", "should", "inside", "while", "over", "under", "same",
    "some", "more", "less", "very", "much", "only", "still", "because", "across", "through", "using", "used",
    "user", "human", "agent", "model", "llm", "jepa", "stuff", "slop", "project",
}


def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_./-]{2,}", text)]


def _read_views(args: argparse.Namespace) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    if getattr(args, "intent", "").strip():
        views.append({"name": "intent", "source": "inline", "text": args.intent.strip()})
    for idx, file_arg in enumerate(getattr(args, "view_file", []) or [], start=1):
        p = Path(file_arg)
        if p.exists():
            views.append({"name": f"view_{idx}", "source": str(p), "text": p.read_text(encoding="utf-8")})
    for idx, file_arg in enumerate(getattr(args, "context_file", []) or [], start=1):
        p = Path(file_arg)
        if p.exists():
            views.append({"name": f"context_{idx}", "source": str(p), "text": p.read_text(encoding="utf-8")})
    blob = getattr(args, "stdin_text", "")
    if blob:
        views.append({"name": "stdin", "source": "stdin", "text": blob})
    return [v for v in views if v["text"].strip()]


def _view_packet(view: dict[str, Any]) -> dict[str, Any]:
    toks = _tokenize(view["text"])
    return {
        "name": view["name"],
        "source": view["source"],
        "chars": len(view["text"]),
        "tokens": len(toks),
        "preview": view["text"][:280],
    }


def _latent_anchors(views: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    provenance: dict[str, list[str]] = {}
    for view in views:
        seen = {tok for tok in _tokenize(view["text"]) if tok not in _STOP}
        for tok in seen:
            counts[tok] = counts.get(tok, 0) + 1
            provenance.setdefault(tok, []).append(view["name"])
    rows = []
    for tok, ct in counts.items():
        if ct < 2:
            continue
        rows.append({"anchor": tok, "views": sorted(provenance[tok]), "score": round(ct / max(1, len(views)), 4)})
    rows.sort(key=lambda r: (-r["score"], -len(r["anchor"]), r["anchor"]))
    return rows[:limit]


def _human_projection(anchors: list[dict[str, Any]], views: list[dict[str, Any]]) -> dict[str, Any]:
    if anchors:
        summary = "Shared anchors across views: " + ", ".join(a["anchor"] for a in anchors[:6]) + "."
    else:
        summary = "No repeated anchors across views yet; package is still a raw intake shell."
    return {
        "summary": summary,
        "view_count": len(views),
        "next_questions": [
            "Which anchor is central rather than incidental?",
            "Which view is strongest evidence versus framing noise?",
            "What concrete repo, paper, or experiment should this bind to next?",
        ],
    }


def _machine_projection(anchors: list[dict[str, Any]], capture_packet: dict[str, Any] | None,
                        portal_packet: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "anchors": anchors,
        "capture_key": capture_packet["key"] if capture_packet else "",
        "portal_key": portal_packet["key"] if portal_packet else "",
        "repo": portal_packet["repo"] if portal_packet else "",
        "candidate_files": portal_packet["candidate_files"][:6] if portal_packet else [],
    }


def _capture_for_views(args: argparse.Namespace, repo: Path | None, combined_text: str) -> dict[str, Any] | None:
    if getattr(args, "no_capture", False):
        return None
    cap_args = argparse.Namespace(
        target=str(repo) if repo else "",
        intent=combined_text,
        context_file=[],
        stdin_text="",
        repo=str(repo) if repo else "",
        project=getattr(args, "project", ""),
        source_type="repo" if repo else "auto",
        max_pages=getattr(args, "max_pages", 25),
        max_depth=getattr(args, "max_depth", 2),
        max_files=getattr(args, "max_files", 250),
        max_chars=getattr(args, "max_chars", 120_000),
        chunk_words=getattr(args, "chunk_words", 320),
        chunk_overlap=getattr(args, "chunk_overlap", 48),
        fact_threshold=getattr(args, "fact_threshold", 0.6),
        embed_provider=getattr(args, "embed_provider", "deterministic"),
        embed_model=getattr(args, "embed_model", ""),
        login_if_needed=False,
        login_url="",
        success_selector=None,
        max_auto_bypass_attempts=0,
        max_auth_handoffs=0,
        browser_engine="chromium",
        refresh_graph=getattr(args, "refresh_graph", False),
    )
    return lgwks_capture.build_capture(cap_args)


def build_package(args: argparse.Namespace) -> dict[str, Any]:
    raw_views = _read_views(args)
    if not raw_views:
        raise ValueError("jepa build requires --intent, --view-file, --context-file, or stdin")
    repo = Path(args.repo).resolve() if getattr(args, "repo", "") else None
    combined = "\n\n".join(v["text"] for v in raw_views)
    anchors = _latent_anchors(raw_views)
    capture_packet = _capture_for_views(args, repo, combined)
    portal_packet = None
    if repo:
        portal_packet = lgwks_portal.build_portal(repo, combined, refresh=args.refresh_graph)
        portal_path = repo / ".lgwks" / "portals" / f"{portal_packet['key'].replace(':', '_')}.json"
        portal_path.parent.mkdir(parents=True, exist_ok=True)
        portal_path.write_text(json.dumps(portal_packet, indent=2, ensure_ascii=False), encoding="utf-8")
    key = f"jepa:{_sha((str(repo or '') + '|' + combined + '|' + time.strftime('%Y%m%d')))}"
    packet = {
        "schema": JEPA_SCHEMA,
        "key": key,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo) if repo else "",
        "views": [_view_packet(v) for v in raw_views],
        "latent": {"anchors": anchors, "view_count": len(raw_views)},
        "machine": _machine_projection(anchors, capture_packet, portal_packet),
        "human": _human_projection(anchors, raw_views),
        "summary": (
            "Deterministic JEPA runtime package. Multiple raw views are collapsed into shared anchors, "
            "then rebound to capture/portal artifacts when a concrete repo is available."
        ),
    }
    out = JEPA_ROOT / f"{key.replace(':', '_')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    return packet


def build_command(args: argparse.Namespace) -> int:
    try:
        packet = build_package(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    return 0


def show_command(args: argparse.Namespace) -> int:
    path = JEPA_ROOT / f"{args.key.replace(':', '_')}.json"
    if not path.exists():
        print(f"error: jepa key not found: {args.key}", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def doctor() -> dict[str, Any]:
    mh = lgwks_model_hub.doctor()
    return {
        "schema": "lgwks.jepa.doctor.v1",
        "runtime": {
            "capture_surface": True,
            "portal_surface": True,
            "machine_and_human_projections": True,
            "multiview_package_builder": True,
        },
        "ml_state": {
            "semantic_eye_up": mh["semantic_eye"]["up"],
            "coreml_classifier_loaded": mh["intent_classifier"]["coreml_model_loaded"],
            "foundation_models": mh["foundation"].get("foundation_models", False),
            "natural_language": mh["foundation"].get("natural_language", False),
        },
        "gaps": [
            "No trained JEPA predictor exists yet.",
            "No promoted BERT/CoreML semantic router is active yet.",
            "No GNN learner is training over temporal package transitions yet.",
            "View-alignment is lexical/embedding-guided runtime packaging, not JEPA loss training.",
        ],
        "next_step": (
            "Use `lgwks jepa build` to create canonical multi-view packages now; "
            "train the future predictor/GNN against those stable artifacts."
        ),
    }


def doctor_command(_args: argparse.Namespace) -> int:
    print(json.dumps(doctor(), indent=2, ensure_ascii=False))
    return 0


def add_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "jepa",
        help="multi-view JEPA runtime packages: shared anchors, machine packet, human projection",
    )
    ins = p.add_subparsers(dest="jepa_command", required=True)

    build = ins.add_parser("build", help="compile multiple raw views into one deterministic JEPA package")
    build.add_argument("--intent", default="", help="inline world-model dump or seed view")
    build.add_argument("--view-file", action="append", default=[], help="repeatable raw view file")
    build.add_argument("--context-file", action="append", default=[], help="repeatable supporting context file")
    build.add_argument("--repo", default="", help="optional repo to bind through portal/capture")
    build.add_argument("--project", default="")
    build.add_argument("--embed-provider", choices=["auto", "ollama", "openrouter-vl", "deterministic"], default="deterministic")
    build.add_argument("--embed-model", default="")
    build.add_argument("--max-pages", type=int, default=25)
    build.add_argument("--max-depth", type=int, default=2)
    build.add_argument("--max-files", type=int, default=250)
    build.add_argument("--max-chars", type=int, default=120_000)
    build.add_argument("--chunk-words", type=int, default=320)
    build.add_argument("--chunk-overlap", type=int, default=48)
    build.add_argument("--fact-threshold", type=float, default=0.6)
    build.add_argument("--refresh-graph", action="store_true")
    build.add_argument("--no-capture", action="store_true", help="skip substrate/capture pass; package views only")
    build.set_defaults(func=build_command)

    show = ins.add_parser("show", help="show a stored JEPA package")
    show.add_argument("key", help="jepa:<hash>")
    show.set_defaults(func=show_command)

    doc = ins.add_parser("doctor", help="report whether the JEPA runtime ingredients are actually present")
    doc.set_defaults(func=doctor_command)
