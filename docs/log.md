# Knowledge Bundle Update Log

## 2026-06-25
* **Creation**: Adopted Google Cloud's **Open Knowledge Format (OKF v0.1)** for `docs/`. Added [knowledge-format](/docs/concepts/knowledge-format.md) (the lineage + disambiguation keystone) and the generator [`scripts/gen_okf.py`](/scripts/gen_okf.py) — frontmatter is derived from source and `index.md` files are synthesized; the bundle is generated, never hand-maintained, so it cannot rot.
* **Creation**: Documented the landed two-plane model layer (epic #335) in [concepts/model-layer](/docs/concepts/model-layer.md).
* **Update**: Injected OKF frontmatter into all 94 existing concepts; generated bundle-root and per-directory `index.md` for progressive disclosure. `python3 scripts/gen_okf.py --check` is the conformance gate.
* **Creation**: Session handoff at [handoff/2026-06-25-model-layer-and-okf](/docs/handoff/2026-06-25-model-layer-and-okf.md).
