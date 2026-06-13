"""lgwks_daemon_event — normalized daemon event envelope for shared referee runtime.

This is the first stable process-boundary contract for the daemon core.

It unifies ingress and telemetry events under one schema so Claude/Codex/Gemini
adapters can submit equivalent envelopes without teaching the core separate
dialects. The envelope is intentionally metadata-first: callers should prefer
content-addressed refs in `payload` over raw text whenever possible.

v2 (#118 — "event_envelope"): additive superset of v1. Every new field is
OPTIONAL and every enum is widened as a superset, so v1 records still validate
unchanged (back-compat) and existing readers are not broken. The new axes are:
  - `source`  — WHERE the event entered (speech/text/browser/repo/terminal/
    model/workflow/artifact), orthogonal to `kind` (the semantic event type).
  - `payload_cid` — content-address of an out-of-band payload (`b2b256:<hex>`),
    reusing the axiom CID scheme; inline `payload` stays for small events.
  - `trust` — trust class of the event (human_confirmed/deterministic/
    model_proposed/untrusted); model output is untrusted until typed.
  - `provenance` — `{derived_from, producer, producer_version}`; every derived
    fact points back to its source events/artifacts.
  - `replay` — `{seq, deterministic, schema_from}`; migration/replay metadata.
`source` and `trust` are the locked public join keys read by #120/#121/#122/#124.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from axiom.cid import CID_ALG

SCHEMA = "lgwks.daemon.event.v2"  # current/default emitted contract
SCHEMA_V1 = "lgwks.daemon.event.v1"  # legacy; still accepted by validate_event
VALID_SCHEMAS = frozenset({SCHEMA_V1, SCHEMA})

LANES = frozenset({"ingress", "telemetry", "workflow", "control"})
# v2 superset: v1 kinds (semantic event types) + source-aligned kinds. Old
# values remain valid; new ones cover the issue's source-coverage list.
KINDS = frozenset({
    "human_message",
    "transcript_turn",
    "tool_call",
    "file_change",
    "workflow_event",
    # v2 additions (superset)
    "browser_action",
    "repo_diff",
    "terminal_output",
    "model_output",
    "artifact_emit",
})
SCOPES = frozenset({"agent_local", "shared_referee"})
ACTORS = frozenset({"human", "agent", "daemon", "system"})
CLIENTS = frozenset({"claude", "codex", "gemini", "human", "daemon", "system", "unknown"})

# v2 axes (all optional on the envelope).
SOURCES = frozenset({
    "speech", "text", "browser", "repo", "terminal", "model", "workflow", "artifact",
})
TRUST_CLASSES = frozenset({
    "human_confirmed", "deterministic", "model_proposed", "untrusted",
})

_ID_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,128}$")
# Content-address shape: reuse the axiom CID scheme (`<alg>:<64-hex>`). Pinning
# the alg prefix to axiom's CID_ALG keeps a single hashing scheme across the repo.
_CID_RE = re.compile(rf"^{re.escape(CID_ALG)}:[0-9a-f]{{64}}$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{name} must match {_ID_RE.pattern}")
    return value


def _require_choice(name: str, value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        opts = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {opts}")
    return value


def _canonical_body(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_id_for(record: dict[str, Any]) -> str:
    body = _canonical_body(record)
    digest = hashlib.blake2b(body.encode("utf-8"), digest_size=16).hexdigest()
    return f"evt-{digest}"


def validate_event(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a daemon event envelope and return it unchanged on success."""
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")

    required = {
        "schema", "event_id", "ts", "tenant_id", "agent_id", "session_id",
        "actor", "client", "lane", "kind", "scope", "payload",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    if record["schema"] not in VALID_SCHEMAS:
        opts = ", ".join(sorted(VALID_SCHEMAS))
        raise ValueError(f"schema must be one of: {opts}")

    for key in ("event_id", "tenant_id", "agent_id", "session_id"):
        _require_id(key, record[key])

    _require_choice("actor", record["actor"], ACTORS)
    _require_choice("client", record["client"], CLIENTS)
    _require_choice("lane", record["lane"], LANES)
    _require_choice("kind", record["kind"], KINDS)
    _require_choice("scope", record["scope"], SCOPES)

    if not isinstance(record["payload"], dict):
        raise ValueError("payload must be a dict")
    if "refs" in record and not isinstance(record["refs"], dict):
        raise ValueError("refs must be a dict when present")
    if "causal_parent_id" in record:
        _require_id("causal_parent_id", record["causal_parent_id"])

    # v2 optional axes — validated only when present (back-compat: absent → v1-shaped).
    if "source" in record:
        _require_choice("source", record["source"], SOURCES)
    if "trust" in record:
        _require_choice("trust", record["trust"], TRUST_CLASSES)
    if "payload_cid" in record:
        # SHAPE only — the envelope cannot re-derive a CID for out-of-band bytes it
        # does not hold. Integrity (bytes actually hash to this CID) MUST be
        # re-checked with axiom.cid.require_cid at the store/resolve boundary that
        # has the bytes (AUDIT F-01: verify, don't trust). A valid-shaped CID here
        # is NOT proof the payload matches.
        cid = record["payload_cid"]
        if not isinstance(cid, str) or not _CID_RE.fullmatch(cid):
            raise ValueError(f"payload_cid must match {_CID_RE.pattern}")
    if "provenance" in record:
        prov = record["provenance"]
        if not isinstance(prov, dict):
            raise ValueError("provenance must be a dict when present")
        if "derived_from" in prov and not isinstance(prov["derived_from"], list):
            raise ValueError("provenance.derived_from must be a list when present")
    if "replay" in record:
        replay = record["replay"]
        if not isinstance(replay, dict):
            raise ValueError("replay must be a dict when present")
        if "deterministic" in replay and not isinstance(replay["deterministic"], bool):
            raise ValueError("replay.deterministic must be a bool when present")
        if replay.get("schema_from") not in (None, SCHEMA_V1):
            raise ValueError(f"replay.schema_from must be {SCHEMA_V1} or null")

    try:
        datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError("ts must be an ISO-8601 timestamp") from exc

    try:
        json.dumps(record["payload"], sort_keys=True, ensure_ascii=True)
        for opt in ("refs", "provenance", "replay"):
            if opt in record:
                json.dumps(record[opt], sort_keys=True, ensure_ascii=True)
    except TypeError as exc:
        raise ValueError("payload/refs/provenance/replay must be JSON-serializable") from exc

    return record


def build_event(
    *,
    tenant_id: str,
    agent_id: str,
    session_id: str,
    actor: str,
    client: str,
    lane: str,
    kind: str,
    scope: str,
    payload: dict[str, Any],
    refs: dict[str, Any] | None = None,
    causal_parent_id: str | None = None,
    ts: str | None = None,
    event_id: str | None = None,
    source: str | None = None,
    trust: str | None = None,
    payload_cid: str | None = None,
    provenance: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a validated daemon event envelope (v2).

    If `event_id` is omitted, it is derived deterministically from the canonical
    event body so adapters can dedupe identical submissions safely. The v2 axes
    (`source`/`trust`/`payload_cid`/`provenance`/`replay`) are optional and, when
    supplied, participate in the canonical body so identical inputs hash alike.
    """
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": ts or _now(),
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "session_id": session_id,
        "actor": actor,
        "client": client,
        "lane": lane,
        "kind": kind,
        "scope": scope,
        "payload": payload,
    }
    if refs:
        record["refs"] = refs
    if causal_parent_id:
        record["causal_parent_id"] = causal_parent_id
    if source is not None:
        record["source"] = source
    if trust is not None:
        record["trust"] = trust
    if payload_cid is not None:
        record["payload_cid"] = payload_cid
    if provenance:
        record["provenance"] = provenance
    if replay:
        record["replay"] = replay

    provisional = dict(record)
    provisional["event_id"] = event_id or _event_id_for(record)
    return validate_event(provisional)


def upgrade_v1_to_v2(record: dict[str, Any]) -> dict[str, Any]:
    """Project a stored v1 event into the v2 envelope WITHOUT recomputing its id.

    Lazy back-compat adapter (build-the-basement seam for #122's packet read path):
    a historical `lgwks.daemon.event.v1` record is returned as a valid v2 record
    with the new axes filled from what v1 already carries — `source` inferred from
    `kind`, a conservative `trust=deterministic` default, and `replay.schema_from`
    marking the upgrade. The original `event_id` is PRESERVED (never re-derived) so
    content identity and dedupe stay stable across the version line. A record that
    is already v2 is returned unchanged.
    """
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    if record.get("schema") == SCHEMA:
        return record
    if record.get("schema") != SCHEMA_V1:
        raise ValueError(f"upgrade_v1_to_v2 expects {SCHEMA_V1}, got {record.get('schema')!r}")

    upgraded = dict(record)
    upgraded["schema"] = SCHEMA
    kind = str(record.get("kind") or "")
    upgraded.setdefault("source", _SOURCE_FROM_KIND.get(kind, "text"))
    # Default trust by kind to the WEAKEST appropriate class — NEVER blanket
    # "deterministic" for model-origin events (model output is untrusted until
    # typed). An existing trust value is preserved (setdefault); only legacy v1
    # records that lacked the field are labelled, and conservatively.
    upgraded.setdefault("trust", _TRUST_FROM_KIND.get(kind, "model_proposed"))
    replay = dict(upgraded.get("replay") or {})
    replay.setdefault("schema_from", SCHEMA_V1)
    replay.setdefault("deterministic", True)
    upgraded["replay"] = replay
    return validate_event(upgraded)


# Inference table for the lazy v1→v2 upgrade: map a v1 `kind` to its `source` axis.
_SOURCE_FROM_KIND = {
    "human_message": "text",
    "transcript_turn": "text",
    "tool_call": "model",
    "file_change": "repo",
    "workflow_event": "workflow",
}

# Conservative trust default per kind for the lazy v1→v2 upgrade. Model-origin
# kinds default to model_proposed (never deterministic); only system/repo-derived
# kinds are deterministic; human messages are human_confirmed.
_TRUST_FROM_KIND = {
    "human_message": "human_confirmed",
    "transcript_turn": "model_proposed",
    "tool_call": "model_proposed",
    "model_output": "model_proposed",
    "browser_action": "model_proposed",
    "file_change": "deterministic",
    "repo_diff": "deterministic",
    "terminal_output": "deterministic",
    "workflow_event": "deterministic",
    "artifact_emit": "deterministic",
}


def add_parser(sub) -> None:
    daemon = sub.add_parser("daemon-event", help="build or validate daemon event envelopes")
    daemon_sub = daemon.add_subparsers(dest="daemon_event_command", required=True)

    build = daemon_sub.add_parser("build", help="build a daemon event envelope")
    build.add_argument("--tenant-id", required=True)
    build.add_argument("--agent-id", required=True)
    build.add_argument("--session-id", required=True)
    build.add_argument("--actor", required=True, choices=sorted(ACTORS))
    build.add_argument("--client", required=True, choices=sorted(CLIENTS))
    build.add_argument("--lane", required=True, choices=sorted(LANES))
    build.add_argument("--kind", required=True, choices=sorted(KINDS))
    build.add_argument("--scope", required=True, choices=sorted(SCOPES))
    build.add_argument("--payload", required=True, help="JSON object")
    build.add_argument("--refs", help="JSON object")
    build.add_argument("--causal-parent-id")
    build.add_argument("--event-id")
    build.add_argument("--source", choices=sorted(SOURCES), help="v2: where the event entered")
    build.add_argument("--trust", choices=sorted(TRUST_CLASSES), help="v2: trust class")
    build.add_argument("--payload-cid", help="v2: content-address of an out-of-band payload")
    build.add_argument("--provenance", help="v2: JSON object {derived_from,producer,producer_version}")
    build.add_argument("--replay", help="v2: JSON object {seq,deterministic,schema_from}")
    build.set_defaults(func=_build_command)

    validate = daemon_sub.add_parser("validate", help="validate a daemon event envelope from stdin")
    validate.set_defaults(func=_validate_command)


def _build_command(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload)
    refs = json.loads(args.refs) if args.refs else None
    provenance = json.loads(args.provenance) if getattr(args, "provenance", None) else None
    replay = json.loads(args.replay) if getattr(args, "replay", None) else None
    record = build_event(
        tenant_id=args.tenant_id,
        agent_id=args.agent_id,
        session_id=args.session_id,
        actor=args.actor,
        client=args.client,
        lane=args.lane,
        kind=args.kind,
        scope=args.scope,
        payload=payload,
        refs=refs,
        causal_parent_id=args.causal_parent_id,
        event_id=args.event_id,
        source=getattr(args, "source", None),
        trust=getattr(args, "trust", None),
        payload_cid=getattr(args, "payload_cid", None),
        provenance=provenance,
        replay=replay,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def _validate_command(_: argparse.Namespace) -> int:
    record = json.load(sys.stdin)
    validate_event(record)
    print(json.dumps({"ok": True, "schema": SCHEMA, "event_id": record["event_id"]}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgwks_daemon_event")
    sub = parser.add_subparsers(dest="command", required=True)
    add_parser(sub)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
