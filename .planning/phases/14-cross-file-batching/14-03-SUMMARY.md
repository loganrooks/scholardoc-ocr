---
phase: 14-cross-file-batching
plan: 03
subsystem: pipeline
tags: [memory-monitoring, adaptive-batching, psutil, mps, gpu-memory]

# Dependency graph
requires:
  - phase: 14-cross-file-batching
    plan: 02
    provides: Cross-file batching infrastructure
provides:
  - check_memory_pressure() for pre-batch memory assessment
  - compute_safe_batch_size() for adaptive batch sizing
  - Memory pressure warnings in pipeline logs
  - surya_batch_pages and surya_batch_files in phase_timings
affects: [pipeline-stability, 8gb-machine-support]

# Tech tracking
tech-stack:
  added: []
  patterns: [memory-pressure-monitoring, conservative-batch-sizing, available-memory-detection]

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/batch.py
    - src/scholardoc_ocr/pipeline.py
    - tests/test_batch.py

key-decisions:
  - "4GB memory pressure threshold: Leaves headroom for OS on 8GB machines"
  - "0.7GB per page estimate: Conservative peak memory during detection + recognition + layout"
  - "50% safety margin: Uses half of available memory to prevent system freezes"
  - "Available not total memory: Accounts for current system load"
  - "Warnings only: Memory pressure logged but batch sizes not auto-reduced"
  - "CPU capped at 32: CPU is more memory-efficient, hard cap for performance"

patterns-established:
  - "Pre-batch memory check: check_memory_pressure() before Surya processing"
  - "Conservative batch sizing: compute_safe_batch_size() with safety margins"
  - "Batch observability: phase_timings includes batch_pages and batch_files"

# Metrics
duration: 7min
completed: 2026-02-05
---

# Phase 14 Plan 03: Adaptive Batch Sizing Summary

**Memory pressure monitoring with conservative batch sizing to prevent system freezes on 8GB machines**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-05T02:05:00Z
- **Completed:** 2026-02-05T02:12:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Added check_memory_pressure() returning (is_constrained, available_gb)
- Added compute_safe_batch_size() for memory-aware batch sizing
- Added BATCH_SIZE_MEMORY_PER_PAGE_GB (0.7GB) and MEMORY_PRESSURE_THRESHOLD_GB (4GB) constants
- Integrated memory pressure check into pipeline before Surya batch
- Added surya_batch_pages and surya_batch_files to phase_timings for observability
- Added 25 new tests for memory monitoring (66 total batch tests)
- All tests passing (79 tests across batch and pipeline)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add memory pressure monitoring to batch.py** - `6bdd251` (feat)
   - check_memory_pressure(), compute_safe_batch_size()
   - BATCH_SIZE_MEMORY_PER_PAGE_GB, MEMORY_PRESSURE_THRESHOLD_GB constants
   - 73 lines added

2. **Task 2: Integrate memory checks into pipeline** - `e3f30a7` (feat)
   - Import and use check_memory_pressure before Surya batch
   - Log warning when memory constrained
   - Add batch info to phase_timings
   - 17 lines added

3. **Task 3: Add comprehensive tests for memory monitoring** - `87dd2fc` (test)
   - TestCheckMemoryPressure: 6 tests
   - TestComputeSafeBatchSize: 14 tests
   - TestBatchIntegration: 3 integration tests
   - 247 lines added

## Files Modified

- `src/scholardoc_ocr/batch.py` - Memory monitoring functions (427 lines total)
- `src/scholardoc_ocr/pipeline.py` - Memory pressure check integration
- `tests/test_batch.py` - 25 new tests (862 lines total)

## Decisions Made

- **4GB threshold:** Conservative to leave headroom on 8GB machines
- **0.7GB per page:** Based on research into Surya memory usage (detection + recognition + layout peak)
- **50% safety margin:** Uses half of available memory for batch sizing
- **Available not total:** Checks available memory to account for other running processes
- **Warnings only:** Logs recommendations but doesn't auto-reduce batch sizes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tasks completed successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Memory pressure monitoring fully implemented and tested
- Pipeline logs warnings when memory constrained
- Batch info recorded in phase_timings for observability
- Phase 14 (Cross-file Batching) now complete
- All BATCH-01 through BATCH-05 requirements satisfied

---
*Phase: 14-cross-file-batching*
*Completed: 2026-02-05*
