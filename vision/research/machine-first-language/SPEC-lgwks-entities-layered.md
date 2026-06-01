# SPEC — lgwks layered-depth entity model (v1)

Status: accepted (Director, 2026-06-01). The ER graph of the whole system, organised on a **z-axis of
depth** — z = distance from the human/agent surface. This is what lets the interface "make the human
think in 3D": the launcher renders entities by depth (brightness = z), and reasoning walks down the
layers before synthesising up (down-then-out-before-up). Machine-checkable: §8 is the canonical entity
table; conformance tooling validates code against it.

## The depth axis (z)

```
 z0  SURFACE      what a human/agent touches        entryway · verbs · dials · raw intent
 z1  SHAPING      intent becomes answerable         the Machine · refinement · schema snapshot
 z2  EVIDENCE     the world is fetched, untrusted    crawls · sources · extract · Hₙ · defenders/contradictors
 z3  JUDGMENT     evidence is weighed                the AI (Tongue) · alignment · per-Hₙ gating · calibration
 z4  CORE         what must never leak or drift      membrane · the three stores · frozen snapshots · audit
```

Rule: an edge may point **down** (decompose), **out** (breadth, same z), or **up** (synthesis) — but a z4
core entity is never reachable *from* a lower-trust layer except through a gated port (the membrane).

## §1 · z0 SURFACE entities

- **Intent** — raw human/agent input. fields: `text`, `actor∈{human,agent}`, `ts`. edge: →(refines)→ RefinedIntent.
  invariant: stored only in the intent-vault (z4), never in a log or URL.
- **Verb** — a machine-first capability surface (manifest·solve·extract·convert·jarvis·research). fields:
  `name`, `args`, `tokens`, `output_schema`. edge: →(emits)→ Artifact. invariant: non-interactive; declares token cost.
- **Dial** — a steering control (frontierness 0..1 · lens -1..1 · depth 0..1). edge: →(conditions)→ Machine, AI.
  invariant: human-set + visible; also gates the Machine's abstain threshold.
- **Entryway** — the human launcher (`lgwks` bare). edge: →(opens)→ Verb. invariant: TTY-only; never blocks the machine surface.

## §2 · z1 SHAPING entities

- **Machine** — the intent/goal engine (NOT AI; discriminative transformer, UniXcoder-class). fields:
  `weights_hash`, `stage∈{dormant,I,II,inflection}`, `calibration`. edges: →(refines)→ RefinedIntent ·
  →(scored_by)→ Calibration · →(taught_by)→ AI. invariant: abstains→bounces-to-human when uncertain;
  promoted only past the FrozenSnapshot (z4).
- **RefinedIntent** — intent after gap-detect/entity-link/specificity-score. fields: `intent_class`,
  `entities[]`, `gaps[]`, `specificity`. edge: →(commits_to)→ IntentCommit · →(distills_to)→ SchemaSnapshot.
- **IntentCommit** — one refinement step, git-style. fields: `parent`, `prompt`, `gap`, `idea`, `why`.
  edge: →(logged_to)→ CognitionLog (z4). invariant: append-only; the chain IS Machine training data.
- **SchemaSnapshot** — the clean, distilled packet handed to the AI. fields: `thought_schema(v0)`,
  `steer`, `intent`, `history_ref`. invariant: the AI sees this, never the raw mess.

## §3 · z2 EVIDENCE entities (all UNTRUSTED)

- **Crawl** — one fetch pass (crawl-1 shallow, crawl-2 deep). fields: `query`, `arms[]`, `arms_empty[]`,
  `provider`. edge: →(yields)→ Source. invariant: reports empty arms (no silent coverage gap).
- **Source** — a fetched document/page. fields: `url`, `kind`, `content_hash`, `text`. edge:
  →(cached_in)→ UntrustedCache (z4) · →(cites)→ Hypothesis. invariant: content-addressed; executable-never.
- **Hypothesis (Hₙ)** — a generated claim under test. fields: `k`, `claim`, `p`, `direction∈{down,out,up}`.
  edges: →(defended_by)→ Evidence · →(contradicted_by)→ Evidence · →(gated_by)→ Gate. invariant: a
  hypothesis with zero contradictors is unproven, not proven.
- **Evidence** — a cited fact for/against an Hₙ. fields: `source_ref`, `stance∈{defender,contradictor}`,
  `quote`. invariant: referenced by hash, never inlined (no token re-spend).

## §4 · z3 JUDGMENT entities

- **AI (Tongue)** — the curious generative tier (free, harnessed). role: TEACH the Machine + predict
  alignment. fields: `provider_chain`, `objective_hook`. edges: →(teaches)→ Machine · →(predicts)→ Alignment.
  invariant: insight-or-silence; output reduced to a calibrated alignment probability per Hₙ, not prose.
- **Alignment** — the AI's statistical judgment that crawl-1 ⊕ crawl-2 ⊕ real-world cohere (minus slop).
  fields: `hyp_ref`, `p_align`, `slop_flag`. edge: →(feeds)→ Gate.
- **Gate** — per-Hₙ decision. fields: `hyp_ref`, `defenders`, `contradictors`, `verdict`, `evidence_streak`.
  invariant: survives iff defenders outweigh contradictors under calibration AND ≥2 stable EVIDENCE rounds.
- **Calibration** — ECE/Brier of a model vs reality. edge: →(triggers)→ Freeze when evolving diverges from
  FrozenSnapshot. invariant: the inflection detector; drift past threshold = auto-freeze.

## §5 · z4 CORE entities (never leak, never silently drift)

- **Membrane** — the one primitive, three walls: Machine abstains · AI insight-or-silence · per-Hₙ gate ·
  WASM sandbox physically. edge: gates every z<4 → z4 access. invariant: reason free inside, act gated outside.
- **UntrustedCache** — fetched world data; content-addressed; quarantined; executable-never.
- **CognitionLog** — AI thinking + IntentCommits; append-only, hash-chained = SOC2 audit + Machine corpus.
- **IntentVault** — human PII/intent + auth sessions; encrypted; never in prompt/log/URL.
- **FrozenSnapshot** — a pinned safetensors hash = the turn-back date; champion/challenger parent + drift oracle + fallback.
- **AuditEntry** — who·what·capability·decision for every trust-boundary crossing.

## §6 · The new signals (Director, this turn) — where they live

- **Slop-detector** — z3, a Machine sub-scorer (AIGCodeSet-trained, advisory, per-generator calibrated;
  detectors drift, so it FEEDS Alignment.slop_flag, never decides alone). Edge: →(annotates)→ Alignment.
- **AgentTrigger keyword augmentation** — z1, when `Intent.actor==agent` the RefinedIntent auto-injects
  slop/quality intent-keywords so an agent-issued query is steered to surface known failure modes.
- **PitfallSurface ("where humans say you fuck up")** — z2/z4: a corpus of human-reported AI failure modes
  (the binning research), queryable pre-task and injected into the SchemaSnapshot so the AI sees its known
  traps before acting. Edge: PitfallSurface →(warns)→ AI. Built on CognitionLog + a curated public corpus.

## §7 · Build mapping

z0 entryway+verbs = done (PR #10). z4 stores = build #2 (unlocks IntentCommit/CognitionLog/Vault). z1
Machine + z3 Calibration/Slop = build #3 (UniXcoder backbone, HF-grounded). z2 Hₙ defenders/contradictors
+ z4 PitfallSurface = build #4. AgentTrigger augmentation rides build #3's RefinedIntent.

## §8 · Canonical entity table (machine-checkable)

```
id                z  kind        key_fields                         edges_out
intent            0  input       text,actor,ts                      refines→refined_intent
verb              0  surface     name,args,tokens                   emits→artifact
dial              0  control     name,range                         conditions→machine,ai
machine           1  model       weights_hash,stage,calibration     refines→refined_intent; taught_by→ai
refined_intent    1  derived     intent_class,entities,gaps,spec    commits_to→intent_commit; distills→snapshot
intent_commit     1  log         parent,prompt,gap,idea,why         logged_to→cognition_log
snapshot          1  packet      thought_schema,steer,history_ref   read_by→ai
crawl             2  action      query,arms,arms_empty,provider     yields→source
source            2  doc*        url,kind,content_hash,text         cached_in→untrusted_cache; cites→hypothesis
hypothesis        2  claim       k,claim,p,direction                defended_by/contradicted_by→evidence; gated_by→gate
evidence          2  fact*       source_ref,stance,quote            (ref-only)
ai                3  generative  provider_chain,objective_hook      teaches→machine; predicts→alignment
alignment         3  judgment    hyp_ref,p_align,slop_flag          feeds→gate
gate              3  decision    defenders,contradictors,verdict    (terminal per Hₙ)
calibration       3  metric      ece,brier                          triggers→freeze
membrane          4  guard       walls[]                            gates→all z4
untrusted_cache   4  store       content_hash                       (sink)
cognition_log     4  store       hash_chain                         (sink; = training corpus)
intent_vault      4  store       encrypted                          (sink; PII)
frozen_snapshot   4  governance  safetensors_hash                   parent_of→machine
audit_entry       4  log         who,what,capability,decision       (sink)
```
`*` = UNTRUSTED. Invariant for the whole graph: no z<4 entity reaches a z4 store except through the membrane port.
