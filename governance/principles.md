# Logical Works Principles

## Clause 1 — Who we exist for

Logical Works exists for operators who run businesses where trust is the product: financial advisors, legal professionals, agencies with fiduciary duties, and independent contractors whose reputation is their balance sheet. We build software that makes their operational reasoning legible, auditable, and durable.

## Clause 2 — What we will not build

We will not build features whose primary purpose is to obscure, deceive, or automate harm. This includes tools designed to evade compliance, flood inboxes, or manipulate counterparties. We ship software our grandmothers would understand and our regulators would approve.

## Clause 3 — How we decide

Every feature ships with a rollback path, an audit trail, and a human who owns it. No autonomous system makes unreviewed decisions that affect customer data or customer trust. The person who writes the code is accountable for its failure modes.

## Clause 4 — We will publish our limits

Logical Works maintains a public Acceptable Use Policy that names the categories of business we will not serve and the conduct we will not support on-platform. The policy is enforced, not decorative. See [`governance/aup.md`](aup.md).

## Clause 5 — Security is a fallback stack

No single control prevents a bad operation. Every sensitive action passes through: schema validation → capability check → cost gate → audit log. Bypassing a layer requires an explicit decision, a named owner, and a ticket number.

## Clause 6 — We fix what we break

A failure after our change is ours. We name it, we fix it, we verify the fix, and we leave evidence that the invariant now holds. No "probably fine." No "works on my machine." Only demonstrated correctness.
