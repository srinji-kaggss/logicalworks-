"""lgwks_artifact_tokenized — canonical tokenized artifact envelope.

Schema id: lgwks.artifact.tokenized.v1

This is the single object that research, run, ingest, and substrate all emit.
Everything else (vector, graph, FTS, relational) is a projection over the Causal
Tape of these artifacts. The artifact carries a `tokenization_id` so every
projection can answer: "which tokenizer/analyzer produced this unit?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_hashing

SCHEMA = "lgwks.artifact.tokenized.v1"

VALID_SOURCES = frozenset({
    "research", "run", "ingest", "substrate", "daemon_event", "project_artifact"
})

VALID_MODALITIES = frozenset({
    "text", "image", "video", "audio", "terminal", "reasoning"
})


class ArtifactError(ValueError):
    """Contract violation in a tokenized artifact."""


@dataclass(frozen=True)
class TokenizedArtifact:
    """Immutable, fully validated lgwks.artifact.tokenized.v1 instance."""

    artifact_cid: str
    tenant_id: str
    source: str
    run_id: str
    session_id: str
    modality: str
    tokenization_id: str
    token_stream: tuple[int, ...]
    payload_cid: str
    payload_meta: dict[str, Any]
    capability_id: str
    timestamp: float
    prev_hash: str
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "artifact_cid": self.artifact_cid,
            "tenant_id": self.tenant_id,
            "source": self.source,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "modality": self.modality,
            "tokenization_id": self.tokenization_id,
            "token_stream": list(self.token_stream),
            "payload_cid": self.payload_cid,
            "payload_meta": self.payload_meta,
            "capability_id": self.capability_id,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
        }

    def canonical_json(self) -> str:
        """Deterministic JSON for content hashing."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _require_nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactError(f"{name} must be a non-empty string")
    return value.strip()


def build_artifact(
    *,
    tenant_id: str,
    source: str,
    run_id: str = "",
    session_id: str = "",
    modality: str,
    tokenization_id: str,
    token_stream: list[int] | tuple[int, ...],
    payload_cid: str,
    payload_meta: dict[str, Any] | None = None,
    capability_id: str,
    timestamp: float,
    prev_hash: str = "genesis",
    artifact_cid: str | None = None,
) -> TokenizedArtifact:
    """Construct and validate a TokenizedArtifact.

    If `artifact_cid` is omitted, it is computed from the canonical JSON form
    of the artifact (minus the cid field itself) using the repo's content-id
    primitive. This makes the artifact content-addressed.
    """
    tenant_id = _require_nonempty(tenant_id, "tenant_id")
    source = _require_nonempty(source, "source")
    if source not in VALID_SOURCES:
        raise ArtifactError(f"source {source!r} must be one of {sorted(VALID_SOURCES)}")

    modality = _require_nonempty(modality, "modality")
    if modality not in VALID_MODALITIES:
        raise ArtifactError(f"modality {modality!r} must be one of {sorted(VALID_MODALITIES)}")

    tokenization_id = _require_nonempty(tokenization_id, "tokenization_id")
    payload_cid = _require_nonempty(payload_cid, "payload_cid")
    capability_id = _require_nonempty(capability_id, "capability_id")

    token_stream = tuple(int(t) for t in token_stream)

    payload_meta = dict(payload_meta or {})
    run_id = run_id or ""
    session_id = session_id or ""
    prev_hash = prev_hash or "genesis"

    # Compute content hash without the cid field to keep it deterministic.
    temp = TokenizedArtifact(
        artifact_cid="",
        tenant_id=tenant_id,
        source=source,
        run_id=run_id,
        session_id=session_id,
        modality=modality,
        tokenization_id=tokenization_id,
        token_stream=token_stream,
        payload_cid=payload_cid,
        payload_meta=payload_meta,
        capability_id=capability_id,
        timestamp=timestamp,
        prev_hash=prev_hash,
    )
    computed_cid = artifact_cid or lgwks_hashing.content_id(temp.canonical_json())

    return TokenizedArtifact(
        artifact_cid=computed_cid,
        tenant_id=tenant_id,
        source=source,
        run_id=run_id,
        session_id=session_id,
        modality=modality,
        tokenization_id=tokenization_id,
        token_stream=token_stream,
        payload_cid=payload_cid,
        payload_meta=payload_meta,
        capability_id=capability_id,
        timestamp=timestamp,
        prev_hash=prev_hash,
    )


def validate_artifact_dict(data: dict[str, Any]) -> TokenizedArtifact:
    """Reconstruct a TokenizedArtifact from a plain dict."""
    if data.get("schema") != SCHEMA:
        raise ArtifactError(f"schema must be {SCHEMA!r}, got {data.get('schema')!r}")
    return build_artifact(
        tenant_id=data["tenant_id"],
        source=data["source"],
        run_id=data.get("run_id", ""),
        session_id=data.get("session_id", ""),
        modality=data["modality"],
        tokenization_id=data["tokenization_id"],
        token_stream=data["token_stream"],
        payload_cid=data["payload_cid"],
        payload_meta=data.get("payload_meta", {}),
        capability_id=data["capability_id"],
        timestamp=float(data["timestamp"]),
        prev_hash=data.get("prev_hash", "genesis"),
        artifact_cid=data.get("artifact_cid"),
    )


def emit_artifact(path: Path, artifact: TokenizedArtifact) -> None:
    """Write one artifact as a single JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(artifact.to_dict(), sort_keys=True) + "\n")
