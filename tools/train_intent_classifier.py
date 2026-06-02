"""
train_intent_classifier.py — training script for the custom English intent classifier.

Trains a DistilBERT-class encoder on lgwks verb intent labels, exports to CoreML
for ANE deployment. All training runs on Apple Silicon MPS.

Usage:
    python3 tools/train_intent_classifier.py [--epochs N] [--export]

//why DistilBERT not BERT: 66M params (vs 110M), 40% faster inference, retains
// 97% of BERT accuracy on classification tasks. Fits on ANE with sub-2ms latency.
// A 4-layer custom encoder from scratch would be ~20M params but requires more
// training data than the manifest currently provides.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Dataset builder — derives labels from the live manifest
# ---------------------------------------------------------------------------

def build_dataset(manifest_path: Path | None = None) -> list[dict]:
    """
    Returns list of {text: str, label: str} dicts.

    Primary source: manifest verb intents (each verb intent string → label = verb id).
    These are the "anchor" examples; the training script should be run with
    synthetically expanded paraphrases before the first real training run.

    //why manifest-derived labels: the manifest IS the class schema. When a new
    // verb lands, re-running this function adds the new class automatically.
    // No label file to maintain separately.
    """
    if manifest_path is None:
        manifest_path = ROOT / "store" / "manifest-cache.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        sys.path.insert(0, str(ROOT))
        import lgwks_manifest
        manifest = lgwks_manifest.build_manifest()

    examples = []
    for verb in manifest.get("verbs", []):
        label = verb["verb"]
        intent = verb.get("intent", "")
        if intent and intent != "(no metadata)":
            examples.append({"text": intent, "label": label})
        # also add the verb name itself as a training example
        examples.append({"text": label.replace(".", " "), "label": label})

    return examples


# ---------------------------------------------------------------------------
# Training (stub — requires torch + transformers)
# ---------------------------------------------------------------------------

def train(epochs: int = 5, export: bool = False) -> None:
    """
    Fine-tune DistilBERT on the intent dataset.

    Requires: pip install torch transformers coremltools datasets
    """
    try:
        import torch  # type: ignore
        from transformers import (  # type: ignore
            DistilBertTokenizerFast,
            DistilBertForSequenceClassification,
            TrainingArguments,
            Trainer,
        )
    except ImportError:
        print("Install: pip install torch transformers datasets", file=sys.stderr)
        sys.exit(1)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Training on: {device}")

    dataset = build_dataset()
    if not dataset:
        print("No training examples — run lgwks manifest first", file=sys.stderr)
        sys.exit(1)

    labels = sorted({ex["label"] for ex in dataset})
    label2id = {l: i for i, l in enumerate(labels)}
    id2label = {i: l for l, i in label2id.items()}
    print(f"Classes: {len(labels)}, Examples: {len(dataset)}")

    tokenizer = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")
    model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    ).to(device)

    # //why stub training loop: full Trainer config belongs in a follow-up
    # once real training data (paraphrases + user inputs) is collected.
    # This stub verifies the import + device chain works end-to-end.
    print("Model loaded. Training stub — add dataset + Trainer config for real run.")
    print(f"Model params: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M")

    if export:
        _export_coreml(model, tokenizer, labels)


def _export_coreml(model: object, tokenizer: object, labels: list[str]) -> None:
    """Export fine-tuned model to CoreML (.mlpackage) for ANE deployment."""
    try:
        import coremltools as ct  # type: ignore
        import torch  # type: ignore
    except ImportError:
        print("Install: pip install coremltools torch", file=sys.stderr)
        return

    out_path = ROOT / "lgwks_intent_classifier.mlpackage"
    print(f"Exporting to {out_path} ...")
    # //why stub: real export requires a traced/scripted model + input spec.
    # Placeholder until the model is actually trained.
    print("Export stub — implement after training data + training loop are complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Train the lgwks intent classifier")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--export", action="store_true", help="export to CoreML after training")
    p.add_argument("--dataset-only", action="store_true",
                   help="print dataset and exit (no training)")
    args = p.parse_args()

    if args.dataset_only:
        ds = build_dataset()
        print(json.dumps(ds, indent=2))
        return

    train(epochs=args.epochs, export=args.export)


if __name__ == "__main__":
    main()
