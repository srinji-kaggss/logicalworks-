# Governance Map (lgwks)

Single index for everything governance-shaped in this repo. If a governance
claim conflicts across files, `principles.md` dictates precedence.

## In this directory
| File | Purpose |
|------|---------|
| `principles.md` | Six-clause operational manifesto — who Logical Works exists for, what won't be built, how decisions are made. **Precedence root.** |
| `aup.md` | Acceptable Use Policy — businesses not served + request categories refused. |
| `aup-refusals.md` | One-line refusal summary (mirrors AUP). |
| `aup-refusals.jsonl` | Structured, append-only refusal log (operational). |

## Governance-shaped artifacts elsewhere (by design, indexed here)
| Path | What it is |
|------|------------|
| `docs/ADR-pipeline-001-tuning.md` | Architecture decision record (pipeline tuning). New ADRs: `docs/ADR-*.md`. |
| `spec/second-harness/` | Data/ingestion layer authority (v1.0) — owns its own decisions; see `CLAUDE.md` authority ladder. |
| `HARDEN-NOTES.md`, `HARDEN-NOTES-expression-v1.md` (root) | Hardening-phase review records. Kept at root because `cl-ideas` symlinks them. |
| `vision/prompts/_doctrine.md` | Cross-fleet agent doctrine (referenced by `logic-os-kernel` too). |

## Rules
- Decisions are append-only: supersede with a new record, never rewrite history.
- A spec without a status header (`draft | final | superseded-by:<path>`) is
  unratified — treat as opinion.
- `docs/SPEC-tier-e-machine-model-v1.md` is a historical draft (2026-06-02);
  verify against `spec/second-harness/` before building from it.
