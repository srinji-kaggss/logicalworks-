"""lgwks_redact — the single source of truth for credential redaction.

One regex, one function. Every surface that writes command output to a log, an
audit record, or the user's screen scrubs through here. This used to be copy-pasted
(`_SECRET_RE` + `_scrub`) into lgwks_debug / lgwks_gh / lgwks_intent — three copies of
a security control means a fix to one leaves the other two leaking. Centralizing makes
"never let a credential reach disk/logs/stdout" enforceable in exactly one place.

Scope: this is the secret-*value* redactor (key=VALUE / bearer TOKEN forms). It is
distinct from, and must not be conflated with:
  - lgwks_substrate_config._SECRET_RE — a secret-*keyword* detector for code analysis.
  - lgwks_run._scrub — a full-URL stripper (query-string credentials).
  - lgwks_hooks._scrub — a dict-field redactor for structured audit payloads.
Those are different jobs; if they ever need this value-redactor too, import it from here.
"""

from __future__ import annotations

import re

__all__ = ["SECRET_RE", "scrub"]

# Matches `api_key = "...."`, `token: bearer ....`, `password=....`, etc. — the
# credential VALUE, redacted whole. The {8,} tail avoids redacting short non-secrets.
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key\w*|token\w*|password\w*|secret\w*|auth\w*)\s*([=:]\s*(bearer|token)?|(bearer|token))\s*['\"]?[^\s'\"]{8,}['\"]?"
)


def scrub(text: str) -> str:
    """Redact credential values from text before any log, display, or audit write."""
    return SECRET_RE.sub("[REDACTED]", text)
