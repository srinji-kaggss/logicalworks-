# Firecrawl Agent Research Artifact — Interpretability + Observability + Competitors

> **Source:** firecrawl MCP agent (job `019efc19-8190-76c2-99a1-0f8e763e4a99`), 2026-06-24.
> **Method:** autonomous multi-source web research (the "300+ searches" pattern). This is the
> competitor research lgwks's own `research` command should eventually produce at this depth.
> **Status:** complete — 15 frontier checklist items, 12 competitors, 7 agent-prompt patterns.

## Key findings (condensed — full payload in the firecrawl job)

### ChatGPT Deep Research (o3) — the fan-out benchmark
- **Decomposition:** hierarchical via RL-trained o3 — broad question → 5-10 subtopics → 3-5 questions each → route to search/browse → collect evidence from **hundreds of sources in parallel** → synthesize.
- **Leveling:** helper model (GPT-4.1) collects preferences; expert = deeper/more sources/longer; beginner = simplified/fewer/visual.
- **Unhappy path:** ambiguous → helper asks clarifying questions; no results → broadens/rephrases; contradictory → notes disagreement, weighs credibility; incomplete → flags gaps.

### Claude Research (Multi-Agent) — the parallel-subagent pattern
- **Decomposition:** sectioning — lead agent decomposes into 3-5 **independent subtopics**, spawns subagents in parallel with **isolated context**. Breadth-first.
- **Unhappy path:** subagent finds nothing → reports to lead, lead re-tasks; conflicting → voting pattern across subagents.

### Cursor Agent Mode — the codebase-investigate-then-execute pattern
- **Decomposition:** task-based — investigate codebase → implementation plan → execute → verify. RL-trained Composer optimizes step ordering.
- **Leveling:** `.cursorrules` per project — beginner = more comments/simpler; expert = established patterns/less verbose.

### Firecrawl /agent — the describe-what-you-need pattern
- **Decomposition:** natural language → agent interprets intent → plans navigation → executes autonomously. No explicit decomposition layer (the LLM agent does it internally).
- **Unhappy path:** anti-bot → Fire Engine stealth; no render → wait for JS, retry; data not found → alternative selectors.

### LangSmith data model — RunTree hierarchy
- Root Run → Child Runs (chains/agents) → Leaf Runs (LLM calls, tool calls). Each run: run_id, parent_run_id, name, run_type (llm/chain/tool/retriever), start/end, inputs, outputs, error, tags, metadata.

### Langfuse data model — Session → Trace → Observation
- Three levels: Session (user interaction) → Trace (single execution) → Observation (steps). Observation types: Event, Span, Generation (LLM call with model, prompt, completion, tokens, cost). OTel integration.

### Arize Phoenix — OpenInference semantic conventions
- Span types: LLM, Retriever, Tool, Chain, Agent, Embedding, Reranker. OTel-aligned. Attributes: llm.model_name, llm.input_messages, llm.token_count.input/output. Built-in evals (LLM-as-judge, code-based, human).

### Braintrust — agent-first schema
- Emphasizes agent decision capture: tool_selection (which tool), tool_arguments, reasoning_steps, state_transitions, memory_operations. Selection_rationale (why this tool). Fallback_triggered. The richest agent-trajectory model.

### OpenLLMetry / OpenInference — the OTel standard
- Extends OpenTelemetry with LLM-specific attributes. Auto-instrumentation for 40+ frameworks. Sends to any OTel backend (Jaeger, Datadog, Phoenix). The interop standard.

## Frontier interpretability checklist (15 items, condensed)
1. Circuit-level interpretability (attribution graphs, SAEs, transcoders)
2. Attention pattern analysis (token-to-token heatmaps, head specialization)
3. Token attribution for agent decisions (Integrated Gradients, JacobianScope)
4. Chain-of-thought inspection (step classification, bad-thought detection)
5. Activation patching (causal intervention, clean vs corrupted runs)
6. Probing classifiers (linear probes on activations → semantic concepts)
7. Sparse autoencoders (TopK SAEs → interpretable features from superposition)
8. Cross-layer transcoders (CLTs → feature-level circuit tracing across model)
9. Mechanistic interpretability for code models (reverse-engineer neural nets)
10. Trajectory analysis for agent runs (thought-action-observation triples, efficiency metrics)
11. AHE 3-pillar observability (component, experience, decision)
12. Evidence corpus distillation from trajectories (Trace2Skill, PDI)
13. Feature attribution (SAE features → output causation, not just token attribution)
14. Decision observability: aggregate patterns across trajectories (SQL-queryable)
15. Revertible action space for harness components (file-level, version-controlled, rollback)

## Agent-prompt pattern permutations (7 flows)
1. ChatGPT: intent-clarify → decompose → parallel-search → synthesize → cite
2. Claude: lead-decompose → parallel-subagents → vote → synthesize
3. Cursor: investigate → plan → execute → verify → iterate
4. Firecrawl: describe-need → autonomous-navigate → extract → structure
5. SKILL.md: frontmatter → overview → prerequisites → steps → examples → troubleshoot
6. Sourcegraph: query → context-fetch (graph+embeddings) → generate with context
7. Hierarchical: strategic → tactical → operational → micro-steps (4-layer)