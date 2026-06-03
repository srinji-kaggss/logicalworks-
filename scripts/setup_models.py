#!/usr/bin/env python3
"""setup_models.py — one-time developer script to download and convert models.

Usage:
    python scripts/setup_models.py download tiny-bert
    python scripts/setup_models.py scrub tiny-bert
    python scripts/setup_models.py convert tiny-bert
    python scripts/setup_models.py all tiny-bert   # download + scrub + convert

This is the ONLY script that touches the network. After setup, the models/ directory
is committed to git (git-lfs for files >100MB) and runtime code loads offline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "distilbert-base-uncased": {
        "repo": "distilbert-base-uncased",
        "license": "Apache-2.0",
    },
    "tiny-bert": {
        "repo": "prajjwal1/bert-tiny",
        "license": "Apache-2.0",
    },
}


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)


def download(name: str) -> dict[str, Any]:
    if name not in _MODEL_CATALOG:
        return {"ok": False, "reason": f"unknown model: {name}"}

    meta = _MODEL_CATALOG[name]
    dest = MODELS_DIR / name
    # A model dir is "complete" if it has config.json + weights
    has_config = (dest / "config.json").exists()
    has_weights = any((dest).glob("*.bin")) or any((dest).glob("*.safetensors"))
    if has_config and has_weights:
        return {"ok": True, "path": str(dest), "reason": "already exists"}

    dest.mkdir(parents=True, exist_ok=True)

    # Primary: huggingface_hub snapshot_download (fast, reliable, handles resume)
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import]

        snapshot_download(repo_id=meta["repo"], local_dir=str(dest), local_dir_use_symlinks=False)
        return {"ok": True, "path": str(dest), "reason": "downloaded via huggingface_hub"}
    except ImportError:
        print("huggingface_hub not installed — pip install huggingface-hub", file=sys.stderr)
    except Exception as exc:
        print(f"huggingface_hub download failed: {exc}", file=sys.stderr)

    # Fallback: transformers AutoTokenizer/AutoModel (slower, needs more RAM)
    try:
        from transformers import AutoTokenizer, AutoModel  # type: ignore[import]

        tokenizer = AutoTokenizer.from_pretrained(meta["repo"])
        model = AutoModel.from_pretrained(meta["repo"])
        tokenizer.save_pretrained(str(dest))
        model.save_pretrained(str(dest))
        return {"ok": True, "path": str(dest), "reason": "downloaded via transformers"}
    except ImportError:
        print("transformers not installed — pip install transformers", file=sys.stderr)
    except Exception as exc:
        print(f"transformers download failed: {exc}", file=sys.stderr)

    return {"ok": False, "reason": "all download methods failed"}


def scrub(name: str) -> dict[str, Any]:
    model_dir = MODELS_DIR / name
    if not model_dir.exists():
        return {"ok": False, "reason": f"model {name} not found in {model_dir}"}

    kept: list[str] = []
    removed: list[str] = []
    for item in model_dir.rglob("*"):
        if not item.is_file():
            continue
        name_lower = item.name.lower()
        if name_lower in (
            "config.json",
            "tokenizer_config.json",
            "vocab.txt",
            "tokenizer.json",
            "special_tokens_map.json",
        ):
            kept.append(str(item.relative_to(model_dir)))
            continue
        if name_lower.endswith((".bin", ".safetensors", ".pt", ".ckpt", ".onnx", ".mlpackage")):
            kept.append(str(item.relative_to(model_dir)))
            continue
        try:
            item.unlink()
            removed.append(str(item.relative_to(model_dir)))
        except Exception:
            pass
    return {"ok": True, "kept": kept, "removed": removed}


def convert(name: str) -> dict[str, Any]:
    model_dir = MODELS_DIR / name
    if not model_dir.exists():
        return {"ok": False, "reason": f"model {name} not found"}

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
        return {"ok": False, "reason": "coremltools not installed"}

    try:
        import torch  # type: ignore[import]
        from transformers import AutoModel, BertTokenizer  # type: ignore[import]
    except ImportError:
        return {"ok": False, "reason": "transformers + torch required"}

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

        output_path = MODELS_DIR / f"{name}.mlpackage"
        mlmodel = ct.convert(
            traced,
            inputs=[
                ct.TensorType(name="input_ids", shape=(1, 128), dtype=int),
                ct.TensorType(name="attention_mask", shape=(1, 128), dtype=int),
            ],
            minimum_deployment_target=ct.target.iOS16,
        )
        mlmodel.save(str(output_path))
        return {"ok": True, "path": str(output_path), "reason": "converted to CoreML"}
    except Exception as exc:
        return {"ok": False, "reason": f"conversion failed: {type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="setup_models", description="download and convert models")
    p.add_argument("action", choices=["download", "scrub", "convert", "all"])
    p.add_argument("model", default="tiny-bert", help="model name")
    args = p.parse_args(argv)

    if args.action == "download":
        r = download(args.model)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    if args.action == "scrub":
        r = scrub(args.model)
        print(json.dumps(r, indent=2))
        return 0

    if args.action == "convert":
        r = convert(args.model)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    if args.action == "all":
        r = download(args.model)
        print(json.dumps(r, indent=2))
        if not r["ok"]:
            return 1
        r = scrub(args.model)
        print(json.dumps(r, indent=2))
        r = convert(args.model)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
