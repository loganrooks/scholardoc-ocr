---
phase: 15-diagnostic-infrastructure
plan: 02
subsystem: diagnostics
tags: [pipeline-wiring, postprocess-counters, signal-breakdown, diagnostics]
requires:
  - phase: 15-01
    provides: PageDiagnostics dataclass, build_always_diagnostics, classify_struggle
provides:
  - Postprocess functions with optional counter tracking (dehyphenations, paragraph_joins, unicode_normalizations, punctuation_fixes)
  - Pipeline wiring that attaches PageDiagnostics to every PageResult from _tesseract_worker
  - Surya phase diagnostics update with struggle category reclassification
affects: [pipeline, postprocess, diagnostics]
tech-stack:
  added: []
  patterns: [optional counter dict as side-effect parameter, closure counter via mutable list, re.subn for replacement counting]
key-files:
  created: []
  modified:
    - src/scholardoc_ocr/postprocess.py
    - src/scholardoc_ocr/pipeline.py
key-decisions:
  - "Postprocess counts are approximate per-page (global counts applied to each page's diagnostics) -- Phase 19 will refine to per-page counting"
  - "Diagnostics construction wrapped in try/except to never break the pipeline"
  - "re.subn used only when counts dict provided (no overhead when counting disabled)"
patterns-established:
  - "Side-effect counter dict: optional dict parameter mutated in place, None means no counting"
  - "Error-resilient diagnostics: try/except around all diagnostic construction, fallback to None"
duration: 4min
completed: 2026-02-17
---

# Phase 15 Plan 02: Pipeline Diagnostic Wiring Summary

**Postprocess counter tracking and always-captured PageDiagnostics wired through _tesseract_worker with error-resilient attachment to every PageResult**

## Performance
- **Duration:** 4 minutes
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Added optional `counts` dict parameter to all 5 postprocess functions (normalize_unicode, dehyphenate, join_paragraphs, normalize_punctuation, postprocess) with zero-overhead when unused
- Wired build_always_diagnostics into both _tesseract_worker code paths (existing-text-is-good and Tesseract-processed)
- Every PageResult now carries signal_scores, signal_details, composite_weights, signal_disagreements, has_signal_disagreement, struggle_categories, and postprocess_counts
- Added Surya phase reclassification to update struggle categories (including surya_insufficient detection) after map_results_to_files
- All 253 existing tests pass unchanged (diagnostics are purely additive)
- Verified pickle roundtrip for ProcessPoolExecutor transport

## Task Commits
1. **Task 1: Add counter tracking to postprocess functions** - `4e36fc4`
2. **Task 2: Wire always-captured diagnostics through _tesseract_worker and run_pipeline** - `7cb3d72`

## Files Created/Modified
- `src/scholardoc_ocr/postprocess.py` - All transform functions accept optional counts parameter; postprocess() passes counts through chain
- `src/scholardoc_ocr/pipeline.py` - Imports build_always_diagnostics and classify_struggle; attaches diagnostics to all PageResults in both code paths; updates struggle categories after Surya processing

## Decisions & Deviations
None - plan executed exactly as written.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Plan 03 can now:
- Add --diagnostics CLI flag for gated diagnostics (image quality metrics, engine comparison)
- Use compute_engine_diff() for Tesseract-vs-Surya comparison on pages that went through Surya
- Diagnostics data is already flowing through JSON metadata sidecars via PageResult.to_dict()

## Self-Check: PASSED
