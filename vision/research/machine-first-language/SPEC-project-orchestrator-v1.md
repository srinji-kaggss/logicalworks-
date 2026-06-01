# SPEC-project-orchestrator-v1

## Intent

One prompt should create a project, fan out authorized workers, deep-crawl academic/open sources,
build vector vaults, let the AI issue the next command set, and keep the whole run bounded by the
prompt form.

Example:

```bash
lgwks project plan "salesforce" \
  --prompt "map Salesforce as an AI-operating-system competitor" \
  --reasoning-cycles 5 \
  --embedding-rounds 400
```

## End State

The project orchestrator is a deterministic harness around a learning loop:

1. **Identify** — parse the single prompt into a project scope, budgets, sources, and worker branches.
2. **Spec** — write a replayable plan: workers, allowed hosts, open-source/public source lanes, auth
   status, embedding rounds, token budgets, stop conditions, and next-command schema.
3. **Deploy** — run bounded workers that fetch, embed, critique, expand the frontier, and append
   every result to the project memory chain and vector vault.

The Machine is not "an LLM running wild." It is a harness with a clock:

```text
prompt -> plan -> workers -> evidence -> embeddings -> critique -> next commands
       -> weights/champion update -> held-out check -> promote or turn clock back
```

## Actor Model

- **Machine**: deterministic harness, budgets, worker queue, chain verifier, vector vault, promotion
  gate. It owns the clock and says when to stop.
- **Curious AI**: proposes frontier queries, critiques evidence, creates next command candidates, and
  labels training examples. It does not get to bypass scope, auth, rate, or budget gates.

## Sources

Default academic/public lanes:

- OpenAlex
- Crossref
- Openverse
- project-scoped authorized hosts, when an active keychain/session lock exists
- local project folder embeddings

The open-source/public lane must carry license metadata. Public reachability is not enough.

## Worker Branches

Each project plan creates branch workers:

| Worker | Job |
| --- | --- |
| `seed` | create initial source set from prompt and project memory |
| `academic` | query open scholarly indexes and open-license metadata |
| `authorized` | crawl active keychain/session hosts only; log `needs_auth` if missing |
| `embed` | generate root + sub-vault embeddings |
| `critic` | grade evidence, contradictions, stale paths, and weak themes |
| `frontier` | issue the next set of commands |

Workers append events; they do not mutate each other's outputs in place.

## Budgets

Defaults:

- reasoning cycles: `5`
- embedding rounds: `400`
- max workers: `4`
- max tokens per reasoning cycle: `8000`
- max commands per cycle: `8`
- per-host rate: source/auth declared; never bypassed

The prompt form must show these before deploy. A missing value defaults; an impossible value is clamped.

## Embedding Rounds

An embedding round is not just "make another vector." It is:

1. choose focus terms from current context chain and critic gaps
2. chunk matching documents
3. write deterministic embeddings
4. optionally write semantic model embeddings when configured
5. compute agreement/disagreement
6. emit new themes, weak spots, and next frontier candidates

Two vector schemas intentionally coexist:

- deterministic feature-hash vectors: replayable backbone
- semantic model vectors: meaning lift

The enrichment signal is the gap between them. If deterministic says two chunks are near but semantic
says far, the critic treats it as lexical collision. If semantic says near but deterministic says far,
the critic treats it as concept bridge.

## Weight Policy

Current weight is not a neural weight file yet. It is a versioned state vector:

```json
{
  "machine_weight": {
    "retrieval": 0.35,
    "evidence_quality": 0.25,
    "novelty": 0.15,
    "contradiction": 0.15,
    "license_safety": 0.10
  }
}
```

The learning path:

1. log all examples to cognition + memory chains
2. train challenger retriever/ranker on accepted examples
3. evaluate on held-out queries and contradiction probes
4. promote only if calibration improves
5. otherwise turn the clock back to the last frozen champion

This is how the harness micro-evolves without pretending to be autonomous intelligence too early.

## Frontier Techniques To Encode

Grounded inspirations:

- RAG: external, updatable memory over retrieved documents.
- ReAct: interleaved reasoning and actions.
- Self-RAG: retrieve/generate/critique loop with reflection.
- HyDE-style query expansion: generate hypothetical target text, embed it, retrieve against that.

Implementation translation:

- `planner` emits query + hypothesis + expected evidence.
- `worker` fetches.
- `critic` grades source, license, contradiction, and novelty.
- `frontier` emits next commands only if the critic identifies a gap worth spending budget on.

## What Truly Remains

Already present:

- project memory chain
- keychain/session auth resolver
- public/open-license source search
- vector vault + sub-vaults
- deterministic embedding cycles
- cognition log and Machine scaffold

Remaining to reach the end state:

1. worker queue with per-host rate leases
2. `lgwks project deploy` executor
3. semantic embedding provider stored alongside deterministic vectors
4. critic scoring schema and held-out eval set
5. champion/challenger model snapshots with rollback
6. next-command emission and approval gate
7. token ledger per reasoning cycle
8. CLI dashboard that makes the chain feel alive without hiding the math

