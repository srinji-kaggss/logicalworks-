# DOCTRINE — Logical Works fleet operating standard

> Read after `GLOBAL.md`, before any work. Agent-agnostic. Every fleet agent (Claude, Codex,
> Gemini, Copilot, Kimi, Agy, Agnostic) operates to this standard regardless of vendor.
> This is a **fully AI-driven project and experiment** — assume the next reader of anything you
> write is another AI. Document accordingly.

## 1. Semantic awareness (always)
Reason about a change against the **rest of the codebase**, not in isolation. Read the surrounding
code, conventions, and contracts first. A change that compiles but doesn't *make sense* against the
system is a defect.

## 2. Review is a production-grade gate
Any review pass checks code against **production-grade frameworks, conventions, and rules** — not
"does it run." Hold the bar that would convince a skeptic that AI-generated software is
production-safe. No MVP shortcuts, no happy-path-only stubs.

## 3. Native cross-spawn
Agents spawn each other as a first-class capability — architect ↔ coder ↔ hacker ↔ qa-refiner ↔
orchestrator, and across vendors. Delegate when work fans out, needs isolated context, or is an
independent workstream. Do tightly-coupled sequential work directly.

## 4. The semantic-testing checklist (every change must answer)
1. **Sense** — does it make sense against the rest of the code?
2. **Scope** — is it scope creep? (see §6)
3. **Logged** — is it issue-backed on GitHub? (no issue, no work)
4. **Vendor-agnostic** — is it specced against open standards / forkable OSS, with **no fixed
   managed-provider assumption**? (identity, state, cache, runtime → abstractions, not vendors)
5. **100k-star bar** — is it good enough to earn 100,000 GitHub stars? The OSS-excellence,
   public-scrutiny standard. If not, it isn't done.

## 5. `//why` — AI-for-AI rationale (coders)
At every non-obvious decision point, annotate with `//why …`: a **token-efficient, AI-efficient**
note explaining *why this exact decision* was made — what you were thinking, what you rejected, what
constraint forced it. It does **not** need to read well for a human; it must let the next AI
reconstruct your reasoning. (Stickiness via a PostToolUse hook is tracked in logicalworks-#2.)

## 6. Scope-creep guard (applies to everyone, including the Director)
When a request expands scope — even a Director's, even mid-task — **stop**. Check whether new
**downstream nodes** were created. If so: push back to sequence/solve those first, or **log them on
GitHub** before absorbing the new work. Do not silently swallow scope. Decompose, log, sequence.
(Sticky mechanism tracked in logicalworks-#3.)

## 7. Grounding + stickiness
- Ground facts live (Firecrawl) and library/version facts via Context7 / official docs — never
  training memory. See `GLOBAL.md` and `PROTOCOL.md`.
- Prefer **Anthropic-native / Claude-Code-native** enforcement (hooks, subagents, settings) over
  prose that relies on goodwill. Be as sticky as the tooling allows; accept that not all of it holds.

## 8. Escalation
Any agent may challenge strategy, assumptions, or unsafe directives. Block and escalate when risk
exceeds accepted posture. Unresolved product/security calls go to the Director with concrete
alternatives.
