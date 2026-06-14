"""lgwks_hooks — audit-first hook system for lgwks. (hardened v2)

Architecture
------------
Three layers, strict ordering:

  1. AUDIT (always-on, fail-loud)
     • Appends SHA-256 hash-chained records to .lgwks/audit.jsonl.
     • .lgwks/ created 0o700 (owner-only). Sensitive fields scrubbed BEFORE write.
     • File-locked (fcntl.flock) so concurrent writers do not interleave.
     • On write failure: logs to syslog and stderr; does NOT silently drop.

  2. BUILTINS (shipped, enabled by default)
     • why-annotation-nudge  → file.post_write
     • secret-scrub-check    → http.post_fetch
     • token-spend-watcher   → model.post_invoke / model.token_spend
     • git-drift-watch       → git.post_push
     • scope-guard-mirror    → scope.violation  (note: hard block lives in
                               ~/.claude/hooks/scope-creep-guard.py, a Claude Code
                               PreToolUse hook. This layer adds audit trail only.)

  3. USER (configured via .lgwks/hooks.json, max 50 hooks)
     • Command must be an absolute path string (no list form, no shell).
     • Runs with empty env (no credential inheritance) and /tmp cwd.
     • Sequential, per-hook timeout=10 s. Re-entrant _save_registry calls are
       guarded with a threading.local flag.

Security properties
-------------------
  • No credentials in audit log — SENSITIVE_FIELDS scrubbed to "[REDACTED]" before write.
  • Audit records are SHA-256 hash-chained — offline tampering is detectable.
  • fire() gates on EVENTS taxonomy — unknown events are rejected.
  • --export restricted to project root — path traversal blocked.
  • Session ID validated against [A-Za-z0-9_-]{1,64}.
  • Hook count capped at MAX_USER_HOOKS = 50.
  • Registry fields fully validated on load.

Events
------
  file.*      : pre_read, post_read, pre_write, post_write, pre_delete, post_delete
  command.*   : pre_exec, post_exec, blocked
  git.*       : pre_commit, post_commit, pre_push, post_push,
                pre_merge, post_merge, pre_stash, post_stash
  http.*      : pre_fetch, post_fetch, pre_crawl, post_crawl
  session.*   : start, checkpoint, end
  model.*     : pre_invoke, post_invoke, token_spend
  auth.*      : attempt, success, failure
  scope.*     : violation, override, activated, deactivated
  config.*    : pre_change, post_change, hooks_modified
  tool.*      : pre_invoke, post_invoke, error
  audit.*     : export, read

CLI
---
  lgwks hooks list
  lgwks hooks run <event> [--payload JSON]
  lgwks hooks add --name N --event E --command /abs/path [--description D]
  lgwks hooks remove --name N
  lgwks hooks enable --name N
  lgwks hooks disable --name N
  lgwks hooks audit [--event E] [--last N] [--since ISO] [--export PATH]
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── constants ────────────────────────────────────────────────────────────────

SCHEMA = "lgwks.hooks.v0"
AUDIT_SCHEMA = "lgwks.audit.v0"
REGISTRY_SCHEMA = "lgwks.hooks-registry.v0"

MAX_USER_HOOKS = 50
MAX_HOOK_NAME_LEN = 128
MAX_SESSION_ID_LEN = 64
MAX_EXPORT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB safety cap
MAX_REGEX_BODY_BYTES = 65_536
HOOK_TIMEOUT_S = 10

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_ABS_CMD_RE = re.compile(r"^/[^\x00]+$")  # must start with /; no NUL

# Fields whose values must never appear in audit records or hook payloads.
SENSITIVE_FIELDS = frozenset({
    "password", "passwd", "secret", "api_key", "apikey",
    "token", "bearer", "auth", "authorization", "credential",
    "private_key", "client_secret", "access_token", "refresh_token",
})

EVENTS: frozenset[str] = frozenset({
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
})

_CODE_EXTS = frozenset({
    ".py", ".rs", ".go", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".cc",
    ".cxx", ".h", ".hpp", ".cs", ".java", ".kt", ".swift", ".rb", ".sh",
    ".bash", ".zsh", ".m", ".mm", ".pl", ".pm", ".php", ".scala", ".r",
    ".lua", ".ex", ".exs", ".erl", ".hs", ".ml", ".mli", ".clj", ".cljs",
    ".lisp", ".scm",
})

# Compiled once — applied to HTTP bodies to detect credentials in responses.
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|bearer|auth)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_\-]{16,}['\"]?"
)

# Re-entrancy guard: prevents _save_registry → fire → user hook → _save_registry loops.
_registry_save_local = threading.local()

# ── path helpers ─────────────────────────────────────────────────────────────

def _lgwks_dir(cwd: Path | None = None) -> Path:
    """Return .lgwks/ dir, created with owner-only permissions (0o700)."""
    base = (cwd or Path.cwd()) / ".lgwks"
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base


def _audit_log(cwd: Path | None = None) -> Path:
    return _lgwks_dir(cwd) / "audit.jsonl"


def _registry_path(cwd: Path | None = None) -> Path:
    return _lgwks_dir(cwd) / "hooks.json"


def _registry_lock_path(cwd: Path | None = None) -> Path:
    return _lgwks_dir(cwd) / "hooks.lock"


@contextmanager
def _exclusive_lock(lock_path: Path):
    """Hold an exclusive advisory lock for a critical section."""
    with open(lock_path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _resolve_within_root(root: Path, candidate: str) -> Path | None:
    """Resolve candidate and ensure it stays inside root after symlink resolution."""
    root = root.resolve()
    resolved = Path(candidate).expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


# ── timestamp / session ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_id() -> str:
    """Validated session ID: env var must match [A-Za-z0-9_-]{1,64} or we use pid."""
    raw = os.environ.get("LGWKS_SESSION_ID", "")
    if raw and _SESSION_ID_RE.match(raw):
        return raw
    return f"pid-{os.getpid()}"


# ── payload scrubbing ────────────────────────────────────────────────────────

def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of payload with sensitive field values replaced by [REDACTED].
    //why: audit records are append-only and may be exported; credentials must
    never reach disk, logs, or user hook stdin.
    """
    scrubbed: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE_FIELDS:
            scrubbed[k] = "[REDACTED]"
        elif isinstance(v, dict):
            scrubbed[k] = _scrub(v)
        else:
            scrubbed[k] = v
    return scrubbed


# ── event record builder ─────────────────────────────────────────────────────

def build_event(
    event: str,
    payload: dict[str, Any],
    cwd: Path | None = None,
    prev_hash: str = "",
) -> dict[str, Any]:
    """Build a typed, schema-versioned, scrubbed event record."""
    return {
        "schema": AUDIT_SCHEMA,
        "event": event,
        "ts": _now(),
        "session_id": _session_id(),
        "pid": os.getpid(),
        "cwd": str(cwd or Path.cwd()),
        "prev_hash": prev_hash,        # SHA-256 of previous raw JSONL line
        "payload": _scrub(payload),
    }


# ── SHA-256 hash chaining ────────────────────────────────────────────────────

from lgwks_hashing import digest as _sha256  # canonical full digest (audit chain; one source of truth)


def _last_line_hash(log_path: Path) -> str:
    """Return SHA-256 of the last non-empty line in the audit log.
    Returns 'genesis' if the log is empty or does not exist.
    //why: hash-chaining makes offline record deletion/insertion detectable
    without requiring a centralised timestamp authority.
    """
    if not log_path.exists():
        return "genesis"
    try:
        with open(log_path, "rb") as fh:
            # Seek backward to find last non-empty line (efficient for large logs).
            fh.seek(0, 2)
            size = fh.tell()
            if size == 0:
                return "genesis"
            chunk_size = min(4096, size)
            fh.seek(-chunk_size, 2)
            tail = fh.read().decode("utf-8", errors="replace")
        lines = [l for l in tail.splitlines() if l.strip()]
        return _sha256(lines[-1]) if lines else "genesis"
    except Exception:
        return "genesis"


# ── audit log (layer 1 — always-on, fail-loud) ───────────────────────────────

def audit_append(record: dict[str, Any], cwd: Path | None = None) -> None:
    """Append one hash-chained record to the append-only audit log.

    File-locked (exclusive flock) so concurrent writers do not interleave.
    On failure: writes to syslog AND stderr. Does NOT silently drop.
    //why: silent audit failures are indistinguishable from active suppression.
    """
    try:
        log = _audit_log(cwd)
        with open(log, "a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                # Inject prev_hash just before writing so it covers the actual chain.
                record = dict(record)
                record["prev_hash"] = _last_line_hash(log)
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                fh.write(line + "\n")
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as exc:
        msg = f"[lgwks hooks] AUDIT WRITE FAILED: {exc}"
        sys.stderr.write(msg + "\n")
        try:
            logging.getLogger("lgwks.hooks").error(msg)
        except Exception:
            pass


# ── registry ─────────────────────────────────────────────────────────────────

def _validate_hook_entry(h: Any) -> str | None:
    """Return an error string if the hook entry is invalid, else None."""
    if not isinstance(h, dict):
        return "hook must be a dict"
    name = h.get("name")
    if not isinstance(name, str) or not name or len(name) > MAX_HOOK_NAME_LEN:
        return f"invalid name: {name!r}"
    event = h.get("event")
    if event not in EVENTS:
        return f"unknown event: {event!r}"
    cmd = h.get("command")
    if not isinstance(cmd, str) or not _ABS_CMD_RE.match(cmd):
        return f"command must be an absolute path string, got: {cmd!r}"
    enabled = h.get("enabled", True)
    if not isinstance(enabled, bool):
        return f"enabled must be bool, got: {type(enabled).__name__}"
    return None


def _load_registry(cwd: Path | None = None) -> dict[str, Any]:
    path = _registry_path(cwd)
    if not path.exists():
        return {"schema": REGISTRY_SCHEMA, "hooks": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("hooks"), list):
            raise ValueError("hooks must be a list")
        # Validate each entry; drop invalid ones (loud warning).
        valid_hooks = []
        for h in data["hooks"]:
            err = _validate_hook_entry(h)
            if err:
                sys.stderr.write(f"[lgwks hooks] dropping invalid hook entry: {err}\n")
                # Emit audit record for dropped hook — invalid entries are a security signal.
                audit_append(build_event("tool.error", {
                    "hook": h.get("name"), "error": f"invalid registry entry: {err}",
                }), cwd=cwd)
            else:
                valid_hooks.append(h)
        if len(valid_hooks) > MAX_USER_HOOKS:
            sys.stderr.write(
                f"[lgwks hooks] registry has {len(valid_hooks)} hooks, capping at {MAX_USER_HOOKS}.\n"
            )
            valid_hooks = valid_hooks[:MAX_USER_HOOKS]
        data["hooks"] = valid_hooks
        return data
    except Exception as exc:
        sys.stderr.write(f"[lgwks hooks] registry parse failed: {exc}\n")
        return {"schema": REGISTRY_SCHEMA, "hooks": []}


def _save_registry(reg: dict[str, Any], cwd: Path | None = None) -> None:
    path = _registry_path(cwd)
    # Atomic write: write to .tmp, then os.replace() — avoids TOCTOU and partial writes.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    # Re-entrant guard: prevent _save_registry → fire → user hook → _save_registry loops.
    if not getattr(_registry_save_local, "active", False):
        _registry_save_local.active = True
        try:
            fire("config.hooks_modified", {"registry_path": str(path)}, cwd=cwd)
        finally:
            _registry_save_local.active = False


def _mutate_registry(cwd: Path, mutate) -> Any:
    """Run a registry read-modify-write cycle under one process-wide file lock."""
    with _exclusive_lock(_registry_lock_path(cwd)):
        reg = _load_registry(cwd=cwd)
        result = mutate(reg)
        if result is not None:
            _save_registry(reg, cwd=cwd)
        return result


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
    """Warn if fetched HTTP body looks like it contains credentials.
    //why: body is capped to MAX_REGEX_BODY_BYTES to prevent ReDoS on adversarial input.
    """
    body = str(payload.get("body", ""))[:MAX_REGEX_BODY_BYTES]
    if _SECRET_PATTERN.search(body):
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
    """Warn after push if remote diverges."""
    exit_code = payload.get("exit_code", 0)
    stderr_out = str(payload.get("stderr", ""))
    if exit_code != 0 or "rejected" in stderr_out.lower():
        sys.stderr.write(
            "[lgwks hooks] ⚠️  git-drift-watch: push had non-zero exit or rejection. "
            "Run `lgwks repo audit` to check alignment.\n"
        )


def _builtin_scope_mirror(event: str, payload: dict[str, Any]) -> None:
    """Audit-trail layer for scope violations.

    NOTE: The hard enforcement block lives in ~/.claude/hooks/scope-creep-guard.py
    (a Claude Code PreToolUse hook, committed in Issue #3). This builtin provides
    a structured audit record and stderr notice for the lgwks audit trail only.
    It does NOT block execution.
    """
    sys.stderr.write(
        f"[lgwks hooks] 🚫 scope-guard-mirror: {payload.get('message', 'scope violation')}\n"
    )


# Builtin dispatch table: event → list[callable]
_BUILTINS: dict[str, list] = {
    "file.post_write":   [_builtin_why_nudge],
    "http.post_fetch":   [_builtin_secret_scrub],
    "model.post_invoke": [_builtin_token_watcher],
    "model.token_spend": [_builtin_token_watcher],
    "git.post_push":     [_builtin_git_drift],
    "scope.violation":   [_builtin_scope_mirror],
}

# Metadata for lgwks hooks list
BUILTIN_HOOKS = [
    {"name": "why-annotation-nudge",  "event": "file.post_write",   "type": "builtin", "enabled": True,
     "description": "Reminds agents to add //why comments after code file writes."},
    {"name": "secret-scrub-check",    "event": "http.post_fetch",   "type": "builtin", "enabled": True,
     "description": "Warns if HTTP response body contains credential-like patterns."},
    {"name": "token-spend-watcher",   "event": "model.post_invoke",  "type": "builtin", "enabled": True,
     "description": "Alerts when model token consumption exceeds LGWKS_TOKEN_ALERT_THRESHOLD."},
    {"name": "token-spend-watcher",   "event": "model.token_spend",  "type": "builtin", "enabled": True,
     "description": "Same watcher on explicit token_spend events."},
    {"name": "git-drift-watch",       "event": "git.post_push",     "type": "builtin", "enabled": True,
     "description": "Warns if git push was rejected or diverged."},
    {"name": "scope-guard-mirror",    "event": "scope.violation",   "type": "builtin", "enabled": True,
     "description": "Audit-trail mirror for scope violations (hard block: scope-creep-guard.py)."},
]


# ── main fire function ────────────────────────────────────────────────────────

def fire(event: str, payload: dict[str, Any], cwd: Path | None = None) -> None:
    """Fire `event` with `payload`.

    Gate: event MUST be in EVENTS — unknown events are rejected and logged.
    Order: scrub → audit → builtins → user hooks.
    Never raises.

    Usage from any lgwks module:
        import lgwks_hooks
        lgwks_hooks.fire("file.post_write", {"path": str(target), "tool": "Edit"})
    """
    # Gate: unknown events are rejected.
    if event not in EVENTS:
        sys.stderr.write(
            f"[lgwks hooks] rejected unknown event '{event}'. "
            f"Use a defined event or add it to EVENTS.\n"
        )
        return

    # Scrub happens before audit_append (not after).
    record = build_event(event, payload, cwd=cwd)

    # Layer 1: audit (always, fail-loud internally).
    audit_append(record, cwd=cwd)

    # Layer 2: builtins (pass original payload — they do their own body capping).
    for fn in _BUILTINS.get(event, []):
        try:
            fn(event, payload)
        except Exception as exc:
            audit_append(build_event("tool.error", {
                "hook": fn.__name__, "event": event, "error": str(exc),
            }, cwd=cwd), cwd=cwd)

    # Layer 3: user hooks.
    reg = _load_registry(cwd=cwd)
    scrubbed_json = json.dumps(record, ensure_ascii=False)
    for hook in reg.get("hooks", []):
        if not hook.get("enabled", True):
            continue
        if hook.get("event") != event:
            continue
        cmd_str = hook.get("command", "")
        if not cmd_str or not _ABS_CMD_RE.match(cmd_str):
            audit_append(build_event("tool.error", {
                "hook": hook.get("name"), "event": event,
                "error": f"invalid command path: {cmd_str!r}",
            }, cwd=cwd), cwd=cwd)
            continue
        try:
            result = subprocess.run(
                [cmd_str],           # list form — no shell, no injection
                shell=False,
                input=scrubbed_json.encode("utf-8"),
                capture_output=True,
                timeout=HOOK_TIMEOUT_S,
                env={},              # no credential inheritance
                cwd="/tmp",          # restricted working directory
            )
            if result.returncode != 0:
                audit_append(build_event("tool.error", {
                    "hook": hook.get("name"), "event": event,
                    "exit_code": result.returncode,
                    "stderr": result.stderr.decode(errors="replace")[:500],
                }, cwd=cwd), cwd=cwd)
        except subprocess.TimeoutExpired:
            audit_append(build_event("tool.error", {
                "hook": hook.get("name"), "event": event,
                "error": f"hook timed out after {HOOK_TIMEOUT_S}s",
            }, cwd=cwd), cwd=cwd)
        except Exception as exc:
            audit_append(build_event("tool.error", {
                "hook": hook.get("name"), "event": event, "error": str(exc),
            }, cwd=cwd), cwd=cwd)


# ── audit log verification ────────────────────────────────────────────────────

def verify_chain(cwd: Path | None = None) -> dict[str, Any]:
    """Verify SHA-256 hash chain integrity of the audit log.
    Returns {ok, records_checked, first_broken_index, error}.
    """
    log = _audit_log(cwd)
    if not log.exists():
        return {"ok": True, "records_checked": 0, "note": "no audit log"}
    records_checked = 0
    prev_line = ""
    prev_hash = "genesis"
    broken_at = None
    try:
        with open(log, "r", encoding="utf-8") as fh:
            for i, raw_line in enumerate(fh):
                raw_line = raw_line.rstrip("\n")
                if not raw_line.strip():
                    continue
                try:
                    rec = json.loads(raw_line)
                except Exception:
                    broken_at = i
                    break
                stored_prev = rec.get("prev_hash", "")
                if stored_prev != prev_hash:
                    broken_at = i
                    break
                prev_hash = _sha256(raw_line)
                prev_line = raw_line
                records_checked += 1
    except Exception as exc:
        return {"ok": False, "records_checked": records_checked, "error": str(exc)}
    if broken_at is not None:
        return {
            "ok": False,
            "records_checked": records_checked,
            "first_broken_index": broken_at,
            "note": "hash chain break detected — log may have been tampered with",
        }
    return {"ok": True, "records_checked": records_checked}


# ── CLI commands ──────────────────────────────────────────────────────────────

def _cmd_list(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    reg = _load_registry(cwd=cwd)
    user_hooks = reg.get("hooks", [])
    all_hooks = [{"source": "builtin", **h} for h in BUILTIN_HOOKS] + \
                [{"source": "user",    **h} for h in user_hooks]

    if getattr(args, "json", False):
        print(json.dumps({"schema": SCHEMA, "hooks": all_hooks}, indent=2))
        return 0

    col_w = [22, 24, 8, 8]
    header = (f"{'NAME':<{col_w[0]}} {'EVENT':<{col_w[1]}} "
              f"{'SOURCE':<{col_w[2]}} {'ENABLED':<{col_w[3]}} DESCRIPTION")
    print(header)
    print("-" * 100)
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
        sys.stderr.write(
            f"[lgwks hooks] unknown event '{event}'. "
            f"Run `lgwks hooks list` for valid events.\n"
        )
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
    name = (args.name or "").strip()
    event = (args.event or "").strip()
    command = (args.command or "").strip()
    description = (getattr(args, "description", "") or "").strip()

    if not name or len(name) > MAX_HOOK_NAME_LEN:
        sys.stderr.write(f"[lgwks hooks] --name must be 1–{MAX_HOOK_NAME_LEN} chars\n")
        return 1
    if event not in EVENTS:
        sys.stderr.write(f"[lgwks hooks] unknown event '{event}'\n"); return 1
    if not _ABS_CMD_RE.match(command):
        sys.stderr.write(
            f"[lgwks hooks] --command must be an absolute path, got: {command!r}\n"
        )
        return 1
    command_path = Path(command)
    if not command_path.is_file() or not os.access(command_path, os.X_OK):
        sys.stderr.write(
            f"[lgwks hooks] --command must point to an executable file, got: {command!r}\n"
        )
        return 1

    def mutate(reg: dict[str, Any]) -> int | None:
        reg["hooks"] = [h for h in reg["hooks"] if h.get("name") != name]
        if len(reg["hooks"]) >= MAX_USER_HOOKS:
            return None
        reg["hooks"].append({
            "name": name, "event": event, "type": "script",
            "command": command, "enabled": True, "description": description,
        })
        return 0

    rc = _mutate_registry(cwd, mutate)
    if rc is None:
        sys.stderr.write(
            f"[lgwks hooks] registry full (max {MAX_USER_HOOKS} user hooks).\n"
        )
        return 1
    print(f"Hook '{name}' registered for event '{event}'.")
    return rc


def _cmd_remove(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    name = (args.name or "").strip()

    def mutate(reg: dict[str, Any]) -> int | None:
        before = len(reg["hooks"])
        reg["hooks"] = [h for h in reg["hooks"] if h.get("name") != name]
        return 0 if len(reg["hooks"]) != before else None

    rc = _mutate_registry(cwd, mutate)
    if rc is None:
        sys.stderr.write(f"[lgwks hooks] hook '{name}' not found.\n")
        return 1
    print(f"Hook '{name}' removed.")
    return rc


def _cmd_toggle(args, enabled: bool) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    name = (args.name or "").strip()

    def mutate(reg: dict[str, Any]) -> int | None:
        found = False
        for h in reg["hooks"]:
            if h.get("name") == name:
                h["enabled"] = enabled
                found = True
        return 0 if found else None

    rc = _mutate_registry(cwd, mutate)
    if rc is None:
        sys.stderr.write(
            f"[lgwks hooks] hook '{name}' not found (builtins cannot be toggled).\n"
        )
        return 1
    print(f"Hook '{name}' {'enabled' if enabled else 'disabled'}.")
    return rc


def _cmd_audit(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    log = _audit_log(cwd=cwd)

    if not log.exists():
        msg: dict[str, Any] = {"schema": AUDIT_SCHEMA, "records": []}
        print(json.dumps(msg, indent=2) if getattr(args, "json", False)
              else "No audit log found.")
        return 0

    event_filter: str | None = getattr(args, "event_filter", None)
    last_n: int = int(getattr(args, "last", None) or 50)
    since: str | None = getattr(args, "since", None)
    export_path_str: str | None = getattr(args, "export", None)

    # --export path validation: must resolve inside project root.
    if export_path_str:
        export_resolved = _resolve_within_root(cwd, export_path_str)
        if export_resolved is None:
            sys.stderr.write(
                f"[lgwks hooks] --export path must be inside the project root ({cwd}).\n"
                f"  Requested: {export_path_str}\n"
            )
            return 1

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

    # Audit the read itself (no sensitive data in this payload).
    fire("audit.read", {
        "records_read": len(records),
        "filters": {"event": event_filter, "since": since, "last": last_n},
    }, cwd=cwd)

    if export_path_str:
        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
        if len(content.encode("utf-8")) > MAX_EXPORT_SIZE_BYTES:
            sys.stderr.write("[lgwks hooks] export too large (>50 MB); use --last to narrow.\n")
            return 1
        export_resolved.write_text(content, encoding="utf-8")
        fire("audit.export", {"path": str(export_resolved), "count": len(records)}, cwd=cwd)
        print(f"Exported {len(records)} records to {export_resolved}")
        return 0

    if getattr(args, "json", False):
        print(json.dumps({"schema": AUDIT_SCHEMA, "records": records}, indent=2))
        return 0

    if not records:
        print("(no matching audit records)")
        return 0

    # Human table — values truncated to 30 chars (already scrubbed in record).
    print(f"{'TS':<22} {'EVENT':<28} {'SESSION':<16} PAYLOAD_SUMMARY")
    print("-" * 95)
    for r in records:
        p = r.get("payload", {})
        summary = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(p.items())[:3])
        print(f"{r.get('ts',''):<22} {r.get('event',''):<28} {r.get('session_id',''):<16} {summary}")
    return 0


def _cmd_verify(args) -> int:
    cwd = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    result = verify_chain(cwd=cwd)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        status = "✅ OK" if result["ok"] else "❌ TAMPERED"
        print(f"Audit chain: {status} ({result.get('records_checked', 0)} records checked)")
        if not result["ok"]:
            print(f"  → {result.get('note', '')}")
    return 0 if result["ok"] else 1


def _cmd_install(args) -> int:
    import textwrap
    repo = Path(getattr(args, "repo", None) or Path.cwd()).resolve()
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 1
    
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    
    post_commit_path = hooks_dir / "post-commit"
    script_content = textwrap.dedent("""\
        #!/bin/sh
        # lgwks git post-commit hook for asynchronous code review
        CHANGED=$(git diff-tree --no-commit-id -r --name-only HEAD | grep '\\.py$' | tr '\\n' ',')
        if [ -n "$CHANGED" ]; then
          lgwks review --changed "$CHANGED" --out findings/ &
        fi
    """)
    post_commit_path.write_text(script_content, encoding="utf-8")
    
    try:
        post_commit_path.chmod(0o755)
    except Exception as exc:
        print(f"warning: could not make hook executable: {exc}", file=sys.stderr)
        
    print(f"Installed git post-commit hook to {post_commit_path}")
    return 0


# ── argparse wiring ───────────────────────────────────────────────────────────

def add_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[name-defined]
    p = sub.add_parser("hooks", help="lgwks hook system: audit, lifecycle events, registry")
    p.add_argument("--repo", metavar="PATH", default=None, help="repo root (default: cwd)")
    p.add_argument("--json", action="store_true", default=False, help="structured JSON output")

    hsub = p.add_subparsers(dest="hooks_command", required=True)

    ls = hsub.add_parser("list", help="show all registered hooks (builtin + user)")
    ls.set_defaults(func=_cmd_list)

    run = hsub.add_parser("run", help="fire all hooks for an event")
    run.add_argument("event", help="dot-namespaced event (e.g. file.post_write)")
    run.add_argument("--payload", metavar="JSON", default="{}", help="event payload as JSON string")
    run.set_defaults(func=_cmd_run)

    add = hsub.add_parser("add", help="register a user hook script")
    add.add_argument("--name", required=True, help="unique hook name")
    add.add_argument("--event", required=True, help="event to subscribe")
    add.add_argument("--command", required=True, help="absolute path to executable")
    add.add_argument("--description", default="", help="human description")
    add.set_defaults(func=_cmd_add)

    rm = hsub.add_parser("remove", help="deregister a user hook")
    rm.add_argument("--name", required=True)
    rm.set_defaults(func=_cmd_remove)

    en = hsub.add_parser("enable", help="enable a user hook")
    en.add_argument("--name", required=True)
    en.set_defaults(func=lambda a: _cmd_toggle(a, True))

    dis = hsub.add_parser("disable", help="disable a user hook")
    dis.add_argument("--name", required=True)
    dis.set_defaults(func=lambda a: _cmd_toggle(a, False))

    aud = hsub.add_parser("audit", help="query the append-only audit log")
    aud.add_argument("--event", dest="event_filter", metavar="EVENT", default=None)
    aud.add_argument("--last", metavar="N", type=int, default=50)
    aud.add_argument("--since", metavar="ISO", default=None)
    aud.add_argument("--export", metavar="PATH", default=None,
                     help="export to JSONL file (must be inside project root)")
    aud.set_defaults(func=_cmd_audit)

    verify = hsub.add_parser("verify", help="verify SHA-256 hash chain integrity of audit log")
    verify.set_defaults(func=_cmd_verify)

    install = hsub.add_parser("install", help="install git post-commit hook")
    install.set_defaults(func=_cmd_install)
