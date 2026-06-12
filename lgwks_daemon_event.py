"""lgwks_daemon_event — normalized daemon event envelope for shared referee runtime.

This is the first stable process-boundary contract for the daemon core.

It unifies ingress and telemetry events under one schema so Claude/Codex/Gemini
adapters can submit equivalent envelopes without teaching the core separate
dialects. The envelope is intentionally metadata-first: callers should prefer
content-addressed refs in `payload` over raw text whenever possible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA = "lgwks.daemon.event.v1"

LANES = frozenset({"ingress", "telemetry", "workflow", "control"})
KINDS = frozenset({
    "human_message",
    "transcript_turn",
    "tool_call",
    "file_change",
    "workflow_event",
})
SCOPES = frozenset({"agent_local", "shared_referee"})
ACTORS = frozenset({"human", "agent", "daemon", "system"})
CLIENTS = frozenset({"claude", "codex", "gemini", "human", "daemon", "system", "unknown"})

_ID_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,128}$")


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

    if record["schema"] != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")

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

    try:
        datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError("ts must be an ISO-8601 timestamp") from exc

    try:
        json.dumps(record["payload"], sort_keys=True, ensure_ascii=True)
        if "refs" in record:
            json.dumps(record["refs"], sort_keys=True, ensure_ascii=True)
    except TypeError as exc:
        raise ValueError("payload/refs must be JSON-serializable") from exc

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
) -> dict[str, Any]:
    """Build a validated daemon event envelope.

    If `event_id` is omitted, it is derived deterministically from the canonical
    event body so adapters can dedupe identical submissions safely.
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

    provisional = dict(record)
    provisional["event_id"] = event_id or _event_id_for(record)
    return validate_event(provisional)


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
    build.set_defaults(func=_build_command)

    validate = daemon_sub.add_parser("validate", help="validate a daemon event envelope from stdin")
    validate.set_defaults(func=_validate_command)


def _build_command(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload)
    refs = json.loads(args.refs) if args.refs else None
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
