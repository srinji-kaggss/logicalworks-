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
    "ModernBERT-base-mlx-4bit": {
        "repo": "mlx-community/answerdotai-ModernBERT-base-4bit",
        "license": "Apache-2.0",
    },
    "liquid-lfm-2.5-1.2b-mlx-4bit": {
        "repo": "mlx-community/LFM2.5-1.2B-Thinking-4bit",
        "license": "LFM-Open-1.0",
    },
    "Qwen2.5-Omni-3B-Instruct-4bit-mlx": {
        "repo": "giangndm/qwen2.5-omni-3b-mlx-4bit",
        "license": "Apache-2.0",
    },
    "Qwen3-VL-8B-Instruct-4bit": {
        "repo": "mlx-community/Qwen3-VL-8B-Instruct-4bit",
        "license": "Apache-2.0",
    },
    "OLMo-2-0325-32B-Instruct-4bit": {
        "repo": "mlx-community/OLMo-2-0325-32B-Instruct-4bit",
        "license": "Apache-2.0",
    },
    "Llama-Prompt-Guard-2-86M": {
        "repo": "meta-llama/Llama-Prompt-Guard-2-86M",
        "license": "Llama-3.1",
    },
    "Qwen3-VL-Embedding-8B": {
        "repo": "nkamiy/Qwen3-VL-Embedding-8B-8bit-mlx",
        "license": "Apache-2.0",
    },
}


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)


def _safe_name(name: str) -> str:
    """Sanitize a user-supplied model name for filesystem use."""
    import os as _os
    if not name:
        raise ValueError("name must be non-empty")
    if _os.path.isabs(name) or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid model name: {name!r}")
    return name


def _assert_under(parent: Path, child: Path) -> Path:
    """Verify child resolves inside parent. Raises ValueError if not."""
    resolved = child.resolve()
    if not str(resolved).startswith(str(parent.resolve())):
        raise ValueError(f"path {child} escapes allowed directory {parent}")
    return resolved


def download(name: str) -> dict[str, Any]:
    if name not in _MODEL_CATALOG:
        return {"ok": False, "reason": f"unknown model: {name}"}

    meta = _MODEL_CATALOG[name]
    safe = _safe_name(name)
    dest = _assert_under(MODELS_DIR, MODELS_DIR / safe)
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
    safe = _safe_name(name)
    model_dir = _assert_under(MODELS_DIR, MODELS_DIR / safe)
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
            "vocab.json",
            "tokenizer.json",
            "merges.txt",
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
    safe = _safe_name(name)
    model_dir = _assert_under(MODELS_DIR, MODELS_DIR / safe)
    if not model_dir.exists():
        return {"ok": False, "reason": f"model {name} not found"}

    output_path = _assert_under(MODELS_DIR, MODELS_DIR / f"{safe}.mlpackage")

    # Deduplicate: delegate to the canonical converter in lgwks_model_hub
    try:
        import lgwks_model_hub as mh
        return mh.convert_to_coreml(model_dir, output_path=output_path)
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
