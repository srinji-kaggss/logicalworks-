"""Tests for lgwks_inbound — I7 L5 consumer pack (RRF fusion + reflex budget).

Acceptance maps 1:1 to PLANS-NEXT-3 §PACKET I7 / INGESTION-LAYER §7-INV (issue #61):

  T1 no-prose        — NO input produces a pack with any free-text field (§7-INV):
                       every string leaf is a cid, a typed modality enum, or the schema id.
  T2 cap-holds       — NO input produces a serialized pack over limit_tokens (PRD-04 04-a);
                       forced overflow triggers truncation.
  T3 truncation-order— forced overflow drops lowest-RRF handles first, every dropped cid is
                       recorded in budget.truncated, and depth_handles survive the cut.
  T4 zero-dangling   — every cid in handles (and every depth_handle id) resolves via
                       get_record to a record present in the store.
  T5 rrf-determinism — same inputs → byte-identical fused order (seed-stability).
  T6 rrf-math        — fusion arithmetic + single-list (graph-only) validity (PRD-04 04-b).
"""

from __future__ import annotations

import json
import os
import random
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lgwks_inbound
import lgwks_rank
import lgwks_access
import lgwks_vector
from lgwks_inbound import (
    SCHEMA,
    RRF_K,
    build_pack,
    fuse,
    assemble_inbound,
    est_tokens,
)
from lgwks_rank import RankRecord

SPACE = "test-space:d8"
DIM = 8

# Real eval corpus (extract, don't rebuild). Mirrors tests/test_rank.py:GRAPH_LW —
# skipped if absent so CI stays green; exercises the fusion/budget path on real structure.
GRAPH_LW = Path.home() / "ingestion_results" / "logicalworks-_graph" / "graph.json"


def _mk_record(conn, source_cid: str, floats: list[float], modality: str = "text"):
    rec = lgwks_vector.encode_record(
        floats, modality=modality, space_id=SPACE, tenant="t", source_cid=source_cid
    )
    lgwks_vector.upsert_record(conn, rec, admin=lgwks_vector.ADMIN)
    return rec


def _build_store_and_graph(conn, n: int = 6):
    """Create n vector records and a connected graph whose node ids ARE their cids."""
    records = []
    for i in range(n):
        floats = [float((i + 1) * (j + 1) % 7) + 0.5 for j in range(DIM)]
        records.append(_mk_record(conn, f"src-{i}", floats))
    cids = [r.cid for r in records]

    rels = lgwks_rank.RELATIONS
    nodes = [{"id": c} for c in cids]
    links = []
    # connect i -> i+1 in a ring with rotating relations, plus a hub edge for variety
    for i in range(n):
        links.append({
            "source": cids[i], "target": cids[(i + 1) % n],
            "relation": rels[i % len(rels)],
            "confidence_score": 0.9, "weight": 1.0,
        })
    for i in range(2, n):
        links.append({
            "source": cids[0], "target": cids[i],
            "relation": rels[(i + 3) % len(rels)],
            "confidence_score": 0.8, "weight": 1.0,
        })
    graph = {"nodes": nodes, "links": links}
    return records, graph


class TestRRFMath(unittest.TestCase):
    """T6 — fusion arithmetic + single-list validity."""

    def _rr(self, cid, rank_det):
        return RankRecord(node_cid=cid, centrality=0.0, rank_det=rank_det,
                          rank_ai=rank_det, delta=0, lane="auto",
                          schema_id="lgwks.rank.record.v1")

    def test_two_list_fusion(self):
        graph = [self._rr("a", 1), self._rr("b", 2), self._rr("c", 3)]
        vec = [("b", 0.99), ("a", 0.50), ("c", 0.10)]  # b best in vector
        fused = dict(fuse(graph, vec))
        # a: 1/(60+1)+1/(60+2)  b: 1/(60+2)+1/(60+1)  → a and b tie, c lowest
        self.assertAlmostEqual(fused["a"], 1/(RRF_K+1) + 1/(RRF_K+2))
        self.assertAlmostEqual(fused["b"], 1/(RRF_K+2) + 1/(RRF_K+1))
        self.assertLess(fused["c"], fused["a"])

    def test_single_list_valid(self):
        graph = [self._rr("a", 1), self._rr("b", 2)]
        fused = fuse(graph, [])  # graph-only — PRD-04 04-b says still valid
        self.assertEqual([c for c, _ in fused], ["a", "b"])
        self.assertAlmostEqual(dict(fused)["a"], 1/(RRF_K+1))

    def test_union_of_lists(self):
        graph = [self._rr("a", 1)]
        vec = [("z", 0.9)]  # z only in vector lane
        fused = dict(fuse(graph, vec))
        self.assertIn("z", fused)
        self.assertIn("a", fused)


class TestPackProperties(unittest.TestCase):
    """T1 no-prose, T2 cap-holds, T3 truncation-order over fuzzed inputs."""

    def _assert_no_prose(self, pack, cid_universe):
        modalities = lgwks_vector.MODALITIES

        def walk(v):
            if isinstance(v, dict):
                for val in v.values():
                    walk(val)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
            elif isinstance(v, bool):
                pass  # bool is an int subclass; numbers are fine
            elif isinstance(v, (int, float)):
                pass
            elif isinstance(v, str):
                ok = v == SCHEMA or v in modalities or v in cid_universe
                self.assertTrue(ok, f"free-text leaked into L5 pack: {v!r}")
            else:
                self.fail(f"non-typed value in pack: {type(v)}")

        walk(pack)

    def test_no_prose_fuzz(self):
        rng = random.Random(1234)
        for trial in range(200):
            n = rng.randint(0, 12)
            handles = [f"cid{i:02d}" for i in range(n)]
            scores = {h: rng.random() for h in handles}
            depth = [{"id": h, "est_tokens": rng.randint(1, 999), "kind": "text"}
                     for h in handles]
            pack = build_pack(handles, scores, limit_tokens=rng.randint(60, 2000),
                              depth_handles=depth)
            self._assert_no_prose(pack, set(handles))

    def test_cap_holds_fuzz(self):
        # The general invariant: build_pack NEVER returns a pack over cap. For a cap so
        # small it cannot even hold the truncation receipt it raises loudly (no silent
        # failure) — never an overflow. Either branch satisfies "no input over cap".
        rng = random.Random(5678)
        overflowed = 0
        for trial in range(300):
            n = rng.randint(1, 40)
            handles = [f"cid{i:03d}" for i in range(n)]
            scores = {h: rng.random() for h in handles}
            depth = [{"id": h, "est_tokens": rng.randint(1, 50), "kind": "text"}
                     for h in handles]
            limit = rng.randint(60, 500)
            try:
                pack = build_pack(handles, scores, limit_tokens=limit, depth_handles=depth)
            except lgwks_inbound.InboundError:
                continue  # cap too small even for an empty envelope — surfaced loudly
            serialized = json.dumps(pack, sort_keys=True, separators=(",", ":"))
            self.assertLessEqual(est_tokens(serialized), limit,
                                 "serialized reflex pack exceeded the cap")
            # used_tokens is a conservative upper bound (max-width counter) — never under
            # the true size, never over the cap.
            self.assertLessEqual(est_tokens(serialized), pack["budget"]["used_tokens"])
            self.assertLessEqual(pack["budget"]["used_tokens"], limit)
            # the visible receipt is bounded; the count is exact
            self.assertLessEqual(len(pack["budget"]["truncated"]), lgwks_inbound.MAX_TRUNCATED_VISIBLE)
            self.assertEqual(pack["budget"]["truncated_count"],
                             n - len(pack["handles"]))
            if pack["budget"]["truncated_count"]:
                overflowed += 1
        self.assertGreater(overflowed, 0, "fuzz never exercised the truncation path")

    def test_truncation_order_and_survival(self):
        # 20 handles, strictly decreasing RRF score; force overflow in the regime where
        # bulk shedding alone gets under cap (limit above the depth-pointer floor).
        n = 20
        handles = [f"cid{i:02d}" for i in range(n)]
        scores = {h: float(n - i) for i, h in enumerate(handles)}  # cid00 best
        depth = [{"id": h, "est_tokens": 1, "kind": "text"} for h in handles]

        full = build_pack(handles, scores, limit_tokens=10**6,
                          depth_handles=depth)["budget"]["used_tokens"]
        depth_floor = build_pack([], {}, limit_tokens=10**6,
                                 depth_handles=depth)["budget"]["used_tokens"]
        limit = depth_floor + 40   # above pointer floor (+receipt room), below full
        self.assertLess(limit, full, "test mis-sized: overflow would not trigger")
        pack = build_pack(handles, scores, limit_tokens=limit, depth_handles=depth)

        kept = pack["handles"]
        dropped = pack["budget"]["truncated"]
        # something must have dropped (overflow forced) but bulk only
        self.assertTrue(dropped, "expected truncation to trigger")
        # kept handles are a strict prefix of the original best-first order
        self.assertEqual(kept, handles[:len(kept)])
        # the count is exact; the visible sample is the dropped tail, best-RRF first
        self.assertEqual(pack["budget"]["truncated_count"], n - len(kept))
        self.assertEqual(dropped, handles[len(kept):])   # all <64 here → full, in order
        # depth_handle pointers survive the cut (PRD-04: pointer never dropped for bulk)
        surviving_ids = {d["id"] for d in pack["depth_handles"]}
        self.assertEqual(surviving_ids, set(handles),
                         "depth_handles must survive bulk truncation")

    def test_empty_pack_under_cap(self):
        pack = build_pack([], {}, limit_tokens=1500)
        self.assertEqual(pack["handles"], [])
        self.assertEqual(pack["budget"]["truncated"], [])
        self.assertEqual(pack["schema"], SCHEMA)


class TestAssembleEndToEnd(unittest.TestCase):
    """T4 zero-dangling, T5 determinism — through assemble_inbound on a real store."""

    def _store(self, td):
        return lgwks_vector.create_store(Path(td) / "vec.db")

    def test_zero_dangling_handles(self):
        with TemporaryDirectory() as td:
            conn = self._store(td)
            try:
                records, graph = _build_store_and_graph(conn, n=6)
                query = records[0]  # an already-embedded query, same space
                pack = assemble_inbound(query, graph, conn)
                self.assertTrue(pack["handles"], "expected non-empty handles")
                for cid in pack["handles"]:
                    self.assertIsNotNone(lgwks_vector.get_record(conn, cid, admin=lgwks_vector.ADMIN),
                                         f"dangling handle: {cid}")
                for d in pack["depth_handles"]:
                    self.assertIsNotNone(lgwks_vector.get_record(conn, d["id"], admin=lgwks_vector.ADMIN),
                                         f"dangling depth handle: {d['id']}")
                    self.assertIn(d["kind"], lgwks_vector.MODALITIES)
            finally:
                conn.close()

    def test_dangling_graph_cid_excluded(self):
        # a graph node with no store record must NOT appear as a handle
        with TemporaryDirectory() as td:
            conn = self._store(td)
            try:
                records, graph = _build_store_and_graph(conn, n=4)
                graph["nodes"].append({"id": "ghost-cid-not-in-store"})
                graph["links"].append({
                    "source": records[0].cid, "target": "ghost-cid-not-in-store",
                    "relation": "calls", "confidence_score": 0.5, "weight": 1.0,
                })
                pack = assemble_inbound(records[0], graph, conn)
                self.assertNotIn("ghost-cid-not-in-store", pack["handles"])
            finally:
                conn.close()

    def test_determinism(self):
        with TemporaryDirectory() as td:
            conn = self._store(td)
            try:
                records, graph = _build_store_and_graph(conn, n=6)
                query = records[1]
                p1 = assemble_inbound(query, graph, conn)
                p2 = assemble_inbound(query, graph, conn)
                s1 = json.dumps(p1, sort_keys=True, separators=(",", ":"))
                s2 = json.dumps(p2, sort_keys=True, separators=(",", ":"))
                self.assertEqual(s1, s2, "assemble_inbound is not byte-deterministic")
            finally:
                conn.close()

    def test_space_mismatch_surfaces(self):
        with TemporaryDirectory() as td:
            conn = self._store(td)
            try:
                records, graph = _build_store_and_graph(conn, n=4)
                bad_query = lgwks_vector.encode_record(
                    [1.0] * DIM, modality="text", space_id="other-space:d8",
                    tenant="t", source_cid="q",
                )
                with self.assertRaises(lgwks_vector.SpaceMismatchError):
                    assemble_inbound(bad_query, graph, conn)
            finally:
                conn.close()

    def test_graph_only_no_query(self):
        with TemporaryDirectory() as td:
            conn = self._store(td)
            try:
                records, graph = _build_store_and_graph(conn, n=5)
                pack = assemble_inbound(None, graph, conn)  # no query → single-list RRF
                self.assertTrue(pack["handles"])
                for cid in pack["handles"]:
                    self.assertIsNotNone(lgwks_vector.get_record(conn, cid, admin=lgwks_vector.ADMIN))
            finally:
                conn.close()


class TestRealGraph(unittest.TestCase):
    """Real-data acceptance: fuse + budget + truncation on the 5130-node lgwks graph.

    Extracted from the real ingestion corpus (not a synthetic rebuild). The graph node
    count (>> handles that fit a 1500-token cap) forces a genuine truncation path.
    """

    @classmethod
    def setUpClass(cls):
        if not GRAPH_LW.exists():
            raise unittest.SkipTest(f"eval graph not found: {GRAPH_LW}")
        with open(GRAPH_LW, encoding="utf-8") as f:
            cls.graph = json.load(f)
        cls.ranks = lgwks_rank.rank_graph(cls.graph)

    def test_real_graph_only_fusion_cap_and_no_prose(self):
        fused = fuse(self.ranks, [])          # graph-only single-list RRF on real ranks
        handles = [cid for cid, _s in fused]
        scores = {cid: s for cid, s in fused}
        pack = build_pack(handles, scores, limit_tokens=1500)

        # cap holds on real data, and overflow genuinely triggered (5130 >> cap)
        serialized = json.dumps(pack, sort_keys=True, separators=(",", ":"))
        self.assertLessEqual(est_tokens(serialized), 1500)
        kept = pack["handles"]
        self.assertGreater(pack["budget"]["truncated_count"], 0,
                           "expected real-graph overflow to truncate")
        # kept handles are the highest-RRF prefix; count is exact; visible sample bounded
        self.assertEqual(kept, handles[:len(kept)])
        self.assertEqual(pack["budget"]["truncated_count"], len(handles) - len(kept))
        self.assertLessEqual(len(pack["budget"]["truncated"]),
                             lgwks_inbound.MAX_TRUNCATED_VISIBLE)
        self.assertEqual(pack["budget"]["truncated"], handles[len(kept):][:len(pack["budget"]["truncated"])])

        # no prose crossed into L5: every string leaf is a real node cid or the schema id
        node_ids = {n["id"] for n in self.graph["nodes"]}

        def walk(v):
            if isinstance(v, dict):
                for val in v.values():
                    walk(val)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
            elif isinstance(v, bool) or isinstance(v, (int, float)):
                pass
            elif isinstance(v, str):
                self.assertTrue(v == SCHEMA or v in node_ids, f"free-text leaked: {v!r}")
        walk(pack)

    def test_real_graph_fusion_deterministic(self):
        f1 = fuse(self.ranks, [])
        f2 = fuse(lgwks_rank.rank_graph(self.graph), [])
        self.assertEqual(f1, f2, "RRF over the real graph is not byte-deterministic")


class TestTenantScopedInbound(unittest.TestCase):
    """§1-INV at the consumer path (ARCH L1/L2): when assemble_inbound is given a
    tenant, a graph node owned by another tenant does not resolve and is dropped —
    no cross-tenant cid ever reaches the reflex pack handles.
    """

    def _mk(self, conn, source_cid, tenant, seed):
        floats = [float((seed + 1) * (j + 1) % 7) + 0.5 for j in range(DIM)]
        rec = lgwks_vector.encode_record(
            floats, modality="text", space_id=SPACE, tenant=tenant, source_cid=source_cid
        )
        lgwks_vector.upsert_record(conn, rec, admin=lgwks_vector.ADMIN)
        return rec

    class _FakePort:
        def __init__(self, principal, scopes):
            self._principal = principal
            self._scopes = frozenset(scopes)

        def verify(self, handle, key):
            return lgwks_access.VerifiedCap(
                principal=self._principal,
                cap_ref="fake-ref",
                scopes=self._scopes,
                _internal_cap=handle,
            )

        def require_scope(self, handle, scope, key):
            verified = self.verify(handle, key)
            if scope not in verified.scopes:
                raise RuntimeError(f"fake-port missing scope {scope}")
            return verified

    def test_cross_tenant_nodes_dropped(self):
        with TemporaryDirectory() as tmp:
            conn = lgwks_vector.create_store(Path(tmp) / "scoped.db")
            a = [self._mk(conn, f"a-{i}", "tenant-A", i) for i in range(3)]
            b = [self._mk(conn, f"b-{i}", "tenant-B", 10 + i) for i in range(3)]
            w = [self._mk(conn, f"w-{i}", lgwks_vector.WORLD_TENANT, 20 + i) for i in range(2)]
            conn.commit()

            all_recs = a + b + w
            cids = [r.cid for r in all_recs]
            rels = lgwks_rank.RELATIONS
            nodes = [{"id": c} for c in cids]
            links = [{"source": cids[i], "target": cids[(i + 1) % len(cids)],
                      "relation": rels[i % len(rels)],
                      "confidence_score": 0.9, "weight": 1.0} for i in range(len(cids))]
            graph = {"nodes": nodes, "links": links}

            b_cids = {r.cid for r in b}
            a_cids = {r.cid for r in a}
            w_cids = {r.cid for r in w}

            store = lgwks_access.TenantStore(
                self._FakePort("tenant-A", {"tenant:rw", "world:r"}),
                handle=None,
                key=b"",
                conn=conn,
            )
            pack = assemble_inbound(None, graph, conn, tenant_store=store)
            handles = set(pack["handles"]) if "handles" in pack else set()
            # Collect every cid that surfaced anywhere in the pack.
            surfaced = set(handles)
            for dh in pack.get("depth_handles", []):
                surfaced.add(dh["id"])

            self.assertEqual(surfaced & b_cids, set(),
                             "§1-INV: tenant-B cids must never reach tenant-A's pack")
            self.assertTrue(surfaced & a_cids, "tenant-A's own cids should resolve")
            self.assertTrue(surfaced & w_cids, "world cids should resolve for tenant-A")
            conn.close()

    def test_tenant_store_path_avoids_raw_tenant_resolver(self):
        with TemporaryDirectory() as td:
            conn = lgwks_vector.create_store(Path(td) / "vec.db")
            try:
                records, graph = _build_store_and_graph(conn, n=4)
                store = lgwks_access.TenantStore(
                    self._FakePort("t", {"tenant:rw", "world:r"}),
                    handle=None,
                    key=b"",
                    conn=conn,
                )
                original = store.read
                seen: list[str] = []
                try:
                    def _tracking_read(cid: str):
                        seen.append(cid)
                        return original(cid)
                    store.read = _tracking_read  # type: ignore[method-assign]
                    pack = assemble_inbound(records[0], graph, conn, tenant_store=store)
                finally:
                    store.read = original  # type: ignore[method-assign]
                self.assertTrue(pack["handles"])
                self.assertTrue(seen, "tenant path must route through TenantStore.read")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
