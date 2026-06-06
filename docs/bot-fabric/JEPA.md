# JEPA In The Bot Fabric

## What JEPA is here

JEPA is not one of the bots.

JEPA is the layer that learns or computes the shared latent object behind many noisy views.

Those views include:

- raw human dump
- deterministic bot findings
- repo graph
- prior continuation packets
- external sources
- outcomes from earlier runs

## What JEPA does

1. Align related views into one package
2. Detect contradictions and stale assumptions
3. Compress evidence into a reusable latent object
4. Improve continuation and package lookup later

## What JEPA does not do

1. Replace graph analysis
2. Replace stress testing
3. Replace security heuristics
4. Act as the final execution authority
5. Write the final human story by itself

## Correct placement in the pipeline

```text
bots create evidence
-> JEPA aligns/compresses/synthesizes machine meaning
-> optional final reasoning LLM refines judgment and reduces token load
```

## Why this matters

Without JEPA:

- every run is a fresh pile of findings
- wording drift is expensive
- the same latent issue is rediscovered repeatedly

With JEPA:

- repeated analysis binds to the same world object
- the machine gets continuity
- the human gets a stable map

## Compute implications

JEPA should be lightweight enough to be:

- deterministic and package-driven first
- optionally learned later

The first implementation does not need full local JEPA training.

It can start as:

1. canonical package construction
2. deterministic multi-view alignment
3. optional small-model ranking

Only later:

4. package-level JEPA predictor
5. temporal GNN over package transitions

## Local vs remote

### Local is good for

- package construction
- graph math
- clustering
- deterministic alignment
- optional small classifier

### Remote is acceptable for

- final synthesis
- occasional package interpretation when the evidence pack is already small

## Recommendation

Do not spend local compute trying to run a large JEPA or general LLM locally right now.

Keep JEPA as:

- package contract first
- learned layer later

Small local models should support JEPA, not replace it.

Preferred local support order:

1. Apple-native Foundation / Apple Intelligence runtime when available
2. CoreML / ANE exported encoder-class membrane
3. small local coder/helper model only when the Apple-native path is insufficient

The important split is:

- JEPA = machine synthesizer
- encoder membrane = advisory routing / depth / keyword weighting
- optional LLM = final judgment cleanup, schema formatting, or human explanation

The package quality bar is:

- if the LLM layer is removed, the machine packet should still stand
- if the LLM layer is present, it should improve compression and prioritization rather than invent core meaning
