# OS Spec — compiled from the ping stream, rendered at draw.io fidelity

The inward twin of the world-map. World-map = *what's out there & who controls it*. OS Spec =
*what we therefore build, where we plug in, what it must comply with, and what it costs to run.*
It is **not authored** — it is **compiled** from the World-Map Notes (`../ARTIFACT_SCHEMA.md §A`)
by the Q13 pass. Fidelity bar: **draw.io / mxGraph XML** you can open and edit.

## Views (for now)
All four live as tabs in one file: `os-spec/os-spec.drawio` (mxfile, one `<diagram>` per tab).
1. **us↔world ERD** (`id=erd`) — our OS layers as entities on the left, world `node`s on the right,
   relations between them (`plugs_into·depends_on·gates·competes·controls`).
2. **architecture** (`id=arch`) — our OS internals: the 7 layers + their internal data flow
   (envelope → gate → tape → widget; ml/sovereignty/distribution as cross-cutting).
3. **compliance scopes** (`id=comp`) — regulatory regimes (`node`s, layer=regulation) mapped to the
   OS layers / data they touch, with the obligation in the edge label.
4. **compute requirements** (`id=cmp`) — per OS component: placement (on-device/cloud), workload,
   the metric that drives scaling. Table-style.
Roadmap (not now): feature-sets per app archetype (e.g. "what an email client needs"), threat map,
data-flow/DPIA overlay.

## The 7 OS layers (fixed entity set on the "us" side)
`protocol` (canvas-protocol envelopes) · `gate` (handoff allow/deny/escalate) · `tape` (append-only
event log) · `widget` (zones: caller/record/next-action/tools/governance/overlay) · `ml`
(prediction/orchestration) · `sovereignty` (E2EE, user-owned compute) · `distribution` (how it
reaches users: extension/native/web). These are stable cell ids: `os.<layer>`.

## Compile mapping (ping → diagram cell) — this is the compile step
| ping kind | becomes |
|--|--|
| world `node` | ERD right-side entity `w.<id>`; if `layer=regulation` also a `comp` regime cell |
| `edge` | ERD relation (label = `r`), source/target by referenced ids |
| `os_hook` | ERD edge `os.<tgt>`→`w.<world_ref>` (label = `tp`); arch annotation; carries `mech/lev/rk` in tooltip |
| `arch_directive` | arch-diagram node/annotation on `os.<tgt>`; appended to `backlog.md`; status drives color |
| `claim` (layer=regulation) | `comp` edge label (the obligation) + source tier in tooltip |
| `claim`/`os_hook` w/ compute hint | `cmp` table row (placement / workload / scaling driver) |
| `gap` | dashed "open question" cell on the relevant tab (signals incomplete) |

## Determinism (so re-compiles diff, not churn)
Cell ids derive from ping ids: world node `w.<ping.i>`, our layer `os.<layer>`, hook
`h.<ping.i>`, directive `d.<ping.i>`. Recompiling over the same notes yields byte-identical cells;
a `sup` (supersede) replaces the prior cell in place; new pings append. Same "diff don't re-emit"
rule as the ping stream. Layout: world nodes grouped by `layer` lane; our layers in a fixed column.

## arch_directive status lifecycle (shown as cell fill)
`proposed` (amber #FEF3C7) → `accepted` (emerald #ECFDF5) → `built` (solid #047857 text-white) →
`reversed` (strikethrough, grey) when its `fx` falsifier fires. Status lives in `backlog.md`
alongside the directive id; the compile reads it to color the arch cell.

## Honesty rule
Only draw what pings support. Unknowns render as **dashed "unverified"** cells, not omitted —
the gaps must be visible in the diagram, not hidden. An `arch_directive` with no `wy` evidence
refs is invalid and dropped.

## Files
- `os-spec.drawio` — the four-tab diagram (compiled artifact; open in draw.io / diagrams.net).
- `backlog.md` — the directive register (id · target · rec · priority · status · falsifier).
- (optional) `compute.json` — structured backing for the `cmp` tab if it outgrows the table.

The compile pass that maintains all of this is **Q13** in `../prompts/QUESTIONS.md`.
