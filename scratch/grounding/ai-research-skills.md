# Grounding: Orchestra-Research / AI-Research-SKILLs

META: repo=github.com/Orchestra-Research/AI-Research-SKILLs · stars≈9.2k · license=MIT · 98 skills / 23 categories · pinned-sha=28f2d29236f2bade2eb92cadb2585189589a5828 · accessed=2026-06-01
TAGLINE: "open-source skills library enabling AI agents to autonomously conduct AI research — from idea to paper"
NOTE: cloned via GitHub MCP (local `git clone` Bash denied in env). Mapped from README + 5 sampled SKILL.md + repo tree + LICENSE/CITATION/.claude-plugin.

## 1. REPO STRUCTURE + SKILL.md PACKAGING CONVENTION

### Top-level tree
```
.claude-plugin/marketplace.json   # Claude Code marketplace manifest (23 plugin entries, one per category)
.github/                          # CI: sync-skills.yml (→Orchestra marketplace), publish-npm.yml
anthropic_official_docs/          # vendored Anthropic skill best-practices (their stated authority)
demos/                            # curated demo gallery (autoresearch papers, eval/FAISS/quant demos)
docs/ (ROADMAP.md, skills.png, assets/)
packages/ai-research-skills/      # npm pkg @orchestra-research/ai-research-skills (installer CLI)
dev_data/ video-promo/
README.md CLAUDE.md CONTRIBUTING.md WELCOME.md CITATION.cff LICENSE package.json
0-autoresearch-skill/             # orchestrator (category 0)
01-model-architecture/ ... 22-agent-native-research-artifact/   # 22 domain categories
```
23 categories = `0-autoresearch-skill` + `01`..`22`. Each category dir holds N kebab-case skill subdirs.

### Skill on-disk layout (per README "Skill Structure")
```
skill-name/
  SKILL.md          # quick ref, 50-150 line target (actual 75-936; avg ~420)
  references/       # deep docs, "300KB+", one level deep only: README.md api.md tutorials.md
                    #   issues.md (real GitHub issues+fixes) releases.md file_structure.md
                    #   citation-workflow.md (paper-writing), review-dimensions.md (rigor), ara-schema.md ...
  scripts/          # optional helper scripts
  assets/           # optional templates/examples
  templates/        # (autoresearch) research-state.yaml, findings.md, research-log.md seeds
```
Progressive disclosure: SKILL.md is the loaded surface; `references/*` are load-on-demand, linked by relative markdown path. Self-imposed cap: references one level deep.

### SKILL.md frontmatter (EXACT — verified across transformer-lens, autoresearch, ara-compiler, ara-research-manager, ara-rigor-reviewer)
YAML block delimited by `---`:
```yaml
---
name: <kebab-case-id>                  # e.g. transformer-lens-interpretability, autoresearch, ara-rigor-reviewer
description: <third-person, 1-3 sentences>   # "Provides/Performs/Orchestrates/Compiles..." + explicit "Use when ..." trigger clause
version: <semver>                      # 1.0.0 / 3.0.0 etc
author: Orchestra Research
license: MIT
tags: [Title Case, Comma Separated]    # e.g. [Mechanistic Interpretability, TransformerLens, Activation Patching]
dependencies: [pkg>=x.y.z, ...]        # pip-style pins; [] or omitted when none
---
```
Conventions (from CONTRIBUTING/README/v1.6.0 notes): names kebab-case; descriptions third-person with a "Use when/after..." trigger; tags Title-Case; references one-level-deep.
Body convention (de facto template observed): H1 title → "When to Use" (+ "Consider alternatives when" cross-pointing to sibling skills) → Installation → Core Concepts → numbered Workflows (with copy-paste code + `[ ]` checklists) → "Common Issues & Solutions" (WRONG/RIGHT pairs) → key-class ref table → references/ table → external papers/docs → version notes.

### Install surfaces
- npm: `npx @orchestra-research/ai-research-skills` (interactive; auto-detects Claude Code, Hermes, OpenCode, Cursor, Gemini CLI, Qwen, Codex, OpenClaw; installs to `~/.orchestra/skills/` + per-agent symlinks, copy-fallback on Windows; subcmds: list/update/uninstall).
- Claude Code marketplace: `/plugin marketplace add orchestra-research/AI-research-SKILLs` then `/plugin install <category>@ai-research-skills` (per-category).
- AI cold-start: point agent at `WELCOME.md` / hosted welcome.md.

## 2. COMPLETE CATALOG (98 skills, by category)

### 0 · Autoresearch (1) — central orchestration layer
- autoresearch — autonomous end-to-end research via two-loop architecture (inner=experiment iteration, outer=synthesis); routes to all domain skills; runs continuously via Claude Code `/loop` or OpenClaw cron heartbeat; produces presentations + papers.

### 21 · Ideation (2)
- brainstorming-research-ideas — structured diverge-converge ideation, 10 complementary lenses for high-impact directions.
- creative-thinking-for-research — cognitive-science frameworks (bisociation, structure-mapping, constraint manipulation) for novel ideas.

### 20 · ML Paper Writing (2)
- ml-paper-writing — publication-ready papers for NeurIPS/ICML/ICLR/ACL/AAAI/COLM; LaTeX templates; **citation-verification workflow (never hallucinate refs)**; writing philosophy from Nanda/Farquhar/Gopen-Swan/Lipton/Perez.
- academic-plotting — publication-quality figures: Gemini-AI architecture diagrams + matplotlib/seaborn data charts with venue-specific styling.

### 01 · Model Architecture (5)
- litgpt — Lightning 20+ clean LLM impls + training recipes.
- mamba — state-space models, O(n), ~5x faster than Transformers.
- rwkv — RNN+Transformer hybrid, infinite context (Linux Foundation).
- nanogpt — Karpathy ~300-line educational GPT.
- torchtitan — PyTorch-native distributed training, Llama 3.1, 4D parallelism.

### 02 · Tokenization (2)
- huggingface-tokenizers — Rust BPE/WordPiece/Unigram, <20s/GB.
- sentencepiece — language-independent, T5/ALBERT, 50k sent/s.

### 03 · Fine-Tuning (4)
- axolotl — YAML-config fine-tuning, 100+ models.
- llama-factory — WebUI no-code fine-tuning.
- unsloth — 2x faster QLoRA.
- peft — LoRA/QLoRA/DoRA + 25+ PEFT methods.

### 04 · Mechanistic Interpretability (4)
- transformer-lens — Neel Nanda lib; HookPoints, activation caching, activation patching, circuit analysis.
- saelens — Sparse Autoencoder training/analysis for feature discovery + monosemanticity.
- pyvene — Stanford causal-intervention lib; declarative configs, DAS, activation patching.
- nnsight — remote interpretability via NDIF; run on 70B+ without local GPU.

### 05 · Data Processing (2)
- ray-data — distributed streaming ML data processing, GPU support.
- nemo-curator — GPU-accelerated curation, 16x faster dedup.

### 06 · Post-Training (8)
- trl-fine-tuning — HF Transformer RL (SFT/DPO/PPO).
- grpo-rl-training — Group Relative Policy Optimization on TRL (**flagged "gold standard"**, 569 lines).
- openrlhf — full RLHF pipeline, Ray + vLLM.
- simpo — Simple Preference Optimization, no reference model.
- verl — ByteDance HybridFlow RL; FSDP/Megatron + vLLM/SGLang.
- slime — THUDM Megatron+SGLang, powers GLM-4.x.
- miles — enterprise slime fork; FP8/INT4/speculative-RL for MoE.
- torchforge — Meta PyTorch-native RL; Monarch+TorchTitan+vLLM.

### 07 · Safety & Alignment (4)
- constitutional-ai — principle-driven self-improvement.
- llamaguard — input/output safety classifier.
- nemo-guardrails — programmable guardrails (Colang).
- prompt-guard — Meta 86M prompt-injection/jailbreak detector, 99%+ TPR, <2ms GPU.

### 08 · Distributed Training (6)
- megatron-core — NVIDIA 2B-462B param training, 47% MFU on H100.
- deepspeed — Microsoft ZeRO / 3D parallelism.
- pytorch-fsdp2 — FSDP v2 (`fully_shard`, DTensor).
- accelerate — HF 4-line distributed API.
- pytorch-lightning — Trainer-class training framework.
- ray-train — multi-node orchestration + HP tuning.

### 09 · Infrastructure (3)
- modal — serverless GPU cloud, Python-native, T4-H200.
- skypilot — multi-cloud orchestration, 20+ providers, spot recovery.
- lambda-labs — reserved/on-demand H100/A100, persistent FS.

### 10 · Optimization (6)
- flash-attention — 2-4x faster memory-efficient attention.
- bitsandbytes — 8/4-bit quantization.
- gptq — 4-bit PTQ, 4x mem, <2% acc loss.
- awq — activation-aware 4-bit quantization.
- hqq — Half-Quadratic Quant, no calibration data, multi-backend.
- gguf — llama.cpp K-quant format, CPU/Metal.

### 11 · Evaluation (3)
- lm-evaluation-harness — EleutherAI standard, 60+ tasks.
- bigcode-evaluation-harness — code-model bench: HumanEval, MBPP, MultiPL-E, pass@k.
- nemo-evaluator — NVIDIA enterprise, 100+ benchmarks across 18+ harnesses, multi-backend (Docker/Slurm/Lepton).

### 12 · Inference & Serving (4)
- vllm — high-throughput PagedAttention serving (**"production-ready"**).
- tensorrt-llm — NVIDIA fastest inference, 24k tok/s, FP8/INT4.
- llama-cpp — CPU/Apple-Silicon inference, GGUF.
- sglang — structured generation, RadixAttention, 5-10x faster for agents.

### 13 · MLOps (3)
- weights-and-biases — tracking, sweeps, artifacts, model registry.
- mlflow — registry, tracking, deployment, autologging.
- tensorboard — visualization, profiling, embeddings.

### 14 · Agents (4)
- langchain — agent framework, 500+ integrations, ReAct (**"production-ready"**).
- llamaindex — data framework for LLM apps, 300+ connectors, RAG-focused.
- crewai — multi-agent role-based orchestration.
- autogpt — autonomous agent platform, visual workflow builder.

### 15 · RAG (5)
- chroma — embedding DB, local/cloud.
- faiss — Facebook similarity search, billion-scale, GPU.
- sentence-transformers — 5000+ embedding models, multilingual.
- pinecone — managed vector DB, auto-scale, <100ms.
- qdrant — Rust vector search, hybrid + filtering.

### 16 · Prompt Engineering (4)
- dspy — declarative prompt programming + optimizers (Stanford NLP).
- instructor — structured outputs via Pydantic validation.
- guidance — constrained generation via regex/grammars (MS Research).
- outlines — FSM-based structured text, zero-overhead.

### 17 · Observability (2)
- langsmith — LLM tracing/eval/monitoring.
- phoenix — OSS AI observability, OpenTelemetry + LLM eval.

### 18 · Multimodal (7)
- clip — OpenAI vision-language, zero-shot classification.
- whisper — speech recognition, 99 languages.
- llava — vision-language assistant, image chat.
- stable-diffusion — text-to-image (Diffusers, SDXL, ControlNet).
- segment-anything — Meta SAM zero-shot segmentation.
- blip-2 — vision-language pretraining, Q-Former, captioning/VQA.
- audiocraft — Meta MusicGen/AudioGen text-to-music/sound.

### 19 · Emerging Techniques (6)
- moe-training — Mixture-of-Experts (DeepSpeed, Mixtral 8x7B).
- model-merging — TIES/DARE/SLERP via mergekit.
- long-context — RoPE/YaRN/ALiBi context extension to 128k.
- speculative-decoding — Medusa/Lookahead, 1.5-3.6x faster.
- knowledge-distillation — 70B→7B, MiniLLM, temperature scaling.
- model-pruning — Wanda/SparseGPT, 50% sparsity, <1% loss.

### 22 · Agent-Native Research Artifact (ARA) (3) — NEWEST, v1.6.0 Apr-2026
- ara-compiler — compiles ANY input (PDF/repo/logs/notes) → structured ARA: cognitive layer (claims/concepts/heuristics), physical layer (configs/code stubs), exploration DAG, grounded evidence. 4-stage epistemic CoT + coverage loop + Seal-L1 validation.
- ara-research-manager — post-task session epilogue; scans conversation history, extracts decisions/experiments/dead-ends/claims/heuristics/pivots into `ara/` with user/ai-suggested/ai-executed/user-revised provenance tags.
- ara-rigor-reviewer — ARA Seal Level 2 semantic epistemic review; scores 6 rigor dimensions, severity-ranked findings, Strong-Accept→Reject grade.
SOURCE: restructured from Orchestra-Research/Agent-Native-Research-Artifact-Init.

CATALOG SANITY: counts sum to 98 (1+2+2+5+2+4+4+2+8+4+6+3+6+3+4+4+5+4+2+7+6+3). README text inconsistently says 87/98 in places; 98 is current (v1.6.0).

## 3. RELEVANCE TAGGING BY USE

### (a) Research / grounding / citation / verification instrument  [HIGHEST relevance to jarvis]
- **autoresearch** — full orchestration template: structured workspace (research-state.yaml, findings.md, research-log.md, literature/, experiments/, to_human/), two-loop engine, git-as-preregistration ("lock protocol before run", confirmatory vs exploratory labels), continuous `/loop`/cron continuity, literature search (Exa MCP / Semantic Scholar / arXiv / CrossRef), HTML/PDF progress reporting.
- **ara-compiler** — input→falsifiable knowledge package; claims↔experiments↔evidence↔code cross-binding; anti-hallucination rules (exact numbers, "Not specified", no synthetic trace, evidence-limited wording, raw-vs-derived table separation).
- **ara-research-manager** — provenance recorder; user/ai-suggested/ai-executed/user-revised tags; exploration DAG with dead_end/decision/pivot node types; forensic claim→proof / heuristic→code / decision→evidence bindings.
- **ara-rigor-reviewer** — 6-dimension epistemic scoring (evidence relevance, falsifiability, scope calibration, argument coherence, exploration integrity, methodological rigor); severity taxonomy (critical/major/minor/suggestion); verbatim-evidence-span requirement; "no false grounding" rule.
- **ml-paper-writing** — citation-verification workflow (references/citation-workflow.md has Semantic Scholar API code); never-hallucinate-refs discipline.
- **brainstorming-research-ideas / creative-thinking-for-research** — hypothesis-generation lenses.
- (supporting) **langsmith / phoenix** — trace/eval instrumentation; **lm-evaluation-harness / nemo-evaluator** — verification harnesses.

### (b) Acquiring & understanding high-quality code at scale
- **ara-compiler** — ingests GitHub repos/code dirs/notebooks; prioritizes README→core-algo→configs→env; produces typed code stubs of the NOVEL contribution; grounds claims in actual code. (Closest fit to "understand code at scale".)
- **autoresearch** — `references/skill-routing.md` = a code/skill-discovery router across the whole library.
- **ara-research-manager** — extracts heuristics/code-refs from sessions; binds heuristic→file paths.
- Each domain skill bundles `references/file_structure.md` (codebase navigation) + `references/issues.md` (real GitHub issues) — a reusable convention for distilling a target codebase into agent-readable form.
- (none of the 98 is a dedicated large-scale code-corpus crawler/indexer — this is an adaptation gap.)

### (c) Training / evaluating / interpreting ML models
- Training: entire 01/03/06/08/10/19 categories (architecture, fine-tuning, post-training/RL, distributed, optimization/quant, MoE/merging/distill/prune). Key: peft, trl-fine-tuning, grpo-rl-training, deepspeed, pytorch-fsdp2, accelerate, megatron-core.
- Evaluating: **lm-evaluation-harness**, **bigcode-evaluation-harness** (code), **nemo-evaluator** (enterprise multi-harness). Plus mlops (wandb/mlflow/tensorboard) + observability (langsmith/phoenix).
- Data/infra around it: ray-data, nemo-curator, modal, skypilot, lambda-labs.

### (d) Mechanistic interpretability / "how the model is thinking"  [direct]
- **transformer-lens** — HookPoints, run_with_cache, activation patching/causal tracing, IOI circuit analysis, induction-head detection, direct logit attribution.
- **saelens** — SAE training for feature discovery / monosemanticity.
- **pyvene** — declarative causal interventions, DAS.
- **nnsight** — remote interp on 70B+ via NDIF.
- (whole category 04 is the answer here.)

## 4. REUSABLE AS-IS vs NEEDS-ADAPTATION (for: research co-processor + self-evolving ML evaluator)

REUSE AS-IS (conventions/specs, vendor-agnostic, MIT-clean):
- SKILL.md frontmatter + body template — directly adoptable packaging standard for our own skills/instruments.
- ARA artifact schema (logic/ src/ trace/ evidence/ + claims/experiments/heuristics/exploration_tree) — a ready ontology for a "research co-processor" memory; isomorphic to our State Fabric / ARA-style fact-log ambitions.
- Provenance tag set (user / ai-suggested / ai-executed / user-revised) — drop-in for our human-vs-AI attribution requirement (matches our memory-discipline + agent-output doctrine).
- ara-rigor-reviewer 6-dimension rubric + severity taxonomy + grade mapping — a near-complete spec for a "self-evolving ML evaluator's" epistemic gate (esp. falsifiability + no-false-grounding + verbatim-evidence-span = our no-gate-weakening posture).
- Exploration-tree node taxonomy (question/experiment/decision/dead_end/pivot) — reusable research-DAG model.
- autoresearch two-loop + git-as-preregistration discipline — adoptable workflow scaffold.
- mech-interp category — usable as-is for "how is the model thinking" probes (TransformerLens/SAELens/pyvene/nnsight).

NEEDS ADAPTATION:
- autoresearch continuity assumes Claude Code `/loop` or OpenClaw cron — must remap to our orchestrator/heartbeat substrate.
- Literature search hardwired to Exa MCP / Semantic Scholar / arXiv — swap to our web+docs tooling (crwl, ctx7, firecrawl) per our tooling memory.
- ara-compiler/rigor-reviewer run "artifact-only, no external fetch/exec" — our co-processor will want live verification (cross-source adversarial check), so verification layer must be extended beyond face-value.
- No code-corpus-scale acquisition skill exists — must build our own crawler/indexer; can reuse their references/{file_structure,issues,api}.md distillation pattern as the per-repo output schema.
- "Self-evolving" loop is external (community SkillEvolve meta-skill, separate repo) — not in this repo; we'd build our own skill-synthesis loop (their `autoskill` analog lives elsewhere/scientific-skills, not here).
- Skills are documentation+code-snippet bundles, NOT executable tools — they are agent context, not callable APIs. Our evaluator needs the executable layer underneath.
- Marketplace/npm installer assumes `~/.orchestra/skills/` global install — irrelevant to our embed-as-grounding use.

## 5. LICENSE + ATTRIBUTION

- **MIT License.** `LICENSE`: "Copyright (c) 2025 Claude AI Research Skills Contributors". Full permissive grant (use/copy/modify/merge/publish/sublicense/sell); only condition = retain copyright + permission notice in copies/substantial portions; provided "AS IS".
- README caveat: individual skills reference third-party libraries under **their own licenses** — per-library license check required before use of any wrapped tool (vLLM, Megatron, TRL, etc.).
- Citation requested (not legally required): CITATION.cff (cff-version 1.2.0, author "Orchestra Research", version 1.4.0) + BibTeX `@software{ai_research_skills, ... year=2025, url=github.com/orchestra-research/AI-research-SKILLs}`. GitHub "Cite this repository" supported.
- Attribution constraint summary: keep MIT notice on any reuse of their text/specs; cite the software if used in a publication; vet sub-library licenses independently. No copyleft, no commercial restriction.
- Acknowledgments credit: Claude Code, Skill Seeker (yusufkaraaslan/Skill_Seekers, automated doc scraping), and EleutherAI/HuggingFace/NVIDIA/Lightning/Meta/Anthropic.
