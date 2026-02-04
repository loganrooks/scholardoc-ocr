---
phase: 12-device-configuration
plan: 04
subsystem: cli
tags: [gpu, mps, cuda, device-detection, cli-flags, startup-diagnostics]

# Dependency graph
requires:
  - phase: 12-device-configuration
    provides: Device detection module (12-01), FileResult.device_used field (12-02)
provides:
  - check_gpu_availability() function with actionable error messages
  - --strict-gpu CLI flag for disabling CPU fallback
  - PipelineConfig.strict_gpu field for inference-time enforcement
  - Verbose startup GPU status display
affects: [12-05, cli-output, user-experience]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Actionable error messages pattern: Return (bool, str) tuple with status and explanation"
    - "Lazy torch import in check_gpu_availability for startup performance"

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/environment.py
    - src/scholardoc_ocr/cli.py
    - src/scholardoc_ocr/pipeline.py
    - tests/test_device.py

key-decisions:
  - "check_gpu_availability() uses lazy torch import to avoid loading ML dependencies at startup"
  - "GPU status logged via existing log_startup_diagnostics() for consistency"
  - "strict_gpu NOT enforced at model load - only at inference time in 12-05"
  - "Verbose mode shows GPU status via Rich console for user visibility"

patterns-established:
  - "Actionable status messages: Always explain why something is available/unavailable and what to do about it"
  - "CLI flag propagation: Add CLI arg -> add to PipelineConfig -> use in processing module"

# Metrics
duration: 3min
completed: 2026-02-04
---

# Phase 12 Plan 04: CLI Device Control Summary

**CLI --strict-gpu flag with startup GPU validation and actionable MPS/CUDA status messages**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-04
- **Completed:** 2026-02-04
- **Tasks:** 3/3
- **Files modified:** 4

## Accomplishments

- Added check_gpu_availability() function with actionable status messages for CUDA, MPS, and CPU
- Implemented --strict-gpu CLI flag to disable CPU fallback behavior
- Added PipelineConfig.strict_gpu field for propagation to inference
- Verbose startup shows GPU status via Rich console
- Comprehensive test coverage for GPU availability, strict_gpu config, and CLI flag

## Task Commits

Each task was committed atomically:

1. **Task 1: Add MPS validation to environment.py** - `641b14e` (feat)
2. **Task 2: Add --strict-gpu flag to CLI and PipelineConfig** - `87d0f87` (feat)
3. **Task 3: Add integration test for device startup** - `0cc1503` (test)

## Files Created/Modified

- `src/scholardoc_ocr/environment.py` - Added check_gpu_availability() with actionable messages, GPU logging in startup diagnostics
- `src/scholardoc_ocr/cli.py` - Added --strict-gpu argument, verbose GPU status display
- `src/scholardoc_ocr/pipeline.py` - Added strict_gpu field to PipelineConfig dataclass
- `tests/test_device.py` - Added 6 new tests for GPU availability and strict_gpu integration

## Decisions Made

- **Lazy torch import:** check_gpu_availability() imports torch inside the function to avoid loading ML dependencies unless needed
- **strict_gpu enforcement deferred:** The flag is stored in config but NOT enforced at model load time - enforcement happens at inference time in plan 12-05's convert_pdf_with_fallback()
- **Actionable messages:** Each GPU status message explains what's available and why (e.g., "MPS built but not available (macOS < 12.3 or no GPU)")

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pytest not initially installed in system Python environment; resolved with pip install --break-system-packages
- Pre-existing uncommitted work found in surya.py (from interrupted 12-05 work); excluded from this plan's commits

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- strict_gpu config ready for 12-05 to implement fallback enforcement in convert_pdf_with_fallback()
- DEV-02 requirements met (startup validation with actionable messages)
- GPU status visibility available in verbose mode for user debugging

---
*Phase: 12-device-configuration*
*Completed: 2026-02-04*
