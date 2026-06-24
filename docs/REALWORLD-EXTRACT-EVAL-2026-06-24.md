# Real-world eval + fixes — `lgwks extract` / `convert` (2026-06-24)

Branch: `fix/extract-realworld-evals`. Method: dogfood the read-anything surface
(`lgwks extract` / `convert` → `lgwks_extract.extract`) against real files and URLs a
coding agent meets daily; root-cause each failure; fix locally. Every claim below is
backed by a command run against a real fixture or a portable regression test
(`tests/test_realworld_extract_convert.py`, 37 cases).

## Constraints honored
- **No egress.** No document bytes leave the machine — no cloud OCR/LLM/converter.
- **No new dependencies.** OCR uses poppler (`pdftoppm`, already installed) + the
  macOS Vision framework via a shipped `tools/vision_ocr.swift` helper (OS-shipped,
  like `pdftotext`/`crwl` already shelled out to). Office/epub extraction uses stdlib
  `zipfile`. Nothing added to `requirements*.txt`.
- **Root files unmoved.** The load-bearing `lgwks_*.py` dispatcher contract is intact.
- **One canonical primitive per concept** (de-dup, see below).

## Gaps found empirically + fixes

| # | Real-world input | Symptom | Root cause | Fix |
|---|------------------|---------|-----------|-----|
| 1 | Image-only PDF (jsPDF screen capture; phone scans) | `extract` → `ok=False`, "could not read" | `_pdf` degrade chain was `pdftotext → pymupdf → ""` — no image-render tier | New tier: render pages (`pdftoppm`) → OCR via the canonical port. A 20MB/12-page capture now yields ~full text in ~7s |
| 2 | The canonical OCR port itself | OCR was **tesseract-only**; with no tesseract the whole OCR path was dead (images AND image-only PDFs) | `_ocr_image_bytes`/`handle()` assumed "OCR == tesseract" | Generalized to a resolver chain **tesseract → macOS Vision**; `_ocr_available()` gates routing. One port, every caller |
| 3 | `.docx` / `.xlsx` / `.pptx` | `ok=False` (markitdown not installed) | `_office` was markitdown-only | Added stdlib `zipfile` fallback tier (`_zip_doc_text`): word/document.xml, xl/sharedStrings.xml, ppt/slides. Works with zero deps |
| 4 | `.epub` | `ok=True` returning **raw ZIP binary garbage** (`PK\x03\x04…`) — a false positive, worse than honest failure | epub fell to the HTML branch which read raw bytes | Routed epub through `_zip_doc_text` (OPS xhtml chapters). Real book text now |
| 5 | `https://arxiv.org/pdf/1706.03762` | `ok=False`, empty | `_ext_of` parsed the path suffix as `.03762` (not `.pdf`) → misrouted to HTML | Magic-byte sniff (`%PDF`) for URL targets whose path signals PDF. arxiv/DOI/`/download/<n>` PDFs now extract |
| 6 | Direct image files (`.png`/`.jpg`) | `ok=True` returning **raw image bytes as "text"** (binary garbage) | `extract()` had no image branch | New image branch → OCR via the **same** canonical port; honest `ok=False` when no OCR backend |

## Canonicalization (de-dup) — one primitive per concept
- **OCR:** `_ocr_image_bytes` (`lgwks_input`) is the single entry point. PDF render
  (`_pdf_render_ocr`), direct images (`extract` image branch), and input items all
  route through it. `_vision_*`/`_tesseract_available` are internal to the resolver.
- **Office/zip docs:** `_zip_doc_text` (`lgwks_extract`) is the single primitive; both
  `_office` (extract path) and `_try_doc_text` (input path) call it. Removed the
  hidden `python-docx` dependency assumption.
- **PDF text:** `_pdf` (`lgwks_extract`) is canonical; `_try_pdf_text` (input) calls it.

## Verified real-world corpus (post-fix, `lgwks extract --json`)
academic PDF → ok/pdf · phone-scan PDF → ok/pdf (OCR) · docx → ok/office · xlsx →
ok/office · epub → ok/epub · code `.py` → ok/text · json → ok/text · arxiv PDF URL →
ok/pdf · example.com → ok/html · empty file → **ok=False (honest)**.

## Test coverage added
`tests/test_realworld_extract_convert.py` (37 cases): type matrix (API), OCR tier
(mocked routing + real-backend gated), zip-doc office/epub (portable stdlib fixtures),
PDF-URL sniff (mocked), image branch, and the real `lgwks extract`/`convert`
subprocess (exit codes + stdout/stderr). `tests/test_input_handler.py` A14 retargeted
from `_tesseract_available` → `_ocr_available` (invariant preserved: OCR_IMAGE iff an
OCR backend is reachable; the old "OCR == tesseract" assumption was the bug).

## Out of scope / follow-ups (noted, not done)
- **General binary-file guard:** an unknown binary (e.g. `.mp4`/`.zip`/`.exe`) still
  hits the HTML/local branch and may surface as `ok=True` text. A `_looks_text` guard
  was considered but rejected — it false-negatives on non-ASCII (CJK) text files, an
  i18n regression not worth the risk here. Needs its own design.
- **PDF→image render consolidation:** `lgwks_multimodal.extract_pdf_page_image` (fitz,
  for the VL-*embedding* subsystem) overlaps conceptually with `_pdf_render_ocr`
  (poppler, for OCR). Different subsystem/renderer/purpose — left intact.
- **Pre-existing `tests/test_graph_viz.py::test_home_quick_v_launches_viz`** fails on
  `origin/main` (passes on `feat/tui-scaffold`). Unrelated to this PR (viz assertion,
  not an import error); not touched.

## Reproduce
```
git worktree add .worktrees/x -b fix/extract-realworld-evals origin/main
LGWKS_CACHE_DIR=/tmp/lgwks-ocr python3 ./lgwks extract <image-only.pdf>      # was empty → now text
python3 ./lgwks extract ~/walkme/Transfers_Quadrus.docx                       # was ok=False → now text
python3 ./lgwks extract https://arxiv.org/pdf/1706.03762                      # was empty → now text
python3 -m pytest tests/test_realworld_extract_convert.py -q                 # 37 passed
```
