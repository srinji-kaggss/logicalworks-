---
type: Handoff
title: Handoff 2026-06-25 — two-plane model layer landed + docs adopted OKF
description: What landed, and a deliberately paranoid map of the debt the next agent must distrust before trusting anything green.
tags: [handoff, model-layer, okf, debt, governance]
timestamp: 2026-06-25T00:00:00Z
---

# What landed this session

1. **Two-plane model layer (epic #335)** on `feat/two-plane-model-layer` — see
   [concepts/model-layer](/docs/concepts/model-layer.md). `lgwks_model_port` is the one
   selector across the locality axis; `lgwks_run.embed` no longer carries a model-id
   literal; the **hallucinated embed law** (`Qwen3.7-VL-Instruct`, a visual agent, not an
   embedder) was corrected to its source spec. Full suite **2291 pass / 0 genuine
   failures** (14 vault failures are a missing `cryptography` env dep — proven, not ours).
2. **Docs became an OKF Knowledge Bundle** — see
   [concepts/knowledge-format](/docs/concepts/knowledge-format.md). Generated +
   validated by [`scripts/gen_okf.py`](/scripts/gen_okf.py); a Keel `docs.okf` lane now
   gates conformance + freshness.
3. **Future PRD filed**: [prd/okf-autobundler](/docs/prd/okf-autobundler.md) — lgwks
   auto-*moves* files into OKF, flags dupes, no content edits.

# Be deeply concerned. This codebase rewards paranoia.

The Director's standard is **never satisfied with a world-class result — always
harden**. Adopt it. The following are not hypotheticals; each bit me or a predecessor
this month. Distrust green until you have re-run the thing yourself.

- **Green tests can hide a dead tool.** The suite runs with `LGWKS_NO_MODELS=1`, so the
  model/bot path agents actually use is *never exercised by CI*. `review` once hung in
  real use while the suite stayed green. When tests pass but a tool misbehaves, ask what
  the harness ENV disables, and reproduce as a cold agent. (See
  [reference: review hang](/docs/archive/) and the navmap staleness column.)
- **The law can be a lie.** `MESH_LAW` is **hand-transcribed**, and it was wrong:
  role=embed pinned a hallucinated `Qwen3.7-VL-8B-Instruct` that does not embed. The
  port asserted "LAW IS TRUTH" while running a different model. **Before trusting any
  pinned id, diff the law against its source spec.** Hand-maintained law is debt; the
  whole thesis is *schema/law-generated, not hand-authored* — MESH_LAW is the next
  thing that should be generated, not typed.
- **Duplicated-but-slightly-different == the bug.** Do not add a parallel path. There is
  one canonical primitive per concept (hashing, cosine, tokenizers, the model port, the
  state fabric). A second near-copy is the defect; collapse it, never grow it. The
  orchestration loops (#255) are still forked — that is open debt, not a pattern to copy.
- **God-functions remain.** `lgwks_substrate_run.build_run` (~471 lines), `lgwks_jarvis`
  (~420), research (~275). They work but are not elegant; decompose behind the existing
  seams when you touch them — do not bolt more on.
- **Root sprawl is a CONTRACT, not a mess.** The ~100 root `lgwks_*.py` are imported by
  name by the dispatcher. Do not "tidy" them into a package — it breaks the CLI and the
  cl-ideas symlinks. (See repo `CLAUDE.md`.)
- **Governance/generated files are not yours to hand-edit.** navmap README, OKF indexes,
  kernel ADRs — all generated. Edit the GENERATOR, re-run, commit the output. Find the
  source before touching anything that looks authoritative.
- **Verify against the right branch.** Triage findings against `main` (or the issue's
  target), not whatever feature branch you happen to stand on.

# What is still open (do not mistake "landed" for "done")

- **Aetherius** is a reserved slot only — no training. "Data is a whole workstream."
- **#222 stragglers**: `lgwks_embed_port` image/video store-path ids; `lgwks_map`,
  `lgwks_geoexpr`, `lgwks_score` still resolve outside the port.
- **MESH_LAW generation** (kill the hand-transcription class of bug at the root).
- **Orchestration fork collapse (#255)** — the agent/research loops are not yet routed
  through the one daemon form.
- **`lgwks research --quick` returned a planning round with zero evidence** this
  session (no fetch). Treat lgwks research output as untrusted until you confirm
  `has_evidence: true`; the dogfood gap is real (log it as CLI feedback).

# How to work here (the short version)

1. Read repo `CLAUDE.md`, then [docs/index.md](/docs/index.md) (the OKF bundle map),
   then the navmap, then the issue.
2. Reproduce the failure at the lowest layer before fixing; re-run that same layer after.
3. Run `python3 scripts/gen_okf.py --verify` and the Keel runner before claiming done.
   **Docs are updated before CI passes — that is now enforced, not optional.**
4. Claim only what a command you ran shows. Over-claiming is the same disease as a CI
   asserting coverage it never ran.
