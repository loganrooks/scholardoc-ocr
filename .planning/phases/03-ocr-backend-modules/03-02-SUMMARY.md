---
phase: "03"
plan: "02"
subsystem: ocr-backend
tags: [surya, marker, ocr, lazy-imports, model-lifecycle]
requires: ["01-exceptions"]
provides: ["surya-backend-module", "surya-unit-tests"]
affects: ["03-03", "04-pipeline"]
tech-stack:
  added: []
  patterns: ["lazy-ml-imports", "model-dict-reuse", "function-based-module"]
key-files:
  created:
    - src/scholardoc_ocr/surya.py
    - tests/test_surya.py
  modified: []
key-decisions:
  - id: "03-02-01"
    decision: "Function-based module with SuryaConfig dataclass"
    rationale: "Matches plan; keeps module simple without class overhead"
patterns-established:
  - "Lazy ML imports inside function bodies only"
  - "Separate model loading from conversion for reuse"
duration: "~3m"
completed: "2026-01-29"
---

# Phase 3 Plan 2: Surya Backend Module Summary

**One-liner:** Surya/Marker OCR backend with lazy imports, explicit model lifecycle (load once, convert many), and 12 mocked unit tests.

## Accomplishments

1. Created `surya.py` with `SuryaConfig`, `load_models()`, `convert_pdf()`, and `is_available()`
2. All torch/marker imports are lazy (inside function bodies only) -- verified by test
3. Model dict loaded once via `load_models()`, passed into `convert_pdf()` calls
4. `is_available()` checks marker via `importlib.import_module` without importing torch
5. 12 unit tests passing with fully mocked marker/torch dependencies

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create surya.py backend module | e819b77 | src/scholardoc_ocr/surya.py |
| 2 | Create unit tests for surya backend | 2425106 | tests/test_surya.py |

## Files

**Created:**
- `src/scholardoc_ocr/surya.py` (138 lines) -- Surya/Marker OCR backend
- `tests/test_surya.py` (254 lines) -- 12 unit tests

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 03-02-01 | Function-based module with dataclass config | Simple, no class overhead, matches plan |

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- surya.py ready for integration into pipeline orchestration (Phase 3 Plan 3 or Phase 4)
- Model dict reuse pattern established for pipeline to call load_models() once
