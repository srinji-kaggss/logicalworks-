"""lgwks_hooks — comprehensive audit-first hook system for lgwks.

Architecture
------------
Every lgwks operation that touches files, commands, git, the network,
sessions, models, or auth SHOULD fire a hook event.  Events flow through
three layers:

  1. AUDIT layer (always-on, cannot be disabled)
     • Appends a structured record to .lgwks/audit.jsonl on every event.
     • The log is append-only; records are never mutated or deleted here.

  2. BUILTIN layer (shipped with lgwks, enabled by default)
     • why-annotation-nudge  → file.post_write   (print //why reminder)
     • scope-guard-mirror    → command.pre_exec   (mirrors scope-creep-guard.py intent)
     • token-spend-watcher   → model.post_invoke  (alert on high spend)
     • secret-scrub-check    → http.post_fetch    (warn on credential-like patterns)
     • git-drift-watch       → git.post_push      (note divergence from remote)

  3. USER layer (configured via .lgwks/hooks.json)
     • Arbitrary scripts called via subprocess.
     • Each receives the event payload as JSON on stdin.
     • Non-zero exit is logged as a hook failure (never crashes the caller).

Event taxonomy
--------------
  file.*           : pre_read, post_read, pre_write, post_write,
                     pre_delete, post_delete
  command.*        : pre_exec, post_exec, blocked
  git.*            : pre_commit, post_commit, pre_push, post_push,
                     pre_merge, post_merge, pre_stash, post_stash
  http.*           : pre_fetch, post_fetch, pre_crawl, post_crawl
  session.*        : start, checkpoint, end
  model.*          : pre_invoke, post_invoke, token_spend
  auth.*           : attempt, success, failure
  scope.*          : violation, override, activated, deactivated
  config.*         : pre_change, post_change, hooks_modified
  tool.*           : pre_invoke, post_invoke, error
  audit.*          : export, read   (meta-events about the audit system itself)

All events carry:
  schema, event, ts, session_id?, pid, cwd, payload (event-specific)

CLI surface
-----------
  lgwks hooks list                          # all hooks (builtin + user)
  lgwks hooks run <event> [--payload JSON]  # fire all hooks for event
  lgwks hooks add --name N --event E --command CMD [--enabled]
  lgwks hooks remove --name N
  lgwks hooks enable --name N
  lgwks hooks disable --name N
  lgwks hooks audit [--event E] [--last N] [--since ISO] [--export PATH]

//why: a single unified audit.jsonl is worth more than N scattered per-module
logs because agents can query one stream for the full story: what files were
written, what commands ran, what the model spent, what got blocked, all in
timestamp order.  Scatter = reasoning gaps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── constants ────────────────────────────────────────────────────────────────

SCHEMA = "lgwks.hooks.v0"
AUDIT_SCHEMA = "lgwks.audit.v0"
REGISTRY_SCHEMA = "lgwks.hooks-registry.v0"

# Events — dot-namespaced; callers import these or use strings directly.
EVENTS = {
    # file system
    "file.pre_read", "file.post_read",
    "file.pre_write", "file.post_write",
    "file.pre_delete", "file.post_delete",
    # command execution
    "command.pre_exec", "command.post_exec", "command.blocked",
    # git
    "git.pre_commit", "git.post_commit",
    "git.pre_push", "git.post_push",
    "git.pre_merge", "git.post_merge",
    "git.pre_stash", "git.post_stash",
    # network
    "http.pre_fetch", "http.post_fetch",
    "http.pre_crawl", "http.post_crawl",
    # session
    "session.start", "session.checkpoint", "session.end",
    # model / LLM
    "model.pre_invoke", "model.post_invoke", "model.token_spend",
    # auth
    "auth.attempt", "auth.success", "auth.failure",
    # scope guard
    "scope.violation", "scope.override", "scope.activated", "scope.deactivated",
    # config
    "config.pre_change", "config.post_change", "config.hooks_modified",
    # tool (lgwks verb invocations)
    "tool.pre_invoke", "tool.post_invoke", "tool.error",
    # audit meta
    "audit.export", "audit.read",
}

_CODE_EXTS = {
    ".py", ".rs", ".go", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".cc",
    ".cxx", ".h", ".hpp", ".cs", ".java", ".kt", ".swift", ".rb", ".sh",
    ".bash", ".zsh", ".m", ".mm", ".pl", ".pm", ".php", ".scala", ".r",
    ".lua", ".ex", ".exs", ".erl", ".hs", ".ml", ".mli", ".clj", ".cljs",
    ".lisp", ".scm",
}

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|bearer|auth)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_\-]{16,}['\"]?"
)

# ── path helpers ─────────────────────────────────────────────────────────────

def _audit_log(cwd: Path | None = None) -> Path:
    # //why: audit log lives in .lgwks/ next to active-scope.json so agents
    # reading the repo state directory get both security policy AND audit trail.
    base = (cwd or Path.cwd()) / ".lgwks"
    base.mkdir(parents=True, exist_ok=True)
    return base / "audit.jsonl"


def _registry_path(cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()) / ".lgwks"
    base.mkdir(parents=True, exist_ok=True)
    return base / "hooks.json"


# ── timestamp / session ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_id() -> str:
    """Best-effort session identifier: env var > pid."""
    return os.environ.get("LGWKS_SESSION_ID", f"pid-{os.getpid()}")


# ── event record builder ─────────────────────────────────────────────────────

def build_event(event: str, payload: dict[str, Any], cwd: Path | None = None) -> dict[str, Any]:
    """Construct a fully-typed, schema-versioned event record."""
    return {
        "schema": AUDIT_SCHEMA,
        "event": event,
        "ts": _now(),
        "session_id": _session_id(),
        "pid": os.getpid(),
        "cwd": str(cwd or Path.cwd()),
        "payload": payload,
    }


# ── audit log (layer 1, always-on) ───────────────────────────────────────────

def audit_append(record: dict[str, Any], cwd: Path | None = None) -> None:
    """Append one structured record to the append-only audit log.
    //why: open-append avoids truncation races; JSON Lines = streamable + grepable.
    //why: errors here are swallowed after stderr notice — hook failures must
    never crash the caller (audit is observability, not a hard gate).
    """
    try:
        log = _audit_log(cwd)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as exc:
        sys.stderr.write(f"[lgwks hooks] audit write failed: {exc}\n")


# ── registry (layer 3 — user hooks) ─────────────────────────────────────────

def _load_registry(cwd: Path | None = None) -> dict[str, Any]:
    path = _registry_path(cwd)
    if not path.exists():
        return {"schema": REGISTRY_SCHEMA, "hooks": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("hooks"), list):
            raise ValueError("hooks must be a list")
        return data
    except Exception as exc:
        sys.stderr.write(f"[lgwks hooks] registry parse failed: {exc}\n")
        return {"schema": REGISTRY_SCHEMA, "hooks": []}


def _save_registry(reg: dict[str, Any], cwd: Path | None = None) -> None:
    path = _registry_path(cwd)
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # emit a meta-event so the audit trail records the registry mutation
    fire("config.hooks_modified", {"registry_path": str(path)}, cwd=cwd)


# ── builtin hook implementations (layer 2) ───────────────────────────────────

def _builtin_why_nudge(event: str, payload: dict[str, Any]) -> None:
    """Nudge on file.post_write for code files."""
    path_str = payload.get("path", "")
    if Path(path_str).suffix.lower() in _CODE_EXTS:
        print(
            "💡 [//why hook] Remember to document non-obvious design decisions "
            "using '//why <rationale>' comments to prevent reasoning drift."
        )


def _builtin_secret_scrub(event: str, payload: dict[str, Any]) -> None:
    """Warn if fetched HTTP body looks like it contains credentials."""
    body = str(payload.get("body", ""))
    if _SECRET_RE.search(body):
        sys.stderr.write(
            "[lgwks hooks] ⚠️  secret-scrub-check: HTTP response contains "
            "credential-like patterns — review before storing.\n"
        )


def _builtin_token_watcher(event: str, payload: dict[str, Any]) -> None:
    """Alert when model token spend exceeds threshold."""
    spent = payload.get("tokens_used", 0)
    threshold = int(os.environ.get("LGWKS_TOKEN_ALERT_THRESHOLD", "50000"))
    if isinstance(spent, int) and spent > threshold:
        sys.stderr.write(
            f"[lgwks hooks] ⚠️  token-spend-watcher: {spent:,} tokens consumed "
            f"(threshold {threshold:,}). Review model call volume.\n"
        )


def _builtin_git_drift(event: str, payload: dict[str, Any]) -> None:
    """Warn after push if remote diverges (fast-forward rejected)."""
    exit_code = payload.get("exit_code", 0)
    stderr_out = payload.get("stderr", "")
    if exit_code != 0 or "rejected" in stderr_out.lower():
        sys.stderr.write(
            "[lgwks hooks] ⚠️  git-drift-watch: push had non-zero exit or rejection. "
            "Run `lgwks repo audit` to check alignment.\n"
        )


def _builtin_scope_mirror(event: str, payload: dict[str, Any]) -> None:
    """Log scope violations as audit events (scope-creep-guard.py is the hard block;
    this adds a structured audit record for later analysis)."""
    # The actual blocking is done by scope-creep-guard.py (PreToolUse hook in Claude).
    # Here we just enrich the audit trail with scope context.
    if event == "scope.violation":
        sys.stderr.write(
            f"[lgwks hooks] 🚫 scope-guard-mirror: {payload.get('message', 'scope violation')}\n"
        )


# Registry of builtin hooks: event → list of callables
_BUILTINS: dict[str, list] = {
    "file.post_write":   [_builtin_why_nudge],
    "http.post_fetch":   [_builtin_secret_scrub],
    "model.post_invoke": [_builtin_token_watcher],
    "model.token_spend": [_builtin_token_watcher],
    "git.post_push":     [_builtin_git_drift],
    "scope.violation":   [_builtin_scope_mirror],
}

# Builtin hook metadata for `lgwks hooks list`
BUILTIN_HOOKS = [
    {"name": "why-annotation-nudge",  "event": "file.post_write",   "type": "builtin", "enabled": True,
     "description": "Reminds agents to add //why comments after code file writes."},
    {"name": "secret-scrub-check",    "event": "http.post_fetch",   "type": "builtin", "enabled": True,
     "description": "Warns if HTTP response body contains credential-like patterns."},
    {"name": "token-spend-watcher",   "event": "model.post_invoke",  "type": "builtin", "enabled": True,
     "description": "Alerts when model token consumption exceeds LGWKS_TOKEN_ALERT_THRESHOLD."},
    {"name": "token-spend-watcher",   "event": "model.token_spend",  "type": "builtin", "enabled": True,
     "description": "Same watcher, also fires on explicit token_spend events."},
    {"name": "git-drift-watch",       "event": "git.post_push",     "type": "builtin", "enabled": True,
     "description": "Warns if git push was rejected or diverged from remote."},
    {"name": "scope-guard-mirror",    "event": "scope.violation",   "type": "builtin", "enabled": True,
     "description": "Mirrors scope.violation events to audit log and stderr."},
]


# ── main fire function (call this from any lgwks module) ─────────────────────

def fire(event: str, payload: dict[str, Any], cwd: Path | None = None) -> None:
    """Fire `event` with `payload`.

    Always:
      1. Writes to audit log.
      2. Runs matching builtin hooks.
      3. Runs matching user hooks (subprocess, stdin = event JSON).

    Never raises — all errors are captured and logged back to audit.

    Usage from any module:
        import lgwks_hooks
        lgwks_hooks.fire("file.post_write", {"path": str(target), "tool": "Edit"})
    """
    record = build_event(event, payload, cwd=cwd)

    # Layer 1: audit (always)
    audit_append(record, cwd=cwd)

    # Layer 2: builtins
    for fn in _BUILTINS.get(event, []):
        try:
            fn(event, payload)
        except Exception as exc:
            audit_append(build_event("tool.error", {
                "hook": fn.__name__, "event": event, "error": str(exc)
            }, cwd=cwd), cwd=cwd)

    # Layer 3: user hooks
    reg = _load_registry(cwd=cwd)
    payload_json = json.dumps(record, ensure_ascii=False)
    for hook in reg.get("hooks", []):
        if not hook.get("enabled", True):
            continue
        if hook.get("event") != event:
            continue
        cmd = hook.get("command", "")
        if not cmd:
            continue
        try:
            result = subprocess.run(
                cmd, shell=False, input=payload_json.encode(),
                capture_output=True, timeout=10,
                args=[cmd] if isinstance(cmd, str) else cmd,
            )
            if result.returncode != 0:
                audit_append(build_event("tool.error", {
                    "hook": hook.get("name"), "event": event,
                    "exit_code": result.returncode,
                    "stderr": result.stderr.decode(errors="replace")[:500],
                }, cwd=cwd), cwd=cwd)
        except Exception as exc:
            audit_append(build_event("tool.error", {
                "hook": hook.get("name"), "event": event, "error": str(exc),
            }, cwd=cwd), cwd=cwd)


# ── CLI commands ──────────────────────────────────────────────────────────────

def _cmd_list(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    reg = _load_registry(cwd=cwd)
    user_hooks = reg.get("hooks", [])
    all_hooks = [{"source": "builtin", **h} for h in BUILTIN_HOOKS] + \
                [{"source": "user", **h} for h in user_hooks]

    if getattr(args, "json", False):
        print(json.dumps({"schema": SCHEMA, "hooks": all_hooks}, indent=2))
        return 0

    # Human table
    col_w = [20, 22, 8, 8, 50]
    header = f"{'NAME':<{col_w[0]}} {'EVENT':<{col_w[1]}} {'SOURCE':<{col_w[2]}} {'ENABLED':<{col_w[3]}} DESCRIPTION"
    print(header)
    print("-" * (sum(col_w) + 4))
    for h in all_hooks:
        print(
            f"{h.get('name',''):<{col_w[0]}} "
            f"{h.get('event',''):<{col_w[1]}} "
            f"{h.get('source',''):<{col_w[2]}} "
            f"{'yes' if h.get('enabled', True) else 'no':<{col_w[3]}} "
            f"{h.get('description','')[:60]}"
        )
    return 0


def _cmd_run(args) -> int:
    event = args.event
    if event not in EVENTS:
        sys.stderr.write(f"[lgwks hooks] unknown event '{event}'. Run `lgwks hooks list` to see valid events.\n")
        return 1
    raw = getattr(args, "payload", None) or "{}"
    try:
        payload = json.loads(raw)
    except Exception as exc:
        sys.stderr.write(f"[lgwks hooks] invalid payload JSON: {exc}\n")
        return 1
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    fire(event, payload, cwd=cwd)
    return 0


def _cmd_add(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    name = args.name.strip()
    event = args.event.strip()
    command = args.command.strip()

    if not name:
        sys.stderr.write("[lgwks hooks] --name is required\n"); return 1
    if event not in EVENTS:
        sys.stderr.write(f"[lgwks hooks] unknown event '{event}'\n"); return 1
    if not command:
        sys.stderr.write("[lgwks hooks] --command is required\n"); return 1

    reg = _load_registry(cwd=cwd)
    # deduplicate by name
    reg["hooks"] = [h for h in reg["hooks"] if h.get("name") != name]
    reg["hooks"].append({
        "name": name,
        "event": event,
        "type": "script",
        "command": command,
        "enabled": True,
        "description": getattr(args, "description", "") or "",
    })
    _save_registry(reg, cwd=cwd)
    print(f"Hook '{name}' registered for event '{event}'.")
    return 0


def _cmd_remove(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    name = args.name.strip()
    reg = _load_registry(cwd=cwd)
    before = len(reg["hooks"])
    reg["hooks"] = [h for h in reg["hooks"] if h.get("name") != name]
    if len(reg["hooks"]) == before:
        sys.stderr.write(f"[lgwks hooks] hook '{name}' not found in user registry.\n")
        return 1
    _save_registry(reg, cwd=cwd)
    print(f"Hook '{name}' removed.")
    return 0


def _cmd_toggle(args, enabled: bool) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    name = args.name.strip()
    reg = _load_registry(cwd=cwd)
    found = False
    for h in reg["hooks"]:
        if h.get("name") == name:
            h["enabled"] = enabled
            found = True
    if not found:
        sys.stderr.write(f"[lgwks hooks] hook '{name}' not found in user registry (builtins cannot be toggled).\n")
        return 1
    _save_registry(reg, cwd=cwd)
    print(f"Hook '{name}' {'enabled' if enabled else 'disabled'}.")
    return 0


def _cmd_audit(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    log = _audit_log(cwd=cwd)

    if not log.exists():
        print(json.dumps({"schema": AUDIT_SCHEMA, "records": []}, indent=2) if getattr(args, "json", False)
              else "No audit log found.")
        return 0

    # Filters
    event_filter: str | None = getattr(args, "event_filter", None)
    last_n: int = int(getattr(args, "last", None) or 0)
    since: str | None = getattr(args, "since", None)
    export_path: str | None = getattr(args, "export", None)

    records: list[dict] = []
    with open(log, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if event_filter and rec.get("event") != event_filter:
                continue
            if since and rec.get("ts", "") < since:
                continue
            records.append(rec)

    if last_n:
        records = records[-last_n:]

    # Fire meta-event (reading the audit log IS auditable)
    fire("audit.read", {"records_read": len(records), "filters": {
        "event": event_filter, "since": since, "last": last_n,
    }}, cwd=cwd)

    if export_path:
        Path(export_path).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
        fire("audit.export", {"path": export_path, "count": len(records)}, cwd=cwd)
        print(f"Exported {len(records)} records to {export_path}")
        return 0

    if getattr(args, "json", False):
        print(json.dumps({"schema": AUDIT_SCHEMA, "records": records}, indent=2))
        return 0

    # Human view — terse table
    if not records:
        print("(no matching audit records)")
        return 0
    print(f"{'TS':<22} {'EVENT':<28} {'SESSION':<14} PAYLOAD_SUMMARY")
    print("-" * 90)
    for r in records:
        p = r.get("payload", {})
        summary = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(p.items())[:3])
        print(f"{r.get('ts',''):<22} {r.get('event',''):<28} {r.get('session_id',''):<14} {summary}")
    return 0


# ── argparse wiring ───────────────────────────────────────────────────────────

def add_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[name-defined]
    p = sub.add_parser("hooks", help="lgwks hook system: audit, lifecycle events, registry")
    p.add_argument("--repo", metavar="PATH", default=None,
                   help="repo root (default: cwd)")
    p.add_argument("--json", action="store_true", default=False,
                   help="structured JSON output")

    hsub = p.add_subparsers(dest="hooks_command", required=True)

    # list
    ls = hsub.add_parser("list", help="show all registered hooks (builtin + user)")
    ls.set_defaults(func=_cmd_list)

    # run
    run = hsub.add_parser("run", help="fire all hooks for an event")
    run.add_argument("event", help="dot-namespaced event (e.g. file.post_write)")
    run.add_argument("--payload", metavar="JSON", default="{}", help="event payload as JSON string")
    run.set_defaults(func=_cmd_run)

    # add
    add = hsub.add_parser("add", help="register a user hook script")
    add.add_argument("--name", required=True, help="unique hook name")
    add.add_argument("--event", required=True, help="event to subscribe (e.g. file.post_write)")
    add.add_argument("--command", required=True, help="executable path (receives event JSON on stdin)")
    add.add_argument("--description", default="", help="human description")
    add.set_defaults(func=_cmd_add)

    # remove
    rm = hsub.add_parser("remove", help="deregister a user hook")
    rm.add_argument("--name", required=True)
    rm.set_defaults(func=_cmd_remove)

    # enable / disable
    en = hsub.add_parser("enable", help="enable a user hook")
    en.add_argument("--name", required=True)
    en.set_defaults(func=lambda a: _cmd_toggle(a, True))

    dis = hsub.add_parser("disable", help="disable a user hook")
    dis.add_argument("--name", required=True)
    dis.set_defaults(func=lambda a: _cmd_toggle(a, False))

    # audit
    aud = hsub.add_parser("audit", help="query the append-only audit log")
    aud.add_argument("--event", dest="event_filter", metavar="EVENT", default=None,
                     help="filter by event name")
    aud.add_argument("--last", metavar="N", type=int, default=50,
                     help="show last N records (default 50)")
    aud.add_argument("--since", metavar="ISO", default=None,
                     help="filter records after ISO timestamp (e.g. 2026-06-01T00:00:00Z)")
    aud.add_argument("--export", metavar="PATH", default=None,
                     help="export matching records to a JSONL file")
    aud.set_defaults(func=_cmd_audit)
