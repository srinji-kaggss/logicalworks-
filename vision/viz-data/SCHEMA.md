# Canvas World-Map — Math + Schema Layer (the engine contract)

**Version `graph-schema/2` · export `canvas-context-export/2`.** This file is the source of truth.
The visual is a *rendering* of this layer. **Updating the map = writing JSON here** (append one object;
the generator does creation, merging, direction, routing, and the math). Conforms to LW-RS/1 (append-only,
stable ids, `sup` supersedes — never rewrite history).

---
## 0. Design laws (why this layer exists)
1. **Nodes are created naturally, never forced.** A node exists iff it is *declared* (manual/seed) **or**
   *referenced by evidence* (derived from a research ping or another node's `refs`). Hubs/collectors
   emerge from membership, not hard-coding.
2. **Every node carries provenance.** You always know if a human placed it, research derived it, or it is
   a structural seed — and whether it was merged.
3. **Direction is computed from roles, not hand-drawn.** A link knows which end *provides* the dependency
   and which end *depends*; flow follows that.
4. **The world is reached per-node.** A node touches the internet only if it actually does; world links
   are not painted across whole layers.
5. **The export is self-contained.** A downloaded node carries enough inlined context + a glossary that an
   AI needs *nothing else* to decode it.

---
## 1. NODE schema (declarative)
```jsonc
{
  "id": "stable-id",                 // stable; diffs key on this
  "label": "human name",
  "origin": "seed|manual|derived|merged",   // PROVENANCE (law 2)
  "manual": false,                   // true => a human placed/curated this node
  "by": "who",                       // author when manual (e.g. "director", "opus")
  "same_as": ["other-id"],           // identity assertion -> triggers merge (law: §3)
  "merge_into": "canonical-id",      // this node is an alias; fold into canonical
  "band": "world-root|incumbent|layer-hub|world|os_hook|bin|primitive|impl|gh_issue|actor",
  "layer": "distribution|identity|cloud|regulation|ecosystem|stack|spine|impl|world|incumbent",
  "feature": "broker|memory|identity|capability|governance|ml|distribution|security|payments|ui|protocol|none",
  "bin": "bin0..bin5|null",
  "collector": false,                // natural aggregator (law 3/§4); auto-set, may be declared
  "touches_internet": false,         // law 4: if true, node routes to world-root
  "priority": 0,                     // 0..3 (computed, §5)
  "maturity": 0.0,                   // 0..1 ships-today-ness (authored/seeded)
  "summary": "WHAT it is",
  "why": "[tag] WHY (decision framework §6)",
  "claims": [{"stmt":"","url":""}],
  "refs": ["ids this derives from"]  // drives derived links + natural creation
}
```
**Creation rule (generator):** emit a node for every object above; ALSO auto-emit a `derived` node for any
`refs`/`wy`/`ab`/`wr` id that is referenced but never declared (so the graph is closed). Auto-emit a
`layer-hub` collector for a layer iff ≥1 node declares it. Auto-emit `world-root` (seed). Bins are seed.

## 2. LINK schema — roles, not arrows
```jsonc
{
  "provider": "id",     // the end that CREATES/serves the dependency
  "dependent": "id",    // the end that NEEDS it
  "rel": "implements|depends_on|gates|controls|contains|ascends|addresses|benchmarks|reaches_world|peer",
  "dir": "uni|bi",      // bi only if an endpoint is a collector (§4)
  "weight": 0.5,        // 0..1 (§5)
  "origin": "derived|manual|seed"
}
```
**Flow law (law 3):** the rendered particle flows **provider → dependent** (capability/value flows toward
the consumer). `source=provider`, `target=dependent` in the emitted graph. Per-rel role table:

| rel | provider (source) | dependent (target) | meaning |
|---|---|---|---|
| implements | impl/foundation | primitive | foundation enables the primitive above it |
| depends_on | the thing relied upon | the relier | flow = enablement toward the relier |
| gates | gatekeeper | gated | gatekeeper's policy flows onto the gated |
| controls | controller | controlled | control flows down |
| contains | collector hub | member | membership |
| ascends | lower bin | higher bin | survivability accrues upward |
| addresses | gh_issue | primitive/bin | the work feeds the feature |
| benchmarks | primitive | incumbent | we measure ourselves against them |
| reaches_world | internet-touching node | world-root | the single per-node plug into the world (§4) |
| peer | collector | collector | lateral; only between collectors |

## 3. MERGE convention
- `same_as:["x"]` or `merge_into:"x"` ⇒ the generator folds the node into the canonical id `x`: union of
  links (re-pointed to `x`), prefer canonical `summary/why`, keep the longer `claims`, set
  `origin:"merged"`, record `merged_from:[ids]` and `aliases:[labels]` on the canonical node.
- Natural-key merge (optional): two `derived` nodes with identical normalized `label` AND same `layer`
  merge automatically (logged). Manual nodes never auto-merge — only via explicit `same_as`.
- Markers after merge: canonical node shows `origin:"merged"`, `merged_from`, `aliases`. The overlay (§7)
  renders a small merge glyph so the merge is visible, not hidden.

## 4. Collectors + bidirectional + world routing
- **Collector** = a natural aggregator. Auto-set `collector:true` when `band ∈ {world-root, layer-hub,
  incumbent}` OR `feature == broker` OR a node has ≥ N=6 inbound links. May also be declared.
- **Bidirectional rule (your law):** `dir:"bi"` is permitted **only** when at least one endpoint is a
  collector. The generator downgrades any other `bi` to `uni` and logs it. So two-way "breathing" emerges
  only from natural collectors (hubs, broker, world).
- **World routing (your law):** the ONLY links into `world-root` are `reaches_world`, emitted **per node**
  for nodes with `touches_internet:true` (manual) or `band=="os_hook"` (derived — a hook is by definition
  an internet/world touchpoint). No blanket layer→world links. So if one regulation (emerald) or identity
  (violet) node actually talks to the internet, that node — and only it — routes up to the world.

## 5. THE MATH (explicit, overlay-able §7)
```
level(node)      = { world-root:0, incumbent:1, layer-hub:1, world:2, os_hook:2,
                     bin:3, primitive:3, impl:4, gh_issue:4, actor:2 }[band]
priority(node)   = max( seedPriority,  max(addressing gh_issue priority) )      // primitives INHERIT urgency
                   pri P0=3,P1=2,P2=1; op:1 flag => +1 (cap 3)
maturity(node)   ∈ [0,1]  authored in why-map / seed (ships-today-ness)
distance(prim)   = clamp( max_incumbent_strength[feature] − maturity , 0, 1 )
frontier_distance= mean( distance(prim) over primitives )                        // HUD headline
val(node)        = base[band] + 1.4*len(claims) + 2*priority                     // render size
weight(link)     = wrel[rel] * (1.0 if origin!="derived" else 0.85)              // curated > derived
flow_speed(link) = 0.002 + 0.010*weight                                          // particle speed
collector(node)  = band∈{world-root,layer-hub,incumbent} ∨ feature=="broker" ∨ inbound≥6
```
`wrel = {implements:.7, depends_on:.6, gates:.8, controls:.7, contains:.3, ascends:.9, addresses:.5,
benchmarks:.6, reaches_world:.4, peer:.5}`. All constants live here so tuning = editing this table.

## 6. Decision framework for `why`
`[tag] ` prefix, tag ∈ `build·ride·avoid·separate·gate·measure`, then 3 lenses: **Survivability** (bin/feature
it serves) · **Failure-if-absent** (what breaks / which incumbent wins) · **Leverage** (what we own/route
around). Raw world nodes may template; curated nodes author it.

## 7. MATH/SCHEMA OVERLAY (render the engine, not just the art)
A toggle in the viz overlays the layer this file defines:
- **Provenance glyphs:** seed=◇, manual=▣ (with `by`), derived=●, merged=⬡ (+merge glyph).
- **Level bands** labeled with their rule (§5); **collectors** ringed; **world-routing** `reaches_world`
  links emphasized; **direction legend** (provider→dependent) shown.
- **Live math panel:** the formulas above with the *current* computed values (frontier_distance, per-feature
  distance, a node's val/priority/weight breakdown when selected).
- Purpose: a viewer sees the math + schema that produced the picture, and knows exactly what to edit.

## 8. EXPORT — `canvas-context-export/2` (self-contained, AI-decodable)
On node click → "Extract context" downloads a file that needs **nothing else** to decode:
```jsonc
{
  "$schema": "canvas-context-export/2",
  "generated_from": "graph-schema/2",
  "exported": "ISO8601",
  "how_to_read": "Plain-language note: this is one node and its world-slice; ids resolve INSIDE this file.",
  "glossary": { "bands":{...}, "features":{...}, "rels":{...}, "bins":{...}, "math":{...} },  // inlined defs
  "focus": { ...full focal node, all fields... },
  "provider_closure": [ { ...FULL node... , "rel_to_focus":"", "depth":1 } ],  // what focus depends on, inlined
  "dependent_closure":[ { ...FULL node... , "rel_to_focus":"", "depth":1 } ],  // what depends on focus, inlined
  "branch_to_world": [ { ...FULL node..., "rel_from_child":"" } ],             // ancestors up to world-root
  "impact_if_disabled": [ { "id":"", "label":"", "reason":"loses path to world-root" } ],
  "math": { "frontier_distance":0.0, "focus_distance":0.0, "val_breakdown":{}, "formulas":{} },
  "decision": { "why":"", "tag":"" }
}
```
Rule: **inline full node content** (summary, why, claims, feature, bin, maturity, distance) for every node
in the closures/branch — never bare ids that need the full index. The `glossary` inlines the meaning of
every band/feature/rel/bin/formula used. Result: an AI reads this one file and has complete world-context
for that node.

## 9. Data files (all append-only / diff-friendly; updating = writing JSON)
- `notes/*.jsonl` — research (derived nodes/edges/os_hooks/directives/claims).
- `viz-data/manual.jsonl` — **NEW**: hand-placed real-world nodes (e.g. an email client) + `same_as`/merge
  declarations. `origin:"manual"`, `manual:true`, `by`. This is the human editing surface.
- `viz-data/implementation.jsonl` · `incumbents.jsonl` · `gh-issues.jsonl` · `why-map.json` — as before,
  now carrying `origin`/role fields per §1–2.
- Generator config: seeds (world-root, bins, primitives), palettes, the §5 math constants mirror.
