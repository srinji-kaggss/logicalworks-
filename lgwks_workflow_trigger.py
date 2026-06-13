"""lgwks_workflow_trigger — event-chain grammar for latent workflows (#121).

A single-prompt classifier (`lgwks_workflows._workflow_for_intent`) sees ONE
request; latent workflows live in **sequences across time and apps**. A trigger
is therefore a **pure predicate over the append-only #118 event log** that, when
matched, emits a #120 action **proposal** — never a direct execution. Two
properties fall out of "pure predicate over the log":
  - REPLAYABLE: evaluate over the same stored slice → identical proposals;
  - CANNOT MUTATE: its only output is a proposal handed to the #120 gate.
Both are acceptance bullets. This module does NOT import or call `lgwks_do` /
`lgwks_workflows` execution paths — `evaluate_triggers` has no I/O and no
side effects.

This is the multi-event generalisation of the single-prompt path; that path is
left intact (generalise alongside, do not delete).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import lgwks_capability_action as ca

SCHEMA = "lgwks.workflow.trigger.v1"

POLICIES = frozenset({"ask", "act"})

# Trust ordering (weakest → strongest) so a proposal inherits the WEAKEST trust
# across the events that triggered it — a chain is only as trusted as its least.
_TRUST_RANK = {"untrusted": 0, "model_proposed": 1, "deterministic": 2, "human_confirmed": 3}


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _matcher_matches(matcher: dict[str, Any], event: dict[str, Any]) -> bool:
    """One EventMatcher against one #118 event. Filters on the #118 source/kind axes."""
    if "source" in matcher and event.get("source") != matcher["source"]:
        return False
    if "kind" in matcher and event.get("kind") != matcher["kind"]:
        return False
    if "subject_kind" in matcher:
        subj = event.get("payload", {}).get("subject", {})
        if not isinstance(subj, dict) or subj.get("kind") != matcher["subject_kind"]:
            return False
    for key in matcher.get("refs_contains", []):
        if key not in (event.get("refs") or {}):
            return False
    if "payload_truthy" in matcher and not event.get("payload", {}).get(matcher["payload_truthy"]):
        return False
    return True


def _match_pattern(pattern: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Greedily match the ordered matcher sequence against an ordered event slice.

    Returns the matched events (one per matcher, in order) or None. Pure."""
    matched: list[dict[str, Any]] = []
    ei = 0
    for matcher in pattern:
        while ei < len(events) and not _matcher_matches(matcher, events[ei]):
            ei += 1
        if ei >= len(events):
            return None
        matched.append(events[ei])
        ei += 1
    return matched


def _evidence_holds(evidence: list[dict[str, Any]], matched: list[dict[str, Any]]) -> bool:
    """Declarative predicates over the matched set. Pure, deterministic."""
    for pred in evidence:
        kind = pred.get("type")
        if kind == "same_field":
            field = pred["field"]
            values = {e.get(field) for e in matched}
            if len(values) != 1:
                return False
        elif kind == "payload_truthy":
            key = pred["key"]
            if not any(e.get("payload", {}).get(key) for e in matched):
                return False
        elif kind == "within_ms":
            stamps = [t for t in (_parse_ts(e.get("ts")) for e in matched) if t is not None]
            if len(stamps) >= 2:
                span_ms = (max(stamps) - min(stamps)).total_seconds() * 1000.0
                if span_ms > float(pred["ms"]):
                    return False
        else:
            raise ValueError(f"unknown required_evidence predicate: {kind!r}")
    return True


def _weakest_trust(matched: list[dict[str, Any]]) -> str:
    trusts = [str(e.get("trust")) for e in matched if e.get("trust") in _TRUST_RANK]
    if not trusts:
        return "untrusted"
    return min(trusts, key=lambda t: _TRUST_RANK[t])


def validate_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(trigger, dict):
        raise ValueError("trigger must be a dict")
    if trigger.get("schema") != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if not trigger.get("trigger_id"):
        raise ValueError("trigger_id is required")
    if not isinstance(trigger.get("pattern"), list) or not trigger["pattern"]:
        raise ValueError("pattern must be a non-empty list of EventMatchers")
    if trigger.get("policy") not in POLICIES:
        raise ValueError(f"policy must be one of {sorted(POLICIES)}")
    conf = trigger.get("confidence")
    if not isinstance(conf, dict) or "score" not in conf or "basis" not in conf:
        raise ValueError("confidence must be {score, basis}")
    if not isinstance(trigger.get("lowers_to"), dict):
        raise ValueError("lowers_to must be a #120 action template dict")
    return trigger


def _proposal_from(trigger: dict[str, Any], matched: list[dict[str, Any]], *, known_verbs) -> dict[str, Any]:
    """Lower a matched trigger into a #120 capability.action.v1 PROPOSAL.

    Always `confirmed=False` — a trigger proposes, it never auto-confirms (an
    irreversible action still requires explicit confirmation at the #120 gate)."""
    tmpl = trigger["lowers_to"]
    proposing = matched[-1].get("event_id")
    action = ca.build_action(
        verb=tmpl["verb"],
        subject=tmpl.get("subject", {"kind": "workflow", "id": trigger["trigger_id"]}),
        effect_class=tmpl.get("effect_class", "read"),
        reversibility=tmpl.get("reversibility", "reversible"),
        required_authority=tmpl.get("required_authority", {"scopes": ["tenant:rw"]}),
        provenance={
            "proposing_event_id": proposing,
            "proposer": f"trigger:{trigger['trigger_id']}",
            "trust": _weakest_trust(matched),
        },
        preconditions=tmpl.get("preconditions", []),
        postconditions=tmpl.get("postconditions", []),
        idempotency_key=f"{trigger['trigger_id']}:{proposing}",
        confirmed=False,
        known_verbs=known_verbs,
    )
    return {
        "trigger_id": trigger["trigger_id"],
        "policy": trigger["policy"],
        "confidence": dict(trigger["confidence"]),
        "matched_event_ids": [e.get("event_id") for e in matched],
        "action": action,
    }


def evaluate_triggers(
    events: list[dict[str, Any]],
    triggers: list[dict[str, Any]],
    *,
    known_verbs: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """PURE evaluation: over an event slice, return #120 action proposals.

    No I/O, no execution — the only sink is a proposal list. `known_verbs`
    defaults to the verbs the triggers themselves declare, so evaluation stays
    hermetic (the LIVE catalog check happens later at the #120 execution gate).
    Cooldown bounds how many times one trigger fires within this slice.
    """
    if known_verbs is None:
        known_verbs = {t.get("lowers_to", {}).get("verb") for t in triggers if t.get("lowers_to")}
        known_verbs = {v for v in known_verbs if v}

    proposals: list[dict[str, Any]] = []
    for trigger in triggers:
        validate_trigger(trigger)
        cooldown = trigger.get("cooldown") or {}
        max_fires = int(cooldown.get("max_fires", 1))
        fires = 0
        window = list(events)
        while fires < max_fires:
            matched = _match_pattern(trigger["pattern"], window)
            if matched is None or not _evidence_holds(trigger.get("required_evidence", []), matched):
                break
            proposals.append(_proposal_from(trigger, matched, known_verbs=known_verbs))
            fires += 1
            # advance past the first matched event so a re-scan finds a later chain
            first_idx = window.index(matched[0])
            window = window[first_idx + 1:]
    return proposals
