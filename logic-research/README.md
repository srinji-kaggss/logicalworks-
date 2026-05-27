# Logic Research Vault — the Map of the Mountain

Goal: a truth-grounded map of how the internet + OS ecosystems work at scale, and where an
AI-native OS-layer (web + desktop app now; Apple-scale ecosystem later) plugs in as a new
primitive. Research fans out across models; Claude owns architecture + final synthesis.

Artifacts land in `artifacts/` using `ARTIFACT_SCHEMA.md` (the RAC). Prompts live in `prompts/`.

## The map = 5 tracks (each expandable)

| Track | What it maps | Primary model(s) |
|-------|--------------|------------------|
| **ecosystems** | Apple, Google, Microsoft as platform owners (meta-prompts self-decompose) | Gemini (facts), Kimi (global/super-app) |
| **stack** | The internet ground: transport/DNS/TLS/BGP, identity, distribution chokepoints, payments, cloud | Gemini |
| **ai-layer** | The new primitive: MCP/A2A, context/memory, on-device vs cloud inference, AI-native UX | Codex (prototypes), Claude |
| **wedge** | US: OS-as-layer architecture, the gate, the tape, sovereignty, anti-hack, ML core | **Claude only** |
| **strategy** | Moats, distribution physics, adoption, regulation, super-app precedents, our niche vs labs | ChatGPT, Kimi |

## Model routing (why each)
- **Claude Opus** — wedge architecture, security/gate threat-modeling, ML-layer design, and the **integrator** (final synthesis). Uses `~/ai-research-skills` (04/06/07/11/14/15) + thinking-skills.
- **Gemini Deep Research** — broad grounded surveys (stack truth, ecosystem facts). Saves Claude's tokens.
- **ChatGPT** — strategy, market sizing, moats, regulation.
- **Kimi 2.5 Cloud** — long global reads; super-app/ecosystem precedents (WeChat, Alipay, Jio, Yandex).
- **Codex** — implementation prototypes from spec (tape/CQRS, MCP/A2A gate).
- **Copilot** — in-repo scoped builds once we start ("build a bit rn").

Karpathy (`~/ai-research-skills/01-model-architecture/nanogpt`) grounds ML-layer fundamentals.
Build phase uses the **factory** skills (`specify-factory` → `implement-factory`).

## How to run
1. Open a model's file in `prompts/`. Paste its **PREAMBLE once** (carries the RAC format).
2. Fire its 30-40 word prompts. Save each result to `artifacts/<id>.md`.
3. When a wave is done, run the **integrator** prompt (in `prompts/claude-opus.md`) in Claude.

## How to EXPAND from here (the framework, not the whole mountain)
This vault is a seed, sized to finish inside budget. To grow it:
- Every artifact has `expand_axes`. Turn any axis into a new 30-40 word prompt using the same
  PREAMBLE, route it to the fitting model (facts→Gemini, global→Kimi, strategy→ChatGPT,
  code→Codex, architecture→Claude). Append the new artifact; the map deepens.
- The Apple/Google **meta-prompts** self-decompose — run them and they hand you the sub-prompts,
  so you never hand-author the sprawl.
- Re-run the integrator after each wave: it re-scores robustness per layer and re-issues the
  top-3 build-now tasks. That's your "point at the world and build a bit rn" loop.
