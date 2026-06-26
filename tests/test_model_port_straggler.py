"""Model-port straggler guard (R5.4) — the embed/reason routing drift-prevention gate.

Machine-checkable complement of the Pristine Program R5 routing pass: every model
resolve/invoke flows through `lgwks_model_port` (the ladder). A future straggler — a
new caller that reaches the embedder/reasoner *beside* the port — fails this test,
not just a code review.

Three invariants (mirrors test_primitive_regrowth.py):
  1. No `lgwks_run.embed_dual(...)` call outside the port + the module that defines it.
  2. No `.model_name_for_role(...)` call outside the port + the law/reasoning tier.
  3. No import of a model-backend provider module outside the model-layer allow-list.

Legit forks in each allow-list are documented with a one-line reason (the R4.7
no-silent-self-allow-listing rule: a fork earns its place with a reason, never a
green checkmark for free).
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ── allow-lists (canonical + documented legit forks) ──────────────────────────

# embed_dual is the dual-vector mechanism; only the port wraps it and lgwks_run
# defines it. Every other caller routes through lgwks_model_port.embed (R5.1).
EMBED_DUAL_ALLOWED = {
    "lgwks_model_port.py",      # the canonical role-port wrapper (value IS the dual)
    "lgwks_run.py",             # defines embed_dual / embed (the tier mechanism)
}

# model_name_for_role pins the law model id; only the port (which asks the law for
# the role's model) and the reasoning tier resolve it. The mesh DEFINES it.
ROLE_MODEL_ALLOWED = {
    "lgwks_model_port.py",      # the role-port — asks the law for the role's model
    "lgwks_model_mesh.py",      # canonical — defines model_name_for_role (the law)
    "lgwks_reasoning_port.py",  # the reasoning tier resolves its own role model id
}

# Provider-backend modules whose IMPORT implies reaching a model invoke path. The
# port fronts all of these; only the model layer itself may import them.
PROVIDER_MODULES = {
    "lgwks_apple",
    "lgwks_openrouter_embed",
    "lgwks_embed_port",
    "lgwks_model_hub",
    "lgwks_reasoning_port",
}

# Files allowed to import a provider backend.
PROVIDER_IMPORT_ALLOWED = {
    # ── model-layer internal: the port + the tiers import each other freely ──
    "lgwks_model_port.py",          # the one port
    "lgwks_run.py",                 # the provider chain (auto→mlx→cloud→deterministic)
    "lgwks_apple.py",               # tier
    "lgwks_openrouter_embed.py",    # tier
    "lgwks_embed_port.py",          # tier (multimodal MLX runtime)
    "lgwks_reasoning_port.py",      # tier
    "lgwks_model_hub.py",           # tier (mlx_embed seam)
    "lgwks_models_dev.py",          # model catalog / locality selector
    # ── documented legit forks: availability PROBE / health / build tooling,
    #    NOT a model-invoke bypass (each verified against the call site) ──
    "lgwks_pipeline.py",            # lgwks_apple.is_available() — provider probe feeding the chain
    "lgwks_research.py",            # lgwks_reasoning_port.resolve_backend() — degrade-consent probe
    "lgwks_jepa.py",                # lgwks_model_hub.doctor() — health check, not an embed/reason call
    "build_capability_embeddings.py",  # model-layer build tooling (offline embedding bake)
    "setup_models.py",              # model-layer setup tooling (lgwks_model_hub.doctor)
    # ── KNOWN STRAGGLERS (not silent): genuine direct-embed bypasses, tracked ──
    # Both call EmbedPort().embed_text() at a caller-chosen dim/space the port does
    # not yet expose; safe routing needs a dim-aware port contract — tracked in #348.
    "lgwks_engine.py",              # STRAGGLER #348: EmbedPort(dim=dim).embed_text() at a dynamic artifact dim
    "lgwks_translate_rag.py",       # STRAGGLER #348: EmbedPort().embed_text() for the 4096-d translate-rag space
}


# ── source-file collector (mirrors test_primitive_regrowth.py) ────────────────

def _source_files() -> list[Path]:
    SKIP_DIRS = {"node_modules", "site-packages", "build", "dist", "__pycache__", "archive"}
    out: list[Path] = []
    for p in REPO.rglob("*.py"):
        parts = p.relative_to(REPO).parts
        if any(seg.startswith(".") for seg in parts):
            continue
        if any(seg in SKIP_DIRS for seg in parts):
            continue
        name = parts[-1]
        if "tests" in parts or name.startswith("test_"):
            continue
        if "vision" in parts:   # separate overlay tree
            continue
        out.append(p)
    return out


def _imported_modules(node: ast.AST) -> list[str]:
    """Top-level module names introduced by an Import / ImportFrom node."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module]
    return []


class TestNoModelPortStraggler(unittest.TestCase):
    """Embed/reason routing must not regrow a path beside the port after R5."""

    def _scan(self) -> tuple[list[str], list[str], list[str]]:
        embed_dual_hits: list[str] = []
        role_model_hits: list[str] = []
        provider_import_hits: list[str] = []
        for path in _source_files():
            name = path.name
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(REPO))
            for node in ast.walk(tree):
                # 1. *.embed_dual( call
                if (
                    name not in EMBED_DUAL_ALLOWED
                    and isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "embed_dual"
                ):
                    embed_dual_hits.append(f"{rel}:{getattr(node, 'lineno', '?')}")
                # 2. *.model_name_for_role( call
                if (
                    name not in ROLE_MODEL_ALLOWED
                    and isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_name_for_role"
                ):
                    role_model_hits.append(f"{rel}:{getattr(node, 'lineno', '?')}")
                # 3. import of a provider-backend module
                if name not in PROVIDER_IMPORT_ALLOWED:
                    for mod in _imported_modules(node):
                        if mod in PROVIDER_MODULES:
                            provider_import_hits.append(
                                f"{rel}:{getattr(node, 'lineno', '?')} ({mod})"
                            )
        return embed_dual_hits, role_model_hits, provider_import_hits

    def test_no_direct_embed_dual(self):
        hits, _, _ = self._scan()
        self.assertEqual(
            hits, [],
            "direct lgwks_run.embed_dual( outside the port — route through "
            "lgwks_model_port.embed(...) and read the envelope value (R5.1):\n  "
            + "\n  ".join(hits),
        )

    def test_no_direct_model_name_for_role(self):
        _, hits, _ = self._scan()
        self.assertEqual(
            hits, [],
            "direct .model_name_for_role( outside the port/law/reasoning tier — "
            "ask the port for the ROLE, not the law for a model id:\n  "
            + "\n  ".join(hits),
        )

    def test_no_direct_provider_import(self):
        _, _, hits = self._scan()
        self.assertEqual(
            hits, [],
            "import of a model-backend provider outside the model-layer allow-list — "
            "route the invoke through lgwks_model_port; if it is a probe/tooling fork, "
            "add it to PROVIDER_IMPORT_ALLOWED WITH A REASON:\n  "
            + "\n  ".join(hits),
        )


if __name__ == "__main__":
    unittest.main()
