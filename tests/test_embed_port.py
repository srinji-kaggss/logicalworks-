"""Tests for lgwks_embed_port (lgwks.embed.port.v1).

All tests are fully mocked — no model weights required, no network calls.

Coverage:
  - Tier detection (mlx-first, transformers fallback, error when neither)
  - Worker lifecycle: start, _rpc, crash detection
  - embed_text / embed_image / embed_video — normalisation, MRL slice
  - embed_from_item — routing by modality/strategy, quarantine raises
  - embed_to_record — produces a valid lgwks.vector.record.v1
  - space_id consistency across tiers
  - _l2_normalize / _mrl_slice math
  - migrate_json_embeddings — reads JSON-text, writes binary records
  - load_graphify — inserts + idempotent reload
  - load_all_graphs — multi-graph discovery
"""

import json
import math
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

# ── path setup ───────────────────────────────────────────────────────────────
_WORKTREE = Path(__file__).resolve().parent.parent
if str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

# ── stub lgwks_vector so tests run without the full repo on PYTHONPATH ───────
# (the real module lives in the primary worktree; in CI the worktree may be isolated)
if "lgwks_vector" not in sys.modules:
    import struct

    _stub = types.ModuleType("lgwks_vector")
    _stub.SCHEMA = "lgwks.vector.record.v1"

    class _FakeRecord:
        def __init__(self, floats, **kw):
            self.floats = floats
            self.meta = kw

    _stub.VectorRecord = _FakeRecord

    def _encode_record(floats, *, modality, space_id, tenant, source_cid):
        return _FakeRecord(floats, modality=modality, space_id=space_id,
                           tenant=tenant, source_cid=source_cid)

    def _create_store(path):
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS vector_records "
            "(cid TEXT PRIMARY KEY, data BLOB)"
        )
        conn.commit()
        return conn

    def _upsert_record(conn, record):
        import hashlib
        cid = hashlib.blake2b(str(record.floats).encode(), digest_size=8).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO vector_records (cid, data) VALUES (?,?)",
            (cid, str(record.floats).encode()),
        )

    def _store_count(conn):
        return conn.execute("SELECT COUNT(*) FROM vector_records").fetchone()[0]

    _stub.encode_record = _encode_record
    _stub.create_store = _create_store
    _stub.upsert_record = _upsert_record
    _stub.store_count = _store_count
    sys.modules["lgwks_vector"] = _stub

# ── also stub axiom.cid used by migrate_json_embeddings ─────────────────────
if "axiom" not in sys.modules:
    _axiom = types.ModuleType("axiom")
    _axiom_cid = types.ModuleType("axiom.cid")

    def _compute_cid(data: bytes) -> str:
        import hashlib
        return "b2b256:" + hashlib.blake2b(data, digest_size=32).hexdigest()

    _axiom_cid.compute_cid = _compute_cid
    _axiom.cid = _axiom_cid
    sys.modules["axiom"] = _axiom
    sys.modules["axiom.cid"] = _axiom_cid

import lgwks_embed_port as ep
from lgwks_embed_port import (
    EmbedDimError,
    EmbedPort,
    EmbedUnavailableError,
    _l2_normalize,
    _mrl_slice,
    load_all_graphs,
    load_graphify,
    migrate_json_embeddings,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _unit_vec(d: int = ep._EMBED_DIM) -> list[float]:
    """A normalised all-ones vector of dim d."""
    v = [1.0] * d
    n = math.sqrt(d)
    return [x / n for x in v]


def _mock_proc(embedding: list[float]):
    """Return a mock Popen-like object that always responds with the given embedding."""
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.readline.return_value = json.dumps({"id": "t", "embedding": embedding}) + "\n"
    return proc


def _make_port(tier: str = "transformers", dim: int = ep._EMBED_DIM, embedding=None):
    """Construct an EmbedPort with a mocked worker process."""
    vec = embedding or _unit_vec(ep._EMBED_DIM)
    with patch("subprocess.Popen", return_value=_mock_proc(vec)), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.object(Path, "write_text"), \
         patch.object(Path, "mkdir"):
        port = EmbedPort(tier=tier, dim=dim)
        port._state.proc = _mock_proc(vec)
    return port


# ═══════════════════════════════════════════════════════════════════════════════
# Math
# ═══════════════════════════════════════════════════════════════════════════════

class TestL2Normalize(unittest.TestCase):
    def test_unit_vector_unchanged(self):
        v = [1.0, 0.0, 0.0]
        n = _l2_normalize(v)
        self.assertAlmostEqual(n[0], 1.0, places=9)
        self.assertAlmostEqual(n[1], 0.0, places=9)

    def test_norm_is_one(self):
        v = [3.0, 4.0]
        n = _l2_normalize(v)
        norm = math.sqrt(sum(x * x for x in n))
        self.assertAlmostEqual(norm, 1.0, places=9)

    def test_zero_vector_raises(self):
        with self.assertRaises(EmbedDimError):
            _l2_normalize([0.0, 0.0, 0.0])


class TestMrlSlice(unittest.TestCase):
    def test_slice_length(self):
        v = _unit_vec(4096)
        s = _mrl_slice(v, 256)
        self.assertEqual(len(s), 256)

    def test_slice_is_normalised(self):
        v = [1.0] * 4096
        s = _mrl_slice(v, 512)
        norm = math.sqrt(sum(x * x for x in s))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_k_gt_dim_raises(self):
        v = [1.0, 2.0, 3.0]
        with self.assertRaises(EmbedDimError):
            _mrl_slice(v, 10)

    def test_full_dim_returns_all(self):
        v = _unit_vec(4096)
        s = _mrl_slice(v, 4096)
        self.assertEqual(len(s), 4096)


# ═══════════════════════════════════════════════════════════════════════════════
# Tier detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestTierDetection(unittest.TestCase):
    def _detect(self, mlx_exists, tf_exists, mlx_import_ok, tf_import_ok):
        def _path_exists(self_path):
            s = str(self_path)
            if "Qwen3-VL-Embedding-8B-mlx" in s:
                return mlx_exists
            if "Qwen3-VL-Embedding-8B" in s and "mlx" not in s:
                return tf_exists
            return True  # venv python

        def _run(cmd, **kw):
            m = MagicMock()
            if "mlx_vlm" in " ".join(cmd):
                m.returncode = 0 if mlx_import_ok else 1
            else:
                m.returncode = 0 if tf_import_ok else 1
            return m

        port = object.__new__(EmbedPort)
        port._target_dim = ep._EMBED_DIM
        with patch.object(Path, "exists", _path_exists), \
             patch("subprocess.run", side_effect=_run):
            return port._detect_tier()

    def test_mlx_preferred_when_available(self):
        self.assertEqual(self._detect(True, True, True, True), "mlx")

    def test_falls_back_to_transformers(self):
        self.assertEqual(self._detect(False, True, False, True), "transformers")

    def test_mlx_model_missing_falls_back(self):
        # mlx dir absent → skip mlx even if mlx_vlm importable
        self.assertEqual(self._detect(False, True, True, True), "transformers")

    def test_neither_available_raises(self):
        port = object.__new__(EmbedPort)
        port._target_dim = ep._EMBED_DIM
        with patch.object(Path, "exists", return_value=False), \
             patch("subprocess.run", return_value=MagicMock(returncode=1)):
            with self.assertRaises(EmbedUnavailableError):
                port._detect_tier()


# ═══════════════════════════════════════════════════════════════════════════════
# EmbedPort — constructor guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbedPortConstructor(unittest.TestCase):
    def test_dim_exceeds_max_raises(self):
        with self.assertRaises(EmbedDimError):
            with patch("pathlib.Path.exists", return_value=True), \
                 patch("subprocess.run", return_value=MagicMock(returncode=0)), \
                 patch("subprocess.Popen", return_value=_mock_proc(_unit_vec())), \
                 patch.object(Path, "write_text"), patch.object(Path, "mkdir"):
                EmbedPort(dim=9999)

    def test_unknown_tier_raises(self):
        with self.assertRaises(EmbedUnavailableError):
            with patch("pathlib.Path.exists", return_value=True), \
                 patch("subprocess.Popen", return_value=_mock_proc(_unit_vec())), \
                 patch.object(Path, "write_text"), patch.object(Path, "mkdir"):
                EmbedPort(tier="nonexistent_tier")

    def test_space_id_format(self):
        port = _make_port(dim=256)
        self.assertEqual(port.space_id(), "qwen3-vl-embedding-8b:d256")

    def test_space_id_full_dim(self):
        port = _make_port(dim=4096)
        self.assertEqual(port.space_id(), "qwen3-vl-embedding-8b:d4096")

    def test_space_id_same_across_tiers(self):
        p1 = _make_port(tier="mlx", dim=512)
        p2 = _make_port(tier="transformers", dim=512)
        self.assertEqual(p1.space_id(), p2.space_id())


# ═══════════════════════════════════════════════════════════════════════════════
# RPC
# ═══════════════════════════════════════════════════════════════════════════════

class TestRpc(unittest.TestCase):
    def test_dead_process_raises(self):
        port = _make_port()
        port._state.proc.poll.return_value = 1  # exited
        with self.assertRaises(EmbedUnavailableError):
            port._rpc({"id": "t", "text": "hello"})

    def test_empty_response_raises(self):
        port = _make_port()
        port._state.proc.stdout.readline.return_value = ""
        with self.assertRaises(EmbedUnavailableError):
            port._rpc({"id": "t", "text": "hello"})

    def test_worker_error_propagates(self):
        port = _make_port()
        port._state.proc.stdout.readline.return_value = (
            json.dumps({"id": "t", "error": "kaboom"}) + "\n"
        )
        with self.assertRaises(EmbedUnavailableError, msg="kaboom"):
            port._rpc({"id": "t", "text": "hello"})

    def test_null_embedding_raises(self):
        port = _make_port()
        port._state.proc.stdout.readline.return_value = (
            json.dumps({"id": "t", "embedding": None}) + "\n"
        )
        with self.assertRaises(EmbedUnavailableError):
            port._rpc({"id": "t", "text": "hello"})


# ═══════════════════════════════════════════════════════════════════════════════
# embed_text
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbedText(unittest.TestCase):
    def test_returns_normalised_vector(self):
        port = _make_port()
        vec = port.embed_text("hello")
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_mrl_slice_applied(self):
        port = _make_port(dim=128)
        vec = port.embed_text("hello")
        self.assertEqual(len(vec), 128)

    def test_instruction_prepended(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_text("my code", instruction="Custom instruction.")
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("Custom instruction.", call_payload["text"])
        self.assertIn("my code", call_payload["text"])

    def test_default_instruction_used_when_empty(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_text("my code")
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("retrieval", call_payload["text"].lower())


# ═══════════════════════════════════════════════════════════════════════════════
# embed_image
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbedImage(unittest.TestCase):
    def test_accepts_path_string(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_image("/tmp/test.png")
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("image_path", call_payload)
        self.assertEqual(call_payload["image_path"], "/tmp/test.png")

    def test_accepts_path_object(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_image(Path("/tmp/test.png"))
        call_payload = port._rpc.call_args[0][0]
        self.assertEqual(call_payload["image_path"], "/tmp/test.png")

    def test_accepts_bytes_writes_temp_file(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        port.embed_image(png_bytes)
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("image_path", call_payload)
        # temp file should be cleaned up already
        self.assertFalse(Path(call_payload["image_path"]).exists())

    def test_returns_normalised_vector(self):
        port = _make_port()
        vec = port.embed_image("/tmp/test.png")
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=6)


# ═══════════════════════════════════════════════════════════════════════════════
# embed_video
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbedVideo(unittest.TestCase):
    def test_accepts_path_string(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_video("/tmp/clip.mp4")
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("video_path", call_payload)

    def test_accepts_bytes_writes_temp_file(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        mp4_bytes = b"\x00\x00\x00\x18ftyp" + b"\x00" * 100
        port.embed_video(mp4_bytes)
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("video_path", call_payload)
        # temp file cleaned up
        self.assertFalse(Path(call_payload["video_path"]).exists())

    def test_returns_normalised_vector(self):
        port = _make_port()
        vec = port.embed_video("/tmp/clip.mp4")
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_mrl_slice_applied(self):
        port = _make_port(dim=512)
        vec = port.embed_video("/tmp/clip.mp4")
        self.assertEqual(len(vec), 512)

    def test_instruction_sent_to_worker(self):
        port = _make_port()
        port._rpc = MagicMock(return_value=_unit_vec())
        port.embed_video("/tmp/clip.mp4", instruction="Describe this screen recording.")
        call_payload = port._rpc.call_args[0][0]
        self.assertIn("Describe this screen recording.", call_payload["text"])


# ═══════════════════════════════════════════════════════════════════════════════
# embed_from_item — routing
# ═══════════════════════════════════════════════════════════════════════════════

def _item(**kw):
    defaults = dict(
        schema="lgwks.modality.item.v1",
        modality="text",
        parsed_unit="hello",
        raw_bytes=None,
        mime="text/plain",
        origin="test",
        extraction_strategy="text_direct",
        frame_index=-1,
        source_fingerprint="",
        quarantine_reason="",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestEmbedFromItem(unittest.TestCase):
    def setUp(self):
        self.port = _make_port()
        self.port.embed_text = MagicMock(return_value=_unit_vec())
        self.port.embed_image = MagicMock(return_value=_unit_vec())
        self.port.embed_video = MagicMock(return_value=_unit_vec())

    def test_text_item_routes_to_embed_text(self):
        self.port.embed_from_item(_item(modality="text", extraction_strategy="text_direct"))
        self.port.embed_text.assert_called_once()
        self.port.embed_image.assert_not_called()
        self.port.embed_video.assert_not_called()

    def test_text_item_passes_parsed_unit(self):
        self.port.embed_from_item(_item(modality="text", parsed_unit="def foo(): pass"))
        args, kwargs = self.port.embed_text.call_args
        self.assertEqual(args[0], "def foo(): pass")

    def test_image_visual_embed_routes_to_embed_image(self):
        raw = b"\x89PNG" + b"\x00" * 10
        self.port.embed_from_item(_item(
            modality="image",
            extraction_strategy="visual_embed",
            raw_bytes=raw,
            parsed_unit=None,
        ))
        self.port.embed_image.assert_called_once_with(raw, "")

    def test_video_embed_routes_to_embed_video(self):
        raw = b"\x00\x00\x00\x18ftyp" + b"\x00" * 10
        self.port.embed_from_item(_item(
            modality="video",
            extraction_strategy="video_embed",
            raw_bytes=raw,
            parsed_unit=None,
        ))
        self.port.embed_video.assert_called_once_with(raw, "")

    def test_quarantine_raises(self):
        with self.assertRaises(ValueError, msg="quarantine"):
            self.port.embed_from_item(_item(modality="quarantine", quarantine_reason="unknown binary"))

    def test_image_missing_raw_bytes_raises(self):
        with self.assertRaises(ValueError, msg="raw_bytes"):
            self.port.embed_from_item(_item(
                modality="image",
                extraction_strategy="visual_embed",
                raw_bytes=None,
            ))

    def test_video_missing_raw_bytes_raises(self):
        with self.assertRaises(ValueError, msg="raw_bytes"):
            self.port.embed_from_item(_item(
                modality="video",
                extraction_strategy="video_embed",
                raw_bytes=None,
            ))

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            self.port.embed_from_item(_item(modality="image", extraction_strategy="ocr_image"))

    def test_instruction_forwarded(self):
        self.port.embed_from_item(
            _item(modality="text", parsed_unit="x"),
            instruction="Custom.",
        )
        _, kwargs = self.port.embed_text.call_args
        self.assertEqual(kwargs.get("instruction") or self.port.embed_text.call_args[0][1], "Custom.")


# ═══════════════════════════════════════════════════════════════════════════════
# embed_to_record
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmbedToRecord(unittest.TestCase):
    def test_produces_vector_record(self):
        port = _make_port(dim=256)
        floats = _unit_vec(256)
        record = port.embed_to_record(floats, modality="text",
                                       source_cid="b2b256:abc", tenant="lgwks")
        self.assertIsNotNone(record)
        self.assertEqual(record.meta["space_id"], "qwen3-vl-embedding-8b:d256")
        self.assertEqual(record.meta["modality"], "text")
        self.assertEqual(record.meta["tenant"], "lgwks")
        self.assertEqual(record.meta["source_cid"], "b2b256:abc")

    def test_space_id_in_record_matches_port(self):
        port = _make_port(dim=1024)
        record = port.embed_to_record(_unit_vec(1024), modality="image",
                                       source_cid="b2b256:xyz", tenant="t")
        self.assertEqual(record.meta["space_id"], port.space_id())


# ═══════════════════════════════════════════════════════════════════════════════
# Context manager
# ═══════════════════════════════════════════════════════════════════════════════

class TestContextManager(unittest.TestCase):
    def test_close_terminates_worker(self):
        port = _make_port()
        proc = port._state.proc
        proc.poll.return_value = None
        port.close()
        proc.terminate.assert_called_once()

    def test_close_idempotent_when_already_dead(self):
        port = _make_port()
        port._state.proc.poll.return_value = 1  # already exited
        port.close()  # should not raise

    def test_context_manager_calls_close(self):
        port = _make_port()
        port.close = MagicMock()
        with port:
            pass
        port.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# migrate_json_embeddings
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrateJsonEmbeddings(unittest.TestCase):
    def _make_src_db(self, tmpdir, rows) -> Path:
        p = Path(tmpdir) / "src.db"
        conn = sqlite3.connect(str(p))
        conn.execute(
            "CREATE TABLE intelligence "
            "(source TEXT, type TEXT, embedding TEXT)"
        )
        for source, typ, emb in rows:
            conn.execute(
                "INSERT INTO intelligence VALUES (?,?,?)",
                (source, typ, json.dumps(emb) if emb is not None else None),
            )
        conn.commit()
        conn.close()
        return p

    def test_valid_rows_inserted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vec = [1.0 / 64] * 4096
            src = self._make_src_db(tmpdir, [
                ("row1", "code", vec),
                ("row2", "law",  vec),
            ])
            dst = Path(tmpdir) / "dst.db"
            stats = migrate_json_embeddings(src, dst)
            self.assertEqual(stats["inserted"], 2)
            self.assertEqual(stats["skipped"], 0)
            self.assertEqual(stats["rows_attempted"], 2)

    def test_short_vector_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src_db(tmpdir, [
                ("r1", "t", [0.1, 0.2]),  # only 2 dims — below min 64
            ])
            stats = migrate_json_embeddings(src, Path(tmpdir) / "dst.db")
            self.assertEqual(stats["inserted"], 0)
            self.assertEqual(stats["skipped"], 1)

    def test_null_embedding_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src_db(tmpdir, [("r1", "t", None)])
            stats = migrate_json_embeddings(src, Path(tmpdir) / "dst.db")
            self.assertEqual(stats["rows_attempted"], 0)  # WHERE NOT NULL filters it

    def test_corrupt_json_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "src.db"
            conn = sqlite3.connect(str(p))
            conn.execute("CREATE TABLE intelligence (source TEXT, type TEXT, embedding TEXT)")
            conn.execute("INSERT INTO intelligence VALUES ('r1','t','not-valid-json')")
            conn.commit()
            conn.close()
            stats = migrate_json_embeddings(p, Path(tmpdir) / "dst.db")
            self.assertEqual(stats["skipped"], 1)

    def test_stats_schema_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src_db(tmpdir, [])
            stats = migrate_json_embeddings(src, Path(tmpdir) / "dst.db")
            self.assertEqual(stats["schema"], "lgwks.vector.record.v1")
            self.assertIn("source_table", stats)
            self.assertIn("destination", stats)


# ═══════════════════════════════════════════════════════════════════════════════
# load_graphify
# ═══════════════════════════════════════════════════════════════════════════════

def _graph_json(nodes=5, edges=4) -> dict:
    return {
        "nodes": [{"id": str(i)} for i in range(nodes)],
        "links": [{"source": str(i), "target": str(i + 1)} for i in range(edges)],
    }


class TestLoadGraphify(unittest.TestCase):
    def test_inserts_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gj = Path(tmpdir) / "logicalworks-_graph" / "graph.json"
            gj.parent.mkdir()
            gj.write_text(json.dumps(_graph_json(10, 8)))
            dst = Path(tmpdir) / "brain.db"
            result = load_graphify(gj, dst)
            self.assertEqual(result["nodes"], 10)
            self.assertEqual(result["edges"], 8)
            conn = sqlite3.connect(str(dst))
            count = conn.execute("SELECT COUNT(*) FROM system_graph").fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)

    def test_idempotent_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gj = Path(tmpdir) / "repo_graph" / "graph.json"
            gj.parent.mkdir()
            gj.write_text(json.dumps(_graph_json(3, 2)))
            dst = Path(tmpdir) / "brain.db"
            load_graphify(gj, dst)
            load_graphify(gj, dst)  # reload
            conn = sqlite3.connect(str(dst))
            count = conn.execute("SELECT COUNT(*) FROM system_graph").fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)  # replaced, not duplicated

    def test_custom_name_used(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gj = Path(tmpdir) / "x_graph" / "graph.json"
            gj.parent.mkdir()
            gj.write_text(json.dumps(_graph_json()))
            dst = Path(tmpdir) / "brain.db"
            result = load_graphify(gj, dst, name="my-graph")
            self.assertEqual(result["graph"], "my-graph")

    def test_edges_key_alias(self):
        """graph.json may use 'edges' instead of 'links'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gj = Path(tmpdir) / "x_graph" / "graph.json"
            gj.parent.mkdir()
            data = {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "a"}]}
            gj.write_text(json.dumps(data))
            dst = Path(tmpdir) / "brain.db"
            result = load_graphify(gj, dst)
            self.assertEqual(result["edges"], 1)


class TestLoadAllGraphs(unittest.TestCase):
    def test_discovers_multiple_graphs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ("logicalworks-_graph", "logic-os-kernel_graph"):
                d = Path(tmpdir) / name
                d.mkdir()
                (d / "graph.json").write_text(json.dumps(_graph_json(4, 3)))
            dst = Path(tmpdir) / "brain.db"
            results = load_all_graphs(Path(tmpdir), dst)
            self.assertEqual(len(results), 2)
            self.assertFalse(any("error" in r for r in results))

    def test_error_row_on_bad_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir) / "broken_graph"
            d.mkdir()
            (d / "graph.json").write_text("not json")
            results = load_all_graphs(Path(tmpdir), Path(tmpdir) / "brain.db")
            self.assertEqual(len(results), 1)
            self.assertIn("error", results[0])

    def test_repo_name_stripped_of_graph_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir) / "myrepo_graph"
            d.mkdir()
            (d / "graph.json").write_text(json.dumps(_graph_json()))
            results = load_all_graphs(Path(tmpdir), Path(tmpdir) / "brain.db")
            self.assertEqual(results[0]["repo"], "myrepo")


if __name__ == "__main__":
    unittest.main()
