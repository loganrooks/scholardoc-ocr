# Phase 1 Plan 1: Foundation Types, Callbacks, and Exceptions Summary

**One-liner:** Leaf modules defining result dataclasses with JSON serialization, Protocol-based progress callbacks, and contextual exception hierarchy.

## What Was Done

### Task 1: types.py -- Result dataclasses and enums
- Created `OCREngine`, `ProcessingPhase`, `PageStatus` as StrEnum
- Created `PageResult`, `FileResult`, `BatchResult` dataclasses with drill-in model
- All types JSON-serializable via `to_dict()` and `to_json()`
- Commit: `e100a8e`

### Task 2: callbacks.py -- Progress callback protocol
- Created `ProgressEvent`, `PhaseEvent`, `ModelEvent` event dataclasses
- Defined `PipelineCallback` as runtime-checkable Protocol
- Implemented `LoggingCallback` (uses logging module) and `NullCallback` (no-op)
- Commit: `22fe0e4`

### Task 3: exceptions.py -- Exception hierarchy
- Created `ScholarDocError` base with message/details
- `OCRError` (+ `TesseractError`, `SuryaError`), `PDFError`, `ConfigError`, `DependencyError`
- Each exception carries contextual attributes (filename, pdf_path, package, etc.)
- Commit: `7182903`

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

None -- all decisions were pre-made in the plan.

## Key Files

| File | Purpose |
|------|---------|
| `src/scholardoc_ocr/types.py` | BatchResult > FileResult > PageResult, OCREngine/ProcessingPhase/PageStatus enums |
| `src/scholardoc_ocr/callbacks.py` | PipelineCallback Protocol, LoggingCallback, NullCallback, event dataclasses |
| `src/scholardoc_ocr/exceptions.py` | ScholarDocError hierarchy with contextual attributes |

## Verification

- All three modules import without error
- Zero internal imports (leaf modules)
- `ruff check` passes on all files
- `BatchResult.to_json()` produces valid JSON
- `LoggingCallback` satisfies `isinstance(cb, PipelineCallback)` check

## Next Phase Readiness

All three leaf modules are ready for use by subsequent plans (01-02 config module, 01-03 tests).
