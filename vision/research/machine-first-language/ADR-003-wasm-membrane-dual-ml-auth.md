# ADR-003 — Endpoint shape, dual-ML governance, and native auth

Status: accepted (Director, 2026-06-01). Supersedes nothing; constrains ADR-002 (harness) and the
engine model in SPEC-lgwks-engine-v0 §2. Build sequence locked: eyes → data-boundary → Tier-E → grounding.

## D1 · The endpoint is a WASM container + frontend, not a CLI process

WASM has no subprocess and no native binaries — our entire capability model (shell out to the best
local tool: curl/crwl/pdftotext/playwright) **cannot run inside it**. This is not a blocker; it is the
membrane made physical:

- **Inside WASM** = pure reasoning, steering, membrane logic, the frontend/viewer. Sandboxed by the
  runtime — it *cannot* touch the world. The "reason free inside" wall is enforced by physics, not prose.
- **Outside, behind a host port** = search · fetch · browser · extract · auth become **services the core
  calls through a single gated host interface**. Every world-touching call crosses one audited boundary
  (the engine/port model, SPEC §2, taken to its end). "Act gated outside" = the host-interface ABI.

Consequence for all capability code from now on: stay behind a clean callable port (no hidden globals,
no direct world access from reasoning paths) so each becomes a host-interface service unchanged. //why
this is the native-enforcement win T6 asks for — the sandbox is the gate.

## D2 · Cheaper-model reasoning: move cognition out of generation

The proposer (Tier G) runs on free/cheap models; quality comes from the harness, not the weights
(DeepMind thesis). Levers, in priority: (1) cheap model drafts, tiny local Tier-E evaluator scores —
never burn a big model on verification; (2) thought-continuation schema kills re-derivation tokens;
(3) the cognition-log caches reasoning so it is never re-paid; (4) schema-constrained dense output, not
prose; (5) escalate to an expensive model only on a Tier-E low-confidence signal (speculative pattern).

## D3 · Dual ML — evolving + weight-locked (champion/challenger, AlphaZero-shaped)

Two running models per evaluator capability:
- **evolving** — learns online, drifts toward higher capability and opacity (the inflection march).
- **frozen** — a content-addressed safetensors snapshot at the last-trusted inflection point. The
  SHA-256 hash **is** the turn-back date. Serves two roles: (a) **drift oracle** — calibration
  divergence (ECE/Brier) of evolving-vs-frozen is the freeze trigger; (b) **fallback** — if the evolving
  model breaches the membrane, route to frozen and quarantine the delta.

Promotion gate: evolving proposes new weights → frozen-model + the evaluator + interpretability
(Captum/attention) must pass it before it becomes the new champion. Self-play against a frozen opponent
is exactly how AlphaZero reached superhuman capability while staying rollback-able. //why never a
blackbox you can't revert: every champion has a parent hash in the fact-log.

## D4 · Native auth / passkeys — orchestrate, never hold the secret (T0)

The most dangerous capability in the system; the honest architecture is the restraint:
- **Never touch a raw credential.** Passkeys are WebAuthn — origin-bound, phishing-resistant, and
  require user presence (Touch ID) by design. A tool *cannot* silently pass a passkey; refusing to fake
  that is the trustworthy answer, not a limitation to engineer around.
- The tool orchestrates auth through the **OS authenticator (Keychain / Secure Enclave) with per-use
  presence**, and holds the resulting **session** (never the secret) in the encrypted **intent-vault**.
- Every auth use is **capability-gated** (membrane outside wall), **origin-scoped**, **throttled**, and
  emits a **SOC2 audit entry** (who · origin · capability · decision). See AUTH_VAULT_SCHEMA.md.
- The existing browser `save_session()` seam is the consented path: the human logs in once in a headed
  window; we persist storage_state, never their password.

## Open obligations seeded here
- Eyes must expose a port boundary (D1) before WASM port — done in build #1.
- intent-vault (build #2) is the home for D4 sessions and D3 snapshot keys.
- Tier-E (build #3) is where D2's evaluator and D3's dual-model first ship.
