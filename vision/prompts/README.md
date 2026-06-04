# prompts/ — Logical Works agent startup layer

Branch-independent, cross-repo context home for the fleet. The prompt bundle is still rooted at
`vision/prompts/`, but context wiring is now manifest-driven rather than dependent on machine-local
absolute symlinks.

| Path | What |
|------|------|
| `GLOBAL.md` | Agent-agnostic global prompt — mission + grounding/adversarial rules (LW-RS/1). |
| `_doctrine.md` | Fleet operating standard: semantic awareness, production-grade review, native cross-spawn, semantic-testing checklist (incl. the 100k-star bar), `//why`, scope-creep guard. |
| `agents/<vendor>.md` | Per-agent startup prompt (claude = orchestrator base; codex/gemini/copilot/kimi/agy/agnostic = peers). |
| `context/` | Symlinks to shared context (see below). |

## context/ symlinks
- `claims`, `artifacts` → **relative** in-repo (the `vision/claims/*.json` json layer + artifacts).
- `governance`, `AGENTS.md`, `roles` → resolved from `vision/prompts/context/manifest.json` against
  `LGWKS_FLEET_HOME` (default: `~/sales-landing-page`), then linked into `context/`.

## bootstrap + verification
- `python -m lgwks_agent_os bootstrap` refreshes `context/` from the manifest and writes
  `agent_cards.json`.
- `python -m lgwks_agent_os doctor` verifies startup prompt files, context links, role subagents,
  and agent-card presence.
- `.project/1/README.md` is the local workpad for Issue #1.

Tracked by logicalworks-#1. Sticky enforcement (the `//why` and scope-creep hooks) is logicalworks-#2 / #3.
