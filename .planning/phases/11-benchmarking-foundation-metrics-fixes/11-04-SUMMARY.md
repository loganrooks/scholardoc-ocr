---
phase: 11-benchmarking-foundation-metrics-fixes
plan: 04
subsystem: pipeline
tags: [timing, mps, surya, metrics, quality-analysis]

# Dependency graph
requires:
  - phase: 11-03
    provides: compute_engine_from_pages function, mps_sync timing utilities
provides:
  - Surya timing capture (model load + inference) in phase_timings
  - Engine field computed from per-page engines (MIXED when appropriate)
  - Quality re-evaluation after Surya enhancement
affects: [11-05, 11-06, benchmarking, performance-analysis]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - MPS synchronization before timing measurements
    - Per-file timing in phase_timings dict
    - Engine aggregation from page-level engines

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/pipeline.py
    - tests/test_pipeline.py

key-decisions:
  - "MPS sync after surya.load_models() and surya.convert_pdf() for accurate GPU timing"
  - "Store surya_model_load in all files that used Surya (shared model load cost)"
  - "Quality re-evaluation uses same QualityAnalyzer class as initial analysis"
  - "Fallback to engine-only update if text file doesn't exist after Surya"

patterns-established:
  - "Pattern: Always call mps_sync() before measuring GPU operation duration"
  - "Pattern: Store per-file timing in phase_timings dict with descriptive keys"
  - "Pattern: Recompute aggregates (engine, quality) at end of Surya phase"

# Metrics
duration: 3min
completed: 2026-02-03
---

# Phase 11 Plan 04: Metrics Fixes Summary

**Fixed pipeline to capture Surya timing with MPS sync, compute engine from pages, and re-evaluate quality after Surya enhancement (BENCH-06, BENCH-07, BENCH-08)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-03T23:36:54Z
- **Completed:** 2026-02-03T23:39:52Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Surya model load time captured with MPS synchronization (BENCH-06)
- Surya inference time captured per-file with MPS synchronization (BENCH-06)
- Engine field recomputed from per-page engines after Surya phase - returns MIXED when appropriate (BENCH-07)
- Quality scores re-evaluated after Surya enhancement using QualityAnalyzer (BENCH-08)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Surya timing capture (BENCH-06)** - `a6c31b5` (feat)
2. **Task 2: Fix engine field and quality re-evaluation (BENCH-07, BENCH-08)** - `687c49b` (feat)
3. **Task 3: Add tests for metrics fixes** - `2b40f4b` (test)

## Files Created/Modified
- `src/scholardoc_ocr/pipeline.py` - Added MPS sync timing, quality re-evaluation, engine aggregation
- `tests/test_pipeline.py` - Added TestMetricsFixes class with unit tests

## Decisions Made
- Import QualityAnalyzer locally inside Surya loop (not at top level) to avoid redefinition with worker function imports
- Use simple page split by "\n\n" for Surya text extraction (consistent with existing approach)
- Fallback to engine-only update if text file doesn't exist (graceful degradation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import structure adjustment**
- **Found during:** Task 2 (Import modifications)
- **Issue:** Plan specified importing PDFProcessor and QualityAnalyzer at top of file, but this caused ruff lint errors (F401 unused import, F811 redefinition)
- **Fix:** Removed PDFProcessor import (not needed), added QualityAnalyzer import locally inside the Surya loop instead
- **Files modified:** src/scholardoc_ocr/pipeline.py
- **Verification:** ruff check passes, all tests pass
- **Committed in:** 687c49b (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix was necessary for lint compliance. No scope creep.

## Issues Encountered
None - execution proceeded smoothly after import structure adjustment.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline now captures accurate Surya timing for benchmarking
- Engine field correctly reflects MIXED when Tesseract and Surya used together
- Quality scores accurate for post-Surya analysis
- Ready for benchmark analysis tools in 11-05

---
*Phase: 11-benchmarking-foundation-metrics-fixes*
*Completed: 2026-02-03*
