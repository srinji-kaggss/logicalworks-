# ML Stack for Many Small Self-Evolving Evaluator Models On-Device (Apple M5 Pro, 24GB UMA, ANE + 16-core GPU, Metal 4)

Grounded research, 2026-06-01. Sources cited inline. Web grounding via official docs/repos (firecrawl was out of credits 402; crwl Bash blocked; used WebFetch on canonical sources).

## TL;DR
- **CoreML is a deployment runtime, not a model and not a real training framework.** Train elsewhere; deploy/accelerate on ANE via Core ML.
- **Train in MLX** (Apple, open-source) for first-class on-device training on Apple-silicon GPU + unified memory, native safetensors checkpoints (clean snapshot/rollback). MLX does **not** use the ANE ("wontfix") — GPU/CPU only.
- **Keep the portable core in PyTorch** if you need the richest interpretability tooling (Captum, TransformerLens) and easy ONNX export; PyTorch MPS uses the GPU via Metal, also **no ANE**.
- **ANE is reachable only through Core ML.** The only way to put your model on the Neural Engine is to convert to Core ML (`.mlpackage`/MLProgram) via coremltools and set compute units. ONNX Runtime's CoreML EP is the portable inference path to ANE.
- **Self-evolution + turn-back checkpoint** = content-addressed (hash-pinned) safetensors snapshots of weights, kept as a fact-log; rollback = reload a pinned hash. Works cleanly in MLX/PyTorch; awkward/blocked in Core ML and llama.cpp.

---

## 1. Comparison Matrix

Columns: [on-device training | ANE access | GPU/Metal | interpretability tooling | snapshot/rollback ergonomics | portability/export | maturity-on-Apple]

### MLX (Apple, open-source) — TRAIN framework
- **On-device training:** Yes, first-class. Autodiff + full training/finetune; README ships "LLaMA … finetuning with LoRA." Source: https://github.com/ml-explore/mlx
- **ANE access:** No. ANE support is "wontfix." Source: https://github.com/ml-explore/mlx/issues/18
- **GPU/Metal:** Yes — CPU + GPU; unified/shared memory so no host-device transfer. Source: https://github.com/ml-explore/mlx
- **Interpretability:** Bring-your-own; no dedicated MI lib. Lazy dynamic graphs + composable transforms (grad, vmap) make activation capture / per-feature grads doable by hand. Source: https://github.com/ml-explore/mlx
- **Snapshot/rollback:** Excellent. Native safetensors / npz weight save-load (`mx.save_safetensors`, `save_weights`/`load_weights`); pure-data checkpoints are trivially hashable/diffable. Source: https://github.com/ml-explore/mlx (saving_and_loading docs)
- **Portability/export:** Partial. Safetensors interops w/ HF/PyTorch tensors; **no built-in ONNX export** (README/docs do not mention ONNX). Bridge out via shared safetensors weights, not a graph export. Source: https://github.com/ml-explore/mlx
- **Maturity-on-Apple:** High and rising — Apple's own framework, purpose-built for Apple silicon; CUDA backend added for Linux. Source: https://github.com/ml-explore/mlx

### CoreML + CreateML — DEPLOY runtime (+ light on-device personalization)
- **On-device training:** Limited. "Updatable models" / model personalization fine-tune **specific layers only** (e.g. last fully-connected/conv + k-NN), not general training. CreateML/TuriCreate train on-device but export-to-deploy oriented. Sources: Apple Core ML model-personalization (JS-rendered, title-only on fetch); TuriCreate exports `.mlmodel` https://github.com/apple/turicreate
- **ANE access:** Yes — this is THE path to the ANE. "Core ML optimizes on-device performance by leveraging the CPU, GPU, and Neural Engine." Source: https://github.com/apple/coremltools
- **GPU/Metal:** Yes (CPU/GPU/ANE, runtime-chosen via compute units). Source: https://github.com/apple/coremltools
- **Interpretability:** Minimal. Closed runtime; no activation-capture API. Treat as black-box deploy target.
- **Snapshot/rollback:** Weak for evolution. `.mlmodel`/`.mlpackage` are compiled artifacts; updatable-model state can be re-saved but it's not a clean diffable weight tensor store.
- **Portability/export:** Apple-locked output format. coremltools converts **in** from PyTorch/TF; no general export out. Source: https://github.com/apple/coremltools
- **Maturity-on-Apple:** Highest (native OS runtime), but it is a runtime, not a training stack.

### PyTorch (+MPS) — TRAIN framework / portable core
- **On-device training:** Yes — full training + eval accelerated on Mac. Source: https://pytorch.org/blog/introducing-accelerated-pytorch-training-on-mac/
- **ANE access:** No. MPS announcement mentions ANE nowhere; MPS = GPU via Metal Performance Shaders only. Source: same blog
- **GPU/Metal:** Yes — "Accelerated GPU training is enabled using Apple's Metal Performance Shaders (MPS)"; unified memory lets you train larger batches locally. Some ops fall back to CPU (`PYTORCH_ENABLE_MPS_FALLBACK`). Source: same blog + MPS notes (docs.pytorch.org/docs/stable/notes/mps.html)
- **Interpretability:** Best-in-class. Captum (Integrated Gradients, DeepLIFT, SHAP variants, Layer/Neuron Conductance, GradCAM, TracIn) https://github.com/pytorch/captum ; TransformerLens (`run_with_cache`, hooks, ablation, logit lens) https://github.com/TransformerLensOrg/TransformerLens . Both PyTorch-native → run on `device="mps"`.
- **Snapshot/rollback:** Strong. `state_dict` → `torch.save` / safetensors; diffable, hashable tensor dicts.
- **Portability/export:** Best. `torch.onnx.export` → ONNX; ONNX → coremltools → Core ML/ANE. The canonical portable bridge.
- **Maturity-on-Apple:** High (since v1.12, macOS 12.3+), broad ecosystem; MPS slightly behind CUDA in op coverage.

### ONNX Runtime — DEPLOY runtime (+ on-device training API)
- **On-device training:** Yes, a dedicated On-Device Training API (separate from inference) for edge personalization/federated learning; produces training artifacts + checkpoint state. Repo: https://github.com/microsoft/onnxruntime-training-examples (on_device_training/)
- **ANE access:** Yes, via the CoreML Execution Provider (delegates ONNX subgraphs to Core ML → CPU/GPU/ANE; MLProgram + compute-unit options). (onnxruntime.ai docs domain blocked on fetch; capability is the CoreML EP.) 
- **GPU/Metal:** Indirectly via CoreML EP; no direct Metal EP.
- **Interpretability:** None native (it's a runtime). Interpret in the training framework.
- **Snapshot/rollback:** Training API checkpoint state is serializable; ONNX graph itself is a fixed artifact.
- **Portability/export:** ONNX = the portability standard; vendor-neutral. Strong.
- **Maturity-on-Apple:** Good as a portable inference runtime + ANE fast-path; less common as the primary trainer.

### ggml / llama.cpp — DEPLOY runtime (inference-only)
- **On-device training:** No — "strictly an inference engine," LLM inference in C/C++. Source: https://github.com/ggml-org/llama.cpp
- **ANE access:** No — "ARM NEON, Accelerate and Metal frameworks"; no ANE. Source: same
- **GPU/Metal:** Yes — "Apple silicon is a first-class citizen … Metal." Source: same
- **Interpretability:** None.
- **Snapshot/rollback:** GGUF is a packaging/quantized artifact, not a training checkpoint; not for evolution.
- **Portability/export:** GGUF format; converts in from HF. Inference-only.
- **Maturity-on-Apple:** Very high for inference of GGUF LLMs; irrelevant to training.

### JAX (+ jax-metal) — TRAIN framework (experimental on Apple)
- **On-device training:** Yes in principle (autodiff/XLA), but Apple plug-in experimental.
- **ANE access:** No (GPU via Metal/OpenXLA PjRT).
- **GPU/Metal:** Yes but **experimental**: "Metal plug-in is experimental and not all JAX functionality may be supported"; missing float64/complex; fails some tests. Source: https://developer.apple.com/metal/jax/
- **Interpretability:** Ecosystem (Penzai, etc.) but thinner than PyTorch's; not Apple-specific.
- **Snapshot/rollback:** Good (pytrees/orbax checkpoints, pure functions favor reproducibility).
- **Portability/export:** Via StableHLO/ONNX-ish paths; less direct than PyTorch→ONNX.
- **Maturity-on-Apple:** Low/experimental — not recommended as the Apple-silicon trainer today. Source: https://developer.apple.com/metal/jax/

### tinygrad — TRAIN framework (pre-1.0)
- **On-device training:** Yes — autograd, nn/optim/datasets "for real training." Source: https://github.com/tinygrad/tinygrad
- **ANE access:** Not mentioned/no. Source: same
- **GPU/Metal:** Yes — METAL backend (ops_metal.py). Source: same
- **Interpretability:** None native.
- **Snapshot/rollback:** safetensors load/save supported; clean.
- **Portability/export:** Multi-backend (CUDA/AMD/Metal/WebGPU); ~25 low-level ops; portable by design.
- **Maturity-on-Apple:** Pre-1.0 — "isn't 1.0 yet"; not for production. Source: same

---

## 2. The category error (train-framework vs deploy-runtime)
- **CoreML is NOT a model and NOT a general training framework — it is Apple's on-device DEPLOYMENT/inference runtime.** CreateML/coremltools produce/optimize `.mlmodel`/`.mlpackage` artifacts; updatable models do only narrow last-layer personalization, not real training. (https://github.com/apple/coremltools, https://github.com/apple/turicreate)
- Same class (DEPLOY/inference runtimes): **ONNX Runtime, ggml/llama.cpp, Core ML.** These run/accelerate models; only ORT has a bolt-on on-device training API.
- TRAIN frameworks (autodiff + optimizers, build/evolve weights): **MLX, PyTorch, JAX, tinygrad.**
- Separate the two axes: pick a TRAIN framework for self-evolution + interpretability; pick a DEPLOY runtime for the ANE/Metal fast path. CoreML belongs only in the second list.

## 3. Recommended split for "many small self-evolving evaluator models"
- **Train/evolve in:** MLX (primary, Apple-native GPU+UMA, native safetensors checkpoints, smallest footprint for MANY small models, fast launch). Use **PyTorch+MPS** as the secondary/interpretability lane when you need Captum/TransformerLens-grade introspection.
- **Deploy/accelerate with:** Core ML (`.mlpackage`/MLProgram via coremltools) for the **ANE fast-path** when a snapshot is "frozen" for cheap, low-power eval inference. Use **ONNX Runtime CoreML EP** as the portable ANE path if you want to stay vendor-neutral at the runtime boundary.
- **Portable core + ANE adapter pattern:**
  1. Canonical weights live as **safetensors** tensor dicts (framework-agnostic, hashable).
  2. Authoring/evolution in MLX (or PyTorch) reads/writes those tensors.
  3. Export bridge: PyTorch → `torch.onnx.export` → ONNX (portable core), **or** ONNX/PyTorch → coremltools → Core ML (ANE fast-path adapter). MLX → share weights via safetensors → PyTorch → ONNX/CoreML.
  4. ANE is an **accelerator adapter behind a port**, never the source of truth. The portable core (safetensors + ONNX graph) stays Apple-independent; Core ML is a swappable fast-path.

## 4. Self-evolution + defined turn-back checkpoint, per framework
General pattern (fits the project's content-addressed E2EE fact-log / State Fabric): each evolution step writes the full weight set (or LoRA delta) as **safetensors**, hash it (e.g. SHA-256 of the file/tensor bytes) → that hash IS the checkpoint id. The fact-log records (parent_hash → child_hash, metric deltas). "Turn-back" = reload the pinned hash; weights are pure data so diffs/rollbacks are deterministic.
- **MLX:** `save_weights`/`load_weights` (.npz) or `mx.save_safetensors`; pure tensor dicts → trivially hash-pin + diff. Best fit. (https://github.com/ml-explore/mlx)
- **PyTorch:** `state_dict` → safetensors (preferred over pickle for hashing/safety); LoRA deltas tiny → cheap per-evaluator snapshots. (https://github.com/pytorch/captum ecosystem)
- **JAX:** orbax / pytree checkpoints; pure functions aid reproducible replay. Apple support experimental. (https://developer.apple.com/metal/jax/)
- **tinygrad:** safetensors save/load; clean but pre-1.0. (https://github.com/tinygrad/tinygrad)
- **ONNX Runtime On-Device Training:** checkpoint state artifact serializable for personalization rollback. (https://github.com/microsoft/onnxruntime-training-examples)
- **Core ML / ggml:** poor for evolution — compiled `.mlpackage` / quantized GGUF are deploy artifacts, not diffable training checkpoints. Treat snapshots as derived/disposable, regenerated from the safetensors source of truth.
Recommended: **safetensors + content-addressed hash-pinning** as the universal checkpoint substrate; MLX/PyTorch are the diffable-weight authors; Core ML/GGUF are regenerated read-only fast-path artifacts keyed to a parent hash.

## 5. Best interpretability libraries on Apple silicon
All run on Apple silicon by virtue of being PyTorch-native (set `device="mps"`); none require CUDA.
- **Captum** (PyTorch) — feature attribution (Integrated Gradients, DeepLIFT, GradientSHAP), layer/neuron attribution (LayerConductance, NeuronConductance), GradCAM, TracIn influence, TCAV concepts. https://github.com/pytorch/captum
- **TransformerLens** (PyTorch) — mechanistic interp: `run_with_cache` activation capture, hooks to edit/ablate activations, logit lens; "reverse engineer the algorithms the model learned." Runs CPU/MPS (PyTorch device arg). https://github.com/TransformerLensOrg/TransformerLens
- **nnsight / SHAP / saliency** — PyTorch-native, same MPS support (general knowledge; verify versions via context7 when coding).
- **MLX:** no dedicated MI library yet; build activation capture via lazy graph + composable grad/vmap transforms by hand. (https://github.com/ml-explore/mlx)
- **Calibration tracking** ("how the model is thinking"): framework-agnostic — log per-snapshot reliability diagrams / ECE / Brier alongside each checkpoint hash in the fact-log; not provided by any single lib, implement in the train framework.
- Implication: doing interpretability + calibration as a hard requirement nudges the **train lane toward PyTorch** (Captum/TransformerLens) even if MLX is the lean runner — hence the dual-lane split in §3.

## Key cross-cutting facts
- **No mainstream TRAINING framework targets the ANE.** MLX(wontfix), PyTorch-MPS, JAX-metal, tinygrad all use the **GPU via Metal**, not the Neural Engine. The ANE is inference-only and reachable solely through **Core ML** (directly or via ONNX Runtime CoreML EP). So "train on GPU, deploy frozen snapshots to ANE for cheap eval" is the only coherent way to use both.
- 24GB UMA + many SMALL models favors MLX (lowest overhead, shared memory, fast model swap) for the evolving lane.
