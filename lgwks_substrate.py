"""lgwks_substrate — thin facade re-exporting all substrate sub-modules.

This module exists solely for backward compatibility. All logic has been split
into focused sub-modules:

  - lgwks_substrate_config   constants, paths, regexes, exceptions
  - lgwks_substrate_io       file I/O, JSONL/JSON, manifest loading
  - lgwks_substrate_text     chunking, scoring, stemming, fact extraction
  - lgwks_substrate_crawl    web crawl engine, auth gates, frontier
  - lgwks_substrate_vector   vector search, vector space identity
  - lgwks_substrate_run      build/query/baseline orchestration, CLI parsers

Defense-in-Depth:
- Layer 1 (entry): facade validates that all sub-modules are importable at load time.
- Layer 2 (business): no logic lives here; every re-export delegates to a sub-module.
- Layer 3 (environment): missing sub-module raises ImportError immediately, not later.
- Layer 4 (debug): __all__ documents the public contract for consumers.
"""

from __future__ import annotations

# Sub-modules re-exported for consumer attribute access (e.g. substrate.lgwks_run)
import lgwks_browser
import lgwks_entity_graph as entity_graph
import lgwks_run
import lgwks_sqlite
import lgwks_substrate_crawl as crawl
import lgwks_substrate_run as _run_mod
from lgwks_html import html_to_markdown

# Config layer
from lgwks_substrate_config import (
    AUTH_GATE_RE,
    CODE_RE,
    EmbeddingProviderUnavailable,
    FrontierList,
    GLOBAL_ROOT,
    NARRATIVE_TERMS,
    NUMERIC_RE,
    PREVIOUS_VERSION_RE,
    PROCEDURE_TERMS,
    REF_RE,
    ROOT,
    RUN_ROOT,
    SENTENCE_SPLIT_RE,
    SKIP_DIRS,
    STRONG_AUTH_GATE_RE,
    TEXT_EXT,
    UPCOMING_EFFECTIVE_DATE,
    VERSION_BUCKETS,
)

# Note: GLOBAL_FACT_DB / lgwks_substrate_db were removed (#170); fact vectors now
# accumulate in the gate's world-tier VectorFabric (lgwks_storage).

# I/O layer
from lgwks_substrate_io import (
    _emit_json,
    _emit_jsonl,
    _iter_text_files,
    _json_cell,
    _load_run_manifest,
    _read_jsonl,
    _read_text,
    _sha,
    _slug,
)

# Text layer
from lgwks_substrate_text import (
    _bucket_facts,
    _chunk_kind,
    _chunk_text,
    _fact_score,
    _fact_sentences,
    _split_sentences,
    _stem_text,
    _version_bucket,
)

# Crawl layer
from lgwks_substrate_crawl import (
    _canonicalize_crawl_url,
    _crawl_map,
    _crawl_site,
    _frontier_status_counts,
    _is_ai_docs_index,
    _looks_like_login_gate,
    _merge_discovered_links,
    _should_discover_clicks,
    _text_discovered_links,
)

# Vector layer
from lgwks_substrate_vector import (
    _dot,
    _model_matches_vector_space,
    _provider_matches_vector_space,
    _query_embed_args,
    _stored_vector_space,
    _vector_search,
)

# Run / orchestration layer
from lgwks_substrate_run import (
    add_parser,
    baseline_command,
    baseline_run,
    build_command as _build_command,
    build_run as _build_run,
    map_command,
    query_command,
    query_run,
    _build_from_local,
    _parse_iso_date,
    _policy_pack_gaps,
    _provider_unavailable_payload,
    _source_type,
)


def build_run(args):
    """Backward-compatible facade wrapper for consumers patching lgwks_substrate.

    The implementation lives in lgwks_substrate_run, but existing tests and
    callers patch facade attributes such as RUN_ROOT and _crawl_site. Mirror those
    values into the implementation for the duration of the call.
    """
    old_run_root = _run_mod.RUN_ROOT
    old_crawl_site = crawl._crawl_site
    _run_mod.RUN_ROOT = globals().get("RUN_ROOT", old_run_root)
    crawl._crawl_site = globals().get("_crawl_site", old_crawl_site)
    try:
        return _run_mod.build_run(args)
    finally:
        _run_mod.RUN_ROOT = old_run_root
        crawl._crawl_site = old_crawl_site


def build_command(args):
    try:
        payload = build_run(args)
    except EmbeddingProviderUnavailable as exc:
        import json
        print(json.dumps(_provider_unavailable_payload(args, exc), indent=2))
        return 1
    import json
    print(json.dumps(payload, indent=2))
    return 0

__all__ = [
    # Exceptions / types
    "EmbeddingProviderUnavailable",
    "FrontierList",
    # Config constants
    "ROOT",
    "RUN_ROOT",
    "GLOBAL_ROOT",
    "TEXT_EXT",
    "SKIP_DIRS",
    "NUMERIC_RE",
    "CODE_RE",
    "REF_RE",
    "SENTENCE_SPLIT_RE",
    "PROCEDURE_TERMS",
    "NARRATIVE_TERMS",
    "AUTH_GATE_RE",
    "STRONG_AUTH_GATE_RE",
    "PREVIOUS_VERSION_RE",
    "VERSION_BUCKETS",
    "UPCOMING_EFFECTIVE_DATE",
    # I/O
    "_sha",
    "_slug",
    "_read_jsonl",
    "_emit_jsonl",
    "_emit_json",
    "_json_cell",
    "_iter_text_files",
    "_read_text",
    "_load_run_manifest",
    # Text
    "_split_sentences",
    "_fact_score",
    "_chunk_kind",
    "_stem_text",
    "_chunk_text",
    "_fact_sentences",
    "_version_bucket",
    "_bucket_facts",
    # Crawl
    "_canonicalize_crawl_url",
    "_is_ai_docs_index",
    "_looks_like_login_gate",
    "_merge_discovered_links",
    "_should_discover_clicks",
    "_text_discovered_links",
    "_crawl_site",
    "_crawl_map",
    "_frontier_status_counts",
    # Vector
    "_dot",
    "_provider_matches_vector_space",
    "_model_matches_vector_space",
    "_query_embed_args",
    "_stored_vector_space",
    "_vector_search",
    # Run
    "_source_type",
    "_parse_iso_date",
    "_build_from_local",
    "_policy_pack_gaps",
    "_provider_unavailable_payload",
    "build_run",
    "query_run",
    "baseline_run",
    "build_command",
    "map_command",
    "query_command",
    "baseline_command",
    "add_parser",
    # Sub-modules for consumer attribute access
    "lgwks_browser",
    "lgwks_run",
    "lgwks_sqlite",
    "entity_graph",
    "html_to_markdown",
]
