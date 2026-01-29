---
phase: 02-quality-analysis-enhancement
plan: "03"
subsystem: quality-analysis
tags: [composite-scoring, multi-signal, quality-analysis, german-support]
requires: ["02-01", "02-02"]
provides: ["CompositeQualityAnalyzer", "QualityResult with signal breakdown"]
affects: ["03", "04"]
tech-stack:
  added: []
  patterns: ["composite signal scoring", "weighted combination with reweighting", "signal floors"]
key-files:
  created: ["tests/test_quality.py"]
  modified: ["src/scholardoc_ocr/quality.py"]
key-decisions:
  - "Weights: garbled 0.4, dictionary 0.3, confidence 0.3 (reweight to 0.55/0.45 without confidence)"
  - "Signal floors for per-signal minimum quality gates"
  - "Confidence short-circuits: >0.95 boosts to 0.9 min, <0.2 caps at 0.3 max"
duration: "~3m"
completed: "2026-01-29"
---

# Phase 2 Plan 3: Composite Quality Scorer Summary

Refactored QualityAnalyzer into composite multi-signal scorer combining garbled regex, dictionary, and confidence signals with weighted scoring and per-signal breakdown.

## Accomplishments

1. **Refactored quality.py** - Original QualityAnalyzer renamed to `_GarbledSignal` (internal), new `QualityAnalyzer` is a composite scorer integrating all three signals
2. **Extended QualityResult** - Added `signal_scores`, `signal_details`, `confidence_mean`, `snippets` fields while preserving backward compatibility
3. **Weighted composite scoring** - Garbled (0.4), dictionary (0.3), confidence (0.3); gracefully reweights to 0.55/0.45 when confidence data missing
4. **Signal floors** - Per-signal minimum thresholds that flag pages even when composite score is acceptable
5. **Confidence short-circuits** - Very high (>0.95) or very low (<0.2) confidence overrides composite
6. **37 unit tests** - Covering composite basics, signal breakdown, confidence integration, dictionary, German support, floors, gray zone, backward compatibility, edge cases

## Task Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | ee81b9d | Refactor QualityAnalyzer into composite multi-signal scorer |
| 2 | 8e7aec1 | Add comprehensive quality analysis unit tests |

## Files

**Modified:** `src/scholardoc_ocr/quality.py` (303 lines)
**Created:** `tests/test_quality.py` (286 lines)

## Decisions Made

- Weighted combination: garbled 0.4, dictionary 0.3, confidence 0.3
- Missing confidence reweights to garbled 0.55, dictionary 0.45
- Signal floors default: confidence 0.3, garbled 0.5, dictionary 0.4
- Gray zone defined as threshold +/- 0.05

## Deviations from Plan

None - plan executed exactly as written.

## Issues

None.

## Next Phase Readiness

Phase 2 complete. All three quality signals (garbled, dictionary, confidence) are integrated into a composite scorer. Ready for Phase 3 (pipeline orchestration) to wire per-page quality data into pipeline results.
