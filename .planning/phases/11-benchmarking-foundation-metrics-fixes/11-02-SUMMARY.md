---
phase: 11-benchmarking-foundation-metrics-fixes
plan: 02
subsystem: testing
tags: [pytest-benchmark, memray, mps, apple-silicon, performance]

# Dependency graph
requires:
  - phase: 11-01
    provides: Benchmark infrastructure (fixtures, timing utilities)
provides:
  - Model loading benchmark with pedantic mode and MPS sync
  - OCR inference benchmark with hardware profile grouping
  - Memory limit tests for model loading (2GB) and inference (4GB)
  - pytest-benchmark grouping by hardware_profile for BENCH-05
affects: [11-03, 11-04, 11-05, 13-model-caching]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "benchmark.pedantic() for expensive GPU operations"
    - "@pytest.mark.limit_memory for memray integration"
    - "mps_sync() after GPU operations for accurate timing"

key-files:
  created:
    - tests/benchmarks/test_model_loading.py
    - tests/benchmarks/test_inference.py
    - tests/benchmarks/test_memory.py
  modified:
    - pyproject.toml

key-decisions:
  - "pedantic mode with rounds=3, warmup_rounds=0 for cold-start model loading"
  - "pedantic mode with rounds=5, warmup_rounds=1 for inference (allows warm cache)"
  - "2GB limit for model loading, 4GB for inference (Apple Silicon reasonable bounds)"
  - "benchmark-group-by=param:hardware_profile,func for BENCH-05 hardware baselines"

patterns-established:
  - "Benchmark pattern: use pedantic mode for GPU operations"
  - "Timing pattern: call mps_sync() after GPU work before timing stops"
  - "Memory pattern: use @pytest.mark.limit_memory with memray"

# Metrics
duration: 5min
completed: 2026-02-03
---

# Phase 11 Plan 02: Benchmark Tests Summary

**Benchmark tests for model loading, inference, and memory with hardware profile grouping for BENCH-05 baselines**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-03T23:32:00Z
- **Completed:** 2026-02-03T23:37:35Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Model loading benchmark using pedantic mode with MPS sync for accurate GPU timing
- Inference benchmark with pre-loaded models and hardware profile grouping
- Memory limit tests validating reasonable Apple Silicon memory bounds
- pytest-benchmark configuration for hardware-specific baseline comparisons (BENCH-05)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create model loading benchmark with hardware profile grouping** - `e4671a7` (feat)
2. **Task 2: Create inference and memory benchmarks** - `481252c` (feat)

## Files Created/Modified

- `tests/benchmarks/test_model_loading.py` - Cold-start model loading benchmark with pedantic mode
- `tests/benchmarks/test_inference.py` - Single-page inference benchmark with MPS sync
- `tests/benchmarks/test_memory.py` - Memory limit tests using @pytest.mark.limit_memory
- `pyproject.toml` - Added benchmark grouping config (--benchmark-group-by=param:hardware_profile,func)

## Decisions Made

- **Pedantic mode parameters:** rounds=3/warmup=0 for model loading (true cold start), rounds=5/warmup=1 for inference (allows warm cache)
- **Memory limits:** 2GB for model loading, 4GB for inference - reasonable for Apple Silicon devices
- **Grouping config:** Combined param:hardware_profile with func for granular baseline comparison

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Minor:** `benchmark_min_rounds` config option not recognized by pytest-benchmark; resolved by using `--benchmark-min-rounds=3` in addopts instead

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Benchmark tests ready for execution
- All tests skip gracefully if Surya not installed (CI compatibility)
- Hardware profile grouping enables BENCH-05 hardware-specific baselines
- Memory tests ready for memray integration (pytest --memray)

---
*Phase: 11-benchmarking-foundation-metrics-fixes*
*Completed: 2026-02-03*
