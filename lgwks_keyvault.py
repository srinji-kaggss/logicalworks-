"""
lgwks_keyvault — macOS Keychain-backed secret resolver for runtime API keys (Issue #7).

The key NEVER lives in source, env files, logs, facts, or git. It lives in the macOS Keychain
(the OS WORM-ish secret store) and is read just-in-time at call sites. This is the same trust model
as lgwks_sign (the HMAC signing key) — generalised so any runtime secret (the cloud Tongue key today;
our own service key tomorrow) resolves through one seam.

Resolution order (first hit wins), fail-closed to None:
  1. env override   (e.g. OPENROUTER_API_KEY)  — for CI / ephemeral shells.
  2. macOS Keychain  generic-password, service = `lgwks:<name>`.
  3. None            → caller degrades (cloud Tongue off → local Ollama → deterministic skeleton).

Service mode (Director's note): when offered as a service we slot OUR key into the SAME Keychain
service name on the host that runs it — no code change, the resolver is the only seam.

Provision a key with no echo and no argv leak:
    python3 lgwks_keyvault.py set openrouter      # prompts twice in-terminal, never echoed
    python3 lgwks_keyvault.py check openrouter     # reports source only, never prints the secret
"""

from __future__ import annotations

import subprocess
import sys

# logical name -> (Keychain service id, env override var). Add new runtime secrets here only.
SECRETS: dict[str, tuple[str, str]] = {
    "openrouter": ("lgwks:openrouter-key", "OPENROUTER_API_KEY"),
}


def _env(var: str) -> str | None:
    import os
    v = os.environ.get(var)
    return v.strip() if v and v.strip() else None


def get_secret(name: str) -> tuple[str | None, str]:
    """Return (secret, source). source in {env, keychain, none}. Never logs the value."""
    spec = SECRETS.get(name)
    if not spec:
        return None, "none"
    service, env_var = spec
    env_val = _env(env_var)
    if env_val:
        return env_val, "env"
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip(), "keychain"
    except Exception:
        pass
    return None, "none"


def is_configured(name: str) -> bool:
    secret, _ = get_secret(name)
    return bool(secret)


def set_secret(name: str) -> int:
    """Store/update a secret via the OS prompt — no echo, no argv exposure (no -w VALUE on the cmdline).
    `security add-generic-password ... -w` (bare -w) makes Keychain prompt interactively."""
    spec = SECRETS.get(name)
    if not spec:
        print(f"unknown secret '{name}'. known: {', '.join(SECRETS)}", file=sys.stderr)
        return 2
    service, _ = spec
    # -U updates if it exists; bare -w triggers the no-echo interactive prompt (value never on argv/ps).
    proc = subprocess.run(
        ["security", "add-generic-password", "-U", "-a", "lgwks", "-s", service, "-w"],
        text=True,
    )
    if proc.returncode == 0:
        print(f"  stored '{name}' in Keychain ({service}). source resolves: keychain")
        return 0
    print(f"  failed to store '{name}' (security exit {proc.returncode})", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    if len(args) < 2 or args[0] not in ("set", "check"):
        print("usage: lgwks_keyvault.py {set|check} <name>\n  names: " + ", ".join(SECRETS),
              file=sys.stderr)
        return 2
    cmd, name = args[0], args[1]
    if cmd == "set":
        return set_secret(name)
    secret, source = get_secret(name)
    print(f"  {name}: {'configured' if secret else 'NOT configured'} (source: {source})")
    return 0 if secret else 1


if __name__ == "__main__":
    raise SystemExit(main())
