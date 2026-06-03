"""
lgwks_project — one-prompt project orchestrator front door (re-export shim).

This is the public name; the real work lives in the four split modules:

  - lgwks_project_artifacts: schemas, JSONL writers, pure record builders
  - lgwks_project_plan:      `lgwks project plan`
  - lgwks_project_deploy:    `lgwks project deploy` + non-ML executor
  - lgwks_project_review:    `lgwks project review`

Spec (round-1, lgwks_project.py split, refactor/project-split):
  L0 intent: preserve every public attribute (build_plan,
    deploy_command, review_project, _deploy_path, _render_review,
    DEPLOY_ROOT) on this module so existing tests + the lgwks binary
    keep working unchanged.
  L1 reality gap: tests monkey-patch `lgwks_project.DEPLOY_ROOT`
    then call `lgwks_project.deploy_command(args)`. The shim's
    DEPLOY_ROOT is the canonical mutable; the deploy module reads
    it through a lazy import of this shim's _deploy_path so the
    monkey-patch takes effect.
  L4 invariant: every public name survives at the lgwks_project
    module level. 123-test suite passes.
  L5 industry parallel: classic facade — a thin re-export layer
    over a set of focused modules; the public name survives.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import lgwks_cycle

from lgwks_project_artifacts import (
    ACADEMIC_SOURCES,
    DEFAULT_EMBEDDING_ROUNDS,
    DEFAULT_REASONING_CYCLES,
    DEFAULT_TOKENS,
    DEFAULT_WEIGHT,
    DEPLOY_ROOT,
    EMBED_DIMS,
    MAPPER_ROLES,
    MAPPER_ROLE_COUNT,
    PROJECT_ROOT,
)
from lgwks_project_plan import DEFAULT_WORKERS  # noqa: F401

# Re-exports for backwards-compatible attribute access on lgwks_project.
# Tests do `import lgwks_project as proj; proj.build_plan(args)` etc.
from lgwks_project_plan import build_plan, plan_command  # noqa: F401
from lgwks_project_deploy import deploy_command  # noqa: F401
from lgwks_project_review import review_command, review_project  # noqa: F401


def _deploy_path(project: str) -> Path:
    """Resolve the per-project deploy directory using this shim's DEPLOY_ROOT.

    Reading DEPLOY_ROOT from `lgwks_project` (not from
    `lgwks_project_artifacts`) is what makes the test pattern
    `proj.DEPLOY_ROOT = tmp/"deploy"; proj.deploy_command(args)` work —
    the shim's DEPLOY_ROOT is the canonical mutable, and the deploy
    module imports _deploy_path from this shim via a lazy import.
    """
    return lgwks_cycle.deploy_dir(DEPLOY_ROOT, project)


# Re-export _render_review for the projection test.
from lgwks_project_review import _render_review  # noqa: F401,E402


# Re-export deploy-internal helpers used by tests.
from lgwks_project_deploy import (  # noqa: F401,E402
    _artifact_embeddings,
    _embedding_record,
    _event,
    _learning_records,
    _operator_profile,
    _run_non_ml_execution,
    _source_records,
    _worker_map,
)


def add_parser(sub) -> None:
    p = sub.add_parser("project", help="one-prompt project orchestrator")
    ps = p.add_subparsers(dest="project_command", required=True)
    plan = ps.add_parser("plan", help="identify/spec a bounded worker plan from one prompt")
    plan.add_argument("project")
    plan.add_argument("--prompt", default="")
    plan.add_argument("--site", default="")
    plan.add_argument("--folder", default=".")
    plan.add_argument("--reasoning-cycles", type=int)
    plan.add_argument("--embedding-rounds", type=int, default=DEFAULT_EMBEDDING_ROUNDS)
    plan.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS)
    plan.add_argument("--tokens-per-cycle", type=int, default=DEFAULT_TOKENS)
    plan.set_defaults(func=plan_command)
    deploy = ps.add_parser("run", aliases=["deploy", "research"], help="run the one-prompt research orchestrator")
    deploy.add_argument("project")
    deploy.add_argument("--prompt", default="")
    deploy.add_argument("--reasoning-cycles", type=int)
    deploy.add_argument("--embedding-rounds", type=int, default=DEFAULT_EMBEDDING_ROUNDS)
    deploy.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS,
                        help="requested workers; hard-capped at 4 concurrent internal mapper slots")
    deploy.add_argument("--tokens-per-cycle", type=int, default=DEFAULT_TOKENS)
    deploy.add_argument("--site", default="open-public-sources")
    deploy.add_argument("--folder", default="", help="optional local folder for deterministic vector vault")
    deploy.add_argument("--source", choices=["all", *ACADEMIC_SOURCES], default="all")
    deploy.add_argument("--source-limit", type=int, default=5)
    deploy.add_argument("--embed-cycles", type=int, default=3)
    deploy.add_argument("--max-files", type=int, default=100)
    deploy.add_argument("--learning-mode", choices=["off", "local-only", "export-allowed"], default="local-only")
    deploy.add_argument("--device-consent", choices=["research-only", "local-device"], default="local-device",
                        help="local-device means the CLI may use local user-owned context for this research run")
    deploy.add_argument("--model-spine", choices=["deterministic", "oss-coreml"], default="oss-coreml")
    deploy.add_argument("--dry-run", action="store_true", help="write planned artifacts without fetch/model execution")
    deploy.add_argument("--execute", action="store_true", help="allow approved non-dry executor when implemented")
    deploy.set_defaults(func=deploy_command)
    review = ps.add_parser("review", help="review a project deploy artifact set")
    review.add_argument("project")
    review.add_argument("--render", action="store_true", help="human projection of the JSON review")
    review.set_defaults(func=review_command)
