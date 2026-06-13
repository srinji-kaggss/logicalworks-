"""lgwks_capability_action — the execution boundary (#120).

The single chokepoint between *proposal* and *mutation* (spec §1.1 + §4): a model
can PROPOSE, but the daemon executes only typed capabilities. The only way state
changes is

    text/intent → compiled ACTION PROPOSAL → validate_action (gate) → the Hand executes

If model text could reach a mutation without passing a validated action envelope,
this contract has failed — that is the negative acceptance test.

Distinct from `lgwks.capability.v2` (an auth *token*: tenant/nonce/sig/scopes).
An action *references* the authority it needs; it is not the token. `verb` MUST be
a member of the live capability vocabulary (`lgwks.map.v1`, the `lgwks manifest`
verb catalog) — unknown verb → reject. The verifier (`postconditions`) and
undo/compensation machinery are shaped now but may be stubbed behind the seam;
#121 lowers triggers into this contract and the future WASM/Axiom capability-port
(spec §2) extends it rather than refactoring.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Iterable

from lgwks_capability import _KNOWN_SCOPES  # tier scopes: tenant:rw / world:r / world:promote
from lgwks_daemon_event import TRUST_CLASSES  # provenance trust rides from the #118 event

SCHEMA = "lgwks.capability.action.v1"

# Effect is DECLARED, not inferred — the gate reasons over what the caller declares.
EFFECT_CLASSES = frozenset({"read", "write", "network", "spawn", "delete", "external_publish"})
# Reversibility ties to the irreversible-vs-purchasable doctrine: irreversible
# effects demand explicit confirmation before the Hand will execute them.
REVERSIBILITY = frozenset({"reversible", "compensatable", "irreversible"})

# Trust→effect policy (harden #120): provenance trust rides from the #118 event.
# Weak-trust provenance (untrusted speech/NL, or merely model-proposed) may NOT
# carry a dangerous effect without explicit confirmation. This is the seam that
# stops #121's lowering — or a future Tongue compiler — from smuggling an
# untrusted natural-language chain into an irreversible/destructive/publishing
# action. The deterministic gate, not the absence of a compiler, holds the line.
_WEAK_TRUST = frozenset({"untrusted", "model_proposed"})
_DANGEROUS_EFFECTS = frozenset({"external_publish", "delete"})


class ActionRejected(ValueError):
    """The governance gate refused an action proposal."""


@functools.lru_cache(maxsize=1)
def _live_verbs() -> frozenset[str]:
    """The live capability vocabulary — the `lgwks.map.v1` verb catalog.

    Cached: the catalog is stable within a process. Loading is best-effort; if the
    catalog cannot be read the caller should pass an explicit `known_verbs` set
    (tests always do, to stay hermetic and avoid the subprocess)."""
    import lgwks_map
    return frozenset(v.get("verb", "") for v in lgwks_map._load_verbs() if v.get("verb"))


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ActionRejected(msg)


def validate_action(record: dict[str, Any], *, known_verbs: Iterable[str] | None = None) -> dict[str, Any]:
    """The gate. Return the record on success; raise ActionRejected otherwise.

    Rejects: malformed envelope, unknown verb (not in the map catalog), undeclared
    or unknown effect_class, missing/invalid required_authority, and an
    `irreversible` action without an explicit confirmation flag.
    """
    _require(isinstance(record, dict), "action must be a dict")
    _require(record.get("schema") == SCHEMA, f"schema must be {SCHEMA}")

    verb = record.get("verb")
    _require(isinstance(verb, str) and bool(verb), "verb must be a non-empty string")
    if known_verbs is not None:
        catalog = frozenset(known_verbs)
    else:
        # FAIL CLOSED, explicitly: if the live catalog can't be loaded, refuse the
        # action (never admit). Surfaced as ActionRejected so a future broadened
        # except can't silently flip this to fail-open.
        try:
            catalog = _live_verbs()
        except Exception as exc:
            raise ActionRejected(f"capability catalog unavailable — failing closed: {exc}") from exc
    _require(verb in catalog, f"unknown verb (not in capability map catalog): {verb!r}")

    subject = record.get("subject")
    _require(isinstance(subject, dict) and "kind" in subject, "subject must be a dict with a kind")

    _require(record.get("effect_class") in EFFECT_CLASSES,
             f"effect_class must be one of {sorted(EFFECT_CLASSES)} (got {record.get('effect_class')!r})")
    _require(record.get("reversibility") in REVERSIBILITY,
             f"reversibility must be one of {sorted(REVERSIBILITY)} (got {record.get('reversibility')!r})")

    auth = record.get("required_authority")
    if not isinstance(auth, dict):
        raise ActionRejected("required_authority must be a dict")
    scopes = auth.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise ActionRejected("required_authority.scopes must be a non-empty list")
    unknown = [s for s in scopes if s not in _KNOWN_SCOPES]
    _require(not unknown, f"required_authority.scopes has unknown scopes: {unknown}")

    prov = record.get("provenance")
    if not isinstance(prov, dict):
        raise ActionRejected("provenance must be a dict")
    trust = prov.get("trust")
    _require(trust in TRUST_CLASSES, f"provenance.trust must be one of {sorted(TRUST_CLASSES)} (got {trust!r})")

    for key in ("preconditions", "postconditions"):
        _require(isinstance(record.get(key), list), f"{key} must be a list")

    undo = record.get("undo")
    _require(undo is None or isinstance(undo, dict), "undo must be a dict or null")

    replay = record.get("replay")
    if not isinstance(replay, dict):
        raise ActionRejected("replay must be a dict")
    _require(isinstance(replay.get("deterministic"), bool), "replay.deterministic must be a bool")
    _require(isinstance(replay.get("idempotency_key"), str), "replay.idempotency_key must be a string")

    # The irreversible chokepoint: never execute an irreversible effect unconfirmed.
    if record["reversibility"] == "irreversible":
        _require(record.get("confirmed") is True,
                 "irreversible action requires confirmed=true before it can execute")
        _require(undo is None, "irreversible action must have undo=null (nothing to compensate)")

    # Trust→effect chokepoint: weak-trust provenance cannot carry a dangerous
    # effect without explicit confirmation — untrusted/model-proposed NL can never
    # auto-trigger an irreversible/destructive/publishing action.
    if trust in _WEAK_TRUST and (
        record["reversibility"] == "irreversible" or record["effect_class"] in _DANGEROUS_EFFECTS
    ):
        _require(record.get("confirmed") is True,
                 f"weak-trust provenance ({trust}) cannot carry an "
                 f"irreversible/external_publish/delete effect without confirmed=true")

    return record


def build_action(
    *,
    verb: str,
    subject: dict[str, Any],
    effect_class: str,
    reversibility: str,
    required_authority: dict[str, Any],
    provenance: dict[str, Any],
    preconditions: list[Any] | None = None,
    postconditions: list[Any] | None = None,
    undo: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    deterministic: bool = True,
    confirmed: bool = False,
    known_verbs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build a validated action proposal. Does NOT execute — only the Hand does."""
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "verb": verb,
        "subject": subject,
        "effect_class": effect_class,
        "reversibility": reversibility,
        "required_authority": required_authority,
        "provenance": provenance,
        "preconditions": list(preconditions or []),
        "postconditions": list(postconditions or []),
        "undo": undo,
        "replay": {
            "deterministic": deterministic,
            "idempotency_key": idempotency_key if idempotency_key is not None else f"{verb}:{subject.get('id') or subject.get('cid') or subject.get('kind')}",
        },
    }
    if confirmed:
        record["confirmed"] = True
    return validate_action(record, known_verbs=known_verbs)


def execute_action(
    action: Any,
    hand: Callable[[dict[str, Any]], Any],
    *,
    known_verbs: Iterable[str] | None = None,
) -> Any:
    """The Hand (deterministic runtime). Executes ONLY a validated action.

    This is the enforced chokepoint: anything that is not a valid action envelope
    (raw model text, an arbitrary dict, a string command) is rejected by
    validate_action BEFORE `hand` is ever called. Mutation entry points should be
    reached only through here — model text can never reach `hand` directly.
    """
    validated = validate_action(action, known_verbs=known_verbs)  # raises on raw / invalid input
    return hand(validated)


# ── Lowering existing surfaces onto the contract (acceptance: ≥1 path lowers in) ──

def lower_do_ship(
    *,
    repo: str,
    proposing_event_id: str | None = None,
    proposer: str = "lgwks_do",
    trust: str = "model_proposed",
    confirmed: bool = False,
    known_verbs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Lower the `do ship` workflow into a capability action proposal.

    `do ship` is the clearest irreversible boundary in `lgwks_do.py`: it publishes
    outward (`external_publish`), so it lowers to an `irreversible` action that the
    gate will refuse to execute unless `confirmed=True`. The `verb` is the real
    catalog entry `"do ship"` (`lgwks.map.v1`) — not an invented name.
    """
    return build_action(
        verb="do ship",
        subject={"kind": "repo", "id": repo, "tenant": f"repo:{repo}"},
        effect_class="external_publish",
        reversibility="irreversible",
        required_authority={"scopes": ["tenant:rw", "world:promote"]},
        provenance={"proposing_event_id": proposing_event_id, "proposer": proposer, "trust": trust},
        preconditions=[{"check": "review_passed"}, {"check": "aup_clean"}],
        postconditions=[{"assert": "shipped_ref_exists"}],
        undo=None,  # irreversible — nothing to compensate
        idempotency_key=f"do-ship:{repo}",
        confirmed=confirmed,
        known_verbs=known_verbs,
    )
