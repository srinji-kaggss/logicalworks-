---
type: Concept
title: LGWKS OKF — the docs Knowledge Format (Google-OKF-inspired)
description: lgwks adopts Google Cloud's Open Knowledge Format for docs/; this disambiguates it from two same-named sibling artifacts.
tags: [concepts, okf, knowledge, docs, context-discipline]
timestamp: 2026-06-25T00:00:00Z
---

# What this is

`docs/` is a **Knowledge Bundle** in the **Open Knowledge Format (OKF)** — a
directory of markdown *concepts*, each carrying YAML frontmatter, cross-linked by
plain markdown links, with `index.md` files for progressive disclosure. It is
**generated and validated** by [`scripts/gen_okf.py`](/scripts/gen_okf.py), never
hand-curated — the same "generated from source, cannot rot" discipline as the
[navmap](/docs/navmap/README.md).

# The lineage (read this — it kills a real context blur)

Three distinct artifacts have collided on the acronym **OKF**. They are *siblings*,
not the same thing. An agent that conflates them will reason wrongly. Hold them apart:

## 1. Google OKF — **Open** Knowledge Format  (the standard we adopt here)
- Published by Google Cloud, **v0.1, 2026-06-12**. Spec:
  `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md`.
- A vendor-neutral markdown spec for **curated knowledge that AI agents consume**:
  a directory of markdown files with YAML frontmatter whose **only required field is
  `type`**; nested folders; reserved `index.md` (progressive disclosure) and `log.md`
  (history); ordinary markdown links form an untyped knowledge graph.
- **This is what `docs/` IS.** "Structure the codebase in OKF format" = this.

## 2. Browser engine OKF — **Optimized** Knowledge Format  (a sibling, different job)
- Lives in `~/next-gen-browser-engine` (ADR-002 there). Serializes **live web-page
  state** into a token-efficient semantic XML subset with spatial bounding boxes
  (~90% token reduction), as a *derived human-readable lens over a Braid/CID anchor*.
- Same acronym, **different artifact**: it represents a *page*, not a knowledge corpus.
  We keep its wording (it predates and earned it); it is **OKF-inspired in spirit**
  (derived lens, not source of truth; token-efficient; content-addressed identity).

## 3. lgwks research "OKF artifact"  (an internal output contract)
- `lgwks_research.py`: "all tiers emit the SAME OKF artifact". This is the
  **provenance-uniform research output** — every reasoning tier (Math/ML/Model) emits
  one shaped artifact. Historically borrowed the acronym; treat it as the *research
  output* meaning, not the doc-bundle standard and not the page lens.

# Why we adopt #1 for docs

The Director's standing axiom — *almost nothing is hand-maintained; everything is
schema/law-generated; kill context blur* — is exactly OKF's value proposition:

- **Self-describing.** Every doc declares its `type`/`title`/`description`; agents
  route and filter without bespoke parsing.
- **Progressive disclosure.** `index.md` lets an agent (or the lgwks subconscious /
  JSONL tail) see what exists before spending tokens opening files — the "low-level
  performance boost" observed on the browser repo, generalized to all docs.
- **Permissive consumption (§9).** Missing optional fields, unknown types, broken
  links are tolerated — the bundle stays useful as it grows and is partly
  agent-generated.
- **Diffable, portable, tool-free.** `cat` to read, `git clone` to ship.

# Two-way hardening — what each side does better (incorporate BOTH)

OKF and lgwks each carry ideas the other lacks. We adopt OKF's structure *and* keep
our strengths as **producer extensions** (OKF §4.1 explicitly permits extra
frontmatter keys; consumers must tolerate them). Neither replaces the other.

## What OKF gives us that we lacked (adopt verbatim)
- **Standardized, required `type`** on every concept → uniform routing/filtering.
- **Concept-ID = file path** (minus `.md`) → a stable, tool-free address.
- **Progressive disclosure via `index.md`** → an agent sees the map before spending
  tokens on bodies (the measured perf win, generalized to all docs).
- **`log.md` history + `# Citations`** conventions → provenance lives in-band.
- **Permissive consumption (§9)** → missing fields / unknown types / broken links are
  *tolerated*, so the bundle survives growth and partial agent-generation.
- **Bundle = unit of distribution** → `git clone` ships knowledge; no registry.

## What lgwks does that OKF omits (keep as producer extensions / siblings)
- **Content-addressed identity (CID).** OKF identity is a *path*, which breaks on
  move. Our substrate identity is a BLAKE3 CID that survives moves/renames. Extension
  field: `cid:` — the path is the human handle, the CID is the durable identity.
- **Generated-not-authored.** OKF is silent on authorship; we **generate** the bundle
  from source (`gen_okf.py`, like `gen_navmap.py`) so it cannot rot. Extension marker:
  generated files carry a "do not hand-edit" banner.
- **Staleness + ownership.** The navmap tracks `staleness`/`owning_issue` per module;
  docs can carry the same. Extension fields: `staleness:`, `owning_issue:`.
- **Provenance tiers.** The research "OKF artifact" stamps WHO produced reasoning
  (Math/ML/Model). Extension field: `provenance:`.
- **Two knowledge graphs, one discipline.** OKF is the *docs* graph; the
  [navmap](/docs/navmap/README.md) is the *code* graph (deps/used_by/staleness). Both
  are generated, queryable, agent-first — the docs bundle links into the navmap.

**Reserved producer-extension keys** (tolerated by §9, meaningful to lgwks consumers):
`cid`, `staleness`, `owning_issue`, `provenance`, `okf_version`.

# Conformance (what the CI gate enforces)

A bundle is OKF v0.1 conformant iff every non-reserved `.md` has a parseable YAML
frontmatter block with a **non-empty `type`**, and reserved files (`index.md`,
`log.md`) follow their structure. Enforced by `python3 scripts/gen_okf.py --check`.
Regenerate with `--write`.

# Citations

[1] [Google Cloud — How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
[2] [OKF SPEC v0.1 — GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
[3] Browser engine ADR-002 (Optimized KF as derived lens) — `~/next-gen-browser-engine/docs/ADR.md`
