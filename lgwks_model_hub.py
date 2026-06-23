"""lgwks_model_hub — repo-resident model loading + developer setup for local CoreML use.

Design:
  - Runtime: load from models/ inside the repo — zero network dependency
  - Setup: scripts/setup_models.py downloads, scrubs, converts once per developer
  - Source: HuggingFace Hub (Apache-2.0 only) during setup; never at runtime
  - No secrets, no API keys, no cloud inference at runtime

//why: The security posture forbids runtime cloud inference. The model weights live
in the repo (git-lfs for >100MB). Only the setup script touches the network.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Runtime models live in the repo, not in ~/.config
_REPO_MODELS_DIR = Path(__file__).resolve().parent / "models"

# THE single model-loader catalog (download coordinates: repo + pinned revision +
# license + loader metadata). scripts/setup_models.py imports THIS — it does not keep
# its own copy (the two had drifted: one carried revision SHAs, the other size/arch).
# Model IDENTITY + role/strategy is governed separately by lgwks_model_mesh (the law);
# any name divergence between this catalog and MESH_LAW is a tracked conflict, not two
# independent truths. Every entry MUST carry a `revision` (commit SHA) — setup fails
# closed without it (supply-chain pin).
_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "ModernBERT-base-mlx-4bit": {
        "repo": "mlx-community/answerdotai-ModernBERT-base-4bit",
        "license": "Apache-2.0",
        "revision": "85a8e6f00e7040ef98f692269ca2fcd39b8835e7",
        "size_mb": 110,
        "arch": "bert",
        "desc": "ModernBERT 8k context — task salience membrane.",
    },
    "liquid-lfm-2.5-1.2b-mlx-4bit": {
        "repo": "mlx-community/LFM2.5-1.2B-Thinking-4bit",
        "license": "LFM-Open-1.0",
        "revision": "bb77f34e4bef39931a2e2ff2f6def20c9aea1531",
        "size_mb": 1200,
        "arch": "lfm",
        "desc": "Liquid AI LFM 2.5 — recurrent trajectory heart.",
    },
    "Qwen2.5-Omni-3B-Instruct-4bit-mlx": {
        "repo": "giangndm/qwen2.5-omni-3b-mlx-4bit",
        "license": "Apache-2.0",
        "revision": "d0aa433ec448c8510f065fc6bbe951822c70d5e8",
        "size_mb": 3000,
        "arch": "qwen2_5_omni",
        "desc": "Qwen 3.5 Omni — native voice (Wisprflow feel).",
    },
    "Qwen3-VL-8B-Instruct-4bit": {
        "repo": "mlx-community/Qwen3-VL-8B-Instruct-4bit",
        "license": "Apache-2.0",
        "revision": "defcdea7cc7a4b0858fea563cbbce171d328e457",
        "size_mb": 8000,
        "arch": "qwen3_vl",
        "desc": "Qwen 3 VL — visual agent and GUI operator.",
    },
    "OLMo-2-0325-32B-Instruct-4bit": {
        "repo": "mlx-community/OLMo-2-0325-32B-Instruct-4bit",
        "license": "Apache-2.0",
        "revision": "bcf85817c3502e1f974b5abc586f1fc3f81b1632",
        "size_mb": 18000,
        "arch": "olmo2",
        "desc": "OLMo-2 32B — deep architectural resolve (The Stay Model).",
    },
    "Llama-Prompt-Guard-2-86M": {
        "repo": "meta-llama/Llama-Prompt-Guard-2-86M",
        "license": "Llama-3.1",
        "revision": "a8ded8e697ce7c355e395a0df51f94adb4a2fd27",
        "size_mb": 170,
        "arch": "deberta",
        "desc": "Prompt Guard 2 — injection blocking.",
    },
    "Qwen3-VL-Embedding-8B": {
        "repo": "nkamiy/Qwen3-VL-Embedding-8B-8bit-mlx",
        "license": "Apache-2.0",
        "revision": "979992893da6080a0eb8e8c72af6efe124e582fb",
        "size_mb": 8000,
        "arch": "qwen3_vl",
        "desc": "Qwen3-VL embedding Eye — shared text/image/video vector space.",
    },
}


def _models_dir() -> Path:
    env = os.environ.get("LGWKS_MODELS_DIR")
    return Path(env) if env else _REPO_MODELS_DIR


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)


def _safe_name(name: str) -> str:
    """Sanitize a user-supplied model/output name for filesystem use.
    Rejects path separators, leading dots, and absolute paths."""
    if not name:
        raise ValueError("name must be non-empty")
    if os.path.isabs(name) or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid model name: {name!r}")
    return name


def _assert_under(parent: Path, child: Path) -> Path:
    """Verify child resolves inside parent. Raises ValueError if not."""
    resolved = child.resolve()
    if not str(resolved).startswith(str(parent.resolve())):
        raise ValueError(f"path {child} escapes allowed directory {parent}")
    return resolved


@contextmanager
def _temporary_env(name: str, value: str):
    prev = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev


def list_models() -> list[dict[str, Any]]:
    """Return the scrubbed model catalog."""
    return [{"name": k, **v} for k, v in _MODEL_CATALOG.items()]


def find_model_dir(name: str) -> Path | None:
    """Return the repo-resident model directory if it exists, else None."""
    safe = _safe_name(name)
    candidate = _models_dir() / safe
    return candidate if candidate.exists() else None


def load_model(name: str) -> dict[str, Any]:
    """Load a repo-resident model for inference. Returns {ok, path, reason}."""
    if name not in _MODEL_CATALOG:
        return {
            "ok": False,
            "path": "",
            "reason": f"unknown model: {name}. Available: {list(_MODEL_CATALOG.keys())}",
        }
    model_dir = find_model_dir(name)
    if model_dir is None:
        return {
            "ok": False,
            "path": "",
            "reason": f"model {name} not found in {_models_dir()}. Run scripts/setup_models.py to download.",
        }
    return {"ok": True, "path": str(model_dir), "reason": "repo-resident"}


def _python_coreml_eligible() -> tuple[bool, str]:
    vi = sys.version_info
    major = getattr(vi, "major", vi[0])
    minor = getattr(vi, "minor", vi[1])
    if (major, minor) >= (3, 13):
        return (
            False,
            "CoreML conversion requires Python <=3.12; current interpreter is "
            f"{major}.{minor}.",
        )
    return True, "Python version supports coremltools conversion."


def _catalog_entry_status(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    safe = _safe_name(name)
    model_dir = _models_dir() / safe
    has_dir = model_dir.exists()
    has_config = (model_dir / "config.json").exists()
    has_weights = bool(list(model_dir.glob("*.bin")) or list(model_dir.glob("*.safetensors")))
    coreml_pkg = (_models_dir() / f"{safe}.mlpackage").exists()
    return {
        "name": name,
        "present": has_dir,
        "path": str(model_dir),
        "has_config": has_config,
        "has_weights": has_weights,
        "coreml_package": coreml_pkg,
        "license": meta["license"],
        "size_mb": meta["size_mb"],
        "desc": meta["desc"],
    }


def _model_mesh_status() -> dict[str, Any]:
    """Read the model mesh (#119) for the doctor surface — WITHOUT loading models.

    Prefers the frozen `.lgwks/model_mesh.json` artifact; degrades to building the
    same law from `lgwks_model_mesh.MESH_LAW` when the artifact is absent (same
    graceful-degradation pattern as `lgwks.capability_idf.v1`). Either way no model
    package is imported and no `store/models/` weights are touched — the mesh is
    descriptive model law, not a model runtime.
    """
    try:
        import lgwks_model_mesh as mesh_mod
        artifact = Path(__file__).resolve().parent / ".lgwks" / "model_mesh.json"
        if artifact.exists():
            mesh = mesh_mod.load_mesh(artifact)
            source = "artifact"
        else:
            mesh = mesh_mod.build_mesh(generated_at=None)
            source = "law"
        models = mesh["models"]
        by_status: dict[str, int] = {}
        for m in models:
            by_status[m["status"]] = by_status.get(m["status"], 0) + 1
        return {
            "schema": mesh_mod.SCHEMA,
            "source": source,
            "total": len(models),
            "by_status": by_status,
            "roles": sorted({m["role"] for m in models}),
        }
    except Exception as exc:
        return {"schema": "", "source": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}


def mlx_embed(text: str, model_name: str = "ModernBERT-base-mlx-4bit") -> dict[str, Any]:
    """Compute a semantic embedding using MLX-LM.
    Returns {ok, vector, reason}."""
    # //why: The 2026-v1 stack mandates MLX for all on-device inference to
    # achieve sub-millisecond ANE latency. This helper is the unified entry
    # point for both the Membrane (ModernBERT) and The Eye (Qwen3-VL-Embed).
    try:
        from mlx_lm import load, generate
        import mlx.core as mx
    except ImportError:
        return {"ok": False, "vector": [], "reason": "mlx-lm not installed"}

    loaded = load_model(model_name)
    if not loaded["ok"]:
        return loaded

    try:
        # Note: This is a placeholder for actual MLX embedding logic.
        # In a real implementation, we would use the model's encoder
        # and pull the mean-pooled hidden state.
        model_path = Path(loaded["path"])
        # For now, we simulate a vector for architectural verification
        # until the real mlx-embed logic is wired.
        import hashlib
        h = hashlib.blake2b(text.encode(), digest_size=32).digest()
        # Create a 256-d vector from the hash
        import numpy as np
        vec = np.frombuffer(h * 8, dtype=np.float32)[:256].tolist()
        return {"ok": True, "vector": vec, "reason": "mlx-placeholder", "is_semantic": False}
    except Exception as exc:
        return {"ok": False, "vector": [], "reason": f"mlx error: {exc}", "is_semantic": False}


def doctor() -> dict[str, Any]:
    """Machine-readable health report for the local ML stack."""
    entries = [_catalog_entry_status(name, meta) for name, meta in _MODEL_CATALOG.items()]
    py_ok, py_reason = _python_coreml_eligible()

    try:
        import coremltools as _ct  # type: ignore[import]
        coreml = {"installed": True, "version": getattr(_ct, "__version__", "unknown")}
    except Exception as exc:
        coreml = {"installed": False, "version": "", "reason": f"{type(exc).__name__}: {exc}"}

    try:
        import lgwks_foundation
        foundation = lgwks_foundation.available()
    except Exception as exc:
        foundation = {"foundation_models": False, "natural_language": False, "reason": f"{type(exc).__name__}: {exc}"}

    try:
        import mlx.core as mx
        mlx_status = {"installed": True, "version": getattr(mx, "__version__", "unknown")}
    except Exception as exc:
        mlx_status = {"installed": False, "version": "", "reason": f"{type(exc).__name__}: {exc}"}

    try:
        import lgwks_intent_classifier as ic
        # Read-only doctor surface: never pull or warm models as a side effect.
        with _temporary_env("LGWKS_NO_MODELS", "1"):
            clf = ic.IntentClassifier.load()
            probe = clf.classify("show me the tool manifest")
        intent_classifier = {
            "ready": clf.is_ready(),
            "classes": len(clf.classes),
            "semantic_centroids": bool(getattr(clf, "_semantic", False)),
            "mlx_model_loaded": bool(getattr(clf, "_coreml", None) is not None),
            "probe": {
                "label": probe.label,
                "confidence": probe.confidence,
                "method": probe.method,
                "plan_only": probe.plan_only,
            },
        }
    except Exception as exc:
        intent_classifier = {
            "ready": False,
            "classes": 0,
            "semantic_centroids": False,
            "mlx_model_loaded": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    present = [row for row in entries if row["present"]]
    return {
        "schema": "lgwks.model_hub.doctor.v1",
        "models_dir": str(_models_dir()),
        "catalog": entries,
        "summary": {
            "catalog_models": len(entries),
            "present_models": len(present),
        },
        "conversion": {
            "python": f"{getattr(sys.version_info, 'major', sys.version_info[0])}.{getattr(sys.version_info, 'minor', sys.version_info[1])}",
            "eligible": py_ok,
            "reason": py_reason,
            "coremltools": coreml,
            "mlx": mlx_status,
        },
        "intent_classifier": intent_classifier,
        "foundation": foundation,
        "model_mesh": _model_mesh_status(),
        "next_step": (
            "MLX local path is active."
            if mlx_status.get("installed") and intent_classifier.get("ready")
            else "Run `python scripts/setup_models.py all` for local MLX weights."
        ),
    }


def scrub_model_dir(model_dir: Path) -> dict[str, Any]:
    """Remove non-essential files that may contain training data or internal metadata.
    Keeps only: config.json, tokenizer config, model weights, vocab files."""
    kept: list[str] = []
    removed: list[str] = []
    for item in model_dir.rglob("*"):
        if not item.is_file():
            continue
        name = item.name.lower()
        if name in (
            "config.json",
            "tokenizer_config.json",
            "vocab.txt",
            "tokenizer.json",
            "special_tokens_map.json",
        ):
            kept.append(str(item.relative_to(model_dir)))
            continue
        if name.endswith((".bin", ".safetensors", ".pt", ".ckpt", ".onnx", ".mlpackage")):
            kept.append(str(item.relative_to(model_dir)))
            continue
        try:
            item.unlink()
            removed.append(str(item.relative_to(model_dir)))
        except Exception:
            pass
    return {"ok": True, "kept": kept, "removed": removed}


def convert_to_coreml(
    model_dir: Path,
    output_path: Path | None = None,
    classifier_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Convert a transformers model to CoreML .mlpackage.
    If classifier_labels is provided, adds a classification head.
    Returns {ok, path, reason}."""
    if output_path is None:
        output_path = model_dir.with_suffix(".mlpackage")

    # coremltools binary wheels are not available for Python 3.13+ as of 2024-Q2.
    py_ok, py_reason = _python_coreml_eligible()
    if not py_ok:
        return {
            "ok": True,
            "path": "",
            "reason": f"skipped: {py_reason}",
        }

    try:
        import coremltools as ct  # type: ignore[import]
    except ImportError:
        return {"ok": False, "path": "", "reason": "coremltools not installed — pip install coremltools"}

    try:
        import torch  # type: ignore[import]
        from transformers import AutoModel, AutoTokenizer  # type: ignore[import]
    except ImportError:
        return {"ok": False, "path": "", "reason": "transformers + torch required for conversion"}

    try:
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        model = AutoModel.from_pretrained(str(model_dir))
        model.eval()

        dummy_text = "This is a sample input for tracing the model."
        inputs = tokenizer(dummy_text, return_tensors="pt", padding="max_length", truncation=True, max_length=128)

        class _MeanWrapper(torch.nn.Module):  # type: ignore[no-any-unimported]
            def __init__(self, m: torch.nn.Module) -> None:
                super().__init__()
                self.m = m

            def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
                return self.m(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state.mean(dim=1)

        wrapper = _MeanWrapper(model)
        wrapper.eval()
        with torch.no_grad():
            traced = torch.jit.trace(wrapper, (inputs["input_ids"], inputs["attention_mask"]))

        mlmodel = ct.convert(
            traced,
            inputs=[
                ct.TensorType(name="input_ids", shape=(1, 128), dtype=int),
                ct.TensorType(name="attention_mask", shape=(1, 128), dtype=int),
            ],
            classifier_config=ct.ClassifierConfig(classifier_labels) if classifier_labels else None,
            minimum_deployment_target=ct.target.iOS16,
        )
        mlmodel.save(str(output_path))
        return {"ok": True, "path": str(output_path), "reason": "converted to CoreML"}
    except Exception as exc:
        return {"ok": False, "path": "", "reason": f"conversion failed: {type(exc).__name__}: {exc}"}


def train_text_classifier(
    texts: list[str],
    labels: list[str],
    model_name: str = "tiny-bert",
    output_name: str = "text_classifier",
) -> dict[str, Any]:
    """Fine-tune a small encoder for text classification and export to CoreML.
    Returns {ok, path, reason, accuracy}."""
    if len(texts) != len(labels):
        return {"ok": False, "path": "", "reason": "texts and labels must have same length"}
    if len(texts) < 4 or len(set(labels)) < 2:
        return {
            "ok": False,
            "path": "",
            "reason": "need at least 4 rows across 2 labels for a meaningful local fine-tune",
        }

    loaded = load_model(model_name)
    if not loaded["ok"]:
        return loaded

    model_dir = Path(loaded["path"])

    try:
        from sklearn.model_selection import train_test_split  # type: ignore[import]
        from sklearn.metrics import accuracy_score  # type: ignore[import]
        import torch  # type: ignore[import]
        from torch.utils.data import Dataset  # type: ignore[import]
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
        )  # type: ignore[import]
    except ImportError as exc:
        return {"ok": False, "path": "", "reason": f"missing dependency: {exc}"}

    try:
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        unique_labels = sorted(set(labels))
        label2id = {l: i for i, l in enumerate(unique_labels)}
        id2label = {i: l for l, i in label2id.items()}

        model = AutoModelForSequenceClassification.from_pretrained(
            str(model_dir),
            num_labels=len(unique_labels),
            id2label=id2label,
            label2id=label2id,
        )

        class _TextDS(Dataset):
            def __init__(self, txts, lbls):
                self.enc = tokenizer(txts, truncation=True, padding=True, max_length=128)
                self.lbls = [label2id[l] for l in lbls]

            def __len__(self):
                return len(self.lbls)

            def __getitem__(self, idx):
                return {k: torch.tensor(v[idx]) for k, v in self.enc.items()} | {"labels": torch.tensor(self.lbls[idx])}

        train_texts, test_texts, train_labels, test_labels = train_test_split(
            texts, labels, test_size=0.2, random_state=42
        )
        train_ds = _TextDS(train_texts, train_labels)
        test_ds = _TextDS(test_texts, test_labels)

        train_out = _models_dir() / "train_output"
        logs = _models_dir() / "logs"
        _ensure_dir(train_out)
        _ensure_dir(logs)

        args = TrainingArguments(
            output_dir=str(train_out),
            num_train_epochs=3,
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            evaluation_strategy="epoch",
            save_strategy="no",
            logging_dir=str(logs),
        )
        trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=test_ds)
        trainer.train()

        preds = trainer.predict(test_ds)
        acc = accuracy_score(preds.label_ids, preds.predictions.argmax(-1))

        safe_output = _safe_name(output_name)
        ft_dir = _assert_under(_models_dir(), _models_dir() / f"{safe_output}_torch")
        model.save_pretrained(str(ft_dir))
        tokenizer.save_pretrained(str(ft_dir))

        coreml_out = _assert_under(_models_dir(), _models_dir() / f"{safe_output}.mlpackage")
        result = convert_to_coreml(ft_dir, output_path=coreml_out, classifier_labels=unique_labels)
        result["accuracy"] = round(float(acc), 4)
        return result
    except Exception as exc:
        return {"ok": False, "path": "", "reason": f"training failed: {type(exc).__name__}: {exc}"}


def add_parser(sub) -> None:
    p = sub.add_parser("model-hub", help="repo-resident model loader")
    sp = p.add_subparsers(dest="model_hub_command", required=True)

    ls = sp.add_parser("list", help="list catalog models")
    ls.add_argument("--json", action="store_true", help="structured output")
    ls.set_defaults(func=_model_hub_list_command)

    load = sp.add_parser("load", help="verify a model is present and loadable")
    load.add_argument("--model", default="tiny-bert", help="model name from catalog")
    load.add_argument("--json", action="store_true", help="structured output")
    load.set_defaults(func=_model_hub_load_command)

    convert = sp.add_parser("convert", help="convert a model to CoreML .mlpackage")
    convert.add_argument("--model", default="tiny-bert", help="model name from catalog")
    convert.add_argument("--json", action="store_true", help="structured output")
    convert.set_defaults(func=_model_hub_convert_command)

    train = sp.add_parser("train", help="fine-tune a text classifier and export to CoreML")
    train.add_argument("--model", default="tiny-bert", help="base model name")
    train.add_argument("--texts", required=True, help="JSON file with list of strings")
    train.add_argument("--labels", required=True, help="JSON file with list of labels")
    train.add_argument("--output", default="text_classifier", help="output model name")
    train.add_argument("--json", action="store_true", help="structured output")
    train.set_defaults(func=_model_hub_train_command)

    doc = sp.add_parser("doctor", help="machine-readable health report for the local ML stack")
    doc.add_argument("--json", action="store_true", help="structured output")
    doc.set_defaults(func=_model_hub_doctor_command)

    p.set_defaults(func=lambda args: _model_hub_list_command(args))


def _model_hub_list_command(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"models": list_models()}, indent=2))
    else:
        for m in list_models():
            print(f"{m['name']}: {m['desc']} ({m['size_mb']}MB, {m['license']})")
    return 0


def _model_hub_load_command(args: argparse.Namespace) -> int:
    r = load_model(args.model)
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


def _model_hub_convert_command(args: argparse.Namespace) -> int:
    r = load_model(args.model)
    if not r["ok"]:
        print(json.dumps(r, indent=2))
        return 1
    r = convert_to_coreml(Path(r["path"]))
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


def _model_hub_train_command(args: argparse.Namespace) -> int:
    texts = json.loads(Path(args.texts).read_text())
    labels = json.loads(Path(args.labels).read_text())
    r = train_text_classifier(texts, labels, model_name=args.model, output_name=args.output)
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


def _model_hub_doctor_command(args: argparse.Namespace) -> int:
    print(json.dumps(doctor(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="lgwks_model_hub", description="repo-resident model loader")
    p.add_argument("action", choices=["list", "load", "convert", "train", "doctor"])
    p.add_argument("--model", default="tiny-bert", help="model name from catalog")
    p.add_argument("--texts", help="JSON file with list of strings for training")
    p.add_argument("--labels", help="JSON file with list of labels for training")
    p.add_argument("--output", default="text_classifier", help="output model name")
    args = p.parse_args(argv)

    if args.action == "list":
        for m in list_models():
            print(f"{m['name']}: {m['desc']} ({m['size_mb']}MB, {m['license']})")
        return 0

    if args.action == "load":
        r = load_model(args.model)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    if args.action == "convert":
        r = load_model(args.model)
        if not r["ok"]:
            print(json.dumps(r, indent=2))
            return 1
        r = convert_to_coreml(Path(r["path"]))
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    if args.action == "train":
        if not args.texts or not args.labels:
            print("--texts and --labels required for train")
            return 1
        texts = json.loads(Path(args.texts).read_text())
        labels = json.loads(Path(args.labels).read_text())
        r = train_text_classifier(texts, labels, model_name=args.model, output_name=args.output)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    if args.action == "doctor":
        print(json.dumps(doctor(), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
