---
phase: 14-cross-file-batching
plan: 02
subsystem: pipeline
tags: [surya, batch-processing, cross-file, fitz, pdf-manipulation]

# Dependency graph
requires:
  - phase: 14-cross-file-batching
    plan: 01
    provides: FlaggedPage dataclass, batch size configuration, memory detection
provides:
  - collect_flagged_pages() for aggregating flagged pages across files
  - create_combined_pdf() for single-batch PDF creation
  - split_markdown_by_pages() for per-page text splitting
  - map_results_to_files() for result mapping back to source files
  - Cross-file batched Surya processing in pipeline
affects: [14-03, pipeline-performance, model-loading-optimization]

# Tech tracking
tech-stack:
  added: []
  patterns: [cross-file-batching, combined-pdf-processing, heuristic-text-splitting]

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/batch.py
    - src/scholardoc_ocr/pipeline.py
    - tests/test_batch.py
    - tests/test_pipeline.py

key-decisions:
  - "Horizontal rule + triple newline heuristics for page splitting: Marker lacks explicit page markers"
  - "batch_index sequential assignment: enables direct mapping from combined PDF back to sources"
  - "Single Surya call per batch: N files with flagged pages -> 1 Surya invocation"
  - "Cleanup per batch not per file: GPU memory freed once after entire batch completes"
  - "Empty combined PDF skipped: PyMuPDF cannot save empty documents"

patterns-established:
  - "Cross-file page collection: aggregate flagged pages with origin tracking"
  - "Combined PDF batch processing: create temp PDF, process, map results, cleanup"
  - "Heuristic text splitting: try multiple separators, fallback to first-page assignment"

# Metrics
duration: 6min
completed: 2026-02-05
---

# Phase 14 Plan 02: Cross-file Page Batching Summary

**Cross-file batching implementation: N files with flagged pages processed in single Surya call via combined PDF**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-05T01:53:12Z
- **Completed:** 2026-02-05T01:59:37Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Extended batch.py with cross-file batching functions (collect_flagged_pages, create_combined_pdf, split_markdown_by_pages, map_results_to_files)
- Replaced per-file Surya loop with single cross-file batch in pipeline.py
- Batch sizes configured before model loading (BATCH-02, BATCH-03)
- Combined PDF created from flagged pages across all files
- Single Surya call processes entire batch, results mapped back to source files
- Added 21 new integration tests for batching functions
- Updated existing pipeline tests to use new cross-file batch mocking pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: Add cross-file batching functions to batch.py** - `7f837ff` (feat)
   - collect_flagged_pages(), create_combined_pdf(), split_markdown_by_pages(), map_results_to_files()
   - 194 lines added

2. **Task 2: Update pipeline.py to use single Surya batch** - `fd98dea` (feat)
   - Replace per-file loop with cross-file batch processing
   - Updated tests to mock convert_pdf_with_fallback

3. **Task 3: Add integration tests for cross-file batching** - `4e92937` (test)
   - 21 new tests: TestSplitMarkdownByPages (7), TestCollectFlaggedPages (6), TestCreateCombinedPdf (3), TestMapResultsToFiles (5)
   - Total batch tests: 41 (20 existing + 21 new)

## Files Modified

- `src/scholardoc_ocr/batch.py` - Cross-file batching functions (354 lines total)
- `src/scholardoc_ocr/pipeline.py` - Single Surya batch processing
- `tests/test_batch.py` - 21 new integration tests
- `tests/test_pipeline.py` - Updated mocks for cross-file batching

## Decisions Made

- **Heuristic text splitting:** Use horizontal rules (---) first, then triple newlines, fallback to first-page assignment
- **batch_index tracking:** Sequential assignment (0,1,2,...) enables direct result mapping
- **Cleanup per batch:** GPU memory freed once after entire cross-file batch, not per file
- **Empty PDF handling:** Skip file creation instead of failing (PyMuPDF limitation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed empty PDF handling in create_combined_pdf**
- **Found during:** Task 3 test execution
- **Issue:** PyMuPDF cannot save empty documents, test failed
- **Fix:** Changed to skip PDF creation and log warning for empty input
- **Files modified:** src/scholardoc_ocr/batch.py
- **Commit:** 4e92937 (included in Task 3)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix)
**Impact on plan:** Minor edge case handling, no scope change

## Issues Encountered

None - plan executed as specified.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Cross-file batching fully implemented and tested
- Pipeline processes N files with flagged pages in single Surya call
- Ready for 14-03: Progress reporting enhancements
- All exports tested: collect_flagged_pages, create_combined_pdf, map_results_to_files, split_markdown_by_pages

---
*Phase: 14-cross-file-batching*
*Completed: 2026-02-05*
