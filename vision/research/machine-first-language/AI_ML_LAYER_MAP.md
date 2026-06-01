# AI/ML Layer Map — token, blackbox, attention, bias, intent

Project: `ai-ml-layers`  
Goal: make the Machine strong enough to research itself: distinguish AI from ML, strip human/AI/prompt
biases, and condense intent into a replayable chain that can drive workers.

## 0. Thesis

ML is the weight-changing substrate. AI is the harnessed behavior that emerges when learned models are
put inside a goal loop with memory, tools, critique, and action.

```text
data -> tokens/features -> embeddings -> attention/sequence mixer -> weights -> logits/actions
     -> harness -> memory -> tools -> critique -> next command -> updated corpus -> future weights
```

The difference is not mystical. It is layering:

- **ML**: learn parameters from examples.
- **Transformer ML**: map token histories through attention + MLP blocks into next-token logits.
- **Assistant AI**: transformer + instruction hierarchy + retrieval + tool-use + safety gates.
- **Machine**: assistant + deterministic orchestrator + project chain + vector vault + promotion/rollback.

The Machine should be less like a chatbot and more like a clockwork lab: whimsical at the surface,
mathematical underneath.

## 1. Layers

| Layer | Unit | Blackbox Risk | Machine Countermeasure |
| --- | --- | --- | --- |
| L0 data | source records | selection bias, licensing ambiguity | source ledger, license basis, provenance |
| L1 token/features | token IDs, chunks, AST/text spans | tokenizer artifacts, chunk boundary distortion | dual chunking, file/path provenance |
| L2 embeddings | vectors | semantic collapse, lexical collision | deterministic + semantic embeddings side-by-side |
| L3 attention | Q/K/V, heads, attention pattern | spurious attention, attention-as-explanation fallacy | attention probes as weak evidence only |
| L4 weights | parameters, adapters, rank updates | learned bias, spurious correlations | held-out eval + rollback |
| L5 logits/actions | next token, command candidate | prompt injection, tool misuse | closed command schema + approval gate |
| L6 harness | loop, workers, budgets | runaway search, duplicated work | worker leases, token ledger, stop rules |
| L7 memory | chain + vector vault | memory bloat, false continuity | HMAC chain, summaries, stable chain head |
| L8 self-learning | champion/challenger | drift, overfit, reward hacking | calibration gate, contradiction probes |

## 2. What "attention + weight + bias + intent" means for lgwks

The orchestrator should represent every cycle as a condensed chain:

```json
{
  "intent": "what we are trying to learn",
  "focus": ["current themes"],
  "attention": [{"source": "chunk-id", "why": "query/critic selected it", "score": 0.82}],
  "weight": {"retrieval": 0.35, "evidence_quality": 0.25, "novelty": 0.15, "contradiction": 0.15, "license_safety": 0.10},
  "bias_flags": ["prompt-framing", "source-selection", "semantic-collapse"],
  "action": ["next lgwks command"],
  "rollback_ref": "champion-snapshot-id"
}
```

This is not the model's hidden attention. It is the Machine's observable attention: what evidence it
looked at, why it looked there, and what budget it spent.

## 3. Bias stripping

Bias cannot be stripped by asking the model to "be unbiased." It has to be separated by plane.

### Human bias

Symptoms:

- prestige bias: famous company/paper/source gets overweighted
- thesis lock: prompt implies conclusion
- vocabulary drift: director's favorite terms replace industry terms

Machine response:

- require an antithesis worker
- score novelty and contradiction separately
- preserve original prompt but rewrite to neutral query forms
- keep "director framing" as data, not as source truth

### AI bias

Symptoms:

- agreeable synthesis
- filling missing evidence with plausible structure
- conflating adjacent concepts: AI, ML, LLM, transformer, agent

Machine response:

- every claim needs source handles or local evidence
- no-evidence cycles may plan only, not conclude
- contradiction probes count positively, not as failure
- critic must label `estimate`, `observed`, `inferred`, or `unsupported`

### Prompt bias

Symptoms:

- the first prompt sets the frame too strongly
- keywords recursively dominate retrieval
- "salesforce" retrieves marketing instead of architecture/evidence

Machine response:

- fork prompt into at least four query forms:
  - literal query
  - neutral academic query
  - disproof query
  - implementation/mechanism query
- compare embedding neighborhoods between forms
- force next commands to cite which prompt-form produced them

### Cognitive bias

Symptoms:

- over-compression
- salience over causality
- confusing language with thought

Machine response:

- maintain separate ledgers for language, evidence, action, and model-state
- summary cannot delete contradiction
- vector vault keeps root + sub-vaults so local context can be re-expanded

## 4. Worker determinism problem

The current workers are not deterministic enough because they are implicit. A true worker needs:

```json
{
  "worker_id": "academic-001",
  "input_chain_head": "hash",
  "budget": {"tokens": 8000, "commands": 8, "fetches": 25},
  "allowed_sources": ["openalex", "crossref"],
  "query_form": "disproof",
  "outputs": ["records.jsonl", "claims.jsonl", "next_commands.json"],
  "postcondition": "every claim has source handle or is marked unsupported"
}
```

Until this exists, fan-out is only parallel shelling. The Machine needs a worker lease table.

## 5. ML model strengthening path

Current state:

- deterministic embeddings exist
- project memory chain exists
- cognition log exists
- project plan emits weights
- no learned ranker is promoted yet

Next model:

1. collect examples from each cycle:
   - query
   - retrieved chunks
   - critic labels
   - accepted/rejected next commands
2. train a tiny ranker first, not a chatbot:
   - input: query vector + chunk vector + metadata features
   - output: usefulness, contradiction, novelty, license safety
3. freeze champion snapshot
4. train challenger on new cognition/vector-vault data
5. evaluate on held-out prompts:
   - "AI vs ML"
   - "Salesforce as AI OS"
   - "auth boundary"
   - "prompt injection"
6. promote only if Brier/calibration improves and contradiction recall does not regress
7. otherwise turn the clock back to champion

This is the "late-stage ML becoming AI" path: not because it wakes up, but because the learned ranker
becomes reliable enough to steer attention inside a deterministic command harness.

## 6. Research grounding from this pass

Open-source/public search seeded:

- `Explainable Artificial Intelligence (XAI): Concepts, taxonomies...`
- `Pre-train, Prompt, and Predict: A Systematic Survey of Prompting Methods...`
- `Interpreting Black-Box Models: A Review on Explainable Artificial Intelligence`
- `Explainability for Large Language Models: A Survey`
- `Dissociating language and thought in large language models`
- `Mamba: Linear-Time Sequence Modeling with Selective State Spaces`

Primary frontier anchors to keep in the doctrine:

- Transformer: attention-only sequence model family introduced by "Attention Is All You Need".
- Transformer circuits: mechanistic interpretability tries to reverse-engineer model computations.
- RAG: external memory reduces reliance on parametric memory alone.
- ReAct: interleave reasoning and actions.
- Self-RAG: retrieve, generate, critique.
- Constitutional AI/RLAIF: model-generated critique can supervise model behavior, but needs principles
  and evaluation gates.

## 7. Identify -> Spec -> Deploy

### Identify

The missing abstraction is not "more crawling." It is a **cycle record** that binds:

```text
intent -> query form -> evidence attention -> bias flags -> next command -> eval result -> weight update
```

### Spec

Create `lgwks project deploy` with:

- worker lease table
- cycle ledger
- token ledger
- claim schema
- critic schema
- model snapshot registry
- deterministic replay mode

### Deploy

Deploy sequence:

1. `lgwks project plan ...`
2. `lgwks project deploy --dry-run` emits worker DAG.
3. `lgwks project deploy --cycles 5 --embedding-rounds 400` runs bounded loop.
4. `lgwks project review` shows:
   - chain head
   - worker outputs
   - contradictions
   - next commands
   - champion/challenger score
   - rollback point

## 8. Whimsy surface

The CLI should feel like an instrument, not a spreadsheet:

```text
Frontier Compass
  intent: AI vs ML at token/blackbox layer
  chain: 27 events · head 91f2...
  attention: 14 sources · 233 chunks · 5 contradictions
  bias weather: prompt-lock amber · source-selection green · semantic-collapse amber
  clock: champion frozen · challenger warming · rollback ready
```

The whimsy is allowed only if the math is visible.

