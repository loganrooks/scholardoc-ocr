---
phase: 15-diagnostic-infrastructure
plan: 03
subsystem: diagnostics
tags: [image-quality, engine-diff, cli-flag, json-sidecar, diagnostics-gating]
requires:
  - phase: 15-02
    provides: Always-captured PageDiagnostics wired through pipeline, postprocess counters
provides:
  - analyze_image_quality function for DPI, contrast, blur_score, skew_angle metrics
  - Tesseract text preservation before Surya overwrite with word-level engine diff
  - --diagnostics CLI flag propagated through PipelineConfig to pipeline behavior
  - JSON diagnostic sidecar ({stem}.diagnostics.json) written alongside output PDF
affects: [pipeline, diagnostics, cli]
tech-stack:
  added: []
  patterns: [lazy cv2/numpy import inside function body, try/except error resilience for all diagnostic operations, Canny+HoughLinesP skew detection]
key-files:
  created: []
  modified:
    - src/scholardoc_ocr/diagnostics.py
    - src/scholardoc_ocr/pipeline.py
    - src/scholardoc_ocr/cli.py
key-decisions:
  - "Lazy import cv2/numpy inside analyze_image_quality function body to avoid import weight for non-diagnostics runs"
  - "Render pages at 150 DPI (not 300) for 4x memory savings during image quality analysis"
  - "Skew detection uses Canny + HoughLinesP with near-horizontal line filter (|angle| < 45 degrees)"
  - "All diagnostic operations (image analysis, text preservation, diff, sidecar) wrapped in try/except -- never breaks pipeline"
patterns-established:
  - "Diagnostics-gated pipeline features: config.diagnostics flag gates expensive operations in both _tesseract_worker and run_pipeline"
  - "DIAG-04 timing: Tesseract text captured BEFORE map_results_to_files mutates page_result.text, diff computed AFTER"
duration: 4min
completed: 2026-02-17
---

# Phase 15 Plan 03: Diagnostics-Gated Features and JSON Sidecar Summary

**Image quality analysis (DPI, contrast, blur, skew), Tesseract text preservation with word-level engine diff, --diagnostics CLI flag, and JSON diagnostic sidecar output -- all gated behind --diagnostics to preserve default pipeline behavior**

## Performance
- **Duration:** 4 minutes
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- Added analyze_image_quality() function computing DPI (from embedded images), contrast, blur_score (Laplacian variance), and skew_angle (Canny + HoughLinesP) for each page
- Added _detect_skew() helper that filters Hough lines to near-horizontal (|angle| < 45 degrees) and returns median angle
- Wired DIAG-01 (image quality) into both _tesseract_worker code paths (existing-text-is-good and Tesseract-processed)
- Implemented DIAG-04 Tesseract text preservation BEFORE map_results_to_files mutates page text, then computed word-level engine diff AFTER Surya text is in place
- Implemented DIAG-08 JSON diagnostic sidecar: writes {stem}.diagnostics.json alongside output PDF with version, config, and full per-page diagnostic breakdown
- Added --diagnostics CLI flag that propagates through PipelineConfig to all gated features
- All 253 existing tests pass unchanged (diagnostics features are purely additive, gated behind flag)

## Task Commits
1. **Task 1: Add image quality analysis to diagnostics.py and --diagnostics flag to CLI + PipelineConfig** - `aaea282`
2. **Task 2: Wire diagnostics-gated features through pipeline and write JSON sidecar** - `0beff52`

## Files Created/Modified
- `src/scholardoc_ocr/diagnostics.py` - Added analyze_image_quality() and _detect_skew() functions for DIAG-01 image quality metrics
- `src/scholardoc_ocr/pipeline.py` - Added diagnostics field to PipelineConfig; wired DIAG-01 (image quality in _tesseract_worker), DIAG-04 (Tesseract text preservation + engine diff in Surya batch loop), DIAG-08 (JSON sidecar output after metadata)
- `src/scholardoc_ocr/cli.py` - Added --diagnostics argument and passed to PipelineConfig

## Decisions & Deviations
None - plan executed exactly as written.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Phase 15 (Diagnostic Infrastructure) is now complete with all 8 DIAG requirements satisfied:
- DIAG-01: Image quality metrics (DPI, contrast, blur, skew) -- Plan 03
- DIAG-02: Signal breakdown (garbled, dictionary, confidence scores + weights) -- Plan 01/02
- DIAG-03: Signal disagreement detection with threshold-based flagging -- Plan 01/02
- DIAG-04: Tesseract text preservation + word-level engine diff -- Plan 03
- DIAG-05: Postprocess change counts (dehyphenations, joins, etc.) -- Plan 02
- DIAG-06: Struggle category labels (8 independent detection rules) -- Plan 01/02
- DIAG-07: PageResult.diagnostics optional field -- Plan 01
- DIAG-08: JSON diagnostic sidecar output -- Plan 03

Downstream phases can now:
- Phase 16: Build evaluation framework leveraging diagnostic data
- Phase 17: Use struggle categories and signal data for smart page selection
- Phase 19: Calibrate struggle category thresholds using ground truth data

## Self-Check: PASSED
