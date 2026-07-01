import pytest
from lgwks_project_review import _render_review
from lgwks_project_artifacts import MAPPER_ROLE_COUNT

def test_render_review_coverage():
    review_data = {
        "project": "test_project",
        "chain_ok": True,
        "cycles": 10,
        "token_status": "ok",
        "token_spend": 100,
        "source_records": 5,
        "vector_vault_status": "ok",
        "vector_records": 20,
        "artifact_embeddings": 3,
        "active_worker_slots": 2,
        "max_concurrent_workers": MAPPER_ROLE_COUNT,
        "machine_packets": 15,
        "graph_edges": 8,
        "model_lineage_count": 1,
        "one_command_replaces_many": True,
        "build_on_existing_work": False,
        "rollback_ref": "abc123def456",
        "unsupported_claims": [],
        "execution_status_counts": {},
    }
    rendered_string = _render_review(review_data)
    assert rendered_string
    assert "test_project" in rendered_string
