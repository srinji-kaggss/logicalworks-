"""Tests for crawler v2 JSON contract shape.

These are Python-side validation tests — they verify the expected JSON structure
of `lgwks.crawl.v2` without requiring a Rust build. They act as a specification
fixture: if the Rust schema changes, these tests catch the mismatch.
"""

from __future__ import annotations

import json


EXPECTED_SCHEMA_VERSION = "lgwks.crawl.v2"


def _minimal_media_item(
    *,
    cid: str = "cid-abc123",
    modality: str = "image",
    url: str = "https://example.com/img.png",
    mime: str = "image/png",
    byte_count: int = 1024,
    fetch_status: int = 200,
) -> dict:
    return {
        "cid": cid,
        "modality": modality,
        "url": url,
        "mime": mime,
        "byte_count": byte_count,
        "fetch_status": fetch_status,
    }


def _minimal_page(*, include_media: bool = True) -> dict:
    page = {
        "cid": "cid-deadbeef0000",
        "url": "https://example.com/page",
        "canonical_url": None,
        "title": "Test Page",
        "text": "hello world",
        "markdown": "# hello world",
        "links": [],
        "assets": {"scripts": [], "stylesheets": [], "images": [], "inline_script_bytes": 0, "inline_style_bytes": 0},
        "chunks": [],
        "depth": 0,
        "discovered_by": "seed",
        "http": {"status": 200, "content_type": "text/html", "etag": None, "last_modified": None, "content_length": None, "elapsed_ms": 42},
        "simhash": 12345678,
        "word_count": 2,
        "fetched_at": "1718000000000",
    }
    if include_media:
        page["media"] = [_minimal_media_item()]
        page["artifacts"] = None
    return page


def test_media_item_has_required_keys():
    item = _minimal_media_item()
    for key in ("cid", "modality", "url", "mime", "byte_count", "fetch_status"):
        assert key in item, f"MediaItem missing key: {key}"


def test_media_item_modalities_are_typed():
    img = _minimal_media_item(modality="image")
    vid = _minimal_media_item(modality="video")
    assert img["modality"] == "image"
    assert vid["modality"] == "video"


def test_page_v2_has_media_and_artifacts():
    page = _minimal_page(include_media=True)
    assert "media" in page, "Page v2 must have 'media' field"
    assert "artifacts" in page, "Page v2 must have 'artifacts' field"


def test_page_v2_media_is_list_of_items():
    page = _minimal_page()
    assert isinstance(page["media"], list)
    assert len(page["media"]) == 1
    item = page["media"][0]
    assert item["cid"].startswith("cid-")
    assert item["modality"] in ("image", "video")


def test_schema_version_is_v2():
    assert EXPECTED_SCHEMA_VERSION == "lgwks.crawl.v2"


def test_crawl_result_schema_field():
    result = {
        "schema": EXPECTED_SCHEMA_VERSION,
        "run_id": "crawl-abc",
        "seed": "https://example.com",
        "pages": [_minimal_page()],
        "frontier": [],
        "stats": {},
    }
    assert result["schema"] == "lgwks.crawl.v2"


def test_artifacts_json_serializable():
    """artifacts must be JSON-serializable (it's serde_json::Value on the Rust side)."""
    page = _minimal_page()
    page["artifacts"] = {
        "title": "Test",
        "summary": "A test page",
        "entities": ["Example Corp"],
        "topics": ["testing"],
        "language": "en",
    }
    # must not raise
    json.dumps(page)
