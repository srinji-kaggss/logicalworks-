# Concepts

## Concept

* [Escalation & Robustness — the tier ceiling and the boundedness invariant](escalation-robustness.md) — Codifies "don't use the LLM until truly needed" as a caller-set tier ceiling on the one escalation harness, and makes a no-model CI robust by proving every hang-class sink is bounded and fail-closed via Keel.
* [LGWKS OKF — the docs Knowledge Format (Google-OKF-inspired)](knowledge-format.md) — lgwks adopts Google Cloud's Open Knowledge Format for docs/; this disambiguates it from two same-named sibling artifacts.
* [Two-Plane Model Layer — one port, locality axis](model-layer.md) — lgwks_model_port is the one selector across a locality axis (local Mesh ⊕ cloud models.dev ⊕ reserved Aetherius), orthogonal to the trust-tier ladder.

## Plan

* [Pristine Codebase Program — Build Order (R3→R9), an executable playbook](pristine-build-order.md) — A sequential, fork-resolved playbook for an executing agent to de-slop lgwks milestone by milestone — each leaf with intent, the one canonical primitive, pre-decided forks, acceptance criteria, the Keel gate, and human-checkpoints where the agent must stop and check in with Opus before anything goes upstream.
* [The Pristine Codebase Program — de-slop lgwks to elegance](pristine-codebase-program.md) — A self-decomposing program that drives lgwks to a pristine state by reconstructing the original intent behind slop, collapsing it to one canonical primitive, and gating the result with Keel.
