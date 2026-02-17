---
phase: 15-diagnostic-infrastructure
plan: 01
subsystem: diagnostics
tags: [dataclass, diagnostic-model, signal-analysis, pickling]
requires:
  - phase: 14-cross-file-batching
    provides: stable PageResult, QualityResult, and pipeline types
provides:
  - PageDiagnostics dataclass with always-captured and diagnostics-gated fields
  - SignalDisagreement and EngineDiff structured sub-data types
  - compute_signal_disagreements for pairwise signal analysis
  - classify_struggle with 8 independent boolean detection rules
  - compute_engine_diff using difflib.SequenceMatcher word-level diff
  - build_always_diagnostics to extract diagnostics from QualityResult
  - PageResult.diagnostics optional field for pipeline integration
affects: [pipeline, batch, types, quality]
tech-stack:
  added: []
  patterns: [TYPE_CHECKING conditional import, primitive-only dataclasses for pickling, two-tier diagnostic gating]
key-files:
  created:
    - src/scholardoc_ocr/diagnostics.py
  modified:
    - src/scholardoc_ocr/types.py
key-decisions:
  - "Use TYPE_CHECKING import in both diagnostics.py and types.py to avoid circular imports"
  - "All dataclass fields use only primitives (float, int, str, bool, list, dict, None) for ProcessPoolExecutor pickling safety"
  - "Signal disagreement stores all pairs, not just those above threshold, for downstream flexibility"
  - "Struggle category thresholds are conservative (under-report), Phase 19 will calibrate"
patterns-established:
  - "Diagnostic data attachment: Optional field on PageResult with None default for backward compatibility"
  - "Two-tier gating: always-captured fields are non-optional, diagnostics-gated fields default to None"
  - "Conditional to_dict: gated fields only serialized when non-None"
duration: 3min
completed: 2026-02-17
---

# Phase 15 Plan 01: Diagnostic Data Model Summary

**PageDiagnostics, SignalDisagreement, and EngineDiff dataclasses with signal disagreement detection, struggle classification, engine diffing, and QualityResult integration -- all pickle-safe for ProcessPoolExecutor transport**

## Performance
- **Duration:** 3 minutes
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Created diagnostics.py module with 3 dataclasses and 4 utility functions as the diagnostic data foundation
- Integrated PageDiagnostics into PageResult via Optional field with full backward compatibility (253 existing tests pass unchanged)
- Verified pickle roundtrip at 417 bytes per page for always-on diagnostics
- Implemented all 8 struggle category detection rules with conservative thresholds

## Task Commits
1. **Task 1: Create diagnostics.py with all dataclasses and utility functions** - `0cb484a`
2. **Task 2: Add Optional[PageDiagnostics] field to PageResult in types.py** - `c4b066e`

## Files Created/Modified
- `src/scholardoc_ocr/diagnostics.py` - New module: PageDiagnostics, SignalDisagreement, EngineDiff dataclasses; compute_signal_disagreements, classify_struggle, compute_engine_diff, build_always_diagnostics utility functions
- `src/scholardoc_ocr/types.py` - Added diagnostics field to PageResult, updated to_dict() for conditional diagnostic serialization

## Decisions & Deviations
None - plan executed exactly as written.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Plans 02 and 03 can now wire diagnostic data through the pipeline:
- Plan 02 can use build_always_diagnostics() to attach diagnostics in _tesseract_worker
- Plan 03 can use compute_engine_diff() for Tesseract-vs-Surya comparison and image quality metrics
- PageResult.diagnostics field is ready to receive data from any pipeline stage

## Self-Check: PASSED
