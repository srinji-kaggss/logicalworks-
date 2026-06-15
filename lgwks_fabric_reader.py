"""lgwks_fabric_reader — the unified read surface over the State Fabric.

The write side has one endpoint (StorageGate.ingest_artifact); this is its read
counterpart. Consumers that used to open a per-run `substrate.db` / `graph.db`
directly query a FabricReader bound to a gate instead, so there is exactly one
place that knows how the fabric is laid out.

It opens no stores of its own — it composes the gate's existing projection
connections (relational FTS, vector, graph) and the Causal Tape. Reads are
unscoped/admin (single-operator context); tenant-scoped reads come with the
two-DB capability work (ARCH-two-db-multitenant.md), not here.

Surfaces, mapped to what the legacy consumers need:
  - lexical search      → relational FTS5 (search_chunks / search_facts)
  - vector retrieval    → VectorFabric (vectors_by_source / vectors_by_artifact)
  - vector-space dim    → VectorFabric.space_dims (was _read_substrate_dims)
  - graph               → GraphFabric.neighbors / stats
  - token streams       → TokenIndex (artifact_tokens)
  - tape replay         → CausalTape.replay (training corpus / projection rebuild)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    import lgwks_storage
    import lgwks_vector as vec_mod


class FabricReader:
    """Unified, read-only view over one gate's State Fabric."""

    def __init__(self, gate: "lgwks_storage.StorageGate"):
        self._gate = gate

    # ---- lexical search (relational FTS5) ----
    def search_chunks(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._gate.relational.search_chunks(query, limit=limit)

    def search_facts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._gate.relational.search_facts(query, limit=limit)

    # ---- vector retrieval ----
    def vectors_by_source(self, source_cid: str, *, space_id: str | None = None) -> "list[vec_mod.VectorRecord]":
        return self._gate.vector_fabric.query_by_source(source_cid, space_id=space_id)

    def vectors_by_artifact(self, artifact_cid: str) -> "list[vec_mod.VectorRecord]":
        return self._gate.vector_fabric.query_by_artifact(artifact_cid)

    def vector_space_dims(self) -> int | None:
        return self._gate.vector_fabric.space_dims()

    # ---- graph ----
    def graph_neighbors(self, node_id: str, direction: str = "both", rel: str | None = None, limit: int = 100) -> list[dict]:
        return self._gate.graph_fabric.neighbors(node_id, direction=direction, rel=rel, limit=limit)

    def graph_stats(self) -> dict[str, Any]:
        return self._gate.graph_fabric.stats()

    # ---- token streams ----
    def artifact_tokens(self, artifact_cid: str) -> list[tuple[str, int, int]]:
        return self._gate.token_index.query_artifact_tokens(artifact_cid)

    def artifacts_with_token(self, tokenization_id: str, token: int) -> list[str]:
        return self._gate.token_index.query_token(tokenization_id, token)

    # ---- tape replay (source of record) ----
    def replay(self, tenant_id: str | None = None) -> Iterator[dict[str, Any]]:
        """Replay the Causal Tape in order — the training corpus / rebuild source."""
        return self._gate.tape.replay(tenant_id=tenant_id)

    # ---- dedup moat lookup ----
    def lookup_fact(self, fact_cid: str) -> dict[str, Any] | None:
        return self._gate.fact_list.lookup(fact_cid)


def open_reader(project_name: str, tenant_id: str = "default") -> tuple["lgwks_storage.StorageGate", FabricReader]:
    """Open a gate for a project and return (gate, reader). Caller closes the gate."""
    import lgwks_storage

    gate = lgwks_storage.get_gate(project_name, tenant_id=tenant_id)
    return gate, FabricReader(gate)
