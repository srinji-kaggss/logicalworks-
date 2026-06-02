"""
lgwks_gate_idiom — G2 Idiom gate (spec-00).

Scores how well candidate code matches this repo's conventions using deterministic
embedding-distance to the repo corpus. Always ADVISORY — never blocks ship.
On embedder failure → CANNOT_DECIDE (excluded from score aggregation, NOT a 0 score).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from lgwks_verify import Klass, Outcome, Verdict


class IdiomVerifier:
    gate_id = "idiom"
    klass = Klass.ADVISORY

    def __init__(self, corpus_dir: str | Path | None = None, max_files: int = 200) -> None:
        self.corpus_dir = Path(corpus_dir) if corpus_dir else Path(__file__).resolve().parent
        self.max_files = max_files

    def _corpus_embeddings(self) -> tuple[list[Path], list[list[float]]] | None:
        """Embed .py files in corpus_dir. Returns (paths, embeddings) or None on failure."""
        try:
            import lgwks_embed
        except Exception as exc:
            return None
        paths: list[Path] = []
        vecs: list[list[float]] = []
        for p in sorted(self.corpus_dir.rglob("*.py")):
            if len(paths) >= self.max_files:
                break
            if any(part.startswith((".", "__")) for part in p.relative_to(self.corpus_dir).parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if not text.strip():
                    continue
                vec = lgwks_embed._embedding(text)
                paths.append(p)
                vecs.append(vec)
            except Exception:
                continue
        if not paths:
            return None
        return paths, vecs

    def check(self, subject: object, context: object) -> Verdict:
        """
        subject: candidate code (str) or file path (Path)
        context: dict with optional corpus_dir, max_files
        """
        if isinstance(context, dict):
            if "corpus_dir" in context:
                self.corpus_dir = Path(context["corpus_dir"])
            if "max_files" in context:
                self.max_files = context["max_files"]

        if isinstance(subject, (str, Path)):
            if isinstance(subject, Path) and subject.exists():
                candidate_text = subject.read_text(encoding="utf-8", errors="replace")
            else:
                candidate_text = str(subject)
        else:
            candidate_text = str(subject)

        try:
            import lgwks_embed
        except Exception as exc:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"embedder unavailable: {type(exc).__name__}: {exc}",
            )

        try:
            candidate_vec = lgwks_embed._embedding(candidate_text)
        except Exception as exc:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis=f"candidate embedding failed: {type(exc).__name__}: {exc}",
            )

        corpus = self._corpus_embeddings()
        if corpus is None:
            return Verdict(
                gate_id=self.gate_id,
                outcome=Outcome.CANNOT_DECIDE,
                klass=self.klass,
                diagnosis="corpus empty or embedder failed — cannot compute idiom score",
            )

        paths, vecs = corpus
        sims = [(p, lgwks_embed._cos(candidate_vec, v)) for p, v in zip(paths, vecs)]
        sims.sort(key=lambda x: x[1], reverse=True)
        top = sims[:5]
        if top:
            score = round(sum(s for _, s in top) / len(top), 4)
        else:
            score = 0.0

        # nearest exemplars (highest similarity)
        exemplars = [f"{p.relative_to(self.corpus_dir)} (sim={s:.4f})" for p, s in top[:3]]
        # deviations (lowest similarity)
        bottom = sims[-3:]
        deviations = [f"{p.relative_to(self.corpus_dir)} (sim={s:.4f})" for p, s in bottom]

        return Verdict(
            gate_id=self.gate_id,
            outcome=Outcome.PASS,
            klass=self.klass,
            score=score,
            evidence=[
                f"idiom score = {score}",
                f"nearest exemplars: {exemplars}",
                f"deviations: {deviations}",
            ],
        )
