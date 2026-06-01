"""
lgwks_auth_runtime — read-only auth resolver for crawler fetches.

Secrets remain in macOS Keychain. This module only maps a URL host to an active
auth lock from `tools/lgwks-auth`, then asks Keychain for that one secret just in
time. No token is printed, logged, cached, or written into the research stores.

Allowed secret shapes:
  Bearer abc...          -> Authorization: Bearer abc...
  Authorization: ...     -> Authorization: ...
  Cookie: ...            -> Cookie: ...
  abc...                 -> Authorization: Bearer abc...
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

VAULT_DIR = Path(os.environ.get("LGWKS_VAULT_DIR", Path.home() / ".lgwks" / "auth-vault"))
REGISTRY = VAULT_DIR / "locks.jsonl"
REQUESTS = VAULT_DIR / "needs_auth.jsonl"
SERVICE_PREFIX = "lgwks:"


def _records() -> list[dict]:
    if not REGISTRY.exists():
        return []
    out: list[dict] = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            return []
    return out


def _active_sites() -> set[str]:
    status: dict[str, str] = {}
    for rec in _records():
        site = str(rec.get("site", "")).lower().strip()
        if not site:
            continue
        if rec.get("event") == "lock":
            status[site] = "active"
        elif rec.get("event") == "stale":
            status[site] = "stale"
    return {site for site, state in status.items() if state == "active"}


def _matches(host: str, site: str) -> bool:
    host = host.lower().rstrip(".")
    site = site.lower().rstrip(".")
    return host == site or host.endswith("." + site)


def site_for_url(url: str) -> str | None:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return None
    matches = [site for site in _active_sites() if _matches(host, site)]
    return sorted(matches, key=len, reverse=True)[0] if matches else None


def _safe_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.split("?", 1)[0].split("#", 1)[0]
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=host, query="", fragment=""))


def request_keyring(url: str, reason: str, status: int | None = None) -> dict:
    """Append a JSON auth request. Never logs query strings, fragments, userinfo, or tokens."""
    host = urllib.parse.urlparse(url).hostname or ""
    rec = {
        "ts": time.time(),
        "event": "needs_auth",
        "host": host,
        "url": _safe_url(url),
        "reason": reason,
        "status": status,
        "cred_ref": f"keychain://{SERVICE_PREFIX}{host}" if host else "",
    }
    REQUESTS.parent.mkdir(parents=True, exist_ok=True)
    with REQUESTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def _keychain_secret(site: str) -> str | None:
    service = f"{SERVICE_PREFIX}{site}"
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    value = proc.stdout.strip() if proc.returncode == 0 else ""
    return value or None


def _headers_from_secret(secret: str) -> dict[str, str]:
    s = secret.strip()
    low = s.lower()
    if low.startswith("authorization:"):
        return {"Authorization": s.split(":", 1)[1].strip()}
    if low.startswith("cookie:"):
        return {"Cookie": s.split(":", 1)[1].strip()}
    if low.startswith("bearer "):
        return {"Authorization": s}
    return {"Authorization": f"Bearer {s}"}


def headers_for_url(url: str) -> dict[str, str]:
    site = site_for_url(url)
    if not site:
        return {}
    secret = _keychain_secret(site)
    if not secret:
        request_keyring(url, reason="active auth lock exists but keychain secret is missing")
        return {}
    return _headers_from_secret(secret) if secret else {}


def note_auth_failure(url: str, status: int) -> None:
    if status in {401, 403}:
        request_keyring(url, reason="remote returned auth failure", status=status)
