# gemini-text

## Overview

Directory-based community: lgwks_input

- **Size**: 19 nodes
- **Cohesion**: 0.2031
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ModalityItem | Class | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 111-144 |
| is_quarantined | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 135-136 |
| needs_extraction | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 138-141 |
| word_count | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 143-144 |
| _sniff_mime | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 151-176 |
| _detect_mime | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 179-185 |
| _fingerprint | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 192-194 |
| _try_pdf_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 201-224 |
| _try_doc_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 227-246 |
| _decode_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 249-255 |
| _looks_text | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 258-263 |
| _tesseract_available | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 270-275 |
| _ocr_image_bytes | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 278-296 |
| _quarantine | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 303-315 |
| handle | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 322-444 |
| extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 452-497 |
| handle_and_extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 504-509 |
| handle_path | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 512-519 |
| handle_path_and_extract | Function | /Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py | 522-529 |

## Execution Flows

- **handle_and_extract** (criticality: 0.38, depth: 3)
- **handle_path_and_extract** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `strip` (6 edge(s))
- `len` (4 edge(s))
- `Path` (4 edge(s))
- `str` (4 edge(s))
- `startswith` (4 edge(s))
- `decode` (3 edge(s))
- `run` (3 edge(s))
- `BytesIO` (3 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestExtractFuzz.test_never_raises_on_text_direct` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestExtractFuzz.test_never_raises_on_50_random_items` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestVideoStrategy.test_extract_video_is_passthrough` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestVideoStrategy.test_extract_video_never_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestImageStrategy.test_extract_ocr_returns_text_when_tesseract_works` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestImageStrategy.test_extract_ocr_falls_back_to_visual_embed_on_failure` (2 edge(s))
- `unlink` (2 edge(s))

### Incoming

- `/Users/srinji/logicalworks-/.worktrees/gemini/lgwks_input.py` (16 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestExtractFuzz.test_never_raises_on_text_direct` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestExtractFuzz.test_never_raises_on_50_random_items` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestVideoStrategy.test_extract_video_is_passthrough` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestVideoStrategy.test_extract_video_never_raises` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestImageStrategy.test_extract_ocr_returns_text_when_tesseract_works` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestImageStrategy.test_extract_ocr_falls_back_to_visual_embed_on_failure` (2 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestExtractFuzz._make_item` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestNeedsExtraction.test_text_direct_does_not_need_extraction` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestNeedsExtraction.test_ocr_image_needs_extraction` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestNeedsExtraction.test_video_embed_does_not_need_extract_call` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestNeedsExtraction.test_none_does_not_need_extraction` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestFingerprint.test_deterministic` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestFingerprint.test_different_inputs_differ` (1 edge(s))
- `/Users/srinji/logicalworks-/.worktrees/gemini/tests/test_input_handler.py::TestFingerprint.test_empty_returns_deterministic_hash` (1 edge(s))
