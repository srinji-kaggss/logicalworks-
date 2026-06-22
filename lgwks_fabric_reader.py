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

    def graph_resolve_node(self, query: str) -> tuple[dict[str, Any] | None, str | None]:
        """Resolve a node label/id against the cumulative graph → (node, err)."""
        return self._gate.graph_fabric.resolve_node(query)

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

    # ---- unified query (#166) ----
    def query(self, text: str, *, limit: int = 10) -> dict[str, Any]:
        """One query, one result set, spanning every projection (#166).

        - lexical : relational FTS5 over chunks + facts (each hit carries its
                    tokenization_id + artifact_cid)
        - tokens  : token-index posting hits for the query's tokens (artifact cids)
        - graph   : the graph node the query resolves to, plus its neighbours
        - vector  : cosine-ranked vector hits against a deterministic embedding of
                    the query (best-effort; empty if no embedder/vectors)

        Every hit is traceable: lexical/vector hits carry artifact_cid +
        tokenization_id, so a consumer always knows which tape entry and which
        analyzer produced a result. The vector arm is isolated — a missing embedder
        never starves the lexical/graph/token arms."""
        chunks = self._gate.relational.search_chunks(text, limit=limit)
        facts = self._gate.relational.search_facts(text, limit=limit)

        # token-index arm: for the artifacts the lexical arm surfaced, report their
        # token-posting coverage from the inverted index. (There is no canonical
        # text→int encoder for the word_regex analyzer — the index is fed opaque
        # token ids by the trajectory tokenizer — so a text query reaches the
        # token-index THROUGH the artifacts it resolves to, carrying provenance.)
        token_hits: list[dict[str, Any]] = []
        for hit in chunks[:limit]:
            acid = hit.get("artifact_cid")
            if not acid:
                continue
            postings = self._gate.token_index.query_artifact_tokens(acid)
            if postings:
                token_hits.append({
                    "artifact_cid": acid,
                    "tokenization_id": postings[0][0],
                    "tokens_indexed": len(postings),
                })

        # graph arm: resolve the query to a node and surface its neighbourhood. Try
        # the whole query first, then fall back to its individual terms (a multi-word
        # query rarely matches a single node label verbatim).
        graph_hits: list[dict] = []
        node = self._resolve_graph_node(text)
        if node and node.get("node_id"):
            graph_hits = self._gate.graph_fabric.neighbors(node["node_id"], limit=limit)

        # vector arm: deterministic query embedding → cosine over the same space.
        vector_hits: list[dict[str, Any]] = []
        try:
            vector_hits = self._vector_arm(text, limit=limit)
        except Exception:
            pass

        return {
            "query": text,
            "lexical": {"chunks": chunks, "facts": facts},
            "tokens": token_hits,
            "graph": {"node": node, "neighbors": graph_hits},
            "vector": vector_hits,
        }

    def _resolve_graph_node(self, text: str) -> dict | None:
        node, _err = self._gate.graph_fabric.resolve_node(text)
        if node and node.get("node_id"):
            return node
        for term in (t for t in text.split() if len(t) >= 2):
            node, _err = self._gate.graph_fabric.resolve_node(term)
            if node and node.get("node_id"):
                return node
        return None

    def _vector_arm(self, text: str, *, limit: int) -> list[dict[str, Any]]:
        import lgwks_run
        import lgwks_vector as vec_mod
        dual = lgwks_run.embed_dual(text, embed_on=True, provider="auto", model="")
        det = dual.get("det") or {}
        floats = det.get("vector") or []
        if not floats:
            return []
        provider, dims = det.get("provider", "unknown"), int(det.get("dims") or len(floats))
        q = vec_mod.encode_record(floats, modality="text", space_id=f"{provider}:d{dims}",
                                  tenant=vec_mod.WORLD_TENANT, source_cid="query")
        out = []
        for score, rec in self._gate.vector_fabric.search_similar(q, limit=limit):
            out.append({"score": round(score, 6), "artifact_cid": rec.artifact_cid,
                        "tokenization_id": rec.tokenization_id, "source_cid": rec.source_cid,
                        "space_id": rec.space_id})
        return out


def open_reader(project_name: str, tenant_id: str = "default") -> tuple["lgwks_storage.StorageGate", FabricReader]:
    """Open a gate for a project and return (gate, reader). Caller closes the gate."""
    import lgwks_storage

    gate = lgwks_storage.get_gate(project_name, tenant_id=tenant_id)
    return gate, FabricReader(gate)


# ─────────────────────────────────────────────────────────────────────────────
# CLI — `lgwks state fabric {status,tokenizers,replay,query}` (#166).
# The fabric introspection surface lives under the `state` verb group (T6:
# "durable state and context fabric"), so it adds no top-level verb and the
# verb-budget gate (tests/test_cli_contract.py) stays fixed.
# ─────────────────────────────────────────────────────────────────────────────
def add_parser(sub) -> None:
    p = sub.add_parser("fabric", help="introspect the State Fabric (status, tokenizers, replay, query)")
    fsub = p.add_subparsers(dest="fabric_cmd", required=True)

    st = fsub.add_parser("status", help="projection counts, tape depth, active tokenizers")
    st.add_argument("--project", default="default")
    st.add_argument("--tenant", default="default")
    st.set_defaults(func=_fabric_status)

    tk = fsub.add_parser("tokenizers", help="list registered analyzers (tokenizers)")
    tk.add_argument("--project", default="default")
    tk.add_argument("--tenant", default="default")
    tk.set_defaults(func=_fabric_tokenizers)

    rp = fsub.add_parser("replay", help="rebuild the relational projection by replaying the tape for a run")
    rp.add_argument("--run", required=True, help="run_id to replay from the Causal Tape")
    rp.add_argument("--project", default="default")
    rp.add_argument("--tenant", default="default")
    rp.set_defaults(func=_fabric_replay)

    qy = fsub.add_parser("query", help="one query across vector + graph + token-index + lexical projections")
    qy.add_argument("text")
    qy.add_argument("--project", default="default")
    qy.add_argument("--tenant", default="default")
    qy.add_argument("--limit", type=int, default=10)
    qy.set_defaults(func=_fabric_query)


def _emit(obj: object) -> int:
    import json as _json
    print(_json.dumps(obj, indent=2, sort_keys=True, default=str))
    return 0


def _fabric_status(args) -> int:
    import lgwks_storage
    with lgwks_storage.get_gate(args.project, tenant_id=getattr(args, "tenant", "default")) as gate:
        return _emit(gate.status())


def _fabric_tokenizers(args) -> int:
    import lgwks_storage
    with lgwks_storage.get_gate(args.project, tenant_id=getattr(args, "tenant", "default")) as gate:
        return _emit([t.to_dict() for t in gate.tokenizers.list_tokenizers()])


def _fabric_replay(args) -> int:
    import lgwks_storage
    with lgwks_storage.get_gate(args.project, tenant_id=getattr(args, "tenant", "default")) as gate:
        result = gate.replay_run(args.run)
        result["status_after"] = gate.status()
        return _emit(result)


def _fabric_query(args) -> int:
    import lgwks_storage
    with lgwks_storage.get_gate(args.project, tenant_id=getattr(args, "tenant", "default")) as gate:
        return _emit(FabricReader(gate).query(args.text, limit=args.limit))
