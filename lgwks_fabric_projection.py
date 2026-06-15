"""lgwks_fabric_projection — the universal projection seam for the State Fabric.

Every workflow and every command routes its data through one endpoint:
`StorageGate.ingest_artifact`. That call appends the artifact to the Causal Tape
(DB1 — the durable source of record) and then fans it out to a *registry* of
Projections. A Projection is any derived view — the vector store, the token
posting list, the entity graph, the relational surface, or a future one nobody
has written yet.

Why this shape (the "stands the test of new things" guarantee):
  - Open/closed: a new projection joins by `register_projection(...)`, never by
    editing the gate. The ingest signature never changes; new per-call inputs are
    added to `IngestContext.extras` and ignored by projections that don't care.
  - Tape-is-truth: the tape commit is the ONLY step that must succeed for an
    ingest to be durable. Projections are DERIVED and REBUILDABLE by replaying
    the tape, so they are best-effort and isolated.
  - Isolation: a projection that raises is contained — its failure is captured in
    the IngestReceipt and never rolls back the tape or starves sibling
    projections.
  - Idempotence: apply() must be safe to replay (content-addressed keys /
    INSERT OR IGNORE / UPSERT), so tape replay reconstructs projections exactly.

This is the contract; concrete projections live in lgwks_storage and adopters
beyond it. See docs/schemas/REGISTRY.md for the artifact wire payload — the types
here are in-process, not cross-module payloads, so they mint no schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import lgwks_artifact_tokenized as artifact_mod
    import lgwks_vector as vec_mod


@dataclass(frozen=True)
class IngestContext:
    """Everything a projection might consume from one ingest call.

    New sidecar inputs (a raw payload, an image tensor, a caption, a new
    modality's blob) are added as fields here or dropped into `extras`;
    projections that don't care simply ignore them. That is why the universal
    ingest signature never has to change as the system grows — extend the
    context, not the gate.
    """

    artifact: "artifact_mod.TokenizedArtifact"
    vector_record: "vec_mod.VectorRecord | None" = None
    index_tokens: bool = True
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectionResult:
    """The fate of one projection for one artifact."""

    name: str
    applied: bool
    written: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class IngestReceipt:
    """Structured outcome of one ingest: the durable record + per-projection fate.

    Truthy iff the durable tape entry was written, so existing callers that only
    checked `if gate.ingest_artifact(...)` keep working. `ok` is True only when
    every projection (and the global fact list) also succeeded.
    """

    entry_hash: str
    artifact_cid: str
    projections: tuple[ProjectionResult, ...] = ()
    ok: bool = True

    def __bool__(self) -> bool:
        return bool(self.entry_hash)

    def failures(self) -> tuple[ProjectionResult, ...]:
        return tuple(r for r in self.projections if not r.ok)


@runtime_checkable
class Projection(Protocol):
    """A derived view over the Causal Tape. Implementations must be idempotent."""

    name: str

    def apply(self, ctx: IngestContext) -> ProjectionResult: ...

    def close(self) -> None: ...


def run_isolated(projection: Any, ctx: IngestContext) -> ProjectionResult:
    """Apply a projection without ever letting its failure escape.

    A projection is derived and rebuildable; a bug or transient error in one must
    not corrupt the tape commit or block sibling projections. The failure is
    captured as a ProjectionResult so the gate can surface it in the receipt
    instead of raising. A projection that returns the wrong type is treated as a
    contract violation, not a silent success.
    """
    name = getattr(projection, "name", type(projection).__name__)
    try:
        result = projection.apply(ctx)
    except Exception as exc:  # noqa: BLE001 — isolation is the whole point
        return ProjectionResult(name=name, applied=False, error=f"{type(exc).__name__}: {exc}")
    if not isinstance(result, ProjectionResult):
        return ProjectionResult(
            name=name,
            applied=False,
            error=f"projection returned {type(result).__name__}, expected ProjectionResult",
        )
    return result
