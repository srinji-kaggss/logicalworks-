"""lgwks_surprise — the Surprise Detection Loop (Phase 1 Hardening).

Computes the "Surprise" coefficient (S) by comparing Layer II (Liquid AI LFM)
predictions against Layer I (Axiom Math) ground truth.

S = |Pred - Truth| / Confidence

High S triggers an immediate "MAYDAY" flag in the Subconscious Engine,
forcing Aetherius to halt and re-ground.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lgwks_clock import now_iso as _now

@dataclass
class SurpriseSignal:
    ts: str = _now()
    source: str = "liquid_lfm"
    target: str = "axiom_math"
    surprise_score: float = 0.0
    is_anomaly: bool = False
    context: dict[str, Any] = None

class SurpriseLoop:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.log_path = repo_root / "store" / "daemon" / "surprise.jsonl"

    def evaluate(self, prediction: float, truth: float, confidence: float) -> SurpriseSignal:
        """Compute surprise score and check for anomalies."""
        if confidence <= 0:
            # Low confidence means infinite surprise if wrong
            s = abs(prediction - truth) * 10.0
        else:
            s = abs(prediction - truth) / confidence

        is_anomaly = s > 0.4  # Empirical threshold for Phase 1
        
        signal = SurpriseSignal(
            surprise_score=round(s, 4),
            is_anomaly=is_anomaly,
            context={"pred": prediction, "truth": truth, "conf": confidence}
        )
        
        self._log_signal(signal)
        return signal

    def _log_signal(self, signal: SurpriseSignal):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": signal.ts,
                "s": signal.surprise_score,
                "anomaly": signal.is_anomaly,
                **signal.context
            }) + "\n")

def check_surprise(args) -> int:
    """CLI hook for surprise checks."""
    loop = SurpriseLoop(Path(args.repo))
    sig = loop.evaluate(args.pred, args.truth, args.conf)
    if sig.is_anomaly:
        print(f"MAYDAY: High Surprise detected! S={sig.surprise_score}")
        return 1
    print(f"Surprise level normal: S={sig.surprise_score}")
    return 0

def add_parser(sub) -> None:
    p = sub.add_parser("surprise", help="run surprise detection loop (LII vs LI)")
    p.add_argument("--pred", type=float, required=True, help="LII prediction")
    p.add_argument("--truth", type=float, required=True, help="LI ground truth")
    p.add_argument("--conf", type=float, default=1.0, help="prediction confidence")
    p.add_argument("--repo", default=".", help="repo root")
    p.set_defaults(func=check_surprise)
