"""
lgwks_vault — the INTENT-VAULT store (build #2, z4 core). The most sensitive store: human PII, intent,
and auth sessions. Encrypted at rest (Fernet = AES-128-CBC + HMAC-SHA256), FAIL-CLOSED.

Key model (no new secret management, no argv leak):
  • the encryption key is DERIVED from the existing lgwks signing secret (lgwks_sign.signing_key — env
    or macOS Keychain, provisioned once interactively, never on argv), domain-separated so it is a
    distinct key from the signing/HMAC use.
  • if no real key is anchored (signing key absent → 'unanchored'), the vault is LOCKED: set/get refuse
    with the exact provisioning command. We NEVER write PII to disk in plaintext — fail-closed is the
    whole point of a vault.

Boundary (T0): values never touch a log, a prompt, a URL, or argv. `keys()` lists names only. This store
holds PII/intent/sessions ONLY — fetched world data is lgwks_cache, AI thinking is lgwks_cognition.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

import lgwks_sign

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "intent"
_SAFE = re.compile(r"[^a-z0-9._-]+")


def _derive_key() -> bytes | None:
    """Derive a Fernet key from the anchored signing secret, domain-separated. None if unanchored
    (fail-closed — caller must refuse to store)."""
    secret, mode = lgwks_sign.signing_key()
    if not lgwks_sign.is_keyed(mode):
        return None
    material = hashlib.sha256(b"lgwks-vault-v1\x00" + secret).digest()   # distinct from signing/HMAC use
    return base64.urlsafe_b64encode(material)


def _fernet():
    key = _derive_key()
    if key is None:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key)


def is_unlocked() -> bool:
    return _derive_key() is not None


def _entry_path(key: str) -> Path:
    safe = _SAFE.sub("-", key.strip().lower()).strip("-") or "unnamed"
    suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return _DIR / f"{safe}-{suffix}.enc"


_LOCKED = ("vault LOCKED — no encryption key anchored. provision once (no echo, no argv):\n"
           "  security add-generic-password -U -a lgwks -s lgwks:signing-key -w")


def set_entry(key: str, value) -> dict:
    """Encrypt+store a PII/intent/session value (json-serialisable). Fail-closed if the vault is locked.
    The plaintext never touches disk, log, or argv."""
    f = _fernet()
    if f is None:
        raise PermissionError(_LOCKED)
    _DIR.mkdir(parents=True, exist_ok=True)
    blob = f.encrypt(json.dumps(value).encode("utf-8"))
    p = _entry_path(key)
    p.write_bytes(blob)
    os.chmod(p, 0o600)
    return {"key": key, "stored": True, "bytes": len(blob)}      # NOTE: never returns the value


def get_entry(key: str):
    """Decrypt+return a value, or None if absent. Returns None (not an error) on a decryption failure —
    a tampered/foreign blob is treated as absent, never surfaced."""
    f = _fernet()
    if f is None:
        raise PermissionError(_LOCKED)
    p = _entry_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(f.decrypt(p.read_bytes()).decode("utf-8"))
    except Exception:
        return None


def delete_entry(key: str) -> bool:
    p = _entry_path(key)
    if p.exists():
        p.unlink()
        return True
    return False


def keys() -> list[str]:
    """Entry names only — NEVER values. The stored filename is the sanitised key."""
    if not _DIR.exists():
        return []
    return sorted(p.stem for p in _DIR.glob("*.enc"))


def status() -> dict:
    return {"store": "intent-vault", "dir": str(_DIR), "unlocked": is_unlocked(),
            "entries": len(keys()), "encryption": "fernet-aes128-cbc+hmac" if is_unlocked() else "locked"}
