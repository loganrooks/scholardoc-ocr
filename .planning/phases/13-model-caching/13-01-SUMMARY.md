---
phase: 13-model-caching
plan: 01
subsystem: caching
tags: [cachetools, ttl-cache, singleton, thread-safety, gpu-memory, mps, cuda]

# Dependency graph
requires:
  - phase: 12-device-configuration
    provides: "load_models() returns tuple (model_dict, device_str)"
provides:
  - ModelCache singleton with TTL-based caching
  - cleanup_between_documents() for inter-document memory cleanup
  - get_memory_stats() for GPU memory monitoring
affects: [13-model-caching, mcp-server, pipeline]

# Tech tracking
tech-stack:
  added: [cachetools>=5.0.0]
  patterns: [double-checked-locking-singleton, cache-aside-pattern, lazy-torch-imports]

key-files:
  created:
    - src/scholardoc_ocr/model_cache.py
    - tests/test_model_cache.py
  modified:
    - pyproject.toml

key-decisions:
  - "TTLCache with maxsize=1 - only one model set cached at a time"
  - "30 minute default TTL - balance between memory and reload frequency"
  - "SCHOLARDOC_MODEL_TTL env var for runtime override without code change"
  - "Load outside lock pattern - prevents blocking on slow model loads"

patterns-established:
  - "Double-checked locking for singleton: check, lock, check again"
  - "Cache-aside: check cache, load if miss, store result"
  - "Lazy torch imports in all GPU-related functions"

# Metrics
duration: 4min
completed: 2026-02-05
---

# Phase 13 Plan 01: Model Cache Module Summary

**Thread-safe ModelCache singleton with TTLCache backend, configurable 30-minute expiration, GPU cleanup utilities, and 24 unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-05T00:40:06Z
- **Completed:** 2026-02-05T00:44:24Z
- **Tasks:** 3/3
- **Files modified:** 3

## Accomplishments

- Created ModelCache class with double-checked locking singleton pattern
- Implemented TTLCache with configurable TTL (default 1800s, env var override)
- Added cleanup_between_documents() for GPU memory cleanup without cache eviction
- Added get_memory_stats() for MPS/CUDA memory monitoring
- 24 unit tests covering singleton, caching, TTL, eviction, thread safety, and utilities

## Task Commits

Each task was committed atomically:

1. **Task 1: Add cachetools dependency** - `e89525f` (chore)
2. **Task 2: Create model_cache.py module** - `ac20fe0` (feat)
3. **Task 3: Create unit tests for model_cache** - `887a313` (test)

## Files Created/Modified

- `pyproject.toml` - Added cachetools>=5.0.0 dependency
- `src/scholardoc_ocr/model_cache.py` - ModelCache singleton, cleanup_between_documents(), get_memory_stats() (248 lines)
- `tests/test_model_cache.py` - 24 comprehensive unit tests (362 lines)

## Decisions Made

- **TTLCache maxsize=1:** Only one model set cached at a time - Surya models are too large to cache multiple versions
- **30 minute default TTL:** Based on typical MCP session patterns - long enough to avoid reloads during active use, short enough to free memory when idle
- **Environment variable override (SCHOLARDOC_MODEL_TTL):** Allows runtime tuning without code changes, useful for different deployment scenarios
- **Load outside lock pattern:** Model loading takes 30-60 seconds; holding lock during load would block all threads

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Mock fixture needed adjustment: `patch("scholardoc_ocr.model_cache.surya")` failed because surya is imported lazily inside get_models(). Fixed by patching `patch("scholardoc_ocr.surya.load_models")` directly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ModelCache ready for integration into pipeline and MCP server
- Plan 02 will integrate ModelCache into pipeline.py for batch processing
- Plan 03 will expose cache control via MCP server tools

---
*Phase: 13-model-caching*
*Completed: 2026-02-05*
