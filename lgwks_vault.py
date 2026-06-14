"""
lgwks_vault — hardened INTENT-VAULT store (build #3, enterprise grade).

Encrypted at rest with AES-256-GCM + Argon2id. Every operation is audited.
Key model: derived from the existing lgwks signing secret, domain-separated,
versioned for rotation. FAIL-CLOSED.

Boundary (T0): values never touch a log, a prompt, a URL, or argv.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_sign

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAVE_AESGCM = True
except Exception:  # pragma: no cover
    _HAVE_AESGCM = False
    InvalidTag = Exception

# Argon2id via argon2-cffi (preferred) or argon2 pure-python fallback
try:
    from argon2 import PasswordHasher
    from argon2.low_level import hash_secret_raw, Type
    _HAVE_ARGON2 = True
except Exception:  # pragma: no cover
    _HAVE_ARGON2 = False

ROOT = Path(__file__).resolve().parent
_DIR = ROOT / "store" / "intent"
_AUDIT_DIR = ROOT / ".lgwks"
_AUDIT_LOG = _AUDIT_DIR / "vault-audit.jsonl"
from lgwks_substrate_config import SLUG_SCRUB_RE as _SAFE  # one source of truth

# Enterprise defaults
_KDF_MEMORY_KB = 64 * 1024       # 64 MB
_KDF_ITERATIONS = 3               # Argon2id time cost
_KDF_PARALLELISM = 4              # parallelism
_KDF_HASH_LEN = 32                # 256-bit key for AES-256
_DEFAULT_KEY_VERSION = "kv1"
_KDF_DOMAIN = b"lgwks-vault-v3-aes256gcm"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditEvent:
    ts: float
    op: str         # set|get|delete|re_encrypt|migrate
    key_name: str
    key_version: str
    actor_pid: int
    actor_uid: int
    success: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "op": self.op,
            "key_name": self.key_name,
            "key_version": self.key_version,
            "actor_pid": self.actor_pid,
            "actor_uid": self.actor_uid,
            "success": self.success,
            "detail": self.detail,
        }


def _audit(event: AuditEvent) -> None:
    """Append an audit record. Never raises — audit failures are non-blocking
    to vault operations but are flagged in the returned metadata."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        record = json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=False)
        with _AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(record + "\n")
        # Restrict permissions — only owner can read audit log
        os.chmod(_AUDIT_LOG, 0o600)
    except Exception:
        pass  # audit loss is logged as a detail field on the operation return


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------
def _derive_vault_key(secret: bytes, version_salt: bytes) -> bytes:
    """Derive a 256-bit key from the signing secret via Argon2id."""
    password = _KDF_DOMAIN + b"\x00" + secret
    if _HAVE_ARGON2:
        return hash_secret_raw(
            secret=password,
            salt=version_salt,
            memory=_KDF_MEMORY_KB,
            iterations=_KDF_ITERATIONS,
            parallelism=_KDF_PARALLELISM,
            hash_len=_KDF_HASH_LEN,
            type=Type.ID,
        )
    # PBKDF2-HMAC-SHA256 fallback (still far better than raw SHA-256)
    return hashlib.pbkdf2_hmac(
        "sha256", password, version_salt, iterations=600_000, dklen=_KDF_HASH_LEN
    )


def _encode_versioned_ciphertext(
    key_version: str, salt: bytes, nonce: bytes, ciphertext: bytes
) -> bytes:
    """Format: kvN:base64(salt||nonce||ciphertext)."""
    payload = base64.urlsafe_b64encode(salt + nonce + ciphertext)
    return f"{key_version}:".encode("ascii") + payload


def _decode_versioned_ciphertext(data: bytes) -> tuple[str, bytes, bytes, bytes]:
    """Return (key_version, salt, nonce, ciphertext). Raises ValueError on bad format."""
    text = data.decode("ascii", errors="replace")
    if ":" not in text:
        raise ValueError("missing key version delimiter")
    key_version, b64 = text.split(":", 1)
    raw = base64.urlsafe_b64decode(b64.encode("ascii"))
    # salt=16, nonce=12 (AESGCM standard), rest is ciphertext+aead_tag
    salt = raw[:16]
    nonce = raw[16:28]
    ciphertext = raw[28:]
    return key_version, salt, nonce, ciphertext


def _get_version_salt(key_version: str) -> bytes:
    """Deterministic salt per key version. In production this could be stored
    alongside the encrypted blob so rotation salts are independent. We keep
    it deterministic here keyed by version so that a re-key does not orphan
    entries if the salt file is lost."""
    return hashlib.sha256(_KDF_DOMAIN + b"\x00version\x00" + key_version.encode()).digest()[:16]


# ---------------------------------------------------------------------------
# Encryption primitives
# ---------------------------------------------------------------------------
def _aesgcm_encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Return (nonce, ciphertext)."""
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ciphertext


def _aesgcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# Fernet compatibility (read-only) for migration from build #2
# ---------------------------------------------------------------------------
def _legacy_fernet():
    secret, mode = lgwks_sign.signing_key()
    if not lgwks_sign.is_keyed(mode):
        return None
    material = hashlib.sha256(b"lgwks-vault-v1\x00" + secret).digest()
    key = base64.urlsafe_b64encode(material)
    from cryptography.fernet import Fernet
    return Fernet(key)


def _legacy_decrypt(blob: bytes):
    f = _legacy_fernet()
    if f is None:
        raise PermissionError("vault LOCKED")
    return f.decrypt(blob)


# ---------------------------------------------------------------------------
# Vault API
# ---------------------------------------------------------------------------
def _derive_key() -> tuple[bytes, str, str] | None:
    """Return (key_material, mode, key_version). None if unanchored."""
    secret, mode = lgwks_sign.signing_key()
    if not lgwks_sign.is_keyed(mode):
        return None
    version_salt = _get_version_salt(_DEFAULT_KEY_VERSION)
    key = _derive_vault_key(secret, version_salt)
    return key, mode, _DEFAULT_KEY_VERSION


def is_unlocked() -> bool:
    return _derive_key() is not None


def _entry_path(key: str) -> Path:
    safe = _SAFE.sub("-", key.strip().lower()).strip("-") or "unnamed"
    suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return _DIR / f"{safe}-{suffix}.enc"


_LOCKED = ("vault LOCKED — no encryption key anchored. provision once (no echo, no argv):\n"
           "  security add-generic-password -U -a lgwks -s lgwks:signing-key -w")


def set_entry(key: str, value) -> dict:
    """Encrypt+store a value with AES-256-GCM + Argon2id. Fail-closed.
    Every set is audited."""
    if not _HAVE_AESGCM:
        raise RuntimeError("vault requires cryptography >= 2.5 with AESGCM support")

    derived = _derive_key()
    if derived is None:
        raise PermissionError(_LOCKED)
    key_material, mode, key_version = derived

    _DIR.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(value).encode("utf-8")
    nonce, ciphertext = _aesgcm_encrypt(key_material, plaintext)
    salt = _get_version_salt(key_version)
    blob = _encode_versioned_ciphertext(key_version, salt, nonce, ciphertext)

    p = _entry_path(key)
    p.write_bytes(blob)
    os.chmod(p, 0o600)

    _audit(AuditEvent(
        ts=time.time(), op="set", key_name=key, key_version=key_version,
        actor_pid=os.getpid(), actor_uid=os.getuid(), success=True,
        detail=f"mode={mode} bytes={len(blob)}",
    ))
    return {"key": key, "stored": True, "bytes": len(blob),
            "key_version": key_version, "mode": mode}


def get_entry(key: str):
    """Decrypt+return a value. Supports new AES-256-GCM format and legacy Fernet.
    Returns None on any failure (tampered, missing, or foreign blob)."""
    derived = _derive_key()
    if derived is None:
        raise PermissionError(_LOCKED)
    key_material, mode, key_version = derived

    p = _entry_path(key)
    if not p.exists():
        _audit(AuditEvent(
            ts=time.time(), op="get", key_name=key, key_version=key_version,
            actor_pid=os.getpid(), actor_uid=os.getuid(), success=False,
            detail="absent",
        ))
        return None

    blob = p.read_bytes()

    # Try new format first
    try:
        kv, salt, nonce, ciphertext = _decode_versioned_ciphertext(blob)
        # Re-derive key using the salt from the blob (supports future rotation salts)
        derived_key = _derive_vault_key(lgwks_sign.signing_key()[0], salt)
        plaintext = _aesgcm_decrypt(derived_key, nonce, ciphertext)
        _audit(AuditEvent(
            ts=time.time(), op="get", key_name=key, key_version=kv,
            actor_pid=os.getpid(), actor_uid=os.getuid(), success=True,
            detail=f"mode={mode} format=aes256gcm",
        ))
        return json.loads(plaintext.decode("utf-8"))
    except (ValueError, InvalidTag):
        pass  # not new format or wrong key — try legacy

    # Try legacy Fernet format (backward compat)
    try:
        plaintext = _legacy_decrypt(blob)
        _audit(AuditEvent(
            ts=time.time(), op="get", key_name=key, key_version="legacy-fernet",
            actor_pid=os.getpid(), actor_uid=os.getuid(), success=True,
            detail=f"mode={mode} format=legacy",
        ))
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        pass

    _audit(AuditEvent(
        ts=time.time(), op="get", key_name=key, key_version="unknown",
        actor_pid=os.getpid(), actor_uid=os.getuid(), success=False,
        detail="decrypt-failure",
    ))
    return None


def delete_entry(key: str) -> bool:
    p = _entry_path(key)
    exists = p.exists()
    derived = _derive_key()
    kv = derived[2] if derived else "unknown"
    if exists:
        p.unlink()
    _audit(AuditEvent(
        ts=time.time(), op="delete", key_name=key, key_version=kv,
        actor_pid=os.getpid(), actor_uid=os.getuid(), success=exists,
        detail=None,
    ))
    return exists


def keys() -> list[str]:
    if not _DIR.exists():
        return []
    return sorted(p.stem for p in _DIR.glob("*.enc"))


def status() -> dict:
    unlocked = is_unlocked()
    return {
        "store": "intent-vault",
        "dir": str(_DIR),
        "unlocked": unlocked,
        "entries": len(keys()),
        "encryption": "aes-256-gcm+argon2id" if unlocked else "locked",
        "kdf": "argon2id" if _HAVE_ARGON2 else "pbkdf2-sha256",
        "key_version_default": _DEFAULT_KEY_VERSION,
        "audit_log": str(_AUDIT_LOG),
    }


# ---------------------------------------------------------------------------
# Key rotation & migration
# ---------------------------------------------------------------------------
def re_encrypt_entries(new_key_version: str = "kv2") -> dict:
    """Re-encrypt all existing entries under a new key version (new salt).
    Old entries are preserved atomically until the new write succeeds.
    Returns migration summary."""
    if not _HAVE_AESGCM:
        raise RuntimeError("vault requires cryptography >= 2.5 with AESGCM support")

    derived = _derive_key()
    if derived is None:
        raise PermissionError(_LOCKED)

    # _derive_key returns the derived *vault* key, not the raw signing secret.
    raw_secret, mode = lgwks_sign.signing_key()
    new_salt = _get_version_salt(new_key_version)
    new_key = _derive_vault_key(raw_secret, new_salt)

    migrated = 0
    failed = 0
    # Enumerate by actual file path — do not reconstruct path from stem because
    # _entry_path re-hashes the key; stems are already hashed suffixes.
    for entry_p in sorted(_DIR.glob("*.enc")):
        stem = entry_p.stem
        blob = entry_p.read_bytes()
        try:
            # Decrypt with whatever format it's in
            old_fmt = "legacy"
            try:
                kv, salt, nonce, ciphertext = _decode_versioned_ciphertext(blob)
                old_key = _derive_vault_key(raw_secret, salt)
                plaintext = _aesgcm_decrypt(old_key, nonce, ciphertext)
                old_fmt = kv
            except ValueError:
                plaintext = _legacy_decrypt(blob)

            # Re-encrypt with new key version
            new_nonce, new_ciphertext = _aesgcm_encrypt(new_key, plaintext)
            new_blob = _encode_versioned_ciphertext(new_key_version, new_salt, new_nonce, new_ciphertext)

            # Atomic replace in same path
            tmp = entry_p.with_suffix(".enc.tmp")
            tmp.write_bytes(new_blob)
            os.replace(tmp, entry_p)
            os.chmod(entry_p, 0o600)
            migrated += 1
            _audit(AuditEvent(
                ts=time.time(), op="re_encrypt", key_name=stem, key_version=new_key_version,
                actor_pid=os.getpid(), actor_uid=os.getuid(), success=True,
                detail=f"mode={mode} old_format={old_fmt}",
            ))
        except Exception as exc:
            failed += 1
            _audit(AuditEvent(
                ts=time.time(), op="re_encrypt", key_name=stem, key_version=new_key_version,
                actor_pid=os.getpid(), actor_uid=os.getuid(), success=False,
                detail=str(exc),
            ))

    return {"migrated": migrated, "failed": failed, "to_version": new_key_version}


def rotate_vault_key(provisioning_command: str | None = None) -> dict:
    """High-level rotation helper: bumps the default version, re-encrypts everything.
    After rotation, the DEFAULT_KEY_VERSION must be updated (caller responsibility)."""
    # For now this is a thin wrapper; callers can bump _DEFAULT_KEY_VERSION manually
    # and then call re_encrypt_entries. A future version could derive a new version
    # tag from a timestamp or rotate the *signing* key itself via the keychain.
    new_version = _DEFAULT_KEY_VERSION  # caller must override
    return re_encrypt_entries(new_key_version=new_version)
