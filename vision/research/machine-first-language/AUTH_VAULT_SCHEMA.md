# Auth Vault — WORM for the bot, editable-by-supersede for the human

Version: `lgwks-auth-vault/1` · Issue #7 · grounds in ADR-061 (anti-self-hydration), ADR-064
(hash-chained telemetry), ADR-001 §7.

## Two stores

1. **Secrets — macOS Keychain** (human-editable via Passwords.app). Holds the actual tokens. The bot
   reads a token into process memory at fetch time via `security find-generic-password -w` and
   **never** writes it to a log, a fact, or git. Service label convention: `lgwks:<site>`.
   A separate `lgwks-bot.keychain-db` (scoped ACL) holds bot-only service auths.
2. **Auth-lock registry — append-only, single-writer, hash-chained** JSONL (gitignored; refs only,
   never secrets). The machine may only **append** `used` / `needs_auth` / `observed` and **read**
   `cred_ref`. The human edits *in effect* by appending `stale` / `supersede` events the bot is
   forbidden to author. → WORM for the machine, editable for the human; full history survives.

## Registry record (`lgwks-auth-vault/1`)

```jsonc
{
  "seq": 7,                                   // monotonic; chain index
  "ts": "2026-05-31T00:00:00Z",
  "event": "lock|used|needs_auth|observed|stale|supersede",
  "site": "scholar.google.com",
  "cred_ref": "keychain://lgwks:scholar",     // REFERENCE only — never the token
  "rate_from_auth": "10/min",                 // honored as a hard cap (L8)
  "legal_basis": "institutional subscription",
  "procured_by": "director",
  "scope": "research|non_commercial",
  "by": "sa-runner|director",                 // who authored the event
  "supersedes": "seq:5",                      // human edits append a supersede, never rewrite
  "prev_hash": "sha256(...)",                 // Hash(N) = SHA256(record_N.core + prev_hash + signer)
  "hash": "sha256(...)"
}
```

**Append rule (L5/L8):** `event ∈ {used,needs_auth,observed}` and `by == sa-runner` is the only
combination the bot may write. `event ∈ {lock,stale,supersede}` requires `by == director`. The bot
cannot author a `stale`/`supersede`/delete — that is the human authority that makes the log editable
without making it rewritable.

## SA-runner flow (each time a fetch hits an auth lock)

```
resolve cred_ref:  security find-generic-password -s lgwks:<site> -w   # token -> process only
  present & not stale -> use, throttle to rate_from_auth, append {used}
  missing | stale     -> DO NOT fetch -> append {needs_auth} -> surface to human
```

## Commands — `tools/lgwks-auth`

| command | effect | secret touched |
|---|---|---|
| `lgwks-auth add <site> --user U --rate 10/min --basis "..." [--bot]` | prompt for token (no echo) -> Keychain; append `lock` | stored in Keychain only |
| `lgwks-auth ls` | site · status · last-used · rate (existence-check, no `-w`) | never |
| `lgwks-auth stale <site>` | append `stale` (director authority) | no |
| `lgwks-auth check <site>` | bot path: is a usable, non-stale cred present? (boolean) | never prints token |
| *escape hatch* | open Passwords.app -> search `lgwks:` -> complete / rotate / delete | human, manually |

## Integrity modes (honest)
The chain HMACs each record under a signer from `lgwks_sign` (env `LGWKS_SIGNING_KEY` → Keychain
`lgwks:signing-key` → none):
- **keyed-*** (a secret key is present): tamper-EVIDENT. A rewriter cannot recompute hashes without
  the secret → adversarial rewrite is detected.
- **unanchored** (no key): a checksum only. Detects ACCIDENTAL corruption/truncation; does **NOT**
  detect an adversarial rewrite (the algorithm + old constant are public). Do not claim more.

## Invariants
- **I1** A token never appears in the registry, a log line, a fact envelope, or git. Only `cred_ref`.
- **I2** The registry is append-only + HMAC-chained. Tamper-evidence holds **only in keyed mode**;
  unanchored is corruption-detection only (see Integrity modes).
- **I3** The bot (`sa-runner`) cannot author `stale`/`supersede`/delete. NOTE: today this is a
  name-based check (`by` arg) — hardening item H1: `HUMAN_EVENTS` must require a human-held signing
  key / Touch ID, since the bot process supplies `by` itself.
- **I4** Honor `rate_from_auth` as a hard cap; never exceed the grant (L8). NOTE: the spine does not
  yet read the vault for the per-host floor (hardening item H5).
- **I5 (platform, not script):** full WORM needs OS-level append-only file mode + a real per-tool
  Keychain ACL (`-T /path/to/tool`, dedicated `lgwks-bot.keychain-db`) — the current `-T ""` is not a
  bot-only ACL (H2). A code convention + keyed HMAC is the interim; OS enforcement is the target.
