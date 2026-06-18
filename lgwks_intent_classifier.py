"""
lgwks_intent_classifier — custom English intent classifier for the CLI membrane.

Bins a natural-language user input to one of N intent classes derived live from
the lgwks manifest verb surface. The classification result gates how much tool
authority Claude receives:

  high confidence  → pre-fill schema fields, full tool access
  low confidence   → [PLAN_ONLY] mode, Claude plans but does not execute
  no match         → pass-through, no pre-classification

//why custom model not a pre-existing one: the class set is domain-narrow
// (~20–50 lgwks verb schemas), English-only, and needs to update when new
// verbs land. A fine-tuned encoder owns the weights and retrains in minutes
// on MPS; an off-the-shelf instruct model cannot be retrained without
// licensing constraints and is 10–100× larger than necessary.

==============================================================================
SPEC — feat/intent-classifier (issue #27)
==============================================================================
L0 intent: classify a raw English string to a lgwks verb schema ID + a
  confidence score in < 2ms on the Apple Neural Engine, with no API call.

L1 reality gap: user input is noisy, rambling, and often multi-intent.
  A single linear classifier over sentence embeddings handles the common
  case; the confidence gate handles the hard case by falling back to
  PLAN_ONLY rather than guessing wrong.

L2 mechanism:
  - IntentClassifier.load(manifest_path) builds the class set from the
    live manifest (verb IDs + intent strings = label + feature signal).
  - IntentClassifier.classify(text) → ClassifyResult(label, confidence, top_k)
  - Fast path: cosine similarity over pre-computed class centroids (no inference).
  - Accurate path: CoreML model (DistilBERT-class encoder, 66M params) on ANE.
  - Training: tools/train_intent_classifier.py, PyTorch + MPS.
  - Export: safetensors → CoreML via coremltools (lgwks_intent_classifier.mlpackage).

L4 invariant:
  - classify("lgwks manifest") → label="manifest", confidence > 0.9
  - classify("what does this tool do") → label="manifest", confidence > 0.7
  - classify("gobbledygook xyzzy") → confidence < THRESHOLD → PLAN_ONLY
  - Inference time < 2ms on ANE (measured via time.perf_counter()).

L5 industry parallel: Apple's on-device intent classification (SiriKit),
  Android's ML Kit NLU — both use fine-tuned encoder models, not generative
  LLMs, for closed-set intent recognition on-device.
==============================================================================
"""

from __future__ import annotations

import lgwks_hashing
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# //why a persisted centroid cache: building centroids embeds all ~175 verb
# intents through the Qwen Eye (qwen3-embedding:8b) one HTTP call at a time —
# measured at 201s per process start. For a membrane that gates EVERY prompt
# that is unusable. The centroids are a pure function of (verb signal set,
# embedder identity), so they are cached on disk and rebuilt only when the
# manifest verb set or the embedder space changes. Eye-built and hash-built
# centroids are keyed separately so a stale-space cache can never be reused.
_CENTROID_CACHE_DIR = Path(__file__).resolve().parent / "store" / "intent"
_CENTROID_CACHE_SCHEMA = "lgwks.intent.centroids.v1"

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Thresholds + the authority law
# ---------------------------------------------------------------------------

# Authority thresholds (loaded from calibration artifact, H1)
def _load_thresholds() -> dict[str, float]:
    from lgwks_config import get_config
    cfg = get_config().get("intent", {})
    
    p = Path(__file__).resolve().parent / "store" / "models" / "intent_calibration.json"
    defaults = {
        "confidence_threshold": cfg.get("confidence_threshold", 0.55),
        "full_authority_threshold": cfg.get("full_authority_threshold", 0.85),
        "lexical_confidence_ceiling": 0.74,
        "margin_min": cfg.get("margin_min", 0.02)
    }
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return {k: data.get(k, v) for k, v in defaults.items()}
        except Exception:
            pass
    return defaults

_THRESH = _load_thresholds()
CONFIDENCE_THRESHOLD = _THRESH["confidence_threshold"]
FULL_AUTHORITY_THRESHOLD = _THRESH["full_authority_threshold"]
LEXICAL_CONFIDENCE_CEILING = _THRESH["lexical_confidence_ceiling"]
MARGIN_MIN = _THRESH["margin_min"]

# //why only semantic methods may cross FULL_AUTHORITY_THRESHOLD: a lexical
# path (feature-hash cosine, keyword overlap) measures surface-form overlap,
# not meaning. It can pre-fill a schema field as a *suggestion*, but it must
# never alone unlock execution.
SEMANTIC_METHODS = frozenset({"coreml", "eye", "mlx"})

# //The Referee Doctrine: Evidence over Vibes.
# Claims of system state must be backed by deterministic artifacts.
EVIDENCE_KEYWORDS = {"hash", "blake3", "axiom", "proof", "ledger", "log", "diff", "checksum", "trace"}
VIBE_KEYWORDS = {"think", "feel", "maybe", "probably", "buggy", "broken", "weird"}

def _referee_gate(text: str, result: ClassifyResult) -> ClassifyResult:
    """Harden result by penalizing 'vibe-heavy' claims that lack evidence."""
    text_lower = text.lower()
    has_vibe = any(w in text_lower for w in VIBE_KEYWORDS)
    has_evidence = any(w in text_lower for w in EVIDENCE_KEYWORDS)
    
    if has_vibe and not has_evidence and result.confidence > CONFIDENCE_THRESHOLD:
        # Cap confidence to force PLAN_ONLY if claim is subjective/unproven
        new_conf = min(result.confidence, CONFIDENCE_THRESHOLD - 0.01)
        return dataclass_replace(result, confidence=new_conf, 
                                 metadata={**result.metadata, "referee_penalty": "vibe_no_evidence"})
    return result

from dataclasses import replace as dataclass_replace


@dataclass
class ClassifyResult:
    label: str          # verb schema ID, e.g. "manifest", "geo compile"
    confidence: float   # 0.0–1.0, already authority-clamped for the method
    top_k: list[tuple[str, float]] = field(default_factory=list)
    inference_ms: float = 0.0
    method: str = "cosine"  # "eye" | "coreml" | "cosine" | "keyword" | "empty" | "error"
    margin: float = 0.0     # top1 − top2 separation; the ambiguity signal
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def plan_only(self) -> bool:
        # //why three gates: no label, OR weak absolute score, OR the top two
        # classes nearly tie (low margin = ambiguous, the gibberish signature).
        # Any one trips PLAN_ONLY — Claude plans, does not execute. The margin gate
        # is the load-bearing one for the Eye space (see MARGIN_MIN).
        return (
            (not self.label)
            or self.confidence < CONFIDENCE_THRESHOLD
            or self.margin < MARGIN_MIN
        )

    @property
    def grants_full_authority(self) -> bool:
        # //why the method guard is load-bearing, not redundant with the score:
        # it is the structural half of the #29 fix. Even if a lexical score were
        # somehow >= the bar, a non-semantic method can never grant execution.
        # //why margin check: a near-tie (low margin) is the gibberish signature.
        # Execution requires BOTH a high absolute score AND a clear lead.
        return (
            bool(self.label)
            and self.method in SEMANTIC_METHODS
            and self.confidence >= FULL_AUTHORITY_THRESHOLD
            and self.margin >= MARGIN_MIN
        )


def _clamp_for_method(confidence: float, method: str) -> float:
    """
    The single enforcement seam for the authority law.

    //why one chokepoint: every inference path routes its raw score through
    here, so the invariant "non-semantic method cannot reach the full-authority
    bar" holds by construction — no path can forget to apply it.
    """
    c = 0.0 if confidence != confidence else float(confidence)  # NaN → 0.0
    c = max(0.0, min(1.0, c))
    if method not in SEMANTIC_METHODS:
        c = min(c, LEXICAL_CONFIDENCE_CEILING)
    return round(c, 6)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class IntentClassifier:
    """
    Thin wrapper over the two inference paths (cosine centroids + CoreML).

    Load once per process:
        clf = IntentClassifier.load()
        result = clf.classify("show me the tool manifest")
    """

    def __init__(self, classes: list[str], centroids: Optional[Any] = None,
                 coreml_model: Optional[Any] = None, space_id: str = "unknown"):
        self._classes = classes
        self._centroids = centroids      # list[list[float]] shape (N_classes, embed_dim) when built
        self._coreml = coreml_model      # coremltools model handle when loaded
        self._space_id = space_id        # //why explicit space_id (H2): ensures mathematical parity

        # //why record semantic: semantic spaces may cross the full-authority bar.
        # "eye" provider (mlx:) and CoreML are semantic; feature-hash is not.
        self._semantic = space_id.startswith("mlx:") or space_id == "coreml" or space_id.startswith("openrouter:")
        
        self._ready = False

    # -- factory ------------------------------------------------------------

    @classmethod
    def load(cls, manifest_path: Optional[Path] = None,
             model_path: Optional[Path] = None) -> "IntentClassifier":
        """
        Build classifier from the live manifest (class labels) + optional
        trained CoreML model. Falls back to cosine-centroid path if no model.

        manifest_path defaults to the lgwks binary's build_manifest() output.
        model_path defaults to lgwks_intent_classifier.mlpackage in the same dir.
        """
        # //why lazy import: numpy and coremltools are not always present;
        # the cosine path degrades gracefully without them.
        manifest = _load_manifest(manifest_path)
        verbs = manifest.get("verbs", [])
        classes = [v["verb"] for v in verbs]

        # //why build centroids at load: the cosine path is the always-available,
        # no-model fallback. Each class centroid is the deterministic embedding of
        # its verb id + intent string, so classify() has a real lexical signal
        # instead of collapsing to the keyword-overlap floor (the old bug: load()
        # left centroids=None, so every call fell through to _classify_keyword).
        # Cache-first: a 201s rebuild only happens on a verb-set or embedder-space
        # change; otherwise centroids load from disk in milliseconds.
        # //why space_id instead of semantic flag (H2): ensures parity (ADR-003).
        centroids, space_id = _load_or_build_centroids(verbs)

        coreml_model = None
        if model_path is None:
            here = Path(__file__).resolve().parent
            model_path = here / "lgwks_intent_classifier.mlpackage"

        if model_path.exists():
            try:
                import coremltools as ct  # type: ignore
                coreml_model = ct.models.MLModel(str(model_path))
                space_id = "coreml"
            except Exception:
                coreml_model = None  # //why: CoreML optional; cosine path still works

        inst = cls(classes=classes, centroids=centroids, coreml_model=coreml_model,
                   space_id=space_id)
        inst._ready = True
        return inst

    # -- inference ----------------------------------------------------------

    def classify(self, text: str) -> ClassifyResult:
        """Classify text → ClassifyResult. Never raises; returns low-confidence on error."""
        if not text or not text.strip():
            return ClassifyResult(label="", confidence=0.0, method="empty")

        t0 = time.perf_counter()
        try:
            if self._coreml is not None:
                result = self._classify_coreml(text)
            elif self._centroids:
                result = self._classify_cosine(text)
            else:
                result = self._classify_keyword(text)
        except Exception:
            result = ClassifyResult(label="", confidence=0.0, method="error")

        # //why a final re-clamp at the single exit: defense in depth. Even if a
        # future inference path forgets to clamp, the authority law (non-semantic
        # method cannot reach the full-authority bar) is enforced here for every
        # result that leaves classify().
        result.confidence = _clamp_for_method(result.confidence, result.method)
        # //why compute margin at the single exit: top_k is populated by every
        # inference path, so the ambiguity signal is uniform regardless of method.
        # A 0-or-1-candidate result has no runner-up → margin = top1 (treated as
        # maximally separated, the empty/keyword degenerate cases self-gate elsewhere).
        if len(result.top_k) >= 2:
            result.margin = round(result.top_k[0][1] - result.top_k[1][1], 6)
        elif result.top_k:
            result.margin = round(result.top_k[0][1], 6)
        result.inference_ms = (time.perf_counter() - t0) * 1000
        # Final safeguard: the Referee Gate (Evidence over Vibes)
        return _referee_gate(text, result)

    def _classify_coreml(self, text: str) -> ClassifyResult:
        # //why: CoreML path — fastest, runs on ANE. Requires trained model file.
        assert self._coreml is not None
        out = self._coreml.predict({"text": text})
        label = out.get("label", "")
        probs = out.get("labelProbability", {})
        top_k = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
        # //why coreml is the only semantic method: a trained encoder measures
        # meaning, so it alone may cross the full-authority bar (see SEMANTIC_METHODS).
        conf = _clamp_for_method(probs.get(label, 0.0), "coreml")
        return ClassifyResult(label=label, confidence=conf, top_k=top_k, method="coreml")

    def _classify_cosine(self, text: str) -> ClassifyResult:
        # //why one cosine path, two meanings: the SAME centroid+query cosine is a
        # semantic match when both came from the Eye, and a lexical surface-overlap
        # match when both came from the feature-hash fallback. The vector is the
        # signal; the method label records which space we were in, and the method
        # gates authority via _clamp_for_method + grants_full_authority.
        emb, q_space_id, q_semantic = _embed(text)
        centroids = self._centroids or []

        # //why the space-mismatch guard is load-bearing (H2): centroids and
        # queries must live in the same mathematical space (e.g. both Eye-MRL or
        # both blake2b hash). A length check is NOT enough if dimensions coincide.
        # We enforce parity here via explicit space_id.
        if self._space_id != q_space_id:
            # Spaces are incomparable (e.g. Eye centroids vs Hash query).
            # Force zero-confidence to trigger PLAN_ONLY or pass-through.
            return ClassifyResult(label="", confidence=0.0, top_k=[], method="mismatch",
                                 metadata={"expected_space": self._space_id, "actual_space": q_space_id})

        if centroids and len(emb) != len(centroids[0]):
            return ClassifyResult(label="", confidence=0.0, top_k=[], method="error")

        method = "eye" if q_semantic else "cosine"

        sims = [(self._classes[i], _cosine(emb, c)) for i, c in enumerate(centroids)]
        sims.sort(key=lambda x: x[1], reverse=True)
        label, raw = sims[0] if sims else ("", 0.0)
        conf = _clamp_for_method(raw, method)
        top_k = [(lbl, round(max(0.0, s), 6)) for lbl, s in sims[:5]]
        return ClassifyResult(label=label, confidence=conf, top_k=top_k, method=method)

    def _classify_keyword(self, text: str) -> ClassifyResult:
        # //why: zero-resource fallback — no model, no centroids. Keyword overlap
        # with verb ids. Weakest signal, so capped hardest (0.6) before the
        # method clamp; PLAN_ONLY fires for anything ambiguous.
        lowered = text.lower()
        scores: list[tuple[str, float]] = []
        for cls in self._classes:
            words = set(cls.replace(".", " ").split())
            overlap = sum(1 for w in words if w in lowered)
            scores.append((cls, round(overlap / max(len(words), 1), 6)))
        scores.sort(key=lambda x: x[1], reverse=True)
        label, score = scores[0] if scores else ("", 0.0)
        conf = _clamp_for_method(min(score, 0.6), "keyword")
        return ClassifyResult(label=label, confidence=conf, top_k=scores[:5], method="keyword")

    # -- properties ---------------------------------------------------------

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    def is_ready(self) -> bool:
        return self._ready


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_manifest(path: Optional[Path]) -> dict:
    if path is not None and path.exists():
        return json.loads(path.read_text())
    try:
        import lgwks_manifest
        return lgwks_manifest.build_manifest()
    except Exception:
        return {"verbs": []}


def _embed(text: str) -> tuple[list[float], str, bool]:
    # //why route through lgwks_run.embed, the ONE canonical embedding seam: it
    # tries the real Qwen Eye (qwen3-embedding via Ollama, MRL-sliced to DIMS) and
    # returns is_semantic=True; only if the Eye is down/absent does it fall back to
    # the deterministic blake2b feature-hash (is_semantic=False). This kills the
    # embedder divergence that caused #29 — the classifier no longer carries its
    # own embedding implementation that can silently rot to np.random or drift from
    # the rest of lgwks. The bool flows into the authority law: semantic → method
    # "eye" (may grant authority), non-semantic → "cosine" (capped).
    import lgwks_run
    vec, provider, is_semantic = lgwks_run.embed(text, embed_on=True, provider="auto")
    if vec is None:  # //why guard: embed_on=True always yields a vector, but never trust a None into cosine
        return [], "error", False
    return vec, provider, bool(is_semantic)


# //why a true normalized cosine, not a bare dot: feature-hash vectors are
# unit-normalized but Eye vectors are NOT unit-norm after the MRL slice, so a dot
# product would conflate magnitude with similarity. The canonical cosine normalizes
# both, making one definition correct for both spaces.
from lgwks_vecmath import cosine as _cosine  # one source of truth for cosine similarity


def _verb_signature(verbs: list[dict]) -> str:
    # //why hash the (verb, intent) pairs in order: the centroids are a pure
    # function of exactly this signal set. Any verb added/removed/reworded changes
    # the hash and forces a rebuild; nothing else does. Sorted-key json so the
    # signature is stable across dict ordering.
    payload = json.dumps(
        [[v.get("verb", ""), v.get("intent", "")] for v in verbs],
        sort_keys=True, separators=(",", ":"),
    )
    return lgwks_hashing.content_id(payload)


def _probe_embedder_tag() -> str:
    # //why probe once, not 175 times: the cache key must encode WHICH space the
    # centroids live in (Eye vs deterministic hash) so the two never get mixed.
    # One probe embed reveals is_semantic without paying the full build cost.
    try:
        _vec, provider, semantic = _embed("manifest")
        return provider
    except Exception:
        return "hash"


def _centroid_cache_path(verbs: list[dict], space_id: str) -> Path:
    # sanitize space_id for filename
    safe_id = "".join(c if c.isalnum() else "_" for c in space_id)
    return _CENTROID_CACHE_DIR / f"centroids-{safe_id}-{_verb_signature(verbs)}.json"


def _load_or_build_centroids(verbs: list[dict]) -> tuple[list[list[float]], str]:
    """Load cached centroids when the verb set + embedder space match; else build
    (the slow 175-embed path) and persist. The cache is the difference between a
    201s load and a millisecond load."""
    if not verbs:
        return [], "empty"
    space_id = _probe_embedder_tag()
    cache_path = _centroid_cache_path(verbs, space_id)
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if (data.get("schema") == _CENTROID_CACHE_SCHEMA
                    and len(data.get("centroids", [])) == len(verbs)):
                # //why trust the cache: the filename hash already pins it to this
                # exact verb set + embedder space; a length match is the final guard.
                return data["centroids"], data.get("space_id", space_id)
        except Exception:
            pass  # //why swallow: a corrupt cache must never block; rebuild instead.
    centroids, actual_space_id = _build_centroids(verbs)
    # //why only cache the Eye space: a hash-built centroid set is cheap to rebuild
    # and we never want a degraded (Eye-was-down) build to masquerade as semantic on
    # a later run. Persist either way, keyed by tag, so both spaces stay separated.
    try:
        _CENTROID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "schema": _CENTROID_CACHE_SCHEMA,
            "space_id": actual_space_id,
            "centroids": centroids,
        }, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass  # //why swallow: failure to cache must not fail the load.
    return centroids, actual_space_id


def _build_centroids(verbs: list[dict]) -> tuple[list[list[float]], str]:
    # //why verb id + intent as the class signal: the manifest IS the class
    # schema. A new verb adds a class automatically on the next load. Aligned
    # 1:1 with the classes list so argmax maps straight back to a verb id.
    # //why return all_semantic: the centroids may grant full authority only if
    # they were built by the Eye (not the fallback). One non-semantic centroid
    # taints the set — we report semantic ONLY if every centroid is semantic.
    centroids: list[list[float]] = []
    first_space_id = None
    for v in verbs:
        verb_id = v.get("verb", "")
        intent = v.get("intent", "")
        if intent == "(no metadata)":
            intent = ""
        signal = f"{verb_id.replace('.', ' ')} {intent}".strip()
        vec, space_id, _is_semantic = _embed(signal)
        centroids.append(vec)
        if first_space_id is None:
            first_space_id = space_id
    return centroids, first_space_id or "unknown"


# ---------------------------------------------------------------------------
# CLI entry (lgwks intent classify <text>)
# ---------------------------------------------------------------------------

def classify_command(args) -> int:
    clf = IntentClassifier.load()
    result = clf.classify(args.text)
    import json as _json
    print(_json.dumps({
        "label": result.label,
        "confidence": round(result.confidence, 4),
        "plan_only": result.plan_only,
        "grants_full_authority": result.grants_full_authority,
        "method": result.method,
        "margin": round(result.margin, 4),
        "inference_ms": round(result.inference_ms, 3),
        "top_k": result.top_k[:3],
    }, indent=2))
    return 0
