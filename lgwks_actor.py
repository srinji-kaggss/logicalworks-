"""lgwks_actor — U2 Actor contract (second-harness PRD §12, L1).

ONE thin protocol every capability conforms to:

    input_schema  →  run(input)  →  {schema, actor, ok, input, output, manifest}

Composable: an actor's run() calls run_actor(other, …) — same interface, nestable.
This is a wrapper protocol over existing functions (lgwks_map, lgwks_ingest), NOT a
new engine. //why Karpathy simplicity: the shapes already exist; U2 just standardizes
the envelope + typed input validation so actors chain without custom glue.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable


class ActorError(Exception):
    """Typed failure: unknown actor, or input that violates the declared schema.
    Carries a machine code so callers can branch (no silent failure / bare strings)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class ActorSpec:
    name: str
    summary: str
    input_schema: dict[str, dict[str, Any]]      # field -> {type, required, default, help}
    run: Callable[[dict[str, Any]], dict[str, Any]]
    composes: tuple[str, ...] = ()               # actors this one may call


REGISTRY: dict[str, ActorSpec] = {}


def register(spec: ActorSpec) -> None:
    REGISTRY[spec.name] = spec


_COERCE: dict[str, Callable[[Any], Any]] = {
    "str": str,
    "int": int,
    "bool": lambda v: v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes"),
}


def _validate(raw: dict[str, Any], schema: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the declared schema: required-check, type-coerce, defaults. Typed errors only."""
    out: dict[str, Any] = {}
    for fname, fspec in schema.items():
        if fname in raw and raw[fname] is not None:
            try:
                out[fname] = _COERCE.get(fspec.get("type", "str"), lambda v: v)(raw[fname])
            except (ValueError, TypeError) as exc:
                raise ActorError("bad_input", f"field {fname!r} is not a valid {fspec.get('type')}: {exc}")
        elif fspec.get("required"):
            raise ActorError("missing_input", f"required field {fname!r} ({fspec.get('help', '')})")
        elif "default" in fspec:
            out[fname] = fspec["default"]
    return out


def run_actor(name: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    """Invoke an actor by name. The single entry point — actors call this to compose."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise ActorError("unknown_actor", f"{name!r}; known: {sorted(REGISTRY)}")
    validated = _validate(raw_input or {}, spec.input_schema)
    t0 = time.time()
    output = spec.run(validated)
    return {
        "schema": "lgwks.actor.v1",
        "actor": name,
        "ok": True,
        "input": validated,
        "output": output,
        "manifest": {"duration_sec": round(time.time() - t0, 3), "composes": list(spec.composes)},
    }


# ── First actors (wrap existing functions) ────────────────────────────────────

def _run_map(inp: dict[str, Any]) -> dict[str, Any]:
    import lgwks_map
    return lgwks_map.map_intent(inp["intent"], top=inp.get("top", 8))


def _run_ingest(inp: dict[str, Any]) -> dict[str, Any]:
    import lgwks_ingest
    return lgwks_ingest.ingest(inp["url"], max_resources=inp.get("max_resources", 40),
                               embed_media=inp.get("embed_media", True))


_URL_RE = re.compile(r"^https?://", re.I)


def _run_scout(inp: dict[str, Any]) -> dict[str, Any]:
    """Composing actor: always map the intent; if it's a URL, also ingest it.
    //why: proves actor-calls-actor at runtime — it invokes other actors via run_actor."""
    intent = inp["intent"]
    mapped = run_actor("map", {"intent": intent})
    ingested = run_actor("ingest", {"url": intent}) if _URL_RE.match(intent) else None
    return {"mapped": mapped, "ingested": ingested}


register(ActorSpec("map", "rank lgwks verbs relevant to an intent",
                   {"intent": {"type": "str", "required": True, "help": "what you want to do"},
                    "top": {"type": "int", "default": 8}}, _run_map))
register(ActorSpec("ingest", "crawl a URL → fact/media artifact tree",
                   {"url": {"type": "str", "required": True, "help": "page to ingest"},
                    "max_resources": {"type": "int", "default": 40},
                    "embed_media": {"type": "bool", "default": True}}, _run_ingest))
register(ActorSpec("scout", "map an intent and, if it is a URL, ingest it",
                   {"intent": {"type": "str", "required": True, "help": "intent or URL"}},
                   _run_scout, composes=("map", "ingest")))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"usage: python3 lgwks_actor.py <actor> '<json input>'\nactors: {sorted(REGISTRY)}")
        raise SystemExit(2)
    actor_name = sys.argv[1]
    payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        print(json.dumps(run_actor(actor_name, payload), indent=2, default=str))
    except ActorError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "detail": exc.detail}}, indent=2))
        raise SystemExit(1)
