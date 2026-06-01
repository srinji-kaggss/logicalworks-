"""
lgwks_sign — keyed integrity for the run log, the vault chain, and gate verdicts (Issue #7).

Fixes the C1 root cause: the chain/verdict integrity used a PUBLIC constant signer, so any rewriter
who read the source could recompute every hash → no tamper-evidence at all. Here integrity is an
HMAC under a SECRET key that never lives in source:

  - key source order: env LGWKS_SIGNING_KEY  →  macOS Keychain item `lgwks:signing-key`  →  none.
  - with a key  ("keyed-*")     → HMAC is unforgeable without the secret: real tamper-evidence.
  - without a key ("unanchored") → degrades to a documented checksum: detects ACCIDENTAL corruption
    only, NOT an adversarial rewrite. The mode is surfaced so no caller can claim more than it has.

Provision the key once:  security add-generic-password -U -s lgwks:signing-key -w   (prompts; no echo)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess

_UNANCHORED = b"local-unanchored"


def signing_key() -> tuple[bytes, str]:
    """Return (key, mode). mode in {keyed-env, keyed-keychain, unanchored}."""
    env = os.environ.get("LGWKS_SIGNING_KEY")
    if env:
        return env.encode("utf-8"), "keyed-env"
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", "lgwks:signing-key", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().encode("utf-8"), "keyed-keychain"
    except Exception:
        pass
    return _UNANCHORED, "unanchored"


def is_keyed(mode: str) -> bool:
    return mode.startswith("keyed")


def mac(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(payload: str, tag: str, key: bytes) -> bool:
    return hmac.compare_digest(mac(payload, key), tag)
