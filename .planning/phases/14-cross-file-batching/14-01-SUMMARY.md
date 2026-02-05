---
phase: 14-cross-file-batching
plan: 01
subsystem: pipeline
tags: [surya, batch-processing, memory-detection, psutil, environment-variables]

# Dependency graph
requires:
  - phase: 13-model-caching
    provides: Model loading infrastructure, lazy torch imports pattern
provides:
  - FlaggedPage dataclass for cross-file page origin tracking
  - get_available_memory_gb() for memory detection (system/CUDA)
  - configure_surya_batch_sizes() for hardware-aware batch sizing
affects: [14-02, 14-03, batched-surya, pipeline-integration]

# Tech tracking
tech-stack:
  added: [psutil]
  patterns: [memory-tier-based-configuration, env-var-setdefault-pattern]

key-files:
  created:
    - src/scholardoc_ocr/batch.py
    - tests/test_batch.py
  modified:
    - pyproject.toml

key-decisions:
  - "psutil for system memory detection: cross-platform, lightweight, already common"
  - "Lazy torch import for CUDA VRAM: avoids ML deps at module import time"
  - "setdefault pattern: allows user env var overrides without code changes"
  - "Memory tier boundaries: 8GB, 16GB, 32GB+ for batch size selection"

patterns-established:
  - "Memory-tier configuration: detect memory, select tier, configure batch sizes"
  - "FlaggedPage origin tracking: dataclass links batch pages back to source files"

# Metrics
duration: 3min
completed: 2026-02-05
---

# Phase 14 Plan 01: Batch Configuration Infrastructure Summary

**Hardware-aware Surya batch size configuration with psutil memory detection and FlaggedPage dataclass for cross-file page tracking**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-05T01:46:39Z
- **Completed:** 2026-02-05T01:49:46Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created batch.py module with FlaggedPage dataclass for tracking page origins across files
- Implemented get_available_memory_gb() with system memory (psutil) and CUDA VRAM detection
- Implemented configure_surya_batch_sizes() with hardware-aware batch size tiers
- Added 20 comprehensive unit tests covering all memory tiers and device types
- Maintained lazy torch import pattern to avoid loading ML deps at module import time

## Task Commits

Each task was committed atomically:

1. **Task 1: Create batch.py module with batch configuration** - `6549206` (feat)
2. **Task 2: Create unit tests for batch configuration** - `106cb8a` (test)

## Files Created/Modified
- `src/scholardoc_ocr/batch.py` - FlaggedPage dataclass, memory detection, batch size configuration
- `tests/test_batch.py` - 20 unit tests for batch configuration
- `pyproject.toml` - Added psutil>=5.9.0 dependency

## Decisions Made
- **psutil for memory detection:** Cross-platform, lightweight, already common in Python ecosystem
- **Memory tier boundaries:** 8GB (conservative), 16GB (moderate), 32GB+ (aggressive) - matches research findings
- **setdefault pattern:** Allows users to override batch sizes via env vars without code changes
- **Lazy torch import:** Only imports torch when checking CUDA VRAM, following established pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added psutil dependency to pyproject.toml**
- **Found during:** Task 1 (batch.py creation)
- **Issue:** psutil package not listed in dependencies, import failing
- **Fix:** Added `psutil>=5.9.0` to pyproject.toml dependencies
- **Files modified:** pyproject.toml
- **Verification:** Import succeeds, tests pass
- **Committed in:** 6549206 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking)
**Impact on plan:** Essential for memory detection functionality. No scope creep.

## Issues Encountered
None - plan executed as specified after adding missing dependency.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- batch.py module ready for integration in 14-02 (batch collection)
- FlaggedPage dataclass ready for cross-file page tracking
- configure_surya_batch_sizes() ready to be called before marker imports
- All exports tested: configure_surya_batch_sizes, get_available_memory_gb, FlaggedPage

---
*Phase: 14-cross-file-batching*
*Completed: 2026-02-05*
