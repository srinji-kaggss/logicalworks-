from __future__ import annotations

from lgwks_diff import diff_chunks


def test_diff_chunks_basic():
    prev = [
        {"section_id": "intro", "chunk_type": "rule", "text": "This is rule number one. It is very strict.", "hash": "h1"},
        {"section_id": "intro", "chunk_type": "rule", "text": "This is rule number two. It is optional.", "hash": "h2"},
        {"section_id": "details", "chunk_type": "note", "text": "This note explains the exceptions.", "hash": "h3"}
    ]
    
    curr = [
        # Unchanged
        {"section_id": "intro", "chunk_type": "rule", "text": "This is rule number one. It is very strict.", "hash": "h1"},
        # Modified slightly
        {"section_id": "intro", "chunk_type": "rule", "text": "This is rule number two. It is now mandatory.", "hash": "h2_mod"},
        # Added
        {"section_id": "details", "chunk_type": "rule", "text": "New rule for details section.", "hash": "h4"},
        # Note h3 was removed
    ]
    
    diffs = diff_chunks(prev, curr)
    
    # Check count
    assert len(diffs) == 4
    
    unchanged = [d for d in diffs if d.status == "unchanged"]
    assert len(unchanged) == 1
    assert unchanged[0].section_id == "intro"
    assert unchanged[0].before_text == "This is rule number one. It is very strict."
    
    modified = [d for d in diffs if d.status == "modified"]
    assert len(modified) == 1
    assert modified[0].section_id == "intro"
    assert modified[0].before_text == "This is rule number two. It is optional."
    assert modified[0].after_text == "This is rule number two. It is now mandatory."
    assert modified[0].similarity > 0.6
    
    added = [d for d in diffs if d.status == "added"]
    assert len(added) == 1
    assert added[0].section_id == "details"
    assert added[0].after_text == "New rule for details section."
    
    removed = [d for d in diffs if d.status == "removed"]
    assert len(removed) == 1
    assert removed[0].section_id == "details"
    assert removed[0].before_text == "This note explains the exceptions."
