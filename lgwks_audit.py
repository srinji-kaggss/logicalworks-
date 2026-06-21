"""lgwks_audit — the one canonical hardened audit-append primitive (#223 family 1).

Five modules (vault, gh, intent, debug, agent_os) each hand-rolled an audit
writer. They drifted on the things that matter for an audit log: file locking,
permissions, crash-safety (fsync), and secret redaction (only `gh` redacted, and
only by dropping a few hard-coded key names). This consolidates the WRITE
behaviour into one primitive; each caller keeps its own log path (paths legitimately
differ — vault uses a dedicated dir, others are cwd-relative or configurable).

Guarantees (vault-grade — `lgwks_vault._audit` was the hardened reference):
- parent dir created and chmod 0700; log file chmod 0600 (owner-only).
- exclusive fcntl lock around the append, so concurrent writers never interleave.
- write + flush + fsync — crash-safe.
- every record is REDACTED before it touches disk: keys whose name denotes a
  credential become "[REDACTED]"; all string values are scrubbed for embedded
  secrets via the canonical lgwks_redact.scrub. This closes the gap where 4 of 5
  writers logged un-redacted records.
- NEVER raises: an audit failure must not break the audited operation. Returns
  True on success, False on any failure so the caller can flag audit loss.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path
from typing import Any

from lgwks_redact import scrub as _scrub

# Key names that denote a credential value regardless of the value's content.
# Bounded so we match a sensitive *segment* (auth_token, apiKey, oauth) but not a
# larger word that merely contains one (author, secretary).
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_\-])?"
    r"(token|password|passphrase|secret|api[_-]?key|auth|credential|bearer|private[_-]?key)"
    r"(?:s)?(?:$|[_\-])"
)


def audit_path(name: str, base_dir: Path | None = None) -> Path:
    """Conventional audit log path: ``<base_dir or cwd>/.lgwks/<name>-audit.jsonl``."""
    return (base_dir or Path.cwd()) / ".lgwks" / f"{name}-audit.jsonl"


def _redact(value: Any) -> Any:
    """Recursively redact a record: values under credential-named keys become
    "[REDACTED]"; string values are scrubbed for embedded credentials."""
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_KEY_RE.search(k):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _scrub(value)
    return value


def audit_append(log_path: Path | str, record: dict[str, Any]) -> bool:
    """Append one redacted JSON audit record to ``log_path`` with vault-grade
    hardening. Never raises; returns True on success, False on any failure."""
    try:
        path = Path(log_path)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            if parent.stat().st_mode & 0o777 != 0o700:
                os.chmod(parent, 0o700)
        except OSError:
            pass  # best-effort; never lose the audit over a chmod
        line = json.dumps(_redact(record), sort_keys=True, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        try:
            if path.stat().st_mode & 0o777 != 0o600:
                os.chmod(path, 0o600)
        except OSError:
            pass
        return True
    except Exception:
        return False  # audit loss is non-blocking; caller may flag it
