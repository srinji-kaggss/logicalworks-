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
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Runtime models live in the repo, not in ~/.config
_REPO_MODELS_DIR = Path(__file__).resolve().parent / "models"

_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "distilbert-base-uncased": {
        "repo": "distilbert-base-uncased",
        "license": "Apache-2.0",
        "size_mb": 66,
        "layers": 6,
        "hidden": 768,
        "desc": "6-layer DistilBERT — fast, accurate enough for classification",
    },
    "tiny-bert": {
        "repo": "prajjwal1/bert-tiny",
        "license": "Apache-2.0",
        "size_mb": 16,
        "layers": 2,
        "hidden": 128,
        "desc": "2-layer BERT — smallest viable encoder for intent classification",
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
    if sys.version_info >= (3, 13):
        return {
            "ok": True,
            "path": "",
            "reason": "skipped: CoreML conversion requires Python <=3.12 (detected {}.{}).".format(
                sys.version_info.major, sys.version_info.minor
            ),
        }

    try:
        import coremltools as ct  # type: ignore[import]
    except ImportError:
        return {"ok": False, "path": "", "reason": "coremltools not installed — pip install coremltools"}

    try:
        import torch  # type: ignore[import]
        from transformers import AutoModel, BertTokenizer  # type: ignore[import]
    except ImportError:
        return {"ok": False, "path": "", "reason": "transformers + torch required for conversion"}

    try:
        tokenizer = BertTokenizer.from_pretrained(str(model_dir))
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
            BertTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
        )  # type: ignore[import]
    except ImportError as exc:
        return {"ok": False, "path": "", "reason": f"missing dependency: {exc}"}

    try:
        tokenizer = BertTokenizer.from_pretrained(str(model_dir))
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


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="lgwks_model_hub", description="repo-resident model loader")
    p.add_argument("action", choices=["list", "load", "convert", "train"])
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

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
