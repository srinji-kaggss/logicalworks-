# Step 0 — The Physics (Ontology)

> **The bottom rung.** Before alphabet, before syntax, before types: what *exists* in this world,
> and what *laws* govern existence. A creator decides the substances and the conservation laws
> first; everything above (steps 1–6) is forced to obey what is fixed here. Postures, not jargon.
>
> Parent: `../RECONCILE.md` (purpose/identity). This file is layer 00 of the bottom-up spec ladder.

---

## 0.0 — The void, and the one inversion

Most languages begin from **permission**: by default a program may touch memory, call the OS, copy
any value, and *claim* completion. Safety is then *subtracted* — sandboxes, linters, reviews bolted
on top. Every subtraction can be forgotten; that is where AI-written code bleeds (forgeable tokens,
ambient auth, dead capability checks — see RECONCILE §6).

**We invert the default.** The world begins **empty**: no authority, no duplication, no effect, no
"done." Nothing is permitted by ambient right. Power *exists only by being handed a thing that
carries it.* Existence is **granted, never assumed.**

This single inversion is the ontological root of blast-radius-zero (RECONCILE §4.5): you cannot
lose what was never ambiently held; a compromised unit started from nothing and can only hold what
it was explicitly given.

---

## 0.1 — The one substance: the **linear resource**

Everything that carries power is one substance: a **linear resource** — a thing that

- **exists exactly once** (cannot be copied, cloned, or duplicated),
- can be **moved** (handed on) or **split by attenuation** (handed on *narrower*),
- can **never be amplified** (no operation widens authority).

Capability = memory ownership = quantum no-cloning = "authority only shrinks downhill." These were
never different ideas. They are one substance with one conservation law:

> **Conservation of authority:** across any hand-off, authority out ≤ authority in. Never more.

(In the code today this substance is *almost* present — `ConfirmToken` is single-use, `TrustBin`
refuses to order itself — but everything `derives Clone`, so the conservation law leaks. Here it
does not leak: non-duplicability is a property of the substance, not a convention.)

---

## 0.2 — The one law: the **proof obligation**

Nothing **is** until its proof discharges.

A construct that has not discharged its obligation does not *exist as valid* — it is not "flagged,"
not "warned," not "TODO." It has no completed form. **"Done" is unreachable without a discharged
proof.** Math has no vibe; this is the forcing function against AI hand-waving (the measured
refinement-decay 2.1→6.2 vulns/sample is a decay of *vibe*; proof has no such gradient).

Refinement types where the property is clean; SMT/Z3 where it is not. The *law* is the same
regardless of which discharges it: **becoming requires proof.**

---

## 0.3 — The one body: the **unit** (node)

The world is made of **units**. A unit is the smallest thing that can *hold* resources, *run*, and
be *addressed*. Three innate properties:

- **Identity is content.** A unit's name *is* the hash of what it is. Change one byte → a different
  unit, not a changed one. Tamper-evidence is structural, not checked. ("Nobody changes a node; its
  keeper supersedes it by publishing a new hash and re-pointing the name.")
- **Ephemeral as instance, durable as record.** The *running* unit is disposable — reset = `/clear`
  = reload, leaving no foothold. The *record* persists by supersession (content-address + vault +
  CRDT). Reset destroys the instance, never the canonical data.
- **A unit is a boundary.** Its edge is real because the floor (the IR/WASM sandbox, step 6) makes
  it real: a unit can reach only what it was handed; everything else is not *forbidden* — it is
  *unreachable*.

A hack therefore lands on one unit among millions, holding only its attenuated grant, persisting
nothing. That is the whole security model, stated as ontology.

---

## 0.4 — Legality is structural, not policed

A thing that would violate the laws of 0.1–0.3 is **not forbidden by a rulebook — it has no
representable form.** No bytes encode it. There is nothing to scan for, because the illegal thing
was never spellable.

Corollary — **door-check once, then run free:** legality is established a single time at admission
by re-deriving it from the bytes themselves (proof-carrying; ignore signatures, humans, and AI
say-so). After admission there is **no runtime patrol** — no security-GC, no always-on scanner.
Two no-GCs fall out together: ownership ⇒ no memory garbage collector; door-check-once ⇒ no
security garbage collector. The unit is a border guard with a self-verifying passport, not a
janitor.

---

## 0.5 — What is *not* in this world

These are not "disallowed operations." They are **permanent residents of the void** — they have no
name, no symbol, no encoding, and step 1 (the Alphabet) will simply not contain them:

- ambient authority (power not carried by a handed resource)
- duplication of a linear resource (copy/clone/replay of authority)
- arbitrary memory access
- arbitrary syscalls / unmediated effects
- completion without a discharged proof ("done" by assertion)
- amplification of authority across a hand-off

Everything that follows is built *only* from what remains.

---

## Invariants this layer fixes for all layers above

1. Default = nothing; power is granted by a carried resource (0.0).
2. Authority is a non-duplicable substance; out ≤ in, always (0.1).
3. Valid existence requires a discharged proof (0.2).
4. The unit of the world is content-addressed, ephemeral-as-instance, a real boundary (0.3).
5. Illegality is non-representation, checked once at admission, never patrolled (0.4).
6. The void list (0.5) is closed and cannot be re-opened by any higher layer.

---

## Open questions surfaced at this layer (for later steps / director)
- **Q0.1** Is *every* value a linear resource, or only authority-bearing ones? (Plain data —
  numbers, immutable text — likely *non-linear/freely-copyable*; only resources carry the law.
  Decide the boundary in step 2/4.)
- **Q0.2** Granularity of a "unit" — one function? one widget? one actor? The mesh is "millions of
  units," so the unit is small, but *how* small is a step-2/3 decision.
- **Q0.3** Proof *cost*: refinement+SMT is not free. What is the discharge budget per unit, and the
  reset-to-seed cap (RECONCILE §4.2 says 3)? Step 4.
