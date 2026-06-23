"""lgwks_embed_port — embedder runtime (lgwks.embed.port.v1).

Packet I4 of INGESTION-PLAN: unified embedding port for Qwen3-VL-Embedding-8B.

Two runtimes, one model, one space_id:
  mlx          — store/models/Qwen3-VL-Embedding-8B-mlx  (Apple Silicon, primary)
  transformers — store/models/Qwen3-VL-Embedding-8B       (CPU/MPS fallback)

NO network calls at runtime. Models must be present in store/models/ before use.
See Makefile `download-models` target — pulls from GitHub Release, not HuggingFace.

Pooling: last-token (hidden_states[-1][:, -1, :]) — decoder embedding models anchor
         meaning at the final token/EOS position, not the mean.
MRL:     caller may request k ≤ 4096; port slices [:k] and re-normalises.
Video:   I4 extracts N frames (LGWKS_EMBED_VIDEO_FRAMES, default 8) from raw bytes
         and passes them as an image sequence to the VL processor → one 4096-d vector.
         I2 never opens video bytes — that boundary is the I2/I4 contract.

Retrieval is a separate layer (the function-calling tongue). This port only produces
lgwks.vector.record.v1 blobs and hands them to the vector store.

Authority: spec/second-harness/INGESTION-PLAN.md §I4
Schema id: lgwks.embed.port.v1
"""

from __future__ import annotations

import json
import os
import re
import threading
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

SCHEMA = "lgwks.embed.port.v1"

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lgwks_vector import (  # noqa: E402
    ADMIN as vector_ADMIN,
    SCHEMA as VECTOR_SCHEMA,
    VectorRecord,
    encode_record,
    create_store,
    upsert_record,
    store_count,
)

# ---------------------------------------------------------------------------
# Paths — all local, no network. Override via env for non-default layouts.
# ---------------------------------------------------------------------------

_MODEL_STORE = _REPO_ROOT / "store" / "models"

_MLX_MODEL_DIR = os.environ.get(
    "LGWKS_EMBED_MLX_MODEL",
    str(_MODEL_STORE / "Qwen3-VL-Embedding-8B-mlx"),
)
_TRANSFORMERS_MODEL_DIR = os.environ.get(
    "LGWKS_EMBED_TRANSFORMERS_MODEL",
    str(_MODEL_STORE / "Qwen3-VL-Embedding-8B"),
)
_VENV_PYTHON = os.environ.get(
    "LGWKS_EMBED_VENV",
    str(_REPO_ROOT / ".venv" / "bin" / "python"),
)

_EMBED_DIM = 4096
_SPACE_PREFIX = "qwen3-vl-embedding-8b"
_N_VIDEO_FRAMES = int(os.environ.get("LGWKS_EMBED_VIDEO_FRAMES", "8"))

_DEFAULT_INSTRUCTIONS: dict[str, str] = {
    "text":  "Represent this code or text for semantic retrieval.",
    "image": "Represent this screenshot or diagram for semantic retrieval.",
    "video": "Represent this video for semantic retrieval.",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EmbedUnavailableError(RuntimeError):
    """No embedding tier is reachable (model not downloaded or venv missing)."""


class EmbedDimError(ValueError):
    """Requested MRL dimension exceeds model capacity."""


# ---------------------------------------------------------------------------
# Worker scripts — injected via stdin/stdout JSON-line protocol.
#
# Protocol:
#   in:  {"id": str, "text": str, "image_path"?: str, "video_path"?: str}
#   out: {"id": str, "embedding": [float, ...]}
#   err: {"id": str, "error": str}
#
# Both workers:
#   - load from a LOCAL path only (local_files_only=True / explicit dir)
#   - use last-token pooling: hidden_states[-1][0, -1, :]
#   - log to stderr only; stdout is pure JSON
# ---------------------------------------------------------------------------

def _mlx_worker_script(model_dir: str, n_frames: int) -> str:
    return f"""
import sys, json, io, os
import mlx.core as mx
from mlx_vlm import load as mlx_load
from PIL import Image

MODEL_DIR = {json.dumps(model_dir)}
N_FRAMES  = {n_frames}

print(f"[embed-port/mlx] loading {{MODEL_DIR}}", file=sys.stderr)
try:
    model, processor = mlx_load(MODEL_DIR)
    print("[embed-port/mlx] ready", file=sys.stderr)
except Exception as e:
    print(f"[embed-port/mlx] FAILED: {{e}}", file=sys.stderr)
    sys.exit(1)

real_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _video_frames(path):
    import av
    c = av.open(path)
    stream = c.streams.video[0]
    total = stream.frames or (N_FRAMES * 2)
    step = max(1, total // N_FRAMES)
    frames = []
    for i, f in enumerate(c.decode(video=0)):
        if i % step == 0:
            frames.append(f.to_image())
        if len(frames) >= N_FRAMES:
            break
    c.close()
    return frames or [Image.new("RGB", (224, 224))]


def embed(text, image_path=None, video_path=None):
    images = None
    if video_path:
        images = _video_frames(video_path)
    elif image_path:
        images = [Image.open(image_path).convert("RGB")]

    if images:
        inputs = processor(text=text, images=images, return_tensors="mlx")
    else:
        inputs = processor(text=text, return_tensors="mlx")

    out = model(**inputs, output_hidden_states=True)
    vec = out.hidden_states[-1][0, -1, :]
    mx.eval(vec)
    return vec.tolist()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        vec = embed(
            text=data.get("text", ""),
            image_path=data.get("image_path"),
            video_path=data.get("video_path"),
        )
        real_out.write(json.dumps({{"id": data.get("id"), "embedding": vec}}) + "\\n")
    except Exception as e:
        real_out.write(json.dumps({{"id": data.get("id", "?"), "error": str(e)}}) + "\\n")
    real_out.flush()
"""


def _transformers_worker_script(model_dir: str, n_frames: int) -> str:
    return f"""
import sys, json, io, os, torch
from transformers import AutoProcessor, AutoModel
from PIL import Image

MODEL_DIR = {json.dumps(model_dir)}
N_FRAMES  = {n_frames}

device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"[embed-port/transformers] loading {{MODEL_DIR}} on {{device}}", file=sys.stderr)
try:
    processor = AutoProcessor.from_pretrained(MODEL_DIR, local_files_only=True, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        MODEL_DIR, local_files_only=True, trust_remote_code=True
    ).to(device).eval()
    print("[embed-port/transformers] ready", file=sys.stderr)
except Exception as e:
    print(f"[embed-port/transformers] FAILED: {{e}}", file=sys.stderr)
    sys.exit(1)

real_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _video_frames(path):
    import av
    c = av.open(path)
    stream = c.streams.video[0]
    total = stream.frames or (N_FRAMES * 2)
    step = max(1, total // N_FRAMES)
    frames = []
    for i, f in enumerate(c.decode(video=0)):
        if i % step == 0:
            frames.append(f.to_image())
        if len(frames) >= N_FRAMES:
            break
    c.close()
    return frames or [Image.new("RGB", (224, 224))]


def embed(text, image_path=None, video_path=None):
    images = None
    if video_path:
        images = _video_frames(video_path)
    elif image_path:
        images = [Image.open(image_path).convert("RGB")]

    if images:
        inputs = processor(text=text, images=images, return_tensors="pt").to(device)
    else:
        inputs = processor(text=text, return_tensors="pt").to(device)

    with torch.no_grad():
        out = model(**inputs, output_hidden_states=True)
        # last-token pooling — hidden_states[-1]: (batch, seq_len, hidden_dim)
        vec = out.hidden_states[-1][:, -1, :].to(torch.float32).cpu().numpy().tolist()[0]
    return vec


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        vec = embed(
            text=data.get("text", ""),
            image_path=data.get("image_path"),
            video_path=data.get("video_path"),
        )
        real_out.write(json.dumps({{"id": data.get("id"), "embedding": vec}}) + "\\n")
    except Exception as e:
        real_out.write(json.dumps({{"id": data.get("id", "?"), "error": str(e)}}) + "\\n")
    real_out.flush()
"""


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _l2_normalize(floats: list[float]) -> list[float]:
    # Canonical L2 math (lgwks_vecmath); translate its zero error to this layer's
    # EmbedDimError so the public contract is unchanged but the math lives in ONE place.
    import lgwks_vecmath
    try:
        return lgwks_vecmath.l2_normalize(floats, on_zero="raise")
    except lgwks_vecmath.ZeroVectorError as exc:
        raise EmbedDimError("zero vector — cannot normalise") from exc


def _mrl_slice(floats: list[float], k: int) -> list[float]:
    if k > len(floats):
        raise EmbedDimError(f"requested dim {k} > model output dim {len(floats)}")
    return _l2_normalize(floats[:k])


# ---------------------------------------------------------------------------
# EmbedPort — the public API
# ---------------------------------------------------------------------------

@dataclass
class _WorkerState:
    proc: Optional[subprocess.Popen] = field(default=None)
    tier: str = ""


class EmbedPort:
    """Local embedding port for Qwen3-VL-Embedding-8B.

    Inputs:  text str | image bytes/path | video bytes/path | ModalityItem
    Outputs: list[float] (normalised, MRL-sliced to `dim`) or VectorRecord (via embed_to_record)

    Usage:
        with EmbedPort() as port:
            vec    = port.embed_text("def foo(): ...")
            record = port.embed_to_record(vec, modality="text",
                                          source_cid="b2b256:...", tenant="lgwks")

    Tier auto-select (same model, same space_id):
        1. mlx          — store/models/Qwen3-VL-Embedding-8B-mlx   exists + mlx_vlm importable
        2. transformers — store/models/Qwen3-VL-Embedding-8B        exists
        else → EmbedUnavailableError (run `make download-models` first)
    """

    def __init__(
        self,
        tier: str = "auto",
        *,
        dim: int = _EMBED_DIM,
    ):
        if dim > _EMBED_DIM:
            raise EmbedDimError(f"dim {dim} exceeds model max {_EMBED_DIM}")
        self._target_dim = dim
        self._state = _WorkerState()

        self._tier = self._detect_tier() if tier == "auto" else tier
        self._start_worker()

    # ── tier detection ────────────────────────────────────────────────────

    def _detect_tier(self) -> str:
        mlx_present = Path(_MLX_MODEL_DIR).exists()
        tf_present = Path(_TRANSFORMERS_MODEL_DIR).exists()

        if mlx_present and Path(_VENV_PYTHON).exists():
            probe = subprocess.run(
                [_VENV_PYTHON, "-c", "import mlx_vlm"],
                capture_output=True,
            )
            if probe.returncode == 0:
                return "mlx"

        if tf_present and Path(_VENV_PYTHON).exists():
            probe = subprocess.run(
                [_VENV_PYTHON, "-c", "import transformers"],
                capture_output=True,
            )
            if probe.returncode == 0:
                return "transformers"

        raise EmbedUnavailableError(
            "no model found in store/models/. "
            "Run `make download-models` to fetch Qwen3-VL-Embedding-8B. "
            f"(mlx_dir={_MLX_MODEL_DIR}, transformers_dir={_TRANSFORMERS_MODEL_DIR})"
        )

    # ── subprocess worker lifecycle ───────────────────────────────────────

    def _start_worker(self) -> None:
        if self._tier == "mlx":
            script = _mlx_worker_script(_MLX_MODEL_DIR, _N_VIDEO_FRAMES)
        elif self._tier == "transformers":
            script = _transformers_worker_script(_TRANSFORMERS_MODEL_DIR, _N_VIDEO_FRAMES)
        else:
            raise EmbedUnavailableError(f"unknown tier: {self._tier!r}")

        tmp = _REPO_ROOT / "store" / f"_embed_worker_{self._tier}.py"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(script)
        # Hardening (#154 M10): remember the generated worker script so close()
        # can remove it instead of leaving stale files in store/.
        self._worker_script = tmp

        proc = subprocess.Popen(
            [_VENV_PYTHON, str(tmp)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # worker logs go to parent stderr — visible to user
            text=True,
            bufsize=1,
        )
        self._state.proc = proc
        self._state.tier = self._tier

    def _readline_bounded(self, proc) -> str:
        """proc.stdout.readline() with a wall-clock deadline. On timeout, kill the
        worker and raise EmbedUnavailableError so the caller fails closed (degrades)
        rather than blocking indefinitely on a stuck model worker."""
        try:
            timeout = float(os.environ.get("LGWKS_EMBED_TIMEOUT", "180"))
        except ValueError:
            timeout = 180.0
        if timeout <= 0:
            return proc.stdout.readline()
        box: dict = {}

        def _rd() -> None:
            try:
                box["line"] = proc.stdout.readline()
            except BaseException as exc:  # noqa: BLE001 — surfaced to caller below
                box["err"] = exc

        t = threading.Thread(target=_rd, daemon=True, name="lgwks-embed-rpc")
        t.start()
        t.join(timeout)
        if t.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            self._state.proc = None
            raise EmbedUnavailableError(f"embed worker exceeded {timeout:g}s — killed; degrading")
        if "err" in box:
            raise box["err"]
        return box.get("line", "")

    def _rpc(self, payload: dict) -> list[float]:
        proc = self._state.proc
        if proc is None or proc.poll() is not None:
            raise EmbedUnavailableError("worker process is not running")
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
        # Bound the blocking read: a wedged worker (or a cold 8B-model load that
        # never returns) must NOT hang the caller forever. The first RPC pays the
        # cold-load, so the deadline is generous (LGWKS_EMBED_TIMEOUT, default
        # 180s) — finite, not infinite. On timeout the worker is killed and the
        # caller degrades via EmbedUnavailableError. (review-hang class fix.)
        line = self._readline_bounded(proc)
        if not line:
            raise EmbedUnavailableError("worker returned empty response (may have crashed)")
        result = json.loads(line)
        if "error" in result:
            raise EmbedUnavailableError(f"worker error: {result['error']}")
        emb = result.get("embedding")
        if not emb:
            raise EmbedUnavailableError("worker returned null embedding")
        return emb

    # ── public embedding methods ──────────────────────────────────────────

    def embed_text(self, text: str, instruction: str = "") -> list[float]:
        """Embed a text string. Returns a normalised float list."""
        inst = instruction or _DEFAULT_INSTRUCTIONS["text"]
        floats = self._rpc({"id": "t", "text": f"{inst} {text}"})
        return _mrl_slice(floats, self._target_dim) if self._target_dim < len(floats) else _l2_normalize(floats)

    def embed_image(
        self,
        source: Union[bytes, str, Path],
        instruction: str = "",
    ) -> list[float]:
        """Embed an image. Accepts raw bytes, a file path, or a Path object."""
        inst = instruction or _DEFAULT_INSTRUCTIONS["image"]
        if isinstance(source, bytes):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(source)
                tmp_path = f.name
            try:
                floats = self._rpc({"id": "i", "text": inst, "image_path": tmp_path})
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        else:
            # Hardening (#154 M2): only forward a real, existing regular file to
            # the worker subprocess. Rejects directories, device nodes, and
            # dangling/symlink-to-nonfile paths so a caller cannot probe
            # arbitrary filesystem locations through the worker.
            resolved = Path(source).resolve()
            if not resolved.is_file():
                raise FileNotFoundError(f"embed_image: not a regular file: {source!r}")
            floats = self._rpc({"id": "i", "text": inst, "image_path": str(resolved)})
        return _mrl_slice(floats, self._target_dim) if self._target_dim < len(floats) else _l2_normalize(floats)

    def embed_video(
        self,
        source: Union[bytes, str, Path],
        instruction: str = "",
    ) -> list[float]:
        """Embed a video. Accepts raw bytes, a file path, or a Path object.

        The worker extracts N evenly-spaced frames and passes them as an image
        sequence to the VL processor — one 4096-d vector out.
        """
        inst = instruction or _DEFAULT_INSTRUCTIONS["video"]
        if isinstance(source, bytes):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(source)
                tmp_path = f.name
            try:
                floats = self._rpc({"id": "v", "text": inst, "video_path": tmp_path})
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        else:
            floats = self._rpc({"id": "v", "text": inst, "video_path": str(source)})
        return _mrl_slice(floats, self._target_dim) if self._target_dim < len(floats) else _l2_normalize(floats)

    def embed_from_item(self, item: object, instruction: str = "") -> list[float]:
        """Dispatch to the correct embed method based on a lgwks.modality.item.v1 ModalityItem.

        text         → embed_text(item.parsed_unit)
        image        → embed_image(item.raw_bytes)
        video        → embed_video(item.raw_bytes)   — native VL, not per-frame OCR
        quarantine   → raises ValueError
        """
        modality = getattr(item, "modality", None)
        strategy = getattr(item, "extraction_strategy", None)

        if modality == "text":
            text = getattr(item, "parsed_unit", "") or ""
            return self.embed_text(text, instruction)

        if modality == "image" and strategy == "visual_embed":
            raw = getattr(item, "raw_bytes", None)
            if raw is None:
                raise ValueError("image ModalityItem has no raw_bytes")
            return self.embed_image(raw, instruction)

        if modality == "video" and strategy == "video_embed":
            raw = getattr(item, "raw_bytes", None)
            if raw is None:
                raise ValueError("video ModalityItem has no raw_bytes")
            return self.embed_video(raw, instruction)

        if modality == "quarantine":
            reason = getattr(item, "quarantine_reason", "")
            raise ValueError(f"cannot embed quarantined item: {reason}")

        raise ValueError(
            f"unhandled modality/strategy pair: modality={modality!r} strategy={strategy!r}"
        )

    def space_id(self) -> str:
        """Canonical space identifier. All tiers produce this same id."""
        return f"{_SPACE_PREFIX}:d{self._target_dim}"

    def embed_to_record(
        self,
        floats: list[float],
        *,
        modality: str,
        source_cid: str,
        tenant: str,
    ) -> "VectorRecord":
        """Wrap a float list into a lgwks.vector.record.v1 record (via I1)."""
        return encode_record(
            floats,
            modality=modality,
            space_id=self.space_id(),
            tenant=tenant,
            source_cid=source_cid,
        )

    def close(self) -> None:
        if self._state.proc and self._state.proc.poll() is None:
            self._state.proc.terminate()
            try:
                self._state.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._state.proc.kill()
        # Hardening (#154 M10): clean up the generated worker script (no leak in store/).
        script = getattr(self, "_worker_script", None)
        if script is not None:
            try:
                Path(script).unlink(missing_ok=True)
            except OSError:
                pass
            self._worker_script = None

    def __enter__(self) -> "EmbedPort":
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Migration helper: JSON-text embeddings → lgwks.vector.record.v1
# Fixes the G-11 gap in ~/ingestion_results/*.db stores.
# ---------------------------------------------------------------------------

def migrate_json_embeddings(
    src_db: Path,
    dst_db: Path,
    *,
    table: str = "intelligence",
    id_col: str = "source",
    embedding_col: str = "embedding",
    type_col: str = "type",
    space_id: str = f"{_SPACE_PREFIX}:d{_EMBED_DIM}",
    tenant: str = "logicalworks-",
    modality: str = "text",
) -> dict:
    """Migrate a JSON-text embedding column to binary lgwks.vector.record.v1 records.

    Reads any SQLite table that stores embeddings as JSON text arrays (the G-11 pattern)
    and writes binary vector records into dst_db via the I1 store.

    Returns: {"rows_attempted": N, "inserted": M, "skipped": K, "store_total": T}
    """
    def _src_cid(ident: str) -> str:
        from axiom.cid import compute_cid as _cc  # type: ignore[import]
        return _cc(ident.encode())

    # HARDEN: Validate identifiers to prevent SQL injection (C4)
    def _validate_ident(s: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", s):
            raise ValueError(f"malicious SQL identifier: {s!r}")
        return s

    _validate_ident(table)
    _validate_ident(id_col)
    _validate_ident(embedding_col)
    _validate_ident(type_col)

    import lgwks_sqlite  # canonical hardened connect (#223 family 4)

    # Read-only source: wal=False so we never rewrite the source DB's journal mode.
    src = lgwks_sqlite.connect(src_db, wal=False)
    dst_conn = create_store(dst_db)

    # Use double-quotes for identifiers in the query (extra safety)
    rows = src.execute(
        f'SELECT "{id_col}", "{type_col}", "{embedding_col}" '
        f'FROM "{table}" WHERE "{embedding_col}" IS NOT NULL'
    ).fetchall()

    inserted = skipped = 0
    for row_id, row_type, emb_json in rows:
        try:
            floats = json.loads(emb_json) if isinstance(emb_json, str) else list(emb_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            skipped += 1
            continue

        if not (64 <= len(floats) <= _EMBED_DIM):
            skipped += 1
            continue

        try:
            record = encode_record(
                floats,
                modality=modality,
                space_id=space_id,
                tenant=row_type or tenant,
                source_cid=_src_cid(str(row_id)),
            )
            upsert_record(dst_conn, record, admin=vector_ADMIN)  # bulk migration — admin context
            inserted += 1
        except Exception:
            skipped += 1

    dst_conn.commit()
    total = store_count(dst_conn)
    dst_conn.close()
    src.close()

    return {
        "schema": VECTOR_SCHEMA,
        "source_table": f"{src_db}::{table}",
        "destination": str(dst_db),
        "rows_attempted": len(rows),
        "inserted": inserted,
        "skipped": skipped,
        "store_total": total,
    }


# ---------------------------------------------------------------------------
# Graph loader: graphify graph.json → system_graph table
# Populates the empty system_graph table in the unified brain DB.
# ---------------------------------------------------------------------------

_SYSTEM_GRAPH_DDL = """
CREATE TABLE IF NOT EXISTS system_graph (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    repo       TEXT NOT NULL DEFAULT '',
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sg_name ON system_graph(name);
"""


def load_graphify(
    graph_json_path: Path,
    dst_db: Path,
    *,
    name: str = "",
    repo: str = "",
    gate: Any = None,
) -> dict:
    """Load a graphify graph.json, recording it on the State Fabric tape.

    Convergence (#165 step 1 — see docs/data-model.mmd): when `gate` (a
    StorageGate) is provided, the graph is recorded as a content-addressed
    `reasoning` artifact on the tape — the Source of Record. The `system_graph`
    table is then a human-readable derived EXPORT, not the source of truth. With
    no gate, behaviour is unchanged (system_graph only).

    Idempotent — replaces any existing system_graph row with the same name; the
    tape dedups by content cid. Returns a summary dict (includes `artifact_cid`
    when routed through the gate).
    """
    data = graph_json_path.read_text()
    graph = json.loads(data)
    node_count = len(graph.get("nodes", []))
    edge_count = len(graph.get("links", graph.get("edges", [])))
    graph_name = name or graph_json_path.parent.name
    repo_val = repo or graph_name

    import lgwks_sqlite  # canonical hardened connect (#223 family 4)

    conn = lgwks_sqlite.connect(dst_db)
    conn.executescript(_SYSTEM_GRAPH_DDL)
    conn.execute("DELETE FROM system_graph WHERE name = ?", (graph_name,))
    conn.execute(
        "INSERT INTO system_graph (name, graph_json, repo, node_count, edge_count) VALUES (?,?,?,?,?)",
        (graph_name, data, repo_val, node_count, edge_count),
    )
    conn.commit()
    conn.close()

    result = {
        "graph": graph_name,
        "repo": repo_val,
        "nodes": node_count,
        "edges": edge_count,
        "destination": str(dst_db),
    }

    # Convergence: record the graph on the tape (SoR), content-addressed by cid,
    # so it joins the one data model instead of living only in a bypass table.
    if gate is not None:
        from axiom.cid import compute_cid
        artifact_cid = compute_cid(data.encode("utf-8", errors="ignore"))
        gate.ingest_fact(
            artifact_cid,
            data,
            "reasoning",
            "system-graph-import",
            meta={
                "title": graph_name,
                "repo": repo_val,
                "node_count": node_count,
                "edge_count": edge_count,
                "chunk_kind": "system_graph",
            },
        )
        result["artifact_cid"] = artifact_cid

    return result


def load_all_graphs(ingestion_dir: Path, dst_db: Path, *, gate: Any = None) -> list[dict]:
    """Load all graph.json files found under ingestion_dir into dst_db.

    When `gate` is provided, each graph is also recorded on the tape (SoR) — see
    load_graphify.
    """
    results = []
    for graph_json in sorted(ingestion_dir.glob("**/graph.json")):
        repo = graph_json.parent.name.replace("_graph", "")
        try:
            results.append(load_graphify(graph_json, dst_db, repo=repo, gate=gate))
        except Exception as exc:
            results.append({"graph": str(graph_json), "error": str(exc)})
    return results
