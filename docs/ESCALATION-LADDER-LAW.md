---
type: Law
title: Escalation Ladder Law
description: Status: active, non-negotiable
tags: [law]
timestamp: 2026-06-17T06:21:56-04:00
---

# Escalation Ladder Law

Status: active, non-negotiable

Every capability in the `lgwks` daemon MUST adhere strictly to the 3-Tier Escalation Ladder defined by the Trust Classes in `lgwks_model_mesh.py`.

## The Rule

1. **Gate 1: Symbolic / Deterministic** (e.g., `crwl`, `ctx7`, math/Python evaluation).
   - *Requirement*: Always executed FIRST. Fast, robust, and zero hallucinations.
2. **Gate 2: Machine Learning / Sensor** (e.g., lightweight classifiers, embeddings, `curl_cffi` impersonation).
   - *Requirement*: Executed ONLY if Gate 1 hits its absolute limit (e.g., bot wall, missing data).
3. **Gate 3: LLM / Generative** (e.g., Qwen3-VL Vision extraction, OLMo-32B text generation).
   - *Requirement*: Executed ONLY if Gate 2 fails completely (e.g., pure Canvas/SPA rendering requiring a screenshot and visual processing).

## The Sin
Jumping straight to LLM/Generative operations because they are "smarter" or "avoid DOM parsing" violates the hardware-first, zero-slop mandate. It slows down the agent exponentially and destroys deterministic reliability. 

Handoffs are ONLY used when the limit of the previous gate is hit, and NEVER before.
