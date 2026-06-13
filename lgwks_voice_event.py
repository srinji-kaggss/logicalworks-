"""lgwks_voice_event — speech ingress, never a gate bypass (#123).

Voice is SOURCE MATERIAL, not authority. Spec §4 is explicit and non-negotiable:
"The dangerous part is not ASR; it is letting natural language bypass capability
gates. That must never happen." So a voice event is a payload shape that lowers
into the #118 envelope with `source:speech` and `trust:untrusted`, carrying zero
execution authority. The full path is:

    mic/transcript → Ear → #118 event → Tongue compiler → intent
                  → #120 action proposal → gate

This contract owns ONLY the first hop (the Ear's output). It does NOT select an
ASR model (spec §3.2/§4 — the Ear slot stays open); the ASR model, VAD/
segmentation, and cleanup model are all open slots behind `audio_source`,
`final`, and `cleanup_provenance.model`. Distinct from `lgwks_tongue` (the
NL→intent compiler, the next hop).
"""

from __future__ import annotations

from typing import Any

from axiom.cid import compute_cid, verify_cid

import lgwks_daemon_event as daemon_event

SCHEMA = "lgwks.voice.event.v1"

AUDIO_KINDS = frozenset({"mic", "file", "stream"})


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def build_voice_event(
    *,
    raw_text: str,
    audio_source: dict[str, Any],
    transcript_span: dict[str, Any] | None = None,
    confidence: float | None = None,
    speaker: dict[str, Any] | None = None,
    normalized_text: str | None = None,
    cleanup_provenance: dict[str, Any] | None = None,
    final: bool = True,
) -> dict[str, Any]:
    """Build a validated voice event.

    `raw_text` is the verbatim ASR output and is IMMUTABLE — `normalized_text`
    (cleanup) defaults to it, and `raw_ref` is a content-address pointer back to
    the raw transcript so the normalized text never overwrites the raw."""
    normalized = raw_text if normalized_text is None else normalized_text
    raw_ref = f"raw:{compute_cid(raw_text.encode('utf-8'))}"
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "audio_source": audio_source,
        "transcript_span": transcript_span if transcript_span is not None else {"start_ms": None, "end_ms": None},
        "confidence": confidence,
        "speaker": speaker,
        "raw_text": raw_text,
        "normalized_text": normalized,
        "raw_ref": raw_ref,
        "cleanup_provenance": cleanup_provenance if cleanup_provenance is not None else {
            "model": None,  # open slot — no ASR/cleanup model selected here
            "method": "passthrough" if normalized == raw_text else "external",
            "changed": normalized != raw_text,
        },
        "final": bool(final),
    }
    return validate_voice_event(record)


def validate_voice_event(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a voice event; return it unchanged on success."""
    _require(isinstance(record, dict), "record must be a dict")
    _require(record.get("schema") == SCHEMA, f"schema must be {SCHEMA}")

    audio = record.get("audio_source")
    if not isinstance(audio, dict):
        raise ValueError("audio_source must be a dict")
    _require(audio.get("kind") in AUDIO_KINDS, f"audio_source.kind must be one of {sorted(AUDIO_KINDS)}")

    _require(isinstance(record.get("raw_text"), str), "raw_text must be a string")
    _require(isinstance(record.get("normalized_text"), str), "normalized_text must be a string")

    raw_ref = record.get("raw_ref")
    if not isinstance(raw_ref, str) or not raw_ref.startswith("raw:"):
        raise ValueError("raw_ref must be a 'raw:<cid>' pointer")
    # The pointer MUST resolve to the exact raw transcript — raw is never lost.
    _require(verify_cid(record["raw_text"].encode("utf-8"), raw_ref[len("raw:"):]),
             "raw_ref does not resolve to raw_text (raw transcript integrity broken)")

    conf = record.get("confidence")
    _require(conf is None or (isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0),
             "confidence must be null or a number in [0,1]")

    span = record.get("transcript_span")
    _require(isinstance(span, dict), "transcript_span must be a dict")

    cleanup = record.get("cleanup_provenance")
    if not isinstance(cleanup, dict):
        raise ValueError("cleanup_provenance must be a dict")
    # `changed` must not lie — it has to reflect the actual raw→normalized delta.
    if "changed" in cleanup:
        _require(bool(cleanup["changed"]) == (record["normalized_text"] != record["raw_text"]),
                 "cleanup_provenance.changed must equal (normalized_text != raw_text)")

    _require(isinstance(record.get("final"), bool), "final must be a bool")
    if record.get("speaker") is not None:
        _require(isinstance(record["speaker"], dict), "speaker must be a dict or null")
    return record


def to_daemon_event(
    voice: dict[str, Any],
    *,
    tenant_id: str,
    agent_id: str,
    session_id: str,
    client: str = "human",
    ts: str | None = None,
) -> dict[str, Any]:
    """Lower a voice event into the #118 envelope — `source:speech`, `trust:untrusted`.

    `trust=untrusted` is the safety invariant: voice can NEVER arrive pre-trusted.
    The raw text is referenced by content-address (`payload_cid`), and provenance
    points back to the raw transcript (`derived_from:[raw_ref]`). The normalized
    text rides in the payload; the raw text is not duplicated inline."""
    validate_voice_event(voice)
    return daemon_event.build_event(
        tenant_id=tenant_id,
        agent_id=agent_id,
        session_id=session_id,
        actor="human",
        client=client,
        lane="ingress",
        kind="transcript_turn",
        scope="agent_local",
        payload={
            "normalized_text": voice["normalized_text"],
            "final": voice["final"],
            "confidence": voice.get("confidence"),
        },
        source="speech",
        trust="untrusted",
        payload_cid=compute_cid(voice["raw_text"].encode("utf-8")),
        provenance={"derived_from": [voice["raw_ref"]], "producer": "lgwks_voice_event"},
        ts=ts,
    )
