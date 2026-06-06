# Hostile Audit — Axiom Machine-First ISA (v0) + First-Pass Implementation

**Auditor role:** Independent adversarial red-team (Logic Hacker, fleet `hacker` agent). **Date:** 2026-06-06.
**Scenario simulated:** Attacker has already defeated L5/L4 (intent/noding) and L2 (the click). Attacker writes raw capsule bytes directly into the L1 fabric / hash-chain, controls all `now` / `window` inputs, and can feed the gauges and comms echo layer arbitrary input. From this position, break everything.
**Targets read in full:** `SPEC-axiom-isa-v0.md`, `STUDY-isa-wasm-jvm-to-machine-first.md`, `ADR-004`, `ADR-005`, `SPEC-translation-chain-bytecode-semantics.md`, `lgwks_axiom.py`, `tests/test_axiom.py`. All exploits below were executed against `lgwks_axiom.py` at HEAD; outputs reproduced inline by the auditor.

> Status: ACCEPTED FINDINGS (2026-06-06). Pen-test gate = **FAIL**. Blocking: F-01, F-02, F-03 (CRITICAL); F-04, F-05, F-06 (HIGH). This audit gates the `axiom/` byte-framework build (chunk C0 → C1).

---

## 1 · Executive summary (ranked by severity)

1. **[CRITICAL · F-01] The CID is never verified on read.** `Fabric.click()` trusts `entry.capsule.grants` / `.state` by dictionary key and never checks `entry.capsule.cid() == stored_key`. An attacker stores high-privilege content under the CID an honest party will reference. Content-addressing — the entire root of trust — is decorative. (`lgwks_axiom.py:110-126`)
2. **[CRITICAL · F-02] A Hole bypasses every check and launders capability grants up the DAG.** `is_hole` short-circuits `click()` *before* kind/base-first/capability/interval. A hole with `grants={charge, admin, node-at-runtime}` is accepted unconditionally, and its grants flow into the lineage union for any child built on it. This is `cap:node-at-runtime` forgery (SPEC §10) reduced to one boolean. (`lgwks_axiom.py:101-102, 119-126`)
3. **[CRITICAL · F-03] No root of grant authority — grants are attacker-writable set-union, not a lattice.** Any capsule may declare arbitrary `grants`; `by:ai+human:<cap>` self-grants any single capability with no base at all. INV-5 ("capability up the DAG") is enforced only relative to attacker-authored fields. (`lgwks_axiom.py:48, 119-126`)
4. **[HIGH · F-04] Caller-controlled `now` makes the transaction a time machine.** `revert()` calls `status(cid, now)` with caller-supplied `now`; rewinding the clock un-commits a COMMITTED capsule and deletes it. `window=0`/negative auto-commits at propose time. (`lgwks_axiom.py:136, 145-163`)
5. **[HIGH · F-05] CID canonical encoding is unstable and non-portable.** `1.0` vs `1` → different CIDs for identical meaning; `0.0` vs `-0.0` split; `float('nan')` serializes to the non-standard JSON token `NaN` (rejected by RFC-8259/JCS decoders) → cross-decoder CID divergence. Breaks INV-1 and contradicts "own the determinism." (`lgwks_axiom.py:52-68`)
6. **[HIGH · F-06] Dangling committed edges.** A base reverted while PENDING is deleted, leaving an already-admitted child pointing at a non-existent base. `del self._by_cid[cid]` means the fabric is not append-only, violating INV-9. (`lgwks_axiom.py:161`)
7. **[MED · F-07] Replay inconsistency in supersede.** `supersede()` runs `click()` on the replacement *before* marking the old superseded, so a replacement depending on the node it supersedes is admitted but fails on re-click — the fabric does not replay. (`lgwks_axiom.py:165-174`)
8. **[MED · F-08] Gauge `next_step` is attacker-steerable; gauges read caller-controlled `now`.** "Unique actionable next step" chosen by `argmin(cid)` over claim text — grindable. `pending_ratio` depends on attacker `now`. (`lgwks_axiom.py:185, 194-201`)
9. **[MED · F-09] No collision economics on a 128-bit digest** (`digest_size=16`). Birthday bound ≈ 2^64. (`lgwks_axiom.py:68`)
10. **[INFO · F-10] Entire upper stack (INV-4/6/8/10, ADR-004 L/R verifier, ADR-005 comms chain, WASM erasure) is prose, unimplemented.** Cannot be attacked → cannot be trusted.

---

## 2 · Threat model & assumptions

The attacker controls, per the scenario:
- **Raw write access to L1** — construct `Capsule`/`_Entry` and insert into `Fabric._by_cid` under any key, bypassing `propose()`/`click()`.
- **All `now`/`window`** fed to `propose`/`status`/`revert`/`supersede` (the core takes injected `now` by design — `lgwks_axiom.py:12`).
- **Arbitrary capsule field content** — `kind`, `by`, `grants`, `needs`, `params`, `on`, `is_hole` are author-writable; no signing, no key, no external root.
- **Arbitrary gauge / comms-echo input.**

What the attacker does **not** need: compiler, model, or L2/L4/L5. The defender's only wall is `click()` + the fabric transaction — porous even without raw bytes (F-02/F-03/F-04 work through the *public* `propose()` API), fully transparent with them (F-01).

---

## 3 · Findings

### F-01 · CID is never verified on read — content-addressing is decorative
- **Class:** Integrity / content-address forgery (CWE-345, CWE-353). **Severity:** CRITICAL. **Confidence:** High. **INV-broken:** INV-1, INV-9.
- **Precondition:** Raw write to `_by_cid`, OR any path storing a capsule under a key not re-derived from content.
- **Attack:** `click()` resolves bases via `self._by_cid.get(base)` and reads `entry.capsule.grants`/`.state`, never asserting `entry.capsule.cid() == base`. Verified: store a `{charge,admin,node-at-runtime}` capsule under a benign entity's CID `K`; a child `on=(K,) needs={admin,charge}` clicks ok. Constant-pool-confusion class (JVM) / "hash says X, bytes are Y" class (IPFS/Git).
- **Impact:** The content-address provides zero integrity; all lineage (F-03) and base-first (F-06) reasoning sits on an unverified lookup.
- **Mitigation:** On every store and every base read, assert `entry.capsule.cid() == key`; route all inserts through one guarded method that recomputes the CID. Enforcement of an already-stated invariant — no spec change.

### F-02 · Hole bypasses all validation AND launders capabilities (the §10 frontier, weaponized)
- **Class:** Auth bypass / priv-esc (CWE-285). **Severity:** CRITICAL. **Confidence:** High. **INV-broken:** INV-5, SPEC §4, ADR-004 D1 ("a Hole cannot widen its own scope").
- **Precondition:** Public `propose()` only.
- **Attack:** `click()`: `if c.is_hole: return Verdict(ok=True)` returns before kind/base-first/capability/interval. A hole with fake kind, dangling `on`, `needs={admin}`, `grants={charge,admin,node-at-runtime}`, out-of-range params is accepted. Then a non-hole child `on=(hole_cid,) needs={charge,admin,node-at-runtime}` clicks ok — lineage union reads `base.capsule.grants` with no `is_hole` filter. A hole grants the system's one self-referential power (§10) to its children.
- **Impact:** Defeats "no un-clicked code runs." A hole — meant as abstention/ticket — is an unchecked capability mint. The JVM-reflection hole §10 claims to close, re-opened at the atom level.
- **Mitigation:** (a) hole must carry `grants=∅` (reject non-empty); (b) hole contributes nothing to the lineage union; (c) still run kind/base-first structural checks on holes.

### F-03 · No root of grant authority — self-rooted and `by`-self-granted capabilities
- **Class:** Priv-esc / missing trust anchor (CWE-862). **Severity:** CRITICAL. **Confidence:** High. **INV-broken:** INV-5, SPEC §5.
- **Precondition:** Public `propose()`.
- **Attack:** `grants` is a free attacker-writable `frozenset`. A base with `grants={charge,write,node-at-runtime,admin,wasi:fs}` clicks (nothing validates what a capsule may grant). Worse: `if c.by.startswith("ai+human:"): lineage.add(c.by.split(":",1)[1])` — a capsule with NO base and `by="ai+human:charge"` self-grants `charge`. The "lattice" is set-union over attacker-written fields; no granter, no signature, no genesis-grant, no proof a grant descends from an authorized root.
- **Impact:** The capability wall (SPEC §11) does not exist against any author; with F-01, non-authors forge it too.
- **Mitigation:** Define a **grant root**: capabilities originate only from a signed genesis capsule (or out-of-band authority list); a non-genesis capsule's `grants ⊆ its own needs` (re-grant only what you hold); the `by:cap` self-grant must require a verifiable human-authority token, not a string prefix. **Spec gap** — SPEC §5/§7 never names the root of authority. The §OPEN `cap:node-at-runtime` granter fork applies to ALL grants.

### F-04 · Caller-controlled `now` → time-machine rewind; `window≤0` → auto-commit
- **Class:** State-machine / TOCTOU (CWE-840, CWE-367). **Severity:** HIGH. **Confidence:** High. **INV-broken:** SPEC §14 monotonicity.
- **Attack:** `status()` derives COMMITTED from `now >= deadline`; `revert()` re-derives with the caller's `now`. A capsule COMMITTED at `now=20` is reverted (deleted) via `revert(cid, now=5)`. `window=0` → COMMITTED at propose time; `window=-50` commits in the past — malicious capsule auto-commits before any review window.
- **Impact:** §14's commit barrier ("human cannot just reject") is meaningless; COMMITTED is not monotone.
- **Mitigation:** `now` from a monotonic, non-rewindable source persisted in the fabric (logical clock = log length, or a max-seen high-water mark the core refuses to go below). Reject `window<=0`. Persist the committed transition rather than re-deriving from caller input.

### F-05 · Non-canonical, non-portable CID encoding (int/float, ±0, NaN token)
- **Class:** Canonical-encoding forgery / round-trip instability (CWE-697). **Severity:** HIGH. **Confidence:** High. **INV-broken:** INV-1, SPEC §3.1 / ADR-004 D3.
- **Attack:** `canonical_bytes()` uses `json.dumps(sort_keys=True)` over Python-native values. `(1.0,0.0,2.0)`→`[1.0,0.0,2.0]` vs `(1,0,2)`→`[1,0,2]` = different CID, same meaning. `0.0` vs `-0.0` split. `float('nan')` emits literal `NaN` (invalid JSON per RFC-8259; rejected by JCS/canonical-CBOR) → unparseable elsewhere → CID divergence across the M2M wire.
- **Impact:** Dedup, replay, M2M transfer unsound; two byte-encodings of one logical capsule (CID confusion).
- **Mitigation:** Strict canonical codec (canonical CBOR or JCS): one number type, reject/normalize NaN/±Inf, normalize ±0, fixed float serialization; hash over canonical *bytes*, never Python JSON. The most irreversible-if-shipped decision (ADR-004 D3 says so) and currently wrong.

### F-06 · Dangling committed edges — fabric is not actually append-only
- **Class:** State-machine integrity (CWE-672). **Severity:** HIGH. **Confidence:** High. **INV-broken:** INV-9 / SPEC §12.9, §4 base-first.
- **Attack:** base `b`, child `ch` on `(b,)`. `revert(b, now=5)` does `del self._by_cid[b]`; `ch` remains, now references a non-existent base, and may itself commit at `now=20`. `revert` does no dependent check. §12.9/§14 promise append-only ("never delete"); `del` violates it literally.
- **Impact:** Stranded/dangling edges in a "structured-CFG-by-construction" graph — the exact dangling-edge case the verifier claims to reject; replay cannot reconstruct the child's base.
- **Mitigation:** Never `del`. Pre-commit reject appends a tombstone/`sup` and refuses if committed dependents exist; revert must cascade or quarantine — **resolve the cascade-vs-quarantine §OPEN fork before this ships.**

### F-07 · Supersede replay inconsistency (admitted-but-won't-re-click)
- **Class:** Logic / replay soundness (CWE-696). **Severity:** MEDIUM. **Confidence:** High. **INV-broken:** SPEC §12.1, §12.9.
- **Attack:** `supersede(cid,new)` calls `propose(new)` (runs `click`) *before* marking `cid` SUPERSEDED. If `new.on=(cid,)`, `click` passes (old still live), `new` admitted, then `cid`→SUPERSEDED; re-clicking `new` now fails "base is superseded." A node sits in the fabric the verifier would reject on replay.
- **Mitigation:** Mark superseded before clicking the replacement, or forbid a replacement depending on the node it supersedes. Add a replay self-test (absent today).

### F-08 · Gauge `next_step` grindable; gauges read caller-controlled `now`
- **Class:** Output-integrity / metric poisoning (CWE-807). **Severity:** MEDIUM. **Confidence:** High. **INV-broken:** INV-7, INV-4 (§15), INV-8 by extension.
- **Attack:** `gauge_open_holes` picks next step by `sorted(holes, key=lambda h: h.cid())[0]` — attacker grinds `claim` text until their hole wins `argmin(cid)`, steering the human's next step. `gauge_pending_ratio` folds `status(cid, now)` over caller `now` → feed a large `now`, junk fabric reads healthy. SPEC §15's "next_step = sensitivity gradient" is, in code, a CID lexical sort; `w(n)` does not exist.
- **Mitigation:** Rank by measured weight (age, dependent count, capability blast-radius), not CID; internal monotonic clock; implement `w(n)` + judgment-dimension flag.

### F-09 · 128-bit digest, no collision economics
- **Class:** Crypto strength (CWE-327). **Severity:** MEDIUM (HIGH with F-01). **INV-broken:** INV-1 robustness.
- **Attack:** `blake2b(digest_size=16)` = 128-bit CID; birthday bound ≈ 2^64. Below 256-bit norm for a key gating capability lineage.
- **Mitigation:** Full-width BLAKE3-256 (the documented canon; `lgwks_axiom.py:18` admits stand-in). Do not ship 128-bit.

### F-10 · Protective upper layers are prose, not code
- **Class:** Assurance gap. **Severity:** INFO (blocks the "production-safe" bar). **INV-broken:** INV-4/6/8/10, ADR-005 INV-C1..C4.
- **Narrative:** No code implements the L/R verifier (ADR-004 D4), divergence/channel-independence (INV-8), comms causal-chain verify (ADR-005 INV-C4), WASM lowering/erasure (§6), intent lattice (§7), `w(n)` (§15). The erasure-boundary TOCTOU (§6: proof dropped at lowering) is a real future hole — nothing binds the verified term to the lowered WASM module; WASM custom-section proof carriage is attacker-writable and erased at execution ("metadata stripped, payload runs").
- **Mitigation:** Do not claim these invariants as held; mark PROPOSED-UNIMPLEMENTED in §12.

---

## 4 · New syntax patterns (compositional exploits — each part clicks, the whole is malicious)

### SP-1 · "Capability Ladder" (grants laddered through holes and self-grants)
```
H = hole{ grants={node-at-runtime}, is_hole=true }     # clicks (F-02: hole short-circuits)
C = claim{ kind=effect, on=(H), by="ai+human:write",   # write self-granted (F-03)
           needs={node-at-runtime, write} }            # node-at-runtime laundered from H (F-02)
```
Each part passes; the composition mints `node-at-runtime` with no granter/audit. Reusable: park any capability in a hole, inherit it.

### SP-2 · "CID Cuckoo" (honest reference, hostile content)
```
1. Honest party publishes benign read-only entity E; CID = K.
2. Attacker raw-writes _by_cid[K] = high-priv capsule (F-01).
3. Any honest child on=(K) inherits attacker grants.
```
The author verified only the CID — never re-checked. They believe they built on E; they built on the cuckoo.

### SP-3 · "Window Sprint" (auto-commit before review)
```
propose(malicious_effect, now=T, window=0)   # COMMITTED at T (F-04)
```
§14 permits any caller `window`; the "reject freely while PENDING" guarantee never materializes.

### SP-4 · "Clock Eddy" (rewind to un-commit, delete, re-propose)
```
propose(X, now=0, window=10); status(now=20)=COMMITTED
revert(X, now=5)   # un-commits + deletes (F-04 + F-06)
propose(X', ...)   # rewrite history
```
Each call is legal; COMMITTED is not monotone and append-only is violated.

### SP-5 · "Dangling Anchor" (revert base under committed child)
```
b = propose(base, window=10); ch = propose(child, on=(b), window=10)
revert(b, now=5)            # base deleted (F-06)
# ch commits at now=20 with a base that no longer exists
```
Structured-CFG/base-first discipline broken post-hoc; the graph has a dangling edge the verifier swore it rejects.

---

## 5 · Invariant coverage matrix

| Invariant | Source | Enforced? | Where / gap |
|---|---|---|---|
| INV-1 byte-identical → same CID | TC §5 / SPEC §2 | **Asserted, broken** | int/float, ±0, NaN token (F-05); CID not verified on read (F-01) |
| INV-2 bias subtracted is logged | TC §5 | **Not implemented** | — |
| INV-3 desire never in basis | TC §5 | **Not implemented** | — |
| INV-4 L recomputed independently | TC §5 / ADR-004 D4 | **Not implemented** | F-10 |
| INV-5 unforeseen → typed hole | TC §5 | Partial / **abused** | hole bypasses checks + launders caps (F-02) |
| INV-6 degrades to plain WASM | TC §5 | **Not implemented** | §6 UNBUILT |
| INV-7 health = pure 0-AI fold | SPEC §12.4 | Partial / **poisonable** | grindable + caller-`now` (F-08); `w(n)` unbuilt |
| INV-8 radar from emissions not narration | ADR-004 D5 | **Not implemented** | F-10 |
| INV-9 global emitter content-addressed | TC §5 | **Not implemented** | `del` breaks append-only (F-06) |
| §12.2 decidable click | SPEC §12 | Enforced — but holes bypass (F-02) | |
| §12.3 base-first | SPEC §12 | Admission only, **not maintained** | reverts strand bases (F-06) |
| §12.4 ≤5 gauges | SPEC §12 | **Not enforced** | no count limit |
| §12.5 capability up DAG | SPEC §12 | **Broken** | attacker-writable grants, no root (F-03), hole-laundering (F-02) |
| §12.9 time-machine append-only | SPEC §12 | **Broken** | `del` (F-06); rewind un-commit (F-04) |
| §12.10 channel-independence | SPEC §12 | **Not implemented** | F-10 |
| ADR-005 INV-C1..C4 | ADR-005 | **Not implemented** | no comms code |

**Summary:** Of 20+ asserted invariants, ~4 are enforced (decidable click on non-holes, base-first at admission, CID-for-equal-Python-objects, weak 0-AI grep). The rest are prose; three claimed-enforced (INV-1, §12.3, §12.5, §12.9) are demonstrably broken.

---

## 6 · Residual-risk register & hardening order

| # | Finding | Sev | Fix cost | Order |
|---|---|---|---|---|
| 1 | F-01 CID not verified on read | CRIT | Low | **First** — one guarded insert + base re-hash |
| 2 | F-02 Hole bypass + cap laundering | CRIT | Low | **Second** — hole `grants=∅`, no lineage contribution, keep structural checks |
| 3 | F-03 No grant root / `by` self-grant | CRIT | Med-High (spec) | **Third** — grant root; `grants ⊆ needs`; signed genesis; resolve §OPEN granter fork for ALL caps |
| 4 | F-05 Canonical encoding | HIGH | Med | **Fourth** — canonical CBOR/JCS, normalize numbers, reject NaN/±Inf, BLAKE3-256 (folds F-09) |
| 5 | F-04 Caller-`now` time machine | HIGH | Med | monotonic logical clock; reject `window≤0`; persist commit |
| 6 | F-06 Dangling committed / `del` | HIGH | Med | never `del`; tombstone/sup; resolve cascade-vs-quarantine §OPEN fork |
| 7 | F-07 Supersede replay | MED | Low | reorder mark-then-click; add replay self-test |
| 8 | F-08 Gauge poisoning | MED | Med | rank by measured weight not CID; internal clock; `w(n)` + flag |
| 9 | F-09 128-bit digest | MED | Low | folded into F-05 (BLAKE3-256) |
| 10 | F-10 Unimplemented invariants | INFO | High | stop asserting; mark UNIMPLEMENTED |

**Verdict for the skeptic:** the first-pass is a clean demo of the *happy path* of a decidable click, but as a trust boundary it does not hold. The two claims the brief most wanted tested — "validity lives in the artifact, not the signoff" (§0) and "no un-clicked code runs" (§10) — are both falsifiable today: the artifact's identity is unverified (F-01), and an abstention launders the system's most dangerous capability (F-02). Do not ship past a hostile boundary until items 1–6 are fixed and the §OPEN granter/cascade forks are closed in the spec.

**Pen-test gate: FAIL.** Blocking: F-01, F-02, F-03 (CRITICAL); F-04, F-05, F-06 (HIGH).
