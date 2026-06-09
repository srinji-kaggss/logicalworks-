# SCIENCE — the method for the messy parts

Status: draft v0.1 · governs every unit marked "gated on SCIENCE" in the child PRDs.
Instrumentation source: ai-research-skills (Orchestra-Research, MIT, 98 skills) — grounded
at [scratch/grounding/ai-research-skills.md](../../../scratch/grounding/ai-research-skills.md); adaptations per its §4.

## §1 The stance

The messy parts (C/G/P, flag detectors, ranking, chunking, budgets, cadence) are
**empirical questions wearing engineering clothes**. The failure mode is fiddling: tweak a
weight, eyeball two queries, declare victory — that is the operating-loop defect with a
notebook. The cure is the same discipline a paper would survive: pre-registered hypotheses,
frozen corpora, baselines, paired comparisons, calibration, and an epistemic reviewer that
is not the author.

## §2 Pre-registration (adopted: autoresearch's git-as-preregistration)

Before any experiment: commit a `spec/second-harness/experiments/EXP-<n>.md` containing
hypothesis, metric, threshold, corpus hash, and decision rule (*ship / reject / iterate*),
**before** the run. Confirmatory vs exploratory labeled explicitly. A result that needed a
post-hoc threshold change is exploratory by definition and cannot ship a unit.
Workspace shape adopted from autoresearch: `experiments/EXP-n/` holds `research-state.yaml`,
`findings.md`, `research-log.md` — machine-readable state so any agent can resume.

## §3 Frozen corpora (the regression spine)

| Corpus | Contents | Serves |
|---|---|---|
| CORP-intent | ≥50 intent → expected-capability pairs (hand-labeled, from real session prompts) | PRD-01 ranking; PRD-06 required_nodes audit |
| CORP-claims | ≥20 transcript turns labeled for unverified-claims (seed: the three documented lies) | 06-a extractor |
| CORP-flags | per flag class, ≥30 labeled spans (slop/sycophancy/dredge) from real transcripts | 06-d gates |
| CORP-retrieval | ≥40 question → answer-bearing-chunk pairs over this repo + ingested docs | PRD-02/03/04 |
| CORP-docs | 20 libraries × 3 questions, ctx7 answers captured as comparator | 03-a parity |
| CORP-secrets | ≥20 planted secret shapes + adversarial variants | 08-c redaction |
| CORP-diffs | 20 historical diffs with known caught/missed outcomes | 09-d review |

Rules: corpora are hash-pinned and committed; additions allowed, mutations of existing
items require a logged reason; every ranking/detector change re-runs against them in CI.
Labeling protocol: two independent passes (Opus + Director spot-check 20%), disagreement
adjudicated and logged — inter-rater agreement reported, not assumed.

## §4 Paired evaluation (rankers, chunkers, budgets)

Never compare across different query sets. Method: same corpus, system A vs system B,
per-item paired deltas, report recall@k / MRR / answer-bearing-rate with bootstrap CIs
(simple percentile bootstrap, n=1000 — no heavier statistics until corpora grow).
Applies to: lexical vs BERT re-rank (01-d), AST chunks vs naive chunks (02-d/04-d),
reflex-cap sizing (04: marginal salience per 100 tokens on the unsolicited channel ONLY —
find the knee, set the INV-8 cap there; the depth channel is evaluated on yield/coverage,
never on size), embedder choice (05), PageRank prior (04-e — pre-registered or it's fiddling).
Tooling: sentence-transformers + faiss skills (ai-research-skills cat. 15) for baseline
embedders/index; eval-harness *pattern* (cat. 11) adapted — our harness is a pytest suite
over frozen corpora, not lm-eval tasks.

## §5 Comparator parity (the replacement bar)

A subscription is replaced only when measured ≥90% parity on its frozen comparator corpus
(CORP-docs for ctx7; CORP-diffs baseline for Greptile-class review) at p95 latency within
2× of the incumbent. Until then the incumbent stays installed — replacement is an empirical
event, not a declaration. Each parity result is a committed EXP record.

## §6 Detector discipline (flags, claims — the precision gates)

Per detector class: pre-registered precision threshold (default 0.85 to enter the Opus
projection; cockpit-only below), measured on its frozen corpus; confusion matrix committed.
Detectors start deterministic (regex/heuristic over transcript structure — e.g. an
assertion about env state with no preceding tool call is *mechanically* checkable);
classifier heads (05-e) must beat the deterministic baseline paired, or they don't ship.
False-positive review: every blocked/flag-acted event in real use is logged with its span;
a weekly pass relabels them — the corpus grows from production errors (the self-evolving
loop, owned, not rented).

## §7 Calibration (P, and any number shown to a human)

P ships with reliability: bin predictions, plot predicted-vs-observed, report Brier score
vs the base-rate baseline. Label source: session outcomes (task completed without rework /
required rework / failed) recorded by the daemon per session — the labeling is itself a
PRD-08 unit. Sample floor: no P in the Opus projection before 30 labeled outcomes; state
the n alongside every calibration claim. C and G, being deterministic ratios, are audited
differently: spot-check required_nodes sets (06-b) — their failure mode is definition
error, not noise.

## §8 The whole-system question (does the subconscious work?)

The honest test, run after 07-b ships: **A/B by session** over ≥20 real work sessions —
injection on vs `LGWKS_SUBCONSCIOUS=0`, alternating, outcomes labeled (rework rate, tokens
to completion, unverified-claim count from 06-a run retrospectively on both arms).
Pre-registered primary metric: unverified-claim count per session. //why this one: it is
the defect the system exists to kill, it is mechanically countable, and token-savings
claims without it are vanity metrics. Confounds acknowledged: task heterogeneity, model
drift across weeks — alternation + paired-by-task-class analysis, and we report honestly
if the data is too noisy to conclude (that result is publishable in-repo too).

## §9 Adversarial verification (adopted: ara-rigor-reviewer, adapted live)

Every EXP that gates a shipping unit gets an independent epistemic review pass before the
unit closes: the 6-dimension rubric (evidence relevance, falsifiability, scope calibration,
argument coherence, exploration integrity, methodological rigor), severity-ranked findings,
verbatim-evidence-span requirement, "no false grounding". Adaptation per grounding doc §4:
unlike ARA's artifact-only mode, our reviewer re-runs commands live (T2: verify before
assert). Reviewer ≠ author: different agent instance, fresh context, given only the EXP
record + corpus — Director approves each spawn per standing subagent gate.
Redaction (08-c) additionally gets a red-team pass: an adversarial agent constructs secret
shapes the filter was not built from; recall on those is the reported number.

## §10 Provenance & the research log (adopted: ara-research-manager tags)

Every experimental claim in any PRD/BUILDLOG carries provenance: `user / ai-suggested /
ai-executed / user-revised`. Dead ends are recorded as dead ends (exploration DAG node
types: question/experiment/decision/dead_end/pivot) — a rejected PageRank prior or a
losing embedder is a committed result, not deleted history. BUILDLOG.md remains the
narrative log; `experiments/` is the structured one.

## Order of first experiments

1. **EXP-1** CORP-intent + lexical baseline scores (cheap; unblocks 01-d and 06-b). 
2. **EXP-2** CORP-claims + deterministic unverified-claim extractor (06-a) — highest
   value-per-effort in the whole program; it mechanizes the operating loop.
3. **EXP-3** AST vs naive chunking on CORP-retrieval (02-d/04-d).
4. **EXP-4** docs parity vs ctx7 (03-a).
5. **EXP-5+** detector gates, calibration, the §8 A/B — in dependency order.

RISK: the method's own failure mode is ceremony — corpora nobody refreshes, EXP files
written after the result. The §6 production-error loop and §9 reviewer-≠-author rule are
the two guards; if either is skipped the science is decoration.
