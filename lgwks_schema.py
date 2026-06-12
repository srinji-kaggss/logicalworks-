"""
lgwks_schema — schema registry for next-agent discovery.

Every lgwks artifact carries a versioned schema (e.g. lgwks.spawn.v1). This module
provides a registry of all known schemas so the next AI can discover what data
shapes are available without reading source code.

Schema discovery is static: the registry is built at import time by scanning
the lgwks codebase for schema declarations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _scan_schemas(root: Path) -> dict[str, dict[str, Any]]:
    """Scan lgwks modules for schema declarations.

    Matches patterns like:
      - schema = "lgwks.foo.v1"
      - SCHEMA = "lgwks.foo.v0"
      - "schema": "lgwks.foo.v0"
      - CAPTURE_SCHEMA = "lgwks.capture.v1"
    """
    schemas: dict[str, dict[str, Any]] = {}
    # Regex for schema string literals in Python files
    pattern = re.compile(r'["\']?((?:lgwks\.[a-z-]+\.(?:v[0-9]+|v[0-9]+\.[0-9]+)))["\']?')
    # Also match variable declarations
    decl_pattern = re.compile(
        r'^(?:\s*(?:schema|SCHEMA|INTENT_SCHEMA|PORTAL_SCHEMA|CAPTURE_SCHEMA|AUDIT_SCHEMA|REGISTRY_SCHEMA)\s*[:=]\s*)'
        r'["\']?((?:lgwks\.[a-z-]+\.(?:v[0-9]+|v[0-9]+\.[0-9]+)))["\']?'
    )

    for pyfile in sorted(root.glob("lgwks_*.py")):
        text = pyfile.read_text(errors="ignore")
        found: set[str] = set()
        for line in text.splitlines():
            m = decl_pattern.match(line)
            if m:
                found.add(m.group(1))
            else:
                # Also find inline schema references
                for match in pattern.finditer(line):
                    found.add(match.group(1))
        for s in found:
            if s not in schemas:
                schemas[s] = {"name": s, "source": pyfile.name, "discovered_in": []}
            schemas[s]["discovered_in"].append(pyfile.name)

    return schemas


def _build_registry() -> dict[str, dict[str, Any]]:
    """Build the schema registry from the lgwks codebase."""
    root = Path(__file__).parent
    schemas = _scan_schemas(root)

    # Manual annotations for known schemas (descriptions from code context)
    annotations: dict[str, dict[str, Any]] = {
        "lgwks.manifest.v0": {
            "description": "Machine-readable contract: every verb, capability, schema",
            "output": "JSON with verbs, domains, tokens",
        },
        "lgwks.do.run.v1": {
            "description": "Unified orchestrator run artifact with per-phase results",
            "output": "JSON with phases, commands, verdicts",
        },
        "lgwks.review.v0": {
            "description": "Graph-aware code review + proposed git actions",
            "output": "JSON with findings, diffs, proposals",
        },
        "lgwks.debug.v0": {
            "description": "Automated debugging: run, parse, propose fix",
            "output": "JSON with reproduction, root_cause, patch_verdict",
        },
        "lgwks.gh.v0": {
            "description": "GitHub surface: issues, PRs, state maps, hardening",
            "output": "JSON with issues, PRs, checks",
        },
        "lgwks.intent.v0": {
            "description": "Schema-driven intent router: declare, probe, act",
            "output": "JSON with project, repo, issue, pr, context, goal, next_if",
        },
        "lgwks.portal.v1": {
            "description": "Deterministic project/portal keys and coding-agent context packets",
            "output": "Stored packet under .lgwks/portals/ plus JSON stdout",
        },
        "lgwks.capture.v1": {
            "description": "Unified operator-facing capture compiler over substrate + portal",
            "output": "Stored packet under store/captures/ plus JSON stdout",
        },
        "lgwks.jepa.v1": {
            "description": "Multi-view package surface over capture + portal",
            "output": "Packet with latent anchors, machine packet, and human projection",
        },
        "lgwks.graph.v2": {
            "description": "Deterministic code-graph queries (impact, complexity, path)",
            "output": "Cypher-like graph JSON",
        },
        "lgwks.graph.v1": {
            "description": "Legacy code-graph schema",
            "output": "Graph JSON",
        },
        "lgwks.hooks.v0": {
            "description": "Comprehensive audit-first hook system",
            "output": "Hook registry JSON",
        },
        "lgwks.audit.v0": {
            "description": "Audit log entry for hook events",
            "output": "Audit event JSON",
        },
        "lgwks.hooks-registry.v0": {
            "description": "Hook registry schema",
            "output": "Registry JSON",
        },
        "lgwks.axiom.run_index.v0": {
            "description": "Verified byte-layer harness run index",
            "output": "Run index JSON",
        },
        "lgwks.crawl.v0": {
            "description": "Single-page browser fetch/extract result",
            "output": "Crawl result JSON with text, links, metadata",
        },
        "lgwks.session.summary.v0": {
            "description": "Session boundary analyzer summary",
            "output": "JSON with commits, reflog, branches, dirty state, r_meter",
        },
        "lgwks.spawn.v1": {
            "description": "AI-AI handoff packet: AUP verdict + context + capabilities + provenance",
            "output": "Spawn packet JSON",
        },
        "lgwks.algebra.v0": {
            "description": "Mathematical expression evaluation result",
            "output": "JSON with expression, result, units",
        },
        "lgwks.thought.v0": {
            "description": "Thought/think artifact from solve operations",
            "output": "JSON with thoughts, claims, evidence",
        },
        "lgwks.solve.v0": {
            "description": "Problem solution artifact",
            "output": "JSON with problem, solution, steps",
        },
        "lgwks.jarvis.substrate_crawl.v0": {
            "description": "Substrate engine crawl result for URL sources",
            "output": "JSON with artifact paths, engine=substrate",
        },
        "lgwks.schema.relations.v2": {
            "description": "D0 relation schema: 8 directed typed-triple relations for RESCAL order-3 scoring; v2 activates directional antisymmetric operators (I5.1), marginal stays identity",
            "output": "JSON with schema, relations list",
        },
        "lgwks.score.record.v1": {
            "description": "Scored triple output: RESCAL score + MDL conformance + content CID (I5)",
            "output": "JSON with triple, score, score_mdl, cid, schema_id, s_ai",
        },
        "lgwks.daemon.event.v1": {
            "description": "Normalized daemon event envelope for ingress, telemetry, workflow, and control lanes",
            "output": "JSON with tenant/session/agent attribution plus lane, kind, scope, refs, payload",
        },
        "lgwks.daemon.events.query.v0": {
            "description": "Daemon event-log query result envelope",
            "output": "JSON with count and stored lgwks.daemon.event.v1 items",
        },
        "lgwks.daemon.sessions.query.v0": {
            "description": "Daemon tenant session-head query result envelope",
            "output": "JSON with count and per-session daemon head rows",
        },
        "lgwks.daemon.status.v0": {
            "description": "Daemon lifecycle status envelope",
            "output": "JSON with lock, pid, heartbeat, transcript path, and event store state",
        },
        "lgwks.daemon.doctor.v0": {
            "description": "Daemon readiness/health report",
            "output": "JSON with root/store/transcript checks and stale-lock reap status",
        },
    }

    for name, ann in annotations.items():
        if name in schemas:
            schemas[name].update(ann)
        else:
            schemas[name] = {"name": name, **ann, "discovered_in": []}

    return schemas


_REGISTRY = _build_registry()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_parser(sub) -> None:
    schema = sub.add_parser("schema", help="schema registry for next-agent discovery")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)

    ls = schema_sub.add_parser("ls", help="list all known schemas")
    ls.add_argument("--json", action="store_true", help="structured output")
    ls.add_argument("--domain", help="filter by domain prefix (e.g. 'lgwks.spawn')")
    ls.set_defaults(func=_schema_ls_command)

    show = schema_sub.add_parser("show", help="show details for a specific schema")
    show.add_argument("name", help="schema name (e.g. lgwks.spawn.v1)")
    show.add_argument("--json", action="store_true", help="structured output")
    show.set_defaults(func=_schema_show_command)


def _schema_ls_command(args: argparse.Namespace) -> int:
    domain_filter = getattr(args, "domain", None)
    schemas = _REGISTRY
    if domain_filter:
        schemas = {k: v for k, v in schemas.items() if k.startswith(domain_filter)}

    items = [
        {
            "name": v["name"],
            "description": v.get("description", "(no description)"),
            "source": v.get("source", "unknown"),
        }
        for v in sorted(schemas.values(), key=lambda x: x["name"])
    ]

    if getattr(args, "json", False):
        print(json.dumps({"schema": "lgwks.schema.registry.v0", "count": len(items), "items": items}, indent=2))
    else:
        print(f"  {len(items)} schema(s) registered")
        for item in items:
            print(f"    {item['name']:<40} {item['source']:<25} {item['description'][:50]}")
    return 0


def _schema_show_command(args: argparse.Namespace) -> int:
    name = args.name
    if name not in _REGISTRY:
        msg = f"unknown schema: {name}"
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    entry = _REGISTRY[name]
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "schema": entry}, indent=2, sort_keys=True))
    else:
        print(f"  {entry['name']}")
        print(f"    description: {entry.get('description', '(none)')}")
        print(f"    output:      {entry.get('output', '(none)')}")
        print(f"    source:      {entry.get('source', 'unknown')}")
        if entry.get("discovered_in"):
            print(f"    found in:    {', '.join(set(entry['discovered_in']))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="lgwks_schema")
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("ls", help="list schemas")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--domain", help="filter by domain")
    ls.set_defaults(func=lambda a: _schema_ls_command(a))

    show = sub.add_parser("show", help="show schema details")
    show.add_argument("name", help="schema name")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=lambda a: _schema_show_command(a))

    parsed = parser.parse_args(args)
    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
