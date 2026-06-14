"""lgwks_subconscious — the Subconscious Engine (PRD-06 U6).

Calculates C/G/P metrics to measure grounding and risk:
- C (Coverage): |grounded| / |required|
- G (Gap/Risk): Weighted sum of unverified claims.
- P (Confidence): Calibrated outcome probability.

Operationalizes §7 equations from the parent PRD.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_hashing
from lgwks_cortex import CortexTurn

@dataclass
class SubconsciousState:
    required_nodes: set[str] = field(default_factory=set)
    grounded_nodes: set[str] = field(default_factory=set)
    unverified_claims: list[dict[str, Any]] = field(default_factory=list)
    
    @property
    def coverage(self) -> float:
        if not self.required_nodes:
            return 1.0
        return len(self.grounded_nodes) / len(self.required_nodes)

    @property
    def gap_score(self) -> float:
        # G = Σ unverified_claim_i × w(tier_i)
        # Weights: 1.0 for uncited, 0.3 for docs, 0.1 for files
        score = 0.0
        for claim in self.unverified_claims:
            tier = claim.get("tier", "uncited")
            weight = {"uncited": 1.0, "docs": 0.3, "files": 0.1}.get(tier, 1.0)
            score += weight
        return score

class SubconsciousEngine:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def evaluate_intent(self, intent: str, turns: list[CortexTurn]) -> dict[str, Any]:
        """Derive C/G/P for a given intent and transcript sequence."""
        
        # 1. Derive required_nodes(intent)
        # PRD-06: union of (a) graph neighborhood, (b) input_schema fields, (c) touched files
        required = self._derive_required_nodes(intent)
        
        # 2. Derive grounded_nodes
        # PRD-06: required nodes with at least one evidence edge in transcript
        grounded = self._derive_grounded_nodes(required, turns)
        
        # 3. Extract unverified claims
        claims = self._extract_claims(turns)
        
        state = SubconsciousState(
            required_nodes=required,
            grounded_nodes=grounded,
            unverified_claims=claims
        )
        
        return {
            "schema": "lgwks.engine.v1",
            "C": round(state.coverage, 4),
            "G": round(state.gap_score, 4),
            "P": None, # Optional until calibrated
            "flags": self._detect_flags(state, turns),
            "required": sorted(list(required)),
            "grounded": sorted(list(grounded)),
        }

    def _derive_required_nodes(self, intent: str) -> set[str]:
        """Deterministic derivation of nodes required to fulfill the intent."""
        # Simple implementation for now; should query lgwks_graph
        nodes = set()
        # Mocking extraction of entities from intent string
        import re
        matches = re.findall(r'\b[a-zA-Z0-9_\-/]+\.[a-z]+\b', intent)
        for m in matches:
            nodes.add(m)
        return nodes

    def _derive_grounded_nodes(self, required: set[str], turns: list[CortexTurn]) -> set[str]:
        """Find which required nodes have evidence in the transcript."""
        grounded = set()
        for turn in turns:
            for entity in turn.entities:
                if entity in required:
                    grounded.add(entity)
        return grounded

    def _extract_claims(self, turns: list[CortexTurn]) -> list[dict[str, Any]]:
        """Find assertions made by the AI that lack tool-call verification."""
        claims = []
        for turn in turns:
            if turn.role == "assistant":
                # Logic to detect unverified assertions (e.g. "X is installed")
                # would go here. For now, we use a simple heuristic.
                if "installed" in turn.content.lower() and "run" not in turn.content.lower():
                    claims.append({"text": turn.content[:100], "tier": "uncited"})
        return claims

    def _detect_flags(self, state: SubconsciousState, turns: list[CortexTurn]) -> list[dict[str, Any]]:
        """Detect slop, sycophancy, or intent drift."""
        flags = []
        if state.coverage < 0.2 and len(turns) > 5:
            flags.append({"class": "low_grounding", "confidence": 0.9})
        return flags
