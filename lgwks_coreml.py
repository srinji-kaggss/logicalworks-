"""lgwks_coreml — local text classification via CoreML.

Thin wrapper for any CoreML .mlpackage trained as a text classifier.
Used by lgwks_entity_graph as the T2 classification tier.

Constraints:
  - CoreML only. No cloud inference, no HuggingFace, no Ollama, no API.
  - Graceful no-op when coremltools is absent or no model file is present.
  - Training pipeline: TF-IDF + Logistic Regression (scikit-learn)
    converted via coremltools.converters.sklearn. Produces ~50–200KB .mlpackage.
    Runs on CPU; no Neural Engine required (though it uses it if present).

//why: A local, auditable, offline classifier is the only option on
a managed laptop with no cloud AI access. TF-IDF + LR is deterministic,
inspectable, and accurate enough for structural schema classification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default model path — override via LGWKS_COREML_MODEL env var
_DEFAULT_MODEL_PATH = Path.home() / ".config" / "lgwks" / "models" / "text_classifier.mlpackage"


def _resolve_model_path() -> Path:
    import os
    env = os.environ.get("LGWKS_COREML_MODEL")
    return Path(env) if env else _DEFAULT_MODEL_PATH


_model: Any | None = None
_model_path_at_load: Path | None = None


def _load_model() -> Any | None:
    path = _resolve_model_path()
    if not path.exists():
        logger.debug("No CoreML model at %s — T2 classification disabled", path)
        return None
    try:
        import coremltools as ct  # type: ignore[import]
        m = ct.models.MLModel(str(path))
        logger.info("Loaded CoreML model from %s", path)
        return m
    except ImportError:
        logger.warning("coremltools not installed — pip install coremltools (user-space, no elevation needed)")
        return None
    except Exception as exc:
        logger.warning("Failed to load CoreML model: %s", exc)
        return None


def _get_model() -> Any | None:
    global _model, _model_path_at_load
    current_path = _resolve_model_path()
    if _model is None or _model_path_at_load != current_path:
        _model = _load_model()
        _model_path_at_load = current_path
    return _model


def classify_page(text: str, max_chars: int = 2000) -> dict[str, Any]:
    """Classify a text snippet. Returns schema + confidence + source tag.

    Returns:
        {"schema": str, "confidence": float, "source": "coreml" | "no_model" | "error"}
    """
    model = _get_model()
    if model is None:
        return {"schema": "UNKNOWN", "confidence": 0.0, "source": "no_model"}

    snippet = text[:max_chars].replace("\n", " ").strip()
    if not snippet:
        return {"schema": "UNKNOWN", "confidence": 0.0, "source": "empty_input"}

    try:
        prediction = model.predict({"text": snippet})
        schema = prediction.get("classLabel", "UNKNOWN")
        probs: dict = prediction.get("classLabelProbs", {})
        confidence = float(probs.get(schema, 0.0))
        return {"schema": schema, "confidence": confidence, "source": "coreml"}
    except Exception as exc:
        logger.warning("CoreML inference error: %s", exc)
        return {"schema": "UNKNOWN", "confidence": 0.0, "source": f"error:{type(exc).__name__}"}


def classify_batch(texts: list[str]) -> list[dict[str, Any]]:
    """Classify multiple texts. Sequential — CoreML is fast enough locally."""
    return [classify_page(t) for t in texts]


def model_info() -> dict[str, Any]:
    """Return metadata about the loaded model (for diagnostics)."""
    model = _get_model()
    path = _resolve_model_path()
    if model is None:
        return {"status": "unavailable", "path": str(path)}
    try:
        spec = model.get_spec()
        return {
            "status": "loaded",
            "path": str(path),
            "description": spec.description.metadata.shortDescription or "",
        }
    except Exception as exc:
        return {"status": "loaded", "path": str(path), "spec_error": str(exc)}


# ── Training recipe (run once, offline, ships the .mlpackage) ────────────────
# This block is documentation — never executed at import time.
#
# SCHEMA_CLASSES (adjust to match your labelled corpus):
#   standard_index, standard_detail, transaction_table, form_reference,
#   glossary, nav_chrome, UNKNOWN
#
# from sklearn.pipeline import Pipeline
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.linear_model import LogisticRegression
# import coremltools as ct
# from coremltools.converters.sklearn import convert
#
# pipeline = Pipeline([
#     ("tfidf", TfidfVectorizer(max_features=4096, ngram_range=(1, 2))),
#     ("clf", LogisticRegression(max_iter=1000, C=1.0)),
# ])
# pipeline.fit(training_texts, training_labels)
#
# coreml_model = convert(
#     pipeline,
#     input_features=[("text", ct.models.datatypes.String())],
#     output_feature_names=["classLabel"],
# )
# coreml_model.save(str(_DEFAULT_MODEL_PATH))
#
# Alternatively: use Create ML (Xcode GUI) → Text Classifier → export .mlpackage
# then set LGWKS_COREML_MODEL to the exported path.
