---
phase: 11-benchmarking-foundation-metrics-fixes
plan: 01
subsystem: testing
tags: [pytest-benchmark, pytest-memray, memray, apple-silicon, mps, timing]

# Dependency graph
requires: []
provides:
  - pytest-benchmark and pytest-memray dev dependencies
  - get_hardware_profile() for M1/M2/M3/M4 detection
  - mps_timed() context manager for GPU-synchronized timing
  - benchmark fixtures (hardware_profile, loaded_models, sample_pdf)
affects: [11-02, 11-03, 11-04, 12-device-config, 13-model-caching, 14-batching]

# Tech tracking
tech-stack:
  added: [pytest-benchmark>=5.0, pytest-memray>=1.0, memray>=1.0]
  patterns: [lazy torch imports, session-scoped fixtures, MPS synchronization]

key-files:
  created:
    - src/scholardoc_ocr/timing.py
    - tests/benchmarks/__init__.py
    - tests/benchmarks/conftest.py
  modified:
    - pyproject.toml

key-decisions:
  - "Lazy torch imports to avoid loading ML dependencies at import time"
  - "Session-scoped fixtures for model loading to minimize benchmark overhead"
  - "Use sysctl for Apple Silicon detection (reliable, no external deps)"

patterns-established:
  - "MPS sync before timing measurement for accurate GPU timing"
  - "Session-scoped model fixtures for benchmark reuse"
  - "Programmatic PDF generation with PyMuPDF for test fixtures"

# Metrics
duration: 3min
completed: 2026-02-03
---

# Phase 11 Plan 01: Benchmark Infrastructure Summary

**pytest-benchmark/memray dependencies with Apple Silicon detection and MPS-synchronized timing utilities**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-03T23:29:42Z
- **Completed:** 2026-02-03T23:32:13Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added pytest-benchmark, pytest-memray, and memray to dev dependencies
- Created timing.py with get_hardware_profile() detecting M1/M2/M3/M4
- Created mps_timed() context manager for GPU-synchronized timing
- Created benchmark fixtures with session-scoped model loading

## Task Commits

Each task was committed atomically:

1. **Task 1: Add benchmark dependencies and timing module** - `55abb81` (feat)
2. **Task 2: Create benchmark test fixtures** - `0027299` (feat)

## Files Created/Modified
- `pyproject.toml` - Added pytest-benchmark>=5.0, pytest-memray>=1.0, memray>=1.0 to dev deps
- `src/scholardoc_ocr/timing.py` - Hardware detection and MPS-aware timing utilities
- `tests/benchmarks/__init__.py` - Benchmark test package marker
- `tests/benchmarks/conftest.py` - Session fixtures for hardware, models, sample PDFs

## Decisions Made
- Used lazy torch imports inside function bodies to avoid loading heavy ML deps at module import
- Session-scoped fixtures for loaded_models to share across entire test session
- Used subprocess/sysctl for Apple Silicon detection (works without torch)
- Added multi_page_pdf fixture beyond plan for batch processing benchmarks

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added multi_page_pdf fixture**
- **Found during:** Task 2
- **Issue:** Plan only specified sample_pdf, but batch benchmarks need multi-page content
- **Fix:** Added multi_page_pdf fixture generating 5-page PDF with varied content
- **Files modified:** tests/benchmarks/conftest.py
- **Verification:** pytest --fixtures shows both fixtures
- **Committed in:** 0027299 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Addition completes fixture set for future batch processing benchmarks. No scope creep.

## Issues Encountered
None - execution was straightforward.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Benchmark infrastructure complete
- Ready for 11-02 (metric tests) and 11-03 (result serialization)
- Hardware profile returns "M4" on current machine
- All benchmark fixtures available and tested

---
*Phase: 11-benchmarking-foundation-metrics-fixes*
*Completed: 2026-02-03*
