"""lgwks_capture — unified operator-facing capture compiler over substrate + portal."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import lgwks_portal
import lgwks_substrate


ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "store" / "captures"
CAPTURE_SCHEMA = "lgwks.capture.v1"


def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


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


def _capture_key(target: str, context: str) -> str:
    return f"capture:{_sha(target + '|' + context + '|' + time.strftime('%Y%m%d'))}"


def _capture_path(key: str) -> Path:
    return CAPTURE_ROOT / f"{key.replace(':', '_')}.json"


def _target_repo(target: str, source_type: str, repo_arg: str) -> Path | None:
    if repo_arg:
        return Path(repo_arg).resolve()
    kind = lgwks_substrate._source_type(target, source_type)
    if kind in {"repo", "folder"}:
        return Path(target).resolve()
    return None


def _materialize_inline_context(key: str, context: str) -> Path:
    inbox = CAPTURE_ROOT / "_inbox" / key.replace(":", "_")
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / "capture.txt"
    path.write_text(context, encoding="utf-8")
    return path


def _substrate_args(args: argparse.Namespace, target: str) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        project=args.project,
        source_type=args.source_type,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_files=args.max_files,
        max_chars=args.max_chars,
        chunk_words=args.chunk_words,
        chunk_overlap=args.chunk_overlap,
        fact_threshold=args.fact_threshold,
        embed_provider=args.embed_provider,
        embed_model=args.embed_model,
        login_if_needed=args.login_if_needed,
        login_url=args.login_url,
        success_selector=args.success_selector,
        max_auto_bypass_attempts=args.max_auto_bypass_attempts,
        max_auth_handoffs=args.max_auth_handoffs,
        browser_engine=args.browser_engine,
    )


def build_capture(args: argparse.Namespace) -> dict[str, Any]:
    context = _read_context(args)
    target = args.target or ""
    if not target and not context:
        raise ValueError("capture build requires a target, inline intent/context, or stdin")
    key = _capture_key(target or "inline", context)
    effective_target = target or str(_materialize_inline_context(key, context))
    substrate_manifest = lgwks_substrate.build_run(_substrate_args(args, effective_target))
    repo = _target_repo(effective_target, args.source_type, args.repo)
    portal_packet: dict[str, Any] | None = None
    if repo and context:
        portal_packet = lgwks_portal.build_portal(repo, context, refresh=args.refresh_graph)
        portal_path = repo / ".lgwks" / "portals" / f"{portal_packet['key'].replace(':', '_')}.json"
        portal_path.parent.mkdir(parents=True, exist_ok=True)
        portal_path.write_text(json.dumps(portal_packet, indent=2, ensure_ascii=False), encoding="utf-8")
    packet = {
        "schema": CAPTURE_SCHEMA,
        "key": key,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input": {
            "target": target,
            "effective_target": effective_target,
            "source_type": lgwks_substrate._source_type(effective_target, args.source_type),
            "project": args.project or "",
            "context_present": bool(context),
        },
        "context": {
            "chars": len(context),
            "preview": context[:400],
        },
        "substrate": {
            "run_id": substrate_manifest["run_id"],
            "manifest_path": str(Path(substrate_manifest["artifacts"]["root"]) / "manifest.json"),
            "counts": substrate_manifest["counts"],
            "embedding": substrate_manifest["embedding"],
            "global_artifacts": substrate_manifest.get("global_artifacts", {}),
        },
        "bindings": {
            "repo": str(repo) if repo else "",
            "project_key": portal_packet["project_key"] if portal_packet else "",
            "portal_key": portal_packet["key"] if portal_packet else "",
        },
        "summary": (
            "Unified deterministic capture packet. Source material is normalized through substrate first; "
            "repo-grounded portal binding is optional and only promoted when a concrete local path exists."
        ),
    }
    out = _capture_path(key)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    return packet


def build_command(args: argparse.Namespace) -> int:
    try:
        packet = build_capture(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    return 0


def show_command(args: argparse.Namespace) -> int:
    path = _capture_path(args.key)
    if not path.exists():
        print(f"error: capture key not found: {args.key}", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def add_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "capture",
        help="unified capture compiler over substrate with optional repo-grounded portal binding",
    )
    ins = p.add_subparsers(dest="capture_command", required=True)

    build = ins.add_parser("build", help="capture a target or inline context into a stored packet")
    build.add_argument("target", nargs="?", default="", help="url|file|folder|repo target; omit for inline-only capture")
    build.add_argument("--intent", default="", help="inline operator context or seed intent")
    build.add_argument("--context-file", action="append", default=[], help="extra context files to fold into the capture")
    build.add_argument("--repo", default="", help="optional repo/folder to bind for portal generation")
    build.add_argument("--project", default="")
    build.add_argument("--source-type", choices=["auto", "url", "file", "folder", "repo"], default="auto")
    build.add_argument("--max-pages", type=int, default=25)
    build.add_argument("--max-depth", type=int, default=2)
    build.add_argument("--max-files", type=int, default=250)
    build.add_argument("--max-chars", type=int, default=120_000)
    build.add_argument("--chunk-words", type=int, default=320)
    build.add_argument("--chunk-overlap", type=int, default=48)
    build.add_argument("--fact-threshold", type=float, default=0.6)
    build.add_argument("--embed-provider", choices=["auto", "ollama", "openrouter-vl", "deterministic"], default="auto")
    build.add_argument("--embed-model", default="")
    build.add_argument("--login-if-needed", action=argparse.BooleanOptionalAction, default=True)
    build.add_argument("--login-url", default="")
    build.add_argument("--auth-selector", dest="success_selector", default=None)
    build.add_argument("--max-auto-bypass-attempts", type=int, default=3)
    build.add_argument("--max-auth-handoffs", type=int, default=3)
    build.add_argument("--chromium", dest="browser_engine", action="store_const", const="chromium",
                       default="webkit", help="use Chromium instead of WebKit")
    build.add_argument("--refresh-graph", action="store_true", help="refresh repo graph cache before portal binding")
    build.set_defaults(func=build_command)

    show = ins.add_parser("show", help="show a stored capture packet")
    show.add_argument("key", help="capture:<hash>")
    show.set_defaults(func=show_command)
