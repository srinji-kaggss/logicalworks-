"""lgwks_algorithms — L4 narrow-ML catalog (semantic-escalation-harness stage L4).

The consultant package (`semantic_escalation_harness/04_algorithm_catalog.yaml`) names the
narrow-ML algorithms that answer questions deterministic code cannot, BELOW the generative
line: score, rank, cluster, detect anomalies, monitor. This module implements the
stdlib-doable minimum-viable set as pure, deterministic functions — no numpy, no sklearn,
no network — so they run in the 3.14 runtime today and are auditable line by line.

Division of labor (ARCHITECTURE.md L-coefficient):
  these are `inferred`/`grounded` operators — L contribution 0. They score and flag;
  they never generate and never decide authority. A high anomaly score is evidence for a
  human/LLM gate, not an action.

Dep-heavy algorithms (LightGBM, HDBSCAN, IsolationForest) are CATALOGED here with their
landing point but not implemented — they need scikit-learn/lightgbm, which the PEP-668
runtime cannot pip-install. See CATALOG `status` and the BUILDLOG deferral ledger.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional


# ── results ───────────────────────────────────────────────────────────────────

@dataclass
class AnomalyVerdict:
    """A point judged against a baseline. `flag` is the decision; `score` is the evidence."""
    score: float          # standardized deviation (z-like); higher = more anomalous
    flag: bool            # score exceeded the threshold
    method: str           # which detector produced this
    threshold: float
    baseline: dict[str, float] = field(default_factory=dict)


# ── spike / trend detectors (consultant: rolling_z_score, EWMA) ────────────────

def rolling_z_score(series: list[float], *, window: int = 20, threshold: float = 3.0) -> AnomalyVerdict:
    """Is the newest observation unusually far from its recent baseline?
    //why robust z (median + MAD), not mean/std: a single prior spike inflates std and
    masks the next one; MAD is breakdown-resistant. 1.4826 scales MAD to a std estimate
    for a normal distribution so `threshold` reads in familiar sigma units."""
    if not series:
        return AnomalyVerdict(0.0, False, "rolling_z_score", threshold)
    latest = series[-1]
    base = series[-(window + 1):-1] if len(series) > 1 else series[:-1]
    if len(base) < 2:
        return AnomalyVerdict(0.0, False, "rolling_z_score", threshold, {"n": len(base)})
    med = _median(base)
    mad = _median([abs(x - med) for x in base]) or 1e-9
    z = abs(latest - med) / (1.4826 * mad)
    return AnomalyVerdict(round(z, 4), z > threshold, "rolling_z_score", threshold,
                          {"median": round(med, 4), "mad": round(mad, 4), "latest": latest})


def ewma(series: list[float], *, alpha: float = 0.3) -> list[float]:
    """Exponentially weighted moving average — smoothed recent trend.
    //why one pass, deterministic: alpha fixes the memory; same input → same curve."""
    if not series:
        return []
    out = [series[0]]
    for x in series[1:]:
        out.append(alpha * x + (1 - alpha) * out[-1])
    return [round(v, 6) for v in out]


def ewma_deviation(series: list[float], *, alpha: float = 0.3, threshold: float = 3.0) -> AnomalyVerdict:
    """Is a persistent short-term trend pulling away from the smoothed baseline?"""
    if len(series) < 3:
        return AnomalyVerdict(0.0, False, "ewma_deviation", threshold)
    smoothed = ewma(series[:-1], alpha=alpha)
    resid = [series[i] - smoothed[i] for i in range(len(smoothed))]
    sigma = _std(resid) or 1e-9
    dev = abs(series[-1] - smoothed[-1]) / sigma
    return AnomalyVerdict(round(dev, 4), dev > threshold, "ewma_deviation", threshold,
                          {"ewma_last": round(smoothed[-1], 4), "sigma": round(sigma, 4)})


# ── interpretable baseline classifier (consultant: logistic_regression) ────────

@dataclass
class LogisticModel:
    weights: list[float]
    bias: float
    feature_names: list[str] = field(default_factory=list)

    def predict_proba(self, x: list[float]) -> float:
        z = self.bias + sum(w * xi for w, xi in zip(self.weights, x))
        return _sigmoid(z)


def fit_logistic(X: list[list[float]], y: list[int], *, epochs: int = 400,
                 lr: float = 0.1, l2: float = 1e-4,
                 feature_names: Optional[list[str]] = None) -> LogisticModel:
    """Batch gradient-descent logistic regression — the interpretable risk/router baseline.
    //why pure-python deterministic GD: no sklearn in the runtime; the weights are
    inspectable (each feature's contribution is its weight × value), which is the whole
    point of a *baseline* — auditable before reaching for a tree ensemble. Fixed epochs/lr,
    no RNG → reproducible. For real scale this is superseded by LightGBM (deferred)."""
    if not X or len(X) != len(y):
        raise ValueError("X and y must be non-empty and equal length")
    n_features = len(X[0])
    w = [0.0] * n_features
    b = 0.0
    n = len(X)
    for _ in range(epochs):
        gw = [0.0] * n_features
        gb = 0.0
        for xi, yi in zip(X, y):
            p = _sigmoid(b + sum(w[j] * xi[j] for j in range(n_features)))
            err = p - yi
            for j in range(n_features):
                gw[j] += err * xi[j]
            gb += err
        for j in range(n_features):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * (gb / n)
    return LogisticModel(weights=[round(v, 6) for v in w], bias=round(b, 6),
                         feature_names=feature_names or [f"f{i}" for i in range(n_features)])


# ── helpers ────────────────────────────────────────────────────────────────────

def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


# ── catalog (mirrors consultant 04_algorithm_catalog.yaml; auditable status) ────

# //why a registry with explicit status: "algorithms figured out" must be auditable —
# what runs today vs what is deferred and why. `impl` points to the live function;
# deferred entries name the dependency and where they land (BUILDLOG deferral ledger).
CATALOG: dict[str, dict[str, Any]] = {
    "rolling_z_score": {"status": "live", "impl": rolling_z_score,
                        "answers": "Is the newest observation far from its recent baseline?",
                        "use_cases": ["latency_spike", "error_spike", "cost_spike", "escalation_score"]},
    "ewma": {"status": "live", "impl": ewma,
             "answers": "What is the smoothed recent trend?",
             "use_cases": ["latency_monitoring", "engagement_drift", "crawler_performance"]},
    "ewma_deviation": {"status": "live", "impl": ewma_deviation,
                       "answers": "Is a persistent trend pulling away from baseline?",
                       "use_cases": ["model_drift", "regression_watch"]},
    "logistic_regression": {"status": "live", "impl": fit_logistic,
                            "answers": "Probability of a label from structured features (interpretable).",
                            "use_cases": ["simple_router", "risk_baseline", "fraud_risk_baseline"]},
    # deferred — need scikit-learn / lightgbm; PEP-668 runtime cannot pip-install
    "lightgbm": {"status": "deferred", "needs": "lightgbm", "lands": "L4 tabular scoring (fraud_risk, escalation_score)",
                 "answers": "Given structured features, what score/class? (gradient-boosted trees)"},
    "isolation_forest": {"status": "deferred", "needs": "scikit-learn", "lands": "L4 global anomaly",
                         "answers": "Which records are globally unusual without labels?"},
    "hdbscan": {"status": "deferred", "needs": "hdbscan", "lands": "L4 density clustering (theme discovery)",
                "answers": "Which natural groups exist without forcing every item into a cluster?"},
    "lof": {"status": "deferred", "needs": "scikit-learn", "lands": "L4 local anomaly",
            "answers": "Which records are strange relative to nearby peers?"},
    "lambdamart": {"status": "deferred", "needs": "lightgbm", "lands": "L3/L4 learning-to-rank",
                   "answers": "In what order should a candidate list appear?"},
    "contextual_bandit": {"status": "deferred", "needs": "feedback loop", "lands": "L4 online exploration",
                          "answers": "Which option to test while favoring known-strong ones?"},
}


def catalog_status() -> dict[str, Any]:
    """Machine-readable: which narrow-ML algorithms are live vs deferred and why."""
    live = sorted(k for k, v in CATALOG.items() if v["status"] == "live")
    deferred = {k: v.get("needs") for k, v in CATALOG.items() if v["status"] == "deferred"}
    return {"schema": "lgwks.algorithms.catalog.v1", "live": live, "deferred": deferred,
            "total": len(CATALOG)}
