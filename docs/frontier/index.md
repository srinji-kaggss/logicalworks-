# Frontier

## Reference

* [BUILD — End-to-End Entry Point](BUILD.md) — 3.
* [Frontier Program — End-to-End Map](MAP.md) — We are not building a better code generator — that road ends at the wall every frontier
* [Gaps — Substrate Unification (2026-06-09)](gaps-2026-06-09.md) — 3.
* [lgwks-human — daemon control surface (Rust TUI)](lgwks-human-control-surface.md) — The human→daemon control surface. A Rust TUI that observes daemon-events.db and steers the daemon via the canonical ops-daemon emit/enqueue write path. Documents the confirm-gate invariant, the WORK_KIND-vs-event-KIND split, and the affordance/input key routing.

## Spec

* [SPEC-00 — The Coherence Engine (more than a compiler)](spec-00-coherence-engine.md) — AI code generation already compiles.
* [SPEC-01 — The Verifier Oracle + the Comprehension Gate](spec-01-verifier-oracle.md) — One typed interface that all gates implement, so the Coherence Engine (spec-00), the existing
* [SPEC-02 — The Three Frontier Models + the AI-Lang Horizon](spec-02-three-models.md) — Sort by how checkable an output is — that property is the line where ML becomes AI.
* [SPEC-03 — Build Units (the implementation plan)](spec-03-build-units.md) — //why at every non-obvious decision; no shims/dead code; functions do one thing; comments say why.
* [SPEC-04 — The Claude + CLI Division of Labor](spec-04-claude-cli-division.md) — A tool call today costs: tokens to figure out the command, tokens for raw output flooding context,
