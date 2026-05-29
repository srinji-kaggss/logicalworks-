# prompts/ — Logical Works agent startup layer

Branch-independent, cross-repo context home for the fleet. Read by absolute path
(`~/logicalworks-/vision/prompts/…`) so every agent worktree sees it regardless of its branch.

| Path | What |
|------|------|
| `GLOBAL.md` | Agent-agnostic global prompt — mission + grounding/adversarial rules (LW-RS/1). |
| `_doctrine.md` | Fleet operating standard: semantic awareness, production-grade review, native cross-spawn, semantic-testing checklist (incl. the 100k-star bar), `//why`, scope-creep guard. |
| `agents/<vendor>.md` | Per-agent startup prompt (claude = orchestrator base; codex/gemini/copilot/kimi/agy/agnostic = peers). |
| `context/` | Symlinks to shared context (see below). |

## context/ symlinks
- `claims`, `artifacts` → **relative** in-repo (the `vision/claims/*.json` json layer + artifacts).
- `governance`, `AGENTS.md`, `roles` → **absolute** into `~/sales-landing-page` (the role contract +
  governance). Absolute symlinks are **machine-local** by design — they match the ecosystem's
  `~/logicalworks-` / `~/sales-landing-page` single-dev path convention. On another machine, repoint
  them (or switch to a manifest — see logicalworks-#1).

Tracked by logicalworks-#1. Sticky enforcement (the `//why` and scope-creep hooks) is logicalworks-#2 / #3.
