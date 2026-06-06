# models/

Repo-resident ML models for offline runtime use.

- `tiny-bert/` — 2-layer BERT (16MB, Apache-2.0) for intent classification
- `distilbert-base-uncased/` — 6-layer DistilBERT (66MB, Apache-2.0) for general classification

## Setup (one-time per developer)

```bash
python scripts/setup_models.py all tiny-bert
```

This downloads from HuggingFace Hub, scrubs non-essential files, and converts to CoreML `.mlpackage`.

To inspect the entire local ML path without guessing:

```bash
./lgwks model-hub doctor
./lgwks doctor
```

## Git LFS

Binary weight files (>100MB) are tracked via git-lfs. Ensure LFS is installed:

```bash
git lfs install
git lfs track "*.bin"
git lfs track "*.safetensors"
git lfs track "*.mlpackage"
```
