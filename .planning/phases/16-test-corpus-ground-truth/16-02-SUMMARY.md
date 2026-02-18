---
phase: 16-test-corpus-ground-truth
plan: 02
subsystem: test-corpus
tags: [ground-truth, diagnostics, coverage-matrix, page-selection]
requires:
  - phase: 16-01
    provides: "Corpus directory structure, manifest, helper scripts"
provides:
  - Baseline diagnostic data for all 4 corpus documents
  - Coverage matrix analysis identifying struggle categories across corpus
  - Coverage-based page selection (28 difficult + 20 regression = 48 pages)
  - 300 DPI PNG renderings of all 48 selected pages for Opus transcription
  - Fully populated manifest with page counts, diagnostic summaries, baseline metadata
affects: [16-03-ground-truth-creation]
tech-stack:
  added: []
  patterns: [coverage-based-sampling, cross-document-diversity]
key-files:
  created:
    - tests/corpus/page_selection.json
    - tests/corpus/baselines/*/final/*.diagnostics.json
    - tests/corpus/baselines/*/final/*.txt
    - tests/corpus/baselines/*/final/*.json
  modified:
    - tests/corpus/corpus.json
    - scripts/corpus/build_coverage_matrix.py
key-decisions:
  - "Sample gray_zone and signal_disagreement pages with cross-document diversity instead of including all (1225 gray_zone pages would be unmanageable)"
  - "48 total selected pages (28 difficult + 20 regression) balances coverage with transcription effort"
  - "All 4 struggle categories covered: gray_zone, signal_disagreement, vocabulary_miss, surya_insufficient"
patterns-established:
  - "Cross-document sampling: evenly distribute selected pages across documents for diversity"
  - "Coverage-capped selection: high-prevalence categories are sampled, not exhaustively included"
duration: 3min
completed: 2026-02-18
---

# Phase 16 Plan 02: Diagnostic Baselines and Coverage Analysis Summary

**Coverage matrix analysis across 1478 pages in 4 documents, selecting 48 pages (28 difficult + 20 regression) covering all 4 detected struggle categories for ground truth creation**

## Performance
- **Duration:** 3 minutes (Task 2 only; Task 1 was user-executed baseline capture)
- **Tasks:** 2 (1 checkpoint + 1 auto)
- **Files modified:** 15

## Accomplishments
- User captured diagnostic baselines for all 4 corpus documents (267 + 452 + 359 + 400 = 1478 total pages)
- Fixed coverage matrix script to sample high-prevalence categories instead of including all (1225 gray_zone pages reduced to 16 sampled)
- Coverage analysis identified 4 struggle categories: gray_zone (1225 pages), signal_disagreement (60), vocabulary_miss (25), surya_insufficient (1)
- Selected 28 difficult pages covering all 4 categories with cross-document diversity
- Selected 20 regression pages (clean, quality > 0.90) spanning front matter, ToC, body, and end matter
- Rendered all 48 selected pages as 300 DPI PNGs ready for Opus transcription
- Updated corpus manifest with actual page counts, diagnostic summaries, baseline metadata, and page selections

## Corpus Diagnostic Overview

| Document | Pages | Flagged | Quality Range | Top Struggles |
|----------|-------|---------|---------------|---------------|
| simondon-technical-objects | 267 | 14 (5.2%) | 0.675 - 1.000 | gray_zone, signal_disagreement, vocabulary_miss |
| derrida-grammatology | 452 | 5 (1.1%) | 0.789 - 1.000 | gray_zone, signal_disagreement, vocabulary_miss |
| derrida-margins | 359 | 1 (0.3%) | 0.828 - 1.000 | gray_zone, signal_disagreement, surya_insufficient |
| derrida-dissemination | 400 | 117 (29.3%) | 0.679 - 1.000 | gray_zone, signal_disagreement, vocabulary_miss |

## Page Selection Summary

**Difficult (28 pages):**
- simondon-technical-objects: 7 pages [0, 1, 64, 83, 100, 141, 204]
- derrida-grammatology: 7 pages [0, 3, 100, 185, 194, 334, 446]
- derrida-margins: 8 pages [0, 2, 29, 102, 191, 203, 235, 270]
- derrida-dissemination: 6 pages [0, 24, 93, 104, 200, 299]

**Regression (20 pages):**
- simondon-technical-objects: 4 pages [3, 72, 91, 98]
- derrida-grammatology: 6 pages [2, 8, 158, 243, 286, 451]
- derrida-margins: 5 pages [4, 94, 149, 182, 356]
- derrida-dissemination: 5 pages [1, 179, 187, 206, 399]

## Task Commits
1. **Task 1: Create PDF symlinks and run diagnostic baselines** - user action (no commit)
2. **Task 2: Coverage analysis, page selection, PNG rendering, manifest update** - `14aee56`

## Files Created/Modified
- `tests/corpus/corpus.json` - Updated with page counts, diagnostic summaries, baseline metadata, selected_pages
- `tests/corpus/page_selection.json` - Machine-readable page selection (difficult + regression)
- `scripts/corpus/build_coverage_matrix.py` - Fixed to sample high-prevalence categories
- `tests/corpus/baselines/*/final/*.diagnostics.json` - Per-page diagnostic sidecars (4 files)
- `tests/corpus/baselines/*/final/*.txt` - Full OCR text output (4 files)
- `tests/corpus/baselines/*/final/*.json` - Pipeline metadata (4 files)
- `tests/corpus/images/*/page_*.png` - 48 page PNGs at 300 DPI (gitignored, regenerable)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed coverage matrix selecting all gray_zone/disagreement pages**
- **Found during:** Task 2, Step 2 (coverage matrix analysis)
- **Issue:** `select_difficult_pages()` added ALL gray_zone (1225) and signal_disagreement (58) pages to the difficult set, producing ~1280 pages instead of the target 40-50
- **Fix:** Added `_sample_cross_document()` helper that distributes page selection evenly across documents with configurable caps (max_gray_zone=16, max_disagreement=12, max_per_category=4)
- **Files modified:** `scripts/corpus/build_coverage_matrix.py`
- **Commit:** `14aee56`

### Observations

- Simondon document language was already corrected to ["en"] in corpus.json by user (English translation by Malaspina)
- A recurring IndexError in batch.py:470 during Surya processing affected 3 of 4 baseline runs but pipeline recovered each time (known edge case, not a blocker for this plan)
- derrida-dissemination has notably high flagged percentage (29.3%) compared to other documents, making it valuable for threshold calibration

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Corpus is ready for Plan 03 (Ground Truth Creation). 48 pages have been selected and rendered as 300 DPI PNGs. Plan 03 will use Opus vision to transcribe these pages, creating ground truth text that enables automated quality evaluation.

## Self-Check: PASSED
- All 11 key files verified present on disk
- Commit 14aee56 verified in git log
- 48 PNG files rendered across 4 document directories
